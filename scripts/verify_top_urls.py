#!/usr/bin/env python3
"""
Quick verification of top university URLs using simple HTTP requests.
"""

import requests
from crawler.config.settings import settings
from collections import Counter

def test_url(url, timeout=10):
    """Test if URL resolves successfully."""
    try:
        response = requests.head(url, timeout=timeout, allow_redirects=True)
        if response.status_code < 400:
            return True, response.status_code, None
        else:
            return False, response.status_code, None
    except requests.exceptions.RequestException as e:
        return False, None, str(e)

def main():
    print("=" * 70)
    print("Top URLs Verification")
    print("=" * 70)

    # Get all sources
    sources = settings.get_university_sources()
    print(f"\nTotal sources: {len(sources)}")

    # Identify priority sources (peer institutions and major facilities)
    priority = []
    regular = []

    for source in sources:
        source_type = source.get('source_type', '')
        if 'facility' in source_type.lower() or source.get('institution_type') == 'peer':
            priority.append(source)
        else:
            regular.append(source)

    print(f"Priority sources (peer + facilities): {len(priority)}")
    print(f"Regular sources (R1): {len(regular)}")

    # Test priority sources first
    print("\n" + "=" * 70)
    print("Testing Priority Sources")
    print("=" * 70)

    success = 0
    failed = []

    for source in priority[:20]:  # Top 20 priority
        name = source.get('name')
        url = source.get('news_url')

        if not url:
            print(f"⚠️  {name}: No URL")
            failed.append((name, url, "No URL"))
            continue

        print(f"\nTesting: {name}")
        print(f"  URL: {url}")

        ok, status, error = test_url(url)

        if ok:
            print(f"  ✅ OK (HTTP {status})")
            success += 1
        else:
            print(f"  ❌ FAILED (HTTP {status}, {error})")
            failed.append((name, url, f"HTTP {status}: {error}"))

    print("\n" + "=" * 70)
    print(f"✅ Success: {success}/{len(priority[:20])}")
    print(f"❌ Failed: {len(failed)}")
    print("=" * 70)

    if failed:
        print("\nFailed URLs:")
        for name, url, reason in failed:
            print(f"  - {name}")
            print(f"    URL: {url}")
            print(f"    Reason: {reason}")

if __name__ == '__main__':
    main()
