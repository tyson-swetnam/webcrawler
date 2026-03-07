#!/usr/bin/env python3
"""
R1 University News URL Verification Script

This script verifies unverified news URLs from r1_universities.json by:
1. Attempting to fetch each URL
2. Validating response codes and content patterns
3. Detecting legitimate university news pages
4. Suggesting corrections for failed URLs
"""

import json
import time
import sys
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Tuple
import requests
from urllib.parse import urlparse, urljoin
import re

# Configure requests session with timeout and user agent
session = requests.Session()
session.headers.update({
    'User-Agent': 'AI-News-Crawler-URLVerifier/1.0 (University News Aggregator; Contact: admin@example.com)'
})

def verify_url(url: str, university_name: str) -> Dict:
    """
    Verify a single URL and return detailed results.

    Args:
        url: The URL to verify
        university_name: Name of the university for context

    Returns:
        Dict with verification results
    """
    result = {
        'university_name': university_name,
        'original_url': url,
        'verified': False,
        'status_code': None,
        'issue': None,
        'suggested_correction': None,
        'notes': None,
        'redirect_url': None
    }

    try:
        # Attempt to fetch the URL with 10 second timeout
        response = session.get(url, timeout=10, allow_redirects=True)
        result['status_code'] = response.status_code

        # Track redirects
        if response.history:
            result['redirect_url'] = response.url
            result['notes'] = f"Redirected from {url} to {response.url}"

        # Check status code
        if response.status_code == 200:
            # Analyze content to confirm it's a news page
            content = response.text.lower()

            # Look for news page indicators
            news_indicators = [
                'news', 'press release', 'article', 'story', 'stories',
                'newsroom', 'media', 'announcements', 'latest'
            ]

            # Look for university branding
            uni_words = university_name.lower().split()
            has_university_branding = any(word in content for word in uni_words if len(word) > 3)

            # Look for news content patterns
            has_news_indicators = sum(1 for indicator in news_indicators if indicator in content) >= 2

            # Look for article listings (common HTML patterns)
            has_article_structure = bool(
                re.search(r'<article|class=".*?(?:post|article|news|story)', content, re.IGNORECASE)
            )

            if has_university_branding and (has_news_indicators or has_article_structure):
                result['verified'] = True
                result['notes'] = "Valid university news page with article listings"
            elif has_news_indicators:
                result['verified'] = True
                result['notes'] = "News page detected but university branding unclear"
            else:
                result['verified'] = False
                result['issue'] = "Page loads but doesn't appear to be a news listing page"
                result['notes'] = "May be a general university page, not specifically news"

        elif response.status_code == 403:
            result['issue'] = "403 Forbidden - Site may be blocking automated access"
            result['notes'] = "Consider manual verification or checking robots.txt"

        elif response.status_code == 404:
            result['issue'] = "404 Not Found - URL does not exist"
            result['suggested_correction'] = suggest_url_correction(url)

        elif response.status_code in [301, 302, 307, 308]:
            # Permanent/temporary redirect
            result['verified'] = True
            result['notes'] = f"Redirects to {response.url}"

        elif response.status_code >= 500:
            result['issue'] = f"{response.status_code} Server Error - Temporary issue"
            result['notes'] = "Server may be temporarily down, retry later"

        else:
            result['issue'] = f"Unexpected status code: {response.status_code}"

    except requests.exceptions.Timeout:
        result['issue'] = "Request timeout after 10 seconds"
        result['notes'] = "Server may be slow or unresponsive"

    except requests.exceptions.SSLError:
        result['issue'] = "SSL certificate error"
        result['suggested_correction'] = url.replace('https://', 'http://')
        result['notes'] = "Try HTTP version or certificate may be expired"

    except requests.exceptions.ConnectionError:
        result['issue'] = "Connection error - unable to reach server"
        result['suggested_correction'] = suggest_url_correction(url)

    except requests.exceptions.TooManyRedirects:
        result['issue'] = "Too many redirects - possible redirect loop"
        result['notes'] = "URL may be misconfigured"

    except Exception as e:
        result['issue'] = f"Unexpected error: {str(e)}"

    return result


def suggest_url_correction(url: str) -> str:
    """
    Suggest potential URL corrections based on common patterns.

    Args:
        url: The failed URL

    Returns:
        Suggested corrected URL
    """
    parsed = urlparse(url)
    suggestions = []

    # Try HTTPS if HTTP
    if parsed.scheme == 'http':
        suggestions.append(url.replace('http://', 'https://'))
    # Try HTTP if HTTPS failed
    elif parsed.scheme == 'https':
        suggestions.append(url.replace('https://', 'http://'))

    # Try with/without trailing slash
    if url.endswith('/'):
        suggestions.append(url.rstrip('/'))
    else:
        suggestions.append(url + '/')

    # Common news URL patterns
    domain = parsed.netloc
    if '/news' not in url.lower():
        suggestions.extend([
            f"https://{domain}/news",
            f"https://{domain}/news/",
            f"https://news.{domain}",
            f"https://{domain}/newsroom",
            f"https://{domain}/press-releases"
        ])

    return suggestions[0] if suggestions else None


def verify_batch(universities: List[Dict], batch_num: int, total_batches: int) -> List[Dict]:
    """
    Verify a batch of universities with rate limiting.

    Args:
        universities: List of university dicts to verify
        batch_num: Current batch number
        total_batches: Total number of batches

    Returns:
        List of verification results
    """
    results = []
    batch_size = len(universities)

    print(f"\n{'='*80}")
    print(f"Processing Batch {batch_num}/{total_batches} ({batch_size} universities)")
    print(f"{'='*80}\n")

    for i, uni in enumerate(universities, 1):
        print(f"[{i}/{batch_size}] Verifying: {uni['name']}")
        print(f"  URL: {uni['url']}")

        result = verify_url(uni['url'], uni['name'])
        results.append(result)

        # Print immediate result
        if result['verified']:
            print(f"  ✓ VERIFIED - {result.get('notes', 'OK')}")
        else:
            print(f"  ✗ FAILED - {result.get('issue', 'Unknown error')}")
            if result.get('suggested_correction'):
                print(f"    Suggestion: {result['suggested_correction']}")

        # Rate limiting: 2 seconds between requests
        if i < batch_size:
            time.sleep(2)

    return results


def main():
    """Main verification workflow"""

    print("="*80)
    print("R1 University News URL Verification")
    print("="*80)

    # Load unverified URLs
    try:
        with open('/tmp/unverified_urls.json', 'r') as f:
            universities = json.load(f)
    except FileNotFoundError:
        print("Error: /tmp/unverified_urls.json not found")
        print("Run the extraction script first")
        sys.exit(1)

    total_count = len(universities)
    print(f"\nTotal universities to verify: {total_count}")

    # Process in batches of 20
    batch_size = 20
    all_results = []
    batches = [universities[i:i+batch_size] for i in range(0, total_count, batch_size)]
    total_batches = len(batches)

    print(f"Processing in {total_batches} batches of up to {batch_size} URLs")
    print(f"Estimated time: ~{(total_count * 2) / 60:.1f} minutes")

    start_time = time.time()

    for batch_num, batch in enumerate(batches, 1):
        batch_results = verify_batch(batch, batch_num, total_batches)
        all_results.extend(batch_results)

        # Progress summary
        verified_so_far = sum(1 for r in all_results if r['verified'])
        failed_so_far = len(all_results) - verified_so_far
        print(f"\nProgress: {len(all_results)}/{total_count} verified")
        print(f"  Success: {verified_so_far} ({verified_so_far/len(all_results)*100:.1f}%)")
        print(f"  Failed: {failed_so_far} ({failed_so_far/len(all_results)*100:.1f}%)")

        # Wait between batches (except last one)
        if batch_num < total_batches:
            print("\nWaiting 10 seconds before next batch...")
            time.sleep(10)

    elapsed_time = time.time() - start_time

    # Generate summary report
    successful = sum(1 for r in all_results if r['verified'])
    failed = total_count - successful

    report = {
        'verification_date': datetime.utcnow().isoformat() + 'Z',
        'total_verified': total_count,
        'successful_verifications': successful,
        'failed_verifications': failed,
        'success_rate': f"{successful/total_count*100:.2f}%",
        'elapsed_time_minutes': f"{elapsed_time/60:.2f}",
        'results': all_results
    }

    # Save report
    report_path = '/home/tswetnam/github/webcrawler/r1_verification_results.json'
    with open(report_path, 'w') as f:
        json.dump(report, f, indent=2)

    # Print final summary
    print("\n" + "="*80)
    print("VERIFICATION COMPLETE")
    print("="*80)
    print(f"\nTotal URLs Verified: {total_count}")
    print(f"Successful: {successful} ({successful/total_count*100:.1f}%)")
    print(f"Failed: {failed} ({failed/total_count*100:.1f}%)")
    print(f"Elapsed Time: {elapsed_time/60:.1f} minutes")
    print(f"\nDetailed report saved to: {report_path}")

    # Identify common issues
    issues = {}
    for result in all_results:
        if not result['verified'] and result.get('issue'):
            issue_type = result['issue'].split('-')[0].strip()
            issues[issue_type] = issues.get(issue_type, 0) + 1

    if issues:
        print("\nCommon Issues:")
        for issue, count in sorted(issues.items(), key=lambda x: x[1], reverse=True):
            print(f"  - {issue}: {count} occurrences")

    # Identify patterns in failures
    failed_domains = {}
    for result in all_results:
        if not result['verified']:
            domain = urlparse(result['original_url']).netloc
            base_domain = '.'.join(domain.split('.')[-2:])
            failed_domains[base_domain] = failed_domains.get(base_domain, 0) + 1

    if failed_domains:
        multi_failures = {d: c for d, c in failed_domains.items() if c > 1}
        if multi_failures:
            print("\nDomains with Multiple Failures:")
            for domain, count in sorted(multi_failures.items(), key=lambda x: x[1], reverse=True):
                print(f"  - {domain}: {count} failures")

    return 0 if failed == 0 else 1


if __name__ == '__main__':
    sys.exit(main())
