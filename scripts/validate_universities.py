#!/usr/bin/env python3
"""
Validate and enrich university JSON data.

This script:
1. Validates universities.json against the JSON schema
2. Checks URL accessibility
3. Verifies RSS feed validity
4. Calculates data quality scores
5. Generates a validation report
"""

import json
import sys
from pathlib import Path
from typing import List, Dict, Tuple
from datetime import datetime
from urllib.parse import urlparse

# Optional dependencies for URL/RSS validation
try:
    import jsonschema
    HAS_JSONSCHEMA = True
except ImportError:
    HAS_JSONSCHEMA = False
    print("Warning: jsonschema not installed. Schema validation disabled.")
    print("Install with: pip install jsonschema")

try:
    import requests
    HAS_REQUESTS = True
except ImportError:
    HAS_REQUESTS = False
    print("Warning: requests not installed. URL validation disabled.")
    print("Install with: pip install requests")

try:
    import feedparser
    HAS_FEEDPARSER = True
except ImportError:
    HAS_FEEDPARSER = False
    print("Warning: feedparser not installed. RSS validation disabled.")
    print("Install with: pip install feedparser")


def load_json_file(filepath: Path) -> dict:
    """Load and parse JSON file."""
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            return json.load(f)
    except FileNotFoundError:
        print(f"Error: File not found: {filepath}")
        sys.exit(1)
    except json.JSONDecodeError as e:
        print(f"Error: Invalid JSON in {filepath}: {e}")
        sys.exit(1)


def validate_against_schema(data: dict, schema: dict) -> Tuple[bool, List[str]]:
    """
    Validate data against JSON schema.

    Returns:
        (is_valid, list_of_errors)
    """
    if not HAS_JSONSCHEMA:
        return (True, ["Schema validation skipped (jsonschema not installed)"])

    errors = []

    try:
        jsonschema.validate(data, schema)
        return (True, [])
    except jsonschema.ValidationError as e:
        errors.append(f"Schema validation failed: {e.message}")
        errors.append(f"  Path: {' -> '.join(str(p) for p in e.path)}")
        return (False, errors)
    except jsonschema.SchemaError as e:
        errors.append(f"Invalid schema: {e.message}")
        return (False, errors)


def verify_url_accessible(url: str, timeout: int = 5) -> Tuple[bool, str]:
    """
    Check if URL is accessible.

    Returns:
        (is_accessible, status_message)
    """
    if not HAS_REQUESTS:
        return (False, "Skipped (requests not installed)")

    try:
        response = requests.head(url, timeout=timeout, allow_redirects=True)
        if response.status_code == 200:
            return (True, "OK")
        elif 200 <= response.status_code < 300:
            return (True, f"Redirect {response.status_code}")
        elif response.status_code == 405:
            # HEAD not allowed, try GET
            response = requests.get(url, timeout=timeout, allow_redirects=True, stream=True)
            response.close()
            return (True, "OK (GET)") if response.status_code == 200 else (False, f"HTTP {response.status_code}")
        else:
            return (False, f"HTTP {response.status_code}")
    except requests.exceptions.Timeout:
        return (False, "Timeout")
    except requests.exceptions.ConnectionError:
        return (False, "Connection failed")
    except requests.exceptions.RequestException as e:
        return (False, f"Request error: {str(e)[:50]}")


def verify_rss_feed(url: str, timeout: int = 10) -> Tuple[bool, str, dict]:
    """
    Check if URL is a valid RSS/Atom feed.

    Returns:
        (is_valid, status_message, feed_info)
    """
    if not HAS_FEEDPARSER:
        return (False, "Skipped (feedparser not installed)", {})

    try:
        feed = feedparser.parse(url, request_headers={'User-Agent': 'Mozilla/5.0'})

        if feed.bozo:
            return (False, f"Parse error: {feed.bozo_exception}", {})

        if len(feed.entries) == 0:
            return (False, "No entries found", {})

        feed_info = {
            'version': feed.version,
            'title': feed.feed.get('title', 'Untitled'),
            'entries_count': len(feed.entries),
            'latest_entry_date': feed.entries[0].get('published', 'Unknown') if feed.entries else None
        }

        return (True, "Valid", feed_info)

    except Exception as e:
        return (False, f"Error: {str(e)[:50]}", {})


def calculate_completeness_score(university: dict) -> float:
    """
    Calculate overall data completeness score (0.0-1.0).

    Weights:
    - basic_info: 0.2 (name, location)
    - news_sources: 0.3 (primary URL)
    - rss_feeds: 0.2 (RSS availability)
    - social_media: 0.1
    - media_relations: 0.1
    - ai_research: 0.1
    """
    weights = {
        'basic_info': 0.2,
        'news_sources': 0.3,
        'rss_feeds': 0.2,
        'social_media': 0.1,
        'media_relations': 0.1,
        'ai_research': 0.1
    }

    scores = {}

    # Basic info score
    basic_fields = [
        university.get('name'),
        university.get('location', {}).get('city'),
        university.get('location', {}).get('state'),
        university.get('location', {}).get('country')
    ]
    scores['basic_info'] = sum(1 for f in basic_fields if f) / len(basic_fields)

    # News sources score
    primary = university.get('news_sources', {}).get('primary')
    ai_tag = primary.get('ai_tag_url') if primary else None
    verified = primary.get('verified', False) if primary else False
    scores['news_sources'] = (
        (1.0 if primary else 0.0) +
        (0.5 if ai_tag else 0.0) +
        (0.5 if verified else 0.0)
    ) / 2.0

    # RSS feeds score (max out at 3 feeds)
    rss_feeds = university.get('news_sources', {}).get('rss_feeds', [])
    active_verified_rss = [f for f in rss_feeds if f.get('active') and f.get('verified')]
    scores['rss_feeds'] = min(len(active_verified_rss) / 3.0, 1.0)

    # Social media score
    social = university.get('social_media', {})
    social_platforms = ['twitter', 'linkedin', 'facebook', 'instagram', 'youtube']
    social_count = sum(1 for p in social_platforms if social.get(p) and social[p].get('url'))
    scores['social_media'] = min(social_count / 3.0, 1.0)  # Max out at 3 platforms

    # Media relations score
    media = university.get('media_relations', {})
    media_fields = [media.get('page_url'), media.get('email'), media.get('phone')]
    scores['media_relations'] = sum(1 for f in media_fields if f) / len(media_fields)

    # AI research score
    ai = university.get('ai_research', {})
    ai_fields = [
        ai.get('has_ai_institute'),
        ai.get('ai_centers'),
        ai.get('ai_focus_areas')
    ]
    scores['ai_research'] = sum(1 for f in ai_fields if f) / len(ai_fields)

    # Calculate weighted total
    total_score = sum(weights[k] * scores[k] for k in weights)

    return total_score


def validate_university_data(
    university: dict,
    check_urls: bool = False,
    check_rss: bool = False
) -> Dict[str, any]:
    """
    Validate a single university entry.

    Returns:
        Dictionary with validation results
    """
    results = {
        'name': university.get('name', 'Unknown'),
        'errors': [],
        'warnings': [],
        'url_checks': {},
        'rss_checks': {},
        'completeness_score': 0.0
    }

    # Required field checks
    if not university.get('name'):
        results['errors'].append("Missing required field: name")
    if not university.get('location', {}).get('state'):
        results['errors'].append("Missing required field: location.state")
    if not university.get('news_sources', {}).get('primary'):
        results['errors'].append("Missing required field: news_sources.primary")

    # URL accessibility checks
    if check_urls:
        primary = university.get('news_sources', {}).get('primary', {})
        primary_url = primary.get('url')

        if primary_url:
            is_accessible, status = verify_url_accessible(primary_url)
            results['url_checks']['primary'] = {
                'url': primary_url,
                'accessible': is_accessible,
                'status': status
            }
            if not is_accessible:
                results['warnings'].append(f"Primary URL not accessible: {status}")

        # Check AI tag URL
        ai_tag_url = primary.get('ai_tag_url')
        if ai_tag_url:
            is_accessible, status = verify_url_accessible(ai_tag_url)
            results['url_checks']['ai_tag'] = {
                'url': ai_tag_url,
                'accessible': is_accessible,
                'status': status
            }
            if not is_accessible:
                results['warnings'].append(f"AI tag URL not accessible: {status}")

    # RSS feed validation
    if check_rss:
        rss_feeds = university.get('news_sources', {}).get('rss_feeds', [])
        for idx, rss in enumerate(rss_feeds):
            if rss.get('active'):
                rss_url = rss.get('url')
                is_valid, status, feed_info = verify_rss_feed(rss_url)
                results['rss_checks'][f'feed_{idx}'] = {
                    'url': rss_url,
                    'valid': is_valid,
                    'status': status,
                    'info': feed_info
                }
                if not is_valid:
                    results['warnings'].append(f"RSS feed invalid: {rss_url} - {status}")

    # Calculate completeness score
    results['completeness_score'] = calculate_completeness_score(university)

    return results


def generate_report(
    data: dict,
    validation_results: List[Dict],
    schema_valid: bool,
    schema_errors: List[str]
) -> str:
    """Generate human-readable validation report."""
    report = []
    report.append("=" * 80)
    report.append("UNIVERSITY DATA VALIDATION REPORT")
    report.append("=" * 80)
    report.append(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    report.append("")

    # Schema validation
    report.append("SCHEMA VALIDATION")
    report.append("-" * 80)
    if schema_valid:
        report.append("✓ JSON schema validation PASSED")
    else:
        report.append("✗ JSON schema validation FAILED")
        for error in schema_errors:
            report.append(f"  {error}")
    report.append("")

    # Metadata
    metadata = data.get('metadata', {})
    report.append("METADATA")
    report.append("-" * 80)
    report.append(f"Schema Version: {metadata.get('schema_version', 'Unknown')}")
    report.append(f"Total Institutions: {metadata.get('total_institutions', 0)}")
    report.append(f"Institutions Included: {len(data.get('universities', []))}")
    report.append(f"Last Updated: {metadata.get('last_updated', 'Unknown')}")
    report.append("")

    # University validation summary
    report.append("UNIVERSITY VALIDATION SUMMARY")
    report.append("-" * 80)

    total_universities = len(validation_results)
    universities_with_errors = sum(1 for r in validation_results if r['errors'])
    universities_with_warnings = sum(1 for r in validation_results if r['warnings'])
    avg_completeness = sum(r['completeness_score'] for r in validation_results) / total_universities if total_universities > 0 else 0

    report.append(f"Total Universities: {total_universities}")
    report.append(f"Universities with Errors: {universities_with_errors}")
    report.append(f"Universities with Warnings: {universities_with_warnings}")
    report.append(f"Average Completeness Score: {avg_completeness:.2%}")
    report.append("")

    # Completeness distribution
    report.append("COMPLETENESS DISTRIBUTION")
    report.append("-" * 80)
    bins = [0.0, 0.25, 0.5, 0.75, 0.9, 1.0]
    bin_labels = ["0-25%", "25-50%", "50-75%", "75-90%", "90-100%"]
    for i, (low, high) in enumerate(zip(bins[:-1], bins[1:])):
        count = sum(1 for r in validation_results if low <= r['completeness_score'] < high)
        bar = "█" * (count // 2) if count > 0 else ""
        report.append(f"{bin_labels[i]:>10}: {count:3d} {bar}")
    report.append("")

    # Detailed university results (only errors and low completeness)
    report.append("DETAILED RESULTS (Issues Only)")
    report.append("-" * 80)

    for result in validation_results:
        has_issues = result['errors'] or result['warnings'] or result['completeness_score'] < 0.5

        if has_issues:
            report.append(f"\n{result['name']}")
            report.append(f"  Completeness: {result['completeness_score']:.2%}")

            if result['errors']:
                report.append("  ERRORS:")
                for error in result['errors']:
                    report.append(f"    - {error}")

            if result['warnings']:
                report.append("  WARNINGS:")
                for warning in result['warnings']:
                    report.append(f"    - {warning}")

            if result['url_checks']:
                report.append("  URL CHECKS:")
                for name, check in result['url_checks'].items():
                    status_symbol = "✓" if check['accessible'] else "✗"
                    report.append(f"    {status_symbol} {name}: {check['status']}")

            if result['rss_checks']:
                report.append("  RSS CHECKS:")
                for name, check in result['rss_checks'].items():
                    status_symbol = "✓" if check['valid'] else "✗"
                    report.append(f"    {status_symbol} {check['url']}: {check['status']}")

    report.append("")
    report.append("=" * 80)
    report.append("END OF REPORT")
    report.append("=" * 80)

    return "\n".join(report)


def main():
    """Main validation script."""
    import argparse

    parser = argparse.ArgumentParser(
        description="Validate university JSON data against schema"
    )
    parser.add_argument(
        '--universities',
        type=Path,
        default=Path('crawler/config/universities.json'),
        help='Path to universities JSON file'
    )
    parser.add_argument(
        '--schema',
        type=Path,
        default=Path('crawler/config/university_schema.json'),
        help='Path to JSON schema file'
    )
    parser.add_argument(
        '--check-urls',
        action='store_true',
        help='Verify URL accessibility (slow)'
    )
    parser.add_argument(
        '--check-rss',
        action='store_true',
        help='Verify RSS feed validity (slow)'
    )
    parser.add_argument(
        '--output',
        type=Path,
        help='Output report to file (default: print to console)'
    )
    parser.add_argument(
        '--json-output',
        type=Path,
        help='Output detailed results as JSON'
    )

    args = parser.parse_args()

    print("Loading university data...")
    data = load_json_file(args.universities)

    print("Loading JSON schema...")
    schema = load_json_file(args.schema)

    print("Validating against schema...")
    schema_valid, schema_errors = validate_against_schema(data, schema)

    print(f"Validating {len(data.get('universities', []))} universities...")
    validation_results = []

    for idx, university in enumerate(data.get('universities', []), 1):
        if idx % 10 == 0:
            print(f"  Processed {idx} universities...")

        result = validate_university_data(
            university,
            check_urls=args.check_urls,
            check_rss=args.check_rss
        )
        validation_results.append(result)

    print("Generating report...")
    report = generate_report(data, validation_results, schema_valid, schema_errors)

    # Output report
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        with open(args.output, 'w', encoding='utf-8') as f:
            f.write(report)
        print(f"Report written to: {args.output}")
    else:
        print("\n" + report)

    # Output JSON results
    if args.json_output:
        json_results = {
            'schema_valid': schema_valid,
            'schema_errors': schema_errors,
            'validation_results': validation_results,
            'summary': {
                'total_universities': len(validation_results),
                'universities_with_errors': sum(1 for r in validation_results if r['errors']),
                'universities_with_warnings': sum(1 for r in validation_results if r['warnings']),
                'average_completeness': sum(r['completeness_score'] for r in validation_results) / len(validation_results) if validation_results else 0
            },
            'generated_at': datetime.now().isoformat()
        }

        args.json_output.parent.mkdir(parents=True, exist_ok=True)
        with open(args.json_output, 'w', encoding='utf-8') as f:
            json.dump(json_results, f, indent=2)
        print(f"JSON results written to: {args.json_output}")

    # Exit with appropriate code
    sys.exit(0 if schema_valid and not any(r['errors'] for r in validation_results) else 1)


if __name__ == '__main__':
    main()
