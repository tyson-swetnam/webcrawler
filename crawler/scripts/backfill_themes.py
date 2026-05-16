"""Re-tag historical articles with the current theme taxonomy.

Run after introducing or changing the taxonomy in crawler/config/themes.json
to bring older articles in line with new themes. Uses a slim Claude prompt
(themes only, not the full impact-score analysis) to keep the cost down.

Usage:
    # Tag only articles missing themes, max 500
    python -m crawler.scripts.backfill_themes --limit 500

    # See what would happen without making API calls
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
from typing import List, Optional

from anthropic import AsyncAnthropic
from sqlalchemy import and_, or_

from crawler.ai.analyzer import THEME_IDS, _THEMES_PROMPT_BLOCK
from crawler.config.settings import settings
from crawler.db.models import Article
from crawler.db.session import get_db_manager, init_db

logger = logging.getLogger(__name__)

_THEMES_ONLY_PROMPT = """You are tagging an AI-research article with theme ids from a fixed taxonomy. Read the title and excerpt below and pick the 1-5 BEST matching ids. Use `general_ai` only if nothing else fits.

Title: {title}
Excerpt: {excerpt}

Taxonomy (use these exact ids, snake_case):
{taxonomy}

Reply with ONLY a single line of comma-separated ids. No explanation, no other formatting. Example: biomedical_ai, robotics
"""


async def _extract_themes(claude: AsyncAnthropic, title: str, content: str) -> List[str]:
    """Call Claude with the slim theme-only prompt and parse the response."""
    excerpt = (content or "")[:1500]
    prompt = _THEMES_ONLY_PROMPT.format(
        title=title or "Untitled",
        excerpt=excerpt,
        taxonomy=_THEMES_PROMPT_BLOCK,
    )
    message = await claude.messages.create(
        model=settings.claude_haiku_model,  # Haiku is plenty for tagging
        max_tokens=64,
        temperature=0.0,
        messages=[{"role": "user", "content": prompt}],
    )
    raw = message.content[0].text.strip()
    # Take just the first line in case the model adds extra text
    raw = raw.splitlines()[0] if raw else ""
    # Cheap parse: split on commas/whitespace, validate against the taxonomy
    seen: List[str] = []
    for token in raw.replace("[", "").replace("]", "").split(","):
        tid = token.strip().strip("\"'").lower()
        if tid and tid in THEME_IDS and tid not in seen:
            seen.append(tid)
    return seen[:5]


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

    claude = AsyncAnthropic(api_key=settings.anthropic_api_key)
    semaphore = asyncio.Semaphore(args.concurrency)

    async def _tag_one(article_id: int, title: str, content: str) -> Optional[List[str]]:
        async with semaphore:
            try:
                return await _extract_themes(claude, title, content)
            except Exception as e:
                logger.warning(f"article_id={article_id}: theme call failed: {e}")
                return None

    with db_manager.session_scope() as db:
        candidates = _build_query(db, retag_all=args.all).limit(args.limit).all()
        logger.info(f"Found {len(candidates)} articles to tag (limit={args.limit}, all={args.all})")

        if not candidates:
            return 0

        if args.dry_run:
            for art in candidates[:20]:
                existing = (art.article_metadata or {}).get("themes")
                logger.info(f"  [dry-run] article_id={art.article_id} themes={existing} :: {art.title[:60] if art.title else ''}")
            logger.info(f"[dry-run] would tag {len(candidates)} articles. exiting.")
            return 0

        # Run all tagging concurrently (bounded by semaphore)
        results = await asyncio.gather(
            *[_tag_one(a.article_id, a.title or "", a.content or "") for a in candidates],
            return_exceptions=False,
        )

        updated = 0
        for art, themes in zip(candidates, results):
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
            if updated % 50 == 0:
                logger.info(f"Tagged {updated}/{len(candidates)}…")
                db.flush()

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
                        help="Show what would be tagged without calling the API")
    parser.add_argument("--concurrency", type=int, default=8,
                        help="Concurrent Claude calls (default: 8)")
    args = parser.parse_args(argv)

    return asyncio.run(_run(args))


if __name__ == "__main__":
    sys.exit(main())
