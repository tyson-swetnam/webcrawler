"""Re-tag historical articles with the current theme taxonomy.

Run after introducing or changing the taxonomy in crawler/config/themes.json
to bring older articles in line with new themes. Uses the Claude Code CLI
(subscription auth) with a slim themes-only prompt, batching many articles
per message to keep quota usage down.

Usage:
    # Tag only articles missing themes, max 500
    python -m crawler.scripts.backfill_themes --limit 500

    # See what would happen without spending any quota
    python -m crawler.scripts.backfill_themes --limit 500 --dry-run

    # Re-tag every article (e.g. after editing the taxonomy)
    python -m crawler.scripts.backfill_themes --all --limit 5000
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys
from datetime import datetime, timezone
from typing import Dict, List, Optional

from sqlalchemy import and_, or_

from crawler.ai.claude_cli import ClaudeCLIError, ClaudeQuotaExhausted, run_structured_prompt
from crawler.ai.themes import THEMES_PROMPT_BLOCK, validate_themes
from crawler.config.settings import settings
from crawler.db.models import Article
from crawler.db.session import get_db_manager, init_db

logger = logging.getLogger(__name__)

_THEMES_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["results"],
    "properties": {
        "results": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["article_id", "themes"],
                "properties": {
                    "article_id": {"type": "integer"},
                    "themes": {"type": "array", "items": {"type": "string"}, "maxItems": 5},
                },
            },
        }
    },
}

_BATCH_SIZE = 25


def _build_prompt(batch: List[Article]) -> str:
    blocks = []
    for art in batch:
        excerpt = (art.content or "")[:1200]
        blocks.append(
            f"ARTICLE_ID: {art.article_id}\n"
            f"TITLE: {art.title or 'Untitled'}\n"
            f"EXCERPT: {excerpt}"
        )
    articles_block = "\n\n---\n\n".join(blocks)
    return f"""You are tagging AI-research articles with theme ids from a fixed taxonomy. For EACH article below pick the 1-5 BEST matching ids. Use `general_ai` only if nothing else fits. Do not use any tools.

Taxonomy (use these exact ids, snake_case):
{THEMES_PROMPT_BLOCK}

Articles ({len(batch)} total — return exactly one result per ARTICLE_ID):

{articles_block}"""


async def _tag_batch(batch: List[Article]) -> Dict[int, List[str]]:
    """Tag one batch of articles; returns article_id -> validated themes."""
    output = await run_structured_prompt(_build_prompt(batch), _THEMES_SCHEMA)
    raw_results = output.get("results", []) if isinstance(output, dict) else output
    expected = {a.article_id for a in batch}
    tagged: Dict[int, List[str]] = {}
    for item in raw_results or []:
        article_id = item.get("article_id")
        if article_id in expected and article_id not in tagged:
            tagged[article_id] = validate_themes(item.get("themes"))
    return tagged


def _build_query(db, retag_all: bool):
    """Articles to tag: AI-related + analyzed, plus the themes-missing filter."""
    q = db.query(Article).filter(
        and_(
            Article.is_ai_related == True,
            Article.last_analyzed.isnot(None),
        )
    )
    if not retag_all:
        # JSONB filter: themes missing OR empty array. Postgres-only.
        q = q.filter(
            or_(
                Article.article_metadata.is_(None),
                Article.article_metadata["themes"].is_(None),
                Article.article_metadata["themes"].astext == "[]",
            )
        )
    return q.order_by(Article.published_date.desc().nullslast())


async def _run(args: argparse.Namespace) -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    init_db(settings.database_url, pool_size=settings.database_pool_size, echo=False)
    db_manager = get_db_manager()

    with db_manager.session_scope() as db:
        candidates = _build_query(db, retag_all=args.all).limit(args.limit).all()
        logger.info(f"Found {len(candidates)} articles to tag (limit={args.limit}, all={args.all})")

        if not candidates:
            return 0

        if args.dry_run:
            for art in candidates[:20]:
                existing = (art.article_metadata or {}).get("themes")
                logger.info(f"  [dry-run] article_id={art.article_id} themes={existing} :: {art.title[:60] if art.title else ''}")
            batches = -(-len(candidates) // _BATCH_SIZE)
            logger.info(f"[dry-run] would tag {len(candidates)} articles in ~{batches} messages. exiting.")
            return 0

        updated = 0
        for start in range(0, len(candidates), _BATCH_SIZE):
            batch = candidates[start:start + _BATCH_SIZE]
            try:
                tagged = await _tag_batch(batch)
            except ClaudeQuotaExhausted as e:
                logger.warning(f"{e}; stopping — {updated} tagged so far, re-run later for the rest")
                break
            except ClaudeCLIError as e:
                logger.warning(f"Batch starting at article_id={batch[0].article_id} failed: {e}")
                continue

            for art in batch:
                themes = tagged.get(art.article_id)
                if themes is None:
                    continue
                if not themes:
                    # The model returned nothing valid — fall back to general_ai
                    # so the article isn't queried again on the next backfill.
                    themes = ["general_ai"]
                art.article_metadata = {
                    **(art.article_metadata or {}),
                    "themes": themes,
                    "themes_backfilled_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                }
                updated += 1
            db.flush()
            logger.info(f"Tagged {updated}/{len(candidates)}…")

        db.commit()
        logger.info(f"Backfill complete: tagged {updated}/{len(candidates)} articles")

    return 0


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--limit", type=int, default=200,
                        help="Max articles to tag in this run (default: 200)")
    parser.add_argument("--all", action="store_true",
                        help="Retag every AI-related article, not just ones missing themes")
    parser.add_argument("--dry-run", action="store_true",
                        help="Show what would be tagged without spending quota")
    args = parser.parse_args(argv)

    return asyncio.run(_run(args))


if __name__ == "__main__":
    sys.exit(main())
