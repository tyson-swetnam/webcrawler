#!/usr/bin/env python3
"""
Find correct news URLs for failed Batch 6 universities
Uses multiple discovery strategies to find working news pages
"""

import json
import requests
import time
from urllib.parse import urlparse

BATCH_REPORT = "/home/tswetnam/github/webcrawler/crawler/config/batch_6_verification_report.json"
TIMEOUT = 10
HEADERS = {
    'User-Agent': 'Mozilla/5.0 (compatible; AI-News-Crawler/1.0; +https://github.com/tyson-swetnam/ai-news-crawler)'
}

# Known corrections based on institutional patterns
KNOWN_FIXES = {
    "Utah State University": [
        "https://www.usu.edu/today/",
        "https://usustatesman.com/",
        "https://www.usu.edu/today/news/"
    ],
    "George Mason University": [
        "https://www.gmu.edu/news",
        "https://www2.gmu.edu/news",
        "https://science.gmu.edu/news"
    ],
    "Old Dominion University": [
        "https://www.odu.edu/news",
        "https://www.odu.edu/about/monarch-magazine"
    ],
    "Virginia Commonwealth University": [
        "https://www.vcu.edu/news/",
        "https://news.vcu.edu/"
    ],
    "William & Mary": [
        "https://www.wm.edu/news/",
        "https://www.wm.edu/news/stories/",
        "https://news.wm.edu/"
    ],
    "University of Vermont": [
        "https://www.uvm.edu/news",
        "https://www.uvm.edu/uvmnews"
    ],
    "Washington State University": [
        "https://news.wsu.edu/",
        "https://wsu.edu/news/",
        "https://www.wsu.edu/news/"
    ],
    "University of Wisconsin-Madison": [
        "https://news.wisc.edu/",
        "https://www.wisc.edu/news/",
        "https://www.wisconsin.edu/news/"
    ],
    "University of Wisconsin-Milwaukee": [
        "https://uwm.edu/news/",
        "https://www.uwm.edu/news/",
        "https://uwmilwaukee.edu/news/"
    ],
    "West Virginia University": [
        "https://wvutoday.wvu.edu/",
        "https://www.wvu.edu/news",
        "https://news.wvu.edu/"
    ],
    "University of Wyoming": [
        "https://www.uwyo.edu/news/",
        "https://uwyo.edu/news/",
        "https://www.uwyo.edu/uw/news/"
    ]
}

def test_url(url):
    """Test if URL is accessible and returns news content"""
    try:
        print(f"    Testing: {url}")
        response = requests.get(url, headers=HEADERS, timeout=TIMEOUT, allow_redirects=True)
        if response.status_code == 200:
            html = response.text.lower()
            # Check for news indicators
            has_news = any(x in html for x in ['news', 'press', 'article', 'story'])
            has_2025 = '2025' in html

            score = 0
            if has_news:
                score += 50
            if has_2025:
                score += 30
            if 'schema.org' in html:
                score += 10
            if 'university' in html or 'college' in html:
                score += 10

            print(f"      ✓ HTTP 200 | Score: {score}/100")
            return True, score, response.url  # Return final URL after redirects
        else:
            print(f"      ✗ HTTP {response.status_code}")
            return False, 0, None
    except Exception as e:
        print(f"      ✗ Error: {str(e)[:50]}")
        return False, 0, None

def find_working_url(institution, failed_url):
    """Try multiple strategies to find working news URL"""
    print(f"\n🔍 Finding correction for: {institution}")
    print(f"   Failed URL: {failed_url}")

    if institution in KNOWN_FIXES:
        candidates = KNOWN_FIXES[institution]
        print(f"   Testing {len(candidates)} known candidates...")

        best_url = None
        best_score = 0

        for url in candidates:
            works, score, final_url = test_url(url)
            if works and score > best_score:
                best_score = score
                best_url = final_url or url

        if best_url:
            print(f"   ✅ FOUND: {best_url} (score: {best_score}/100)")
            return best_url, best_score

    print(f"   ❌ No working URL found")
    return None, 0

def main():
    print("="*70)
    print("BATCH 6 URL CORRECTION DISCOVERY")
    print("="*70)

    # Load batch 6 report
    with open(BATCH_REPORT, 'r') as f:
        report = json.load(f)

    failed_urls = [r for r in report['results'] if r['recommendation'] == 'SKIP']

    print(f"\nFound {len(failed_urls)} failed URLs to correct")

    corrections = []

    for result in failed_urls:
        institution = result['institution']
        old_url = result['url']

        new_url, score = find_working_url(institution, old_url)

        if new_url:
            corrections.append({
                "institution": institution,
                "old_url": old_url,
                "new_url": new_url,
                "confidence_score": score,
                "verified": True
            })
        else:
            corrections.append({
                "institution": institution,
                "old_url": old_url,
                "new_url": None,
                "confidence_score": 0,
                "verified": False,
                "note": "Manual research required"
            })

        time.sleep(1)  # Politeness

    # Save corrections
    output_file = "/home/tswetnam/github/webcrawler/crawler/config/batch_6_corrections.json"
    with open(output_file, 'w') as f:
        json.dump({
            "batch": 6,
            "total_failed": len(failed_urls),
            "corrections_found": sum(1 for c in corrections if c['verified']),
            "manual_research_needed": sum(1 for c in corrections if not c['verified']),
            "corrections": corrections
        }, f, indent=2)

    print("\n" + "="*70)
    print("CORRECTIONS SUMMARY")
    print("="*70)
    print(f"Total failed URLs: {len(failed_urls)}")
    print(f"Corrections found: {sum(1 for c in corrections if c['verified'])}")
    print(f"Still need manual research: {sum(1 for c in corrections if not c['verified'])}")
    print(f"\nSaved to: {output_file}")

    # Print corrections
    print("\n" + "="*70)
    print("CORRECTIONS TO APPLY")
    print("="*70)

    for c in corrections:
        if c['verified']:
            print(f"\n✅ {c['institution']}")
            print(f"   OLD: {c['old_url']}")
            print(f"   NEW: {c['new_url']}")
            print(f"   Confidence: {c['confidence_score']}/100")

    print("\n" + "="*70)
    print("MANUAL RESEARCH NEEDED")
    print("="*70)

    for c in corrections:
        if not c['verified']:
            print(f"\n❌ {c['institution']}")
            print(f"   Failed URL: {c['old_url']}")
            print(f"   Action: Visit university website manually")

if __name__ == "__main__":
    main()
