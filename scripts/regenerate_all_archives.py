#!/usr/bin/env python3
"""
Regenerate all archive HTML files.
This script finds all dates with articles and regenerates their HTML files.
"""

import sys
from pathlib import Path
from datetime import datetime

# Add project to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from crawler.config.settings import settings
from crawler.db.session import init_db, get_db
from crawler.db.models import Article
from crawler.utils.html_generator import HTMLReportGenerator
from sqlalchemy import func

def main():
    """Regenerate all archive HTML files."""
    print("Initializing database connection...")
    init_db(
        settings.database_url,
        pool_size=settings.database_pool_size,
        echo=False
    )

    print("Finding dates with articles...")
    with get_db() as session:
        # Get all unique dates with AI-related articles
        stmt = (
            session.query(func.date(Article.first_scraped).label('date'))
            .filter(Article.is_ai_related == True)
            .group_by(func.date(Article.first_scraped))
            .order_by(func.date(Article.first_scraped).desc())
        )

        dates = [row.date for row in stmt.all()]
        print(f"Found {len(dates)} dates with articles")

    # Generate HTML for each date
    html_gen = HTMLReportGenerator(
        output_dir=settings.local_output_dir,
        github_pages_dir="docs"
    )

    for date_obj in dates:
        # Convert date to datetime
        dt = datetime.combine(date_obj, datetime.min.time())
        print(f"Generating report for {date_obj}...")
        html_gen.generate_daily_report(dt)

    # Also regenerate archive index and how it works
    print("Generating archive index...")
    html_gen.generate_archive_index()

    print("Generating how it works page...")
    html_gen.generate_how_it_works()

    print(f"\n✨ Regenerated {len(dates)} archive files!")
    print(f"   - Main output: {settings.local_output_dir}")
    print(f"   - GitHub Pages: docs/")

    return 0

if __name__ == "__main__":
    sys.exit(main())
