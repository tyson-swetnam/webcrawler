#!/usr/bin/env python
"""
Simplified crawler runner that avoids subprocess hanging issues.
Runs Scrapy spider directly, then generates HTML reports.
"""

import sys
from datetime import datetime, timezone
from scrapy.crawler import CrawlerProcess
from crawler.spiders.university_spider import UniversityNewsSpider
from crawler.config.settings import settings
from crawler.db.session import init_db
from crawler.utils.html_generator import HTMLReportGenerator

def main():
    print("=" * 70)
    print("🚀 AI News Crawler - Simplified Runner")
    print("=" * 70)
    print(f"Started at: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}")
    print()

    # Initialize database
    print("📊 Initializing database...")
    init_db(
        settings.database_url,
        pool_size=settings.database_pool_size,
        echo=settings.database_echo
    )
    print("✅ Database initialized")
    print()

    # Phase 1: Crawl with Scrapy
    print("📡 Phase 1: Crawling university news sites...")
    print(f"   Crawling 52 universities")
    print()

    try:
        process = CrawlerProcess({
            'LOG_LEVEL': 'INFO',
            'USER_AGENT': settings.user_agent,
            'ROBOTSTXT_OBEY': True,
            'CONCURRENT_REQUESTS': settings.max_concurrent_requests,
            'DOWNLOAD_DELAY': settings.crawl_delay,
            'CONCURRENT_REQUESTS_PER_DOMAIN': 1,
            'AUTOTHROTTLE_ENABLED': True,
            'AUTOTHROTTLE_START_DELAY': 1.0,
            'AUTOTHROTTLE_MAX_DELAY': 10.0,
            'AUTOTHROTTLE_TARGET_CONCURRENCY': 2.0,
            'DOWNLOAD_TIMEOUT': 30,
            'RETRY_TIMES': 3,
            'RETRY_HTTP_CODES': [500, 502, 503, 504, 408, 429],
            'COOKIES_ENABLED': False,
            # Depth limiting - prevent crawling too deep (max 10 pages of pagination)
            'DEPTH_LIMIT': 10,
            'DEPTH_PRIORITY': 1,
        })

        process.crawl(UniversityNewsSpider)
        process.start()  # This blocks until crawling is done

        print()
        print("✅ Phase 1: Crawling completed")
        print()

    except Exception as e:
        print(f"❌ Crawling failed: {e}")
        return 1

    # Phase 2: Generate HTML reports
    print("📄 Phase 2: Generating HTML reports...")
    try:
        html_gen = HTMLReportGenerator(output_dir=settings.local_output_dir)

        # Generate today's report
        today_file = html_gen.generate_daily_report()
        print(f"   ✅ Daily report: {today_file}")

        # Generate archive index
        archive_file = html_gen.generate_archive_index()
        print(f"   ✅ Archive index: {archive_file}")

        print()
        print("=" * 70)
        print("🎉 Crawler completed successfully!")
        print(f"Finished at: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}")
        print("=" * 70)
        print()
        print(f"📁 View your website: file://{today_file}")
        print()

        return 0

    except Exception as e:
        print(f"❌ HTML generation failed: {e}")
        import traceback
        traceback.print_exc()
        return 1

if __name__ == "__main__":
    sys.exit(main())
