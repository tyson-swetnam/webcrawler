"""
Claude-only article analyzer backed by the user's Claude Max subscription.

Replaces the old MultiAIAnalyzer (Claude Sonnet + Claude Haiku + OpenAI,
3 paid API calls per article). This analyzer batches many articles into a
single Claude Code CLI headless invocation with a strict JSON schema, so a
run of N articles costs ceil(N / ai_articles_per_prompt) subscription
messages instead of 3N API calls.

Result dicts keep the exact shape the storage loops in crawler/__main__.py
already unpack, so the ai_analyses table and downstream HTML/parquet
exports are unchanged (openai_*/gemini_* columns simply stay NULL).
"""

import asyncio
import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

from crawler.ai.claude_cli import (
    ClaudeCLIError,
    ClaudeQuotaExhausted,
    preflight,
    run_structured_prompt,
)
from crawler.ai.themes import THEMES_PROMPT_BLOCK, validate_themes
from crawler.config.settings import settings

logger = logging.getLogger(__name__)


ANALYSIS_SCHEMA: Dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "required": ["results"],
    "properties": {
        "results": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": [
                    "article_id",
                    "is_ai_related",
                    "confidence",
                    "summary",
                    "relevance_score",
                ],
                "properties": {
                    "article_id": {"type": "integer"},
                    "is_ai_related": {"type": "boolean"},
                    "confidence": {"type": "number", "minimum": 0, "maximum": 1},
                    "summary": {"type": "string"},
                    "key_points": {
                        "type": "array",
                        "items": {"type": "string"},
                        "maxItems": 5,
                    },
                    "relevance_score": {"type": "number", "minimum": 1, "maximum": 10},
                    "themes": {
                        "type": "array",
                        "items": {"type": "string"},
                        "maxItems": 5,
                    },
                    "impact_scores": {
                        "type": "object",
                        "additionalProperties": False,
                        "properties": {
                            "scientific": {"type": "number"},
                            "financial": {"type": "number"},
                            "partnership": {"type": "number"},
                        },
                    },
                },
            },
        }
    },
}


class ClaudeCodeAnalyzer:
    """Batch article analysis via Claude Code CLI (subscription auth)."""

    def __init__(self):
        ok, message = preflight()
        if not ok:
            raise RuntimeError(f"Claude Code analyzer unavailable: {message}")
        self.messages_used = 0
        self._quota_exhausted = False
        logger.info(
            "Initialized ClaudeCodeAnalyzer "
            f"(model={settings.claude_code_model}, "
            f"articles/prompt={settings.ai_articles_per_prompt}, "
            f"message budget={settings.ai_message_budget})"
        )

    async def batch_analyze(
        self, articles: List[Dict[str, Any]], max_concurrent: int = 2
    ) -> List[Optional[Dict[str, Any]]]:
        """Analyze articles in chunked prompts.

        Returns a list aligned with the input: one result dict per article,
        or None for articles that could not be analyzed (chunk failure or
        quota exhaustion). Callers must leave last_analyzed NULL for None
        entries so the next run picks them up again.
        """
        if not articles:
            return []

        chunk_size = settings.ai_articles_per_prompt
        chunks = [articles[i:i + chunk_size] for i in range(0, len(articles), chunk_size)]
        semaphore = asyncio.Semaphore(max(1, min(max_concurrent, 2)))

        async def analyze_chunk(chunk: List[Dict[str, Any]]) -> Dict[int, Dict[str, Any]]:
            async with semaphore:
                if self._quota_exhausted:
                    return {}
                if self.messages_used >= settings.ai_message_budget:
                    logger.warning(
                        f"AI message budget ({settings.ai_message_budget}) reached; "
                        f"skipping remaining chunks (resumable next run)"
                    )
                    return {}
                start = datetime.utcnow()
                self.messages_used += 1
                try:
                    output = await run_structured_prompt(
                        self._build_prompt(chunk), ANALYSIS_SCHEMA
                    )
                except ClaudeQuotaExhausted as e:
                    self._quota_exhausted = True
                    logger.warning(f"{e} — remaining articles stay unanalyzed until next run")
                    return {}
                except ClaudeCLIError as e:
                    logger.error(f"Chunk of {len(chunk)} articles failed: {e}")
                    return {}
                elapsed_ms = int((datetime.utcnow() - start).total_seconds() * 1000)
                return self._reconcile(chunk, output, elapsed_ms)

        chunk_results = await asyncio.gather(*(analyze_chunk(c) for c in chunks))

        by_id: Dict[int, Dict[str, Any]] = {}
        for result_map in chunk_results:
            by_id.update(result_map)

        results = [by_id.get(a.get("article_id")) for a in articles]
        analyzed = sum(1 for r in results if r)
        logger.info(
            f"ClaudeCodeAnalyzer: {analyzed}/{len(articles)} articles analyzed "
            f"in {self.messages_used} subscription message(s)"
        )
        return results

    def _build_prompt(self, chunk: List[Dict[str, Any]]) -> str:
        blocks = []
        for article in chunk:
            content = (article.get("content") or "")[: settings.ai_max_content_chars]
            blocks.append(
                f"ARTICLE_ID: {article.get('article_id')}\n"
                f"TITLE: {article.get('title', 'Untitled')}\n"
                f"URL: {article.get('url', '')}\n"
                f"CONTENT: {content}"
            )
        articles_block = "\n\n---\n\n".join(blocks)

        return f"""You are an analyst for a university AI-news aggregator. Analyze EVERY article below and return one result per article via the structured output schema. Do not use any tools; answer from the provided text only.

For each article provide:
- article_id: echoed exactly from the input
- is_ai_related: whether the article is genuinely about artificial intelligence research, applications, policy, education, or infrastructure
- confidence: 0.0-1.0, your confidence in the is_ai_related judgment
- summary: a concise 2-3 sentence summary of the main findings
- key_points: 3-5 key points or innovations
- relevance_score: 1-10, how significant this is as AI news (10 = major breakthrough)
- themes: 1-5 ids from the fixed taxonomy below (best matches only; use general_ai only if nothing else fits; empty if not AI-related)
- impact_scores: each 1-10 — scientific (significance of the innovation), financial (billions=9-10, hundreds of millions=7-8, tens of millions=5-6, smaller/none=1-4), partnership (significance of academia/government/industry partnerships)

Theme taxonomy (use these exact ids):
{THEMES_PROMPT_BLOCK}

Articles ({len(chunk)} total — return exactly one result for each ARTICLE_ID):

{articles_block}"""

    def _reconcile(
        self,
        chunk: List[Dict[str, Any]],
        output: Any,
        elapsed_ms: int,
    ) -> Dict[int, Dict[str, Any]]:
        """Match model results back to input articles by article_id."""
        raw_results = output.get("results", []) if isinstance(output, dict) else output
        expected_ids = {a.get("article_id") for a in chunk}

        reconciled: Dict[int, Dict[str, Any]] = {}
        per_article_ms = max(1, elapsed_ms // max(1, len(chunk)))

        for item in raw_results or []:
            if not isinstance(item, dict):
                continue
            article_id = item.get("article_id")
            if article_id not in expected_ids or article_id in reconciled:
                continue

            themes = validate_themes(item.get("themes"))
            raw_scores = item.get("impact_scores") or {}
            impact_scores = {
                "scientific": float(raw_scores.get("scientific", 1.0)),
                "financial": float(raw_scores.get("financial", 1.0)),
                "partnership": float(raw_scores.get("partnership", 1.0)),
            }
            summary = (item.get("summary") or "").strip()
            claude_payload = {
                "summary": summary,
                "key_points": [str(p) for p in (item.get("key_points") or [])][:5],
                "relevance_score": float(item.get("relevance_score", 5)),
                "is_ai_related": bool(item.get("is_ai_related")),
                "themes": themes,
                "impact_scores": impact_scores,
                "model": settings.claude_code_model,
            }
            reconciled[article_id] = {
                "article_id": article_id,
                "claude": claude_payload,
                "openai": None,
                "haiku": None,
                "consensus": {
                    "summary": summary,
                    "is_ai_related": bool(item.get("is_ai_related")),
                    "confidence": max(0.0, min(1.0, float(item.get("confidence", 0.5)))),
                    "relevance_score": float(item.get("relevance_score", 5)),
                    "providers_count": 1,
                },
                "processing_time_ms": per_article_ms,
            }

        missing = expected_ids - set(reconciled)
        if missing:
            logger.warning(
                f"Model response missing {len(missing)} article(s) "
                f"({sorted(missing)[:5]}...) — they stay unanalyzed for next run"
            )
        return reconciled
