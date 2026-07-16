"""
Editorial Curator - Claude as Daily News Editor for Top News selection.

Performs batch curation of high-impact articles, selecting and ranking
the top stories with editorial context. Runs through the Claude Code CLI
(subscription auth) — one message per run.
"""

import logging
from typing import Any, Dict, List

from crawler.ai.claude_cli import ClaudeCLIError, ClaudeQuotaExhausted, run_structured_prompt

logger = logging.getLogger(__name__)

IMPACT_CATEGORIES = [
    "Scientific Breakthrough",
    "Major Funding",
    "Strategic Partnership",
    "Policy Impact",
]

EDITORIAL_SCHEMA: Dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "required": ["picks"],
    "properties": {
        "picks": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["rank", "article_id", "editorial_note", "impact_category"],
                "properties": {
                    "rank": {"type": "integer", "minimum": 1},
                    "article_id": {"type": "integer"},
                    "editorial_note": {"type": "string"},
                    "impact_category": {"type": "string", "enum": IMPACT_CATEGORIES},
                },
            },
        }
    },
}


class EditorialCurator:
    """Batch editorial curation — Claude as Daily News Editor."""

    async def curate_top_news(self, candidates: List[Dict], max_picks: int = 10) -> List[Dict]:
        """
        Select and rank top news stories from today's articles.

        Args:
            candidates: List of article dicts with article_metadata containing impact_scores
            max_picks: Maximum number of top stories to select

        Returns:
            List of editorial picks with rank, article_id, editorial_note, impact_category
        """
        filtered = self._select_candidates(candidates)

        if len(filtered) < 3:
            logger.info(f"Editorial curation: only {len(filtered)} candidates (need 3+), skipping")
            return []

        try:
            prompt = self._build_prompt(filtered, max_picks)
            output = await run_structured_prompt(prompt, EDITORIAL_SCHEMA)
            picks = self._validate_picks(output, {c["article_id"] for c in filtered}, max_picks)

            logger.info(
                f"Editorial curation: selected {len(picks)} top stories "
                f"from {len(filtered)} candidates"
            )
            return picks

        except (ClaudeCLIError, ClaudeQuotaExhausted) as e:
            logger.warning(f"Editorial curation failed (non-fatal): {e}")
            return []

    def _select_candidates(self, articles: List[Dict]) -> List[Dict]:
        """Rank articles by impact scores for editorial consideration.

        All AI-related articles are included as candidates. Articles with
        impact scores are ranked higher; articles without scores get defaults
        so Claude can still judge importance from their summaries.
        """
        candidates = []

        for art in articles:
            metadata = art.get('article_metadata') or {}
            scores = metadata.get('impact_scores', {})

            scientific = float(scores.get('scientific', 3.0))
            financial = float(scores.get('financial', 3.0))
            partnership = float(scores.get('partnership', 3.0))
            composite = (scientific + financial + partnership) / 3.0

            candidates.append({
                **art,
                '_composite': composite,
                '_scores': {
                    'scientific': scientific,
                    'financial': financial,
                    'partnership': partnership,
                }
            })

        # Sort by composite score descending, take top 50
        candidates.sort(key=lambda x: x['_composite'], reverse=True)
        return candidates[:50]

    def _build_prompt(self, candidates: List[Dict], max_picks: int) -> str:
        """Build the editorial curation prompt."""
        articles_text = []
        for c in candidates:
            scores = c['_scores']
            summary = (c.get('consensus_summary') or '')[:200]
            articles_text.append(
                f"ARTICLE_ID: {c['article_id']}\n"
                f"TITLE: {c.get('title', 'Untitled')}\n"
                f"UNIVERSITY: {c.get('university_name', 'Unknown')}\n"
                f"SUMMARY: {summary}\n"
                f"SCORES: Scientific={scores['scientific']}, Financial={scores['financial']}, Partnership={scores['partnership']}"
            )

        articles_block = "\n\n".join(articles_text)

        return f"""You are the Daily News Editor for an AI university news aggregator. Select the {max_picks} most important stories from this week's articles and explain why each matters. Do not use any tools; judge from the provided text only.

Select stories that represent genuine significance: major scientific breakthroughs, notable funding announcements, important partnerships between academia/government/industry, policy changes affecting AI research, or novel AI applications with real-world impact.

Here are this week's candidate articles:

{articles_block}

Return your picks via the structured output schema: for each pick give its rank (1 = most important), the ARTICLE_ID echoed exactly from the input, a 1-2 sentence editorial_note explaining why the story matters, and an impact_category. Only include stories that are truly significant — if fewer than {max_picks} qualify, include fewer."""

    def _validate_picks(
        self, output: Any, valid_ids: set, max_picks: int
    ) -> List[Dict]:
        """Validate structured picks: known ids, dense ranks, capped count."""
        raw_picks = output.get("picks", []) if isinstance(output, dict) else output
        picks = []
        seen_ids = set()

        for item in sorted(raw_picks or [], key=lambda p: p.get("rank", 999)):
            article_id = item.get("article_id")
            if article_id not in valid_ids or article_id in seen_ids:
                continue
            seen_ids.add(article_id)
            picks.append({
                "rank": len(picks) + 1,
                "article_id": article_id,
                "editorial_note": (item.get("editorial_note") or "").strip(),
                "impact_category": item.get("impact_category")
                if item.get("impact_category") in IMPACT_CATEGORIES
                else "Scientific Breakthrough",
            })
            if len(picks) >= max_picks:
                break

        return picks
