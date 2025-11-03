#!/usr/bin/env python3
"""
Test script for the new university source configurations.

This script tests all source types to ensure they load correctly.
"""

import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from crawler.config.settings import Settings
from pydantic_settings import SettingsConfigDict


def test_source_type(source_type: str, include_meta: bool = False):
    """Test loading a specific source type."""
    print(f"\n{'='*60}")
    print(f"Testing Source Type: {source_type}")
    if include_meta:
        print("With meta news services included")
    print('='*60)

    try:
        # Create settings with specific source type
        settings = Settings(
            university_source_type=source_type,
            include_meta_news=include_meta,
            prefer_ai_tag_urls=True,
            use_rss_feeds=True,
            # Required fields (use dummy values for testing)
            database_url="postgresql://test:test@localhost/test",
            anthropic_api_key="test-key",
            openai_api_key="test-key",
            gemini_api_key="test-key",
            slack_webhook_url="https://hooks.slack.com/test",
            email_from="test@example.com",
            email_to=["test@example.com"],
            smtp_password="test-password"
        )

        # Load sources
        sources = settings.get_university_sources()

        print(f"\n✅ Successfully loaded {len(sources)} sources")

        # Show statistics
        source_types = {}
        has_rss = 0
        has_ai_tag = 0

        for source in sources:
            # Count by type
            stype = source.get('source_type', 'unknown')
            source_types[stype] = source_types.get(stype, 0) + 1

            # Count features
            if source.get('rss_feed'):
                has_rss += 1
            if source.get('ai_tag_url'):
                has_ai_tag += 1

        print(f"\n📊 Statistics:")
        print(f"   Total sources: {len(sources)}")
        for stype, count in source_types.items():
            print(f"   {stype}: {count}")
        print(f"   Sources with RSS feeds: {has_rss}")
        print(f"   Sources with AI tag URLs: {has_ai_tag}")

        # Show first 3 sources
        print(f"\n📄 Sample Sources (first 3):")
        for i, source in enumerate(sources[:3], 1):
            print(f"\n   {i}. {source.get('name', 'Unknown')}")
            print(f"      URL: {source.get('news_url', 'N/A')}")
            if source.get('ai_tag_url'):
                print(f"      AI Tag: {source.get('ai_tag_url')}")
            if source.get('rss_feed'):
                print(f"      RSS: {source.get('rss_feed')}")
            print(f"      Type: {source.get('source_type', 'unknown')}")
            if source.get('location'):
                print(f"      Location: {source.get('location')}")

        return True

    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
        return False


def main():
    """Run all tests."""
    print("="*60)
    print("University Source Configuration Test Suite")
    print("="*60)

    results = {}

    # Test each source type
    source_types = ['legacy', 'r1', 'top_public', 'top_universities']

    for source_type in source_types:
        success = test_source_type(source_type, include_meta=False)
        results[source_type] = success

    # Test with meta news
    print("\n\n" + "="*60)
    print("Testing with Meta News Services")
    print("="*60)
    success = test_source_type('r1', include_meta=True)
    results['r1_with_meta'] = success

    # Summary
    print("\n\n" + "="*60)
    print("TEST SUMMARY")
    print("="*60)

    passed = sum(1 for v in results.values() if v)
    total = len(results)

    for test_name, success in results.items():
        status = "✅ PASS" if success else "❌ FAIL"
        print(f"{status} - {test_name}")

    print(f"\n{passed}/{total} tests passed")

    if passed == total:
        print("\n🎉 All tests passed!")
        return 0
    else:
        print(f"\n⚠️  {total - passed} test(s) failed")
        return 1


if __name__ == "__main__":
    sys.exit(main())
