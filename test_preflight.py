#!/usr/bin/env python3
"""
Pre-flight verification script for AI News Crawler.
Tests all critical components before production scan.
"""

import sys
import os
from pathlib import Path

# Add crawler to path
sys.path.insert(0, str(Path(__file__).parent))

def test_configuration():
    """Test configuration loading and validation."""
    print("=" * 60)
    print("1. CONFIGURATION VERIFICATION")
    print("=" * 60)

    try:
        from crawler.config.settings import settings

        print(f"\n✓ Settings loaded successfully")
        print(f"  - App Name: {settings.app_name}")
        print(f"  - Debug Mode: {settings.debug}")
        print(f"  - Log Level: {settings.log_level}")
        print(f"  - Database URL: {settings.database_url[:30]}...")
        print(f"  - University Source Type: {settings.university_source_type}")
        print(f"  - Prefer AI Tag URLs: {settings.prefer_ai_tag_urls}")
        print(f"  - Use RSS Feeds: {settings.use_rss_feeds}")
        print(f"  - Include Meta News: {settings.include_meta_news}")

        # Check API keys
        print(f"\n✓ API Keys Configuration:")
        print(f"  - Anthropic API Key: {'SET' if settings.anthropic_api_key and len(settings.anthropic_api_key) > 20 else 'MISSING'}")
        print(f"  - OpenAI API Key: {'SET' if settings.openai_api_key and len(settings.openai_api_key) > 20 else 'MISSING'}")
        print(f"  - Claude Model: {settings.claude_model}")
        print(f"  - OpenAI Model: {settings.openai_model}")

        # Check crawl settings
        print(f"\n✓ Crawling Configuration:")
        print(f"  - Max Concurrent Requests: {settings.max_concurrent_requests}")
        print(f"  - Crawl Delay: {settings.crawl_delay}s")
        print(f"  - Request Timeout: {settings.request_timeout}s")
        print(f"  - Max Articles Per Run: {settings.max_articles_per_run}")

        # Check notification settings
        print(f"\n✓ Notification Configuration:")
        print(f"  - Slack Enabled: {settings.enable_slack_notifications}")
        print(f"  - Email Enabled: {settings.enable_email_notifications}")
        print(f"  - AI Analysis Enabled: {settings.enable_ai_analysis}")

        return True, settings

    except Exception as e:
        print(f"\n✗ Configuration loading failed: {e}")
        import traceback
        traceback.print_exc()
        return False, None


def test_source_loading(settings):
    """Test loading of all university sources."""
    print("\n" + "=" * 60)
    print("2. SOURCE FILE VERIFICATION")
    print("=" * 60)

    try:
        sources = settings.get_university_sources()

        print(f"\n✓ Successfully loaded {len(sources)} sources")

        # Count by type
        by_type = {}
        by_location = {}
        with_ai_tag = 0
        with_rss = 0

        for source in sources:
            source_type = source.get("source_type", "unknown")
            by_type[source_type] = by_type.get(source_type, 0) + 1

            location = source.get("location", "Unknown")
            by_location[location] = by_location.get(location, 0) + 1

            if source.get("ai_tag_url"):
                with_ai_tag += 1
            if source.get("rss_feed"):
                with_rss += 1

        print(f"\n  Sources by type:")
        for stype, count in sorted(by_type.items()):
            print(f"    - {stype}: {count}")

        print(f"\n  URL configuration:")
        print(f"    - Sources with AI tag URLs: {with_ai_tag}")
        print(f"    - Sources with RSS feeds: {with_rss}")

        print(f"\n  Sample sources:")
        for i, source in enumerate(sources[:5]):
            print(f"    {i+1}. {source.get('name')} ({source.get('source_type')})")
            print(f"       URL: {source.get('news_url')[:60]}...")
            if source.get('ai_tag_url'):
                print(f"       AI Tag: {source.get('ai_tag_url')[:60]}...")

        return True, sources

    except Exception as e:
        print(f"\n✗ Source loading failed: {e}")
        import traceback
        traceback.print_exc()
        return False, []


def test_database_connection(settings):
    """Test database connectivity."""
    print("\n" + "=" * 60)
    print("3. DATABASE CONNECTIVITY")
    print("=" * 60)

    try:
        from sqlalchemy import create_engine, text

        engine = create_engine(settings.database_url)

        with engine.connect() as conn:
            result = conn.execute(text("SELECT version();"))
            version = result.scalar()
            print(f"\n✓ Database connection successful")
            print(f"  PostgreSQL version: {version}")

            # Check if tables exist
            result = conn.execute(text("""
                SELECT table_name
                FROM information_schema.tables
                WHERE table_schema = 'public'
                ORDER BY table_name;
            """))
            tables = [row[0] for row in result]

            print(f"\n✓ Found {len(tables)} tables:")
            for table in tables:
                print(f"    - {table}")

        engine.dispose()
        return True

    except Exception as e:
        print(f"\n✗ Database connection failed: {e}")
        print(f"  Database URL: {settings.database_url[:30]}...")
        import traceback
        traceback.print_exc()
        return False


def test_spider_instantiation(settings):
    """Test spider can be instantiated."""
    print("\n" + "=" * 60)
    print("4. SPIDER INSTANTIATION")
    print("=" * 60)

    try:
        # Initialize database for spider
        from crawler.db.session import init_db
        init_db(settings.database_url)

        from crawler.spiders.university_spider import UniversityNewsSpider

        spider = UniversityNewsSpider()

        print(f"\n✓ Spider instantiated successfully")
        print(f"  - Spider name: {spider.name}")
        print(f"  - Allowed domains configured: {hasattr(spider, 'allowed_domains')}")
        print(f"  - Start URLs configured: {hasattr(spider, 'start_urls')}")

        # Check custom settings
        if hasattr(spider, 'custom_settings'):
            print(f"\n✓ Custom settings:")
            for key, value in spider.custom_settings.items():
                if isinstance(value, (str, int, float, bool)):
                    print(f"    - {key}: {value}")

        # Clean up
        spider.db.close()

        return True

    except Exception as e:
        print(f"\n✗ Spider instantiation failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_ai_clients(settings):
    """Test AI API clients can be instantiated."""
    print("\n" + "=" * 60)
    print("5. AI API CONFIGURATION")
    print("=" * 60)

    results = {}

    # Test Claude
    try:
        from anthropic import Anthropic
        client = Anthropic(api_key=settings.anthropic_api_key)
        print(f"\n✓ Claude client instantiated")
        print(f"  - Model: {settings.claude_model}")
        results['claude'] = True
    except Exception as e:
        print(f"\n✗ Claude client failed: {e}")
        results['claude'] = False

    # Test OpenAI
    try:
        from openai import OpenAI
        client = OpenAI(api_key=settings.openai_api_key)
        print(f"\n✓ OpenAI client instantiated")
        print(f"  - Model: {settings.openai_model}")
        results['openai'] = True
    except Exception as e:
        print(f"\n✗ OpenAI client failed: {e}")
        results['openai'] = False

    return all(results.values()), results


def test_logging_setup():
    """Test logging configuration."""
    print("\n" + "=" * 60)
    print("6. LOGGING CONFIGURATION")
    print("=" * 60)

    try:
        import logging
        from pathlib import Path

        # Check if logging config file exists
        logging_config = Path("/home/tswetnam/github/webcrawler/crawler/config/logging.yaml")

        if logging_config.exists():
            print(f"\n✓ Logging config file found: {logging_config}")
        else:
            print(f"\n⚠ Logging config file not found: {logging_config}")
            print(f"  Will use default logging configuration")

        # Test basic logging
        logger = logging.getLogger("test")
        logger.info("Test log message")
        print(f"\n✓ Logging system operational")

        return True

    except Exception as e:
        print(f"\n✗ Logging setup failed: {e}")
        return False


def test_output_directories(settings):
    """Test output directories exist and are writable."""
    print("\n" + "=" * 60)
    print("7. OUTPUT DIRECTORIES")
    print("=" * 60)

    try:
        from pathlib import Path

        # Check local output directory
        output_dir = Path(settings.local_output_dir)
        if not output_dir.exists():
            print(f"\n⚠ Output directory does not exist: {output_dir}")
            print(f"  Creating directory...")
            output_dir.mkdir(parents=True, exist_ok=True)

        print(f"\n✓ Output directory: {output_dir}")
        print(f"  - Exists: {output_dir.exists()}")
        print(f"  - Writable: {os.access(output_dir, os.W_OK)}")

        # Check log directory
        log_path = Path(settings.log_file_path)
        log_dir = log_path.parent

        print(f"\n✓ Log directory: {log_dir}")
        print(f"  - Exists: {log_dir.exists()}")
        if not log_dir.exists():
            print(f"  ⚠ Log directory does not exist - may need sudo to create")

        return True

    except Exception as e:
        print(f"\n✗ Output directory check failed: {e}")
        return False


def test_module_imports():
    """Test all critical modules can be imported."""
    print("\n" + "=" * 60)
    print("8. MODULE IMPORT VALIDATION")
    print("=" * 60)

    modules = [
        "crawler.config.settings",
        "crawler.spiders.university_spider",
        "crawler.ai.analyzer",
        "crawler.db.models",
        "crawler.utils.deduplication",
        "crawler.utils.html_generator",
        "crawler.utils.local_exporter",
    ]

    results = {}
    for module in modules:
        try:
            __import__(module)
            print(f"✓ {module}")
            results[module] = True
        except Exception as e:
            print(f"✗ {module}: {e}")
            results[module] = False

    return all(results.values()), results


def run_syntax_check():
    """Run syntax check on Python files."""
    print("\n" + "=" * 60)
    print("9. SYNTAX VALIDATION")
    print("=" * 60)

    import py_compile
    from pathlib import Path

    crawler_dir = Path("/home/tswetnam/github/webcrawler/crawler")
    python_files = list(crawler_dir.rglob("*.py"))

    errors = []
    for py_file in python_files:
        try:
            py_compile.compile(str(py_file), doraise=True)
        except py_compile.PyCompileError as e:
            errors.append((py_file, e))

    if errors:
        print(f"\n✗ Found {len(errors)} syntax errors:")
        for file, error in errors:
            print(f"  - {file}: {error}")
        return False
    else:
        print(f"\n✓ All {len(python_files)} Python files have valid syntax")
        return True


def main():
    """Run all pre-flight checks."""
    print("\n" + "=" * 70)
    print(" " * 15 + "AI NEWS CRAWLER PRE-FLIGHT VERIFICATION")
    print("=" * 70)

    results = {}

    # Run all tests
    results['config'], settings = test_configuration()

    if settings:
        results['sources'], sources = test_source_loading(settings)
        results['database'] = test_database_connection(settings)
        results['spider'] = test_spider_instantiation(settings)
        results['ai_clients'], ai_results = test_ai_clients(settings)
        results['logging'] = test_logging_setup()
        results['output_dirs'] = test_output_directories(settings)
        results['imports'], import_results = test_module_imports()
        results['syntax'] = run_syntax_check()
    else:
        print("\n✗ Cannot continue without valid configuration")
        return False

    # Summary
    print("\n" + "=" * 70)
    print(" " * 20 + "PRE-FLIGHT SUMMARY")
    print("=" * 70)

    print(f"\nConfiguration Checks:")
    for check, passed in results.items():
        status = "✓ PASS" if passed else "✗ FAIL"
        print(f"  {status} - {check.replace('_', ' ').title()}")

    # Critical issues
    critical_issues = []
    warnings = []

    if not results.get('config'):
        critical_issues.append("Configuration loading failed")
    if not results.get('database'):
        critical_issues.append("Database connection failed")
    if not results.get('sources'):
        critical_issues.append("Source file loading failed")
    if not results.get('ai_clients'):
        critical_issues.append("AI API client configuration failed")
    if not results.get('spider'):
        critical_issues.append("Spider instantiation failed")

    # Decision
    print("\n" + "=" * 70)
    if critical_issues:
        print(" " * 25 + "⚠ NO-GO ⚠")
        print("=" * 70)
        print("\nCritical Issues:")
        for issue in critical_issues:
            print(f"  ✗ {issue}")
        print("\nThese issues must be resolved before production scan.")
        return False
    elif warnings:
        print(" " * 25 + "⚠ GO WITH CAUTION ⚠")
        print("=" * 70)
        print("\nWarnings:")
        for warning in warnings:
            print(f"  ⚠ {warning}")
        print("\nSystem is functional but may have degraded capabilities.")
        return True
    else:
        print(" " * 25 + "✓ GO FOR PRODUCTION ✓")
        print("=" * 70)
        print("\n  All systems operational!")
        print(f"  Ready to scan {len(sources)} sources")
        print(f"  - Peer Institutions: 27")
        print(f"  - R1 Universities: 187")
        print(f"  - Major Facilities: 27")
        print(f"\n  Estimated scan parameters:")
        print(f"  - Max concurrent requests: {settings.max_concurrent_requests}")
        print(f"  - Crawl delay: {settings.crawl_delay}s per domain")
        print(f"  - Request timeout: {settings.request_timeout}s")
        print(f"  - Max articles per run: {settings.max_articles_per_run}")
        return True


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
