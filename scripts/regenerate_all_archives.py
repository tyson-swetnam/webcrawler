#!/usr/bin/env python3
"""
Rebuild the archive: one page per publication date, plus the search index.

Finds every date (>= --since) on which an analyzed, AI-related article was
published and regenerates its archive page. Pages are keyed by publication
date — the axis the archive index displays — not by crawl date, so articles
backfilled long after publication land on the correct pages.

After the daily pages, the Pagefind search stubs are regenerated and (when
the `pagefind` CLI is available) reindexed, and the archive index is rebuilt
with the current popular-topic counts.

Used by .github/workflows/backfill-archive.yml after each analysis chunk;
also runnable locally against a hydrated database:

    python scripts/regenerate_all_archives.py --since 2026-03-10
"""

import argparse
import shutil
import subprocess
import sys
import tempfile
from datetime import date, datetime
from pathlib import Path

# Add project to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from crawler.config.settings import settings
from crawler.db.session import init_db, get_db
from crawler.db.models import Article
from crawler.utils.html_generator import HTMLReportGenerator


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--since",
        default="2025-10-01",
        help="Earliest publication date to rebuild (YYYY-MM-DD). Guards "
             "against junk publication dates creating absurd archive pages.",
    )
    args = parser.parse_args()
    since = datetime.strptime(args.since, "%Y-%m-%d").date()
    today = date.today()

    print("Initializing database connection...")
    init_db(
        settings.database_url,
        pool_size=settings.database_pool_size,
        echo=False
    )

    print(f"Finding publication dates with analyzed AI articles (since {since})...")
    with get_db() as session:
        stmt = (
            session.query(Article.published_date)
            .filter(
                Article.is_ai_related == True,
                Article.last_analyzed != None,
                Article.published_date != None,
                Article.published_date >= since,
                Article.published_date <= today,
            )
            .distinct()
            .order_by(Article.published_date.desc())
        )
        dates = [row[0] for row in stmt.all()]
    print(f"Found {len(dates)} dates with articles")

    html_gen = HTMLReportGenerator(
        output_dir=settings.local_output_dir,
        github_pages_dir="docs"
    )

    for date_obj in dates:
        dt = datetime.combine(date_obj, datetime.min.time())
        print(f"Generating report for {date_obj}...")
        html_gen.generate_daily_report(dt)

    # Rebuild the Pagefind search index over the regenerated pages so
    # backfilled articles become searchable. Non-fatal: without the CLI the
    # existing index simply stays as-is.
    popular_topics = []
    staging = tempfile.mkdtemp(prefix="pagefind_stubs_")
    try:
        stub_count, popular_topics = html_gen.generate_search_stubs(staging)
        print(f"Generated {stub_count} search stubs")
        result = subprocess.run(
            ["pagefind", "--site", staging, "--output-path", str(Path("docs") / "pagefind")],
            capture_output=True, text=True, timeout=300,
        )
        if result.returncode == 0:
            print("Pagefind index rebuilt")
        else:
            print(f"Pagefind failed (non-fatal): {result.stderr.strip()[:500]}")
    except FileNotFoundError:
        print("pagefind CLI not found; skipping search index rebuild")
    except Exception as e:
        print(f"Search index rebuild failed (non-fatal): {e}")
    finally:
        shutil.rmtree(staging, ignore_errors=True)

    print("Generating archive index...")
    html_gen.generate_archive_index(popular_topics=popular_topics)

    print("Generating how it works page...")
    html_gen.generate_how_it_works()

    print(f"\n✨ Regenerated {len(dates)} archive files!")
    print(f"   - Main output: {settings.local_output_dir}")
    print(f"   - GitHub Pages: docs/")

    return 0

if __name__ == "__main__":
    sys.exit(main())
