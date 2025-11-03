#!/usr/bin/env python3
"""
Quick test script for HTML report generator.

This script generates sample HTML reports to verify the generator is working.
"""

import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from crawler.utils.html_generator import HTMLReportGenerator
from crawler.db.session import init_db
from crawler.config.settings import settings


def test_html_generator():
    """Test HTML report generator"""
    print("=" * 60)
    print("Testing HTML Report Generator")
    print("=" * 60)
    print()

    try:
        # Initialize database connection
        print("🔌 Initializing database connection...")
        init_db(
            settings.database_url,
            pool_size=settings.database_pool_size,
            echo=False
        )
        print("✅ Database initialized")
        print()

        # Create generator
        print("📝 Creating HTML report generator...")
        gen = HTMLReportGenerator(output_dir="html_output")
        print("✅ Generator created successfully")
        print()

        # Generate today's report
        print("📄 Generating today's report...")
        today_file = gen.generate_daily_report()
        print(f"✅ Today's report: {today_file}")
        print()

        # Generate archive index
        print("📑 Generating archive index...")
        archive_file = gen.generate_archive_index()
        print(f"✅ Archive index: {archive_file}")
        print()

        # Verify files exist
        print("🔍 Verifying files...")
        today_path = Path(today_file)
        archive_path = Path(archive_file)

        if today_path.exists():
            print(f"✅ Today's report exists ({today_path.stat().st_size} bytes)")
        else:
            print(f"❌ Today's report not found: {today_file}")

        if archive_path.exists():
            print(f"✅ Archive index exists ({archive_path.stat().st_size} bytes)")
        else:
            print(f"❌ Archive index not found: {archive_file}")

        print()
        print("=" * 60)
        print("✅ HTML report generation test completed!")
        print("=" * 60)
        print()
        print("Next steps:")
        print("  1. View the reports:")
        print("     python scripts/serve_html.py")
        print()
        print("  2. Then open in browser:")
        print("     http://localhost:8000/")
        print()

        return 0

    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(test_html_generator())
