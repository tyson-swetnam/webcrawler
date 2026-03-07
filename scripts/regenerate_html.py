#!/usr/bin/env python3
"""
Regenerate HTML reports without running the full crawler.
This is useful when you've made changes to the HTML generator
and just want to refresh the website.
"""

import sys
from pathlib import Path

# Add project to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from crawler.config.settings import settings
from crawler.db.session import init_db
from crawler.utils.html_generator import HTMLReportGenerator

def main():
    """Regenerate all HTML reports from existing database data."""
    print("Initializing database connection...")
    init_db(
        settings.database_url,
        pool_size=settings.database_pool_size,
        echo=False
    )

    print("Generating HTML reports...")
    html_gen = HTMLReportGenerator(
        output_dir=settings.local_output_dir,
        github_pages_dir="docs"
    )

    # Generate all reports
    today_file = html_gen.generate_daily_report()
    print(f"✅ Today's report: {today_file}")

    archive_file = html_gen.generate_archive_index()
    print(f"✅ Archive index: {archive_file}")

    how_it_works_file = html_gen.generate_how_it_works()
    print(f"✅ How It Works page: {how_it_works_file}")

    print("\n✨ HTML regeneration complete!")
    print(f"   - Main output: {settings.local_output_dir}")
    print(f"   - GitHub Pages: docs/")

    return 0

if __name__ == "__main__":
    sys.exit(main())
