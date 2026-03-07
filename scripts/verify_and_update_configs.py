#!/usr/bin/env python3
"""
Verify all URLs using curl and update config files with verification status.
"""

import json
import subprocess
from pathlib import Path
from datetime import datetime, timezone
from collections import defaultdict

config_dir = Path(__file__).parent.parent / "crawler" / "config"

def test_url(url: str, timeout: int = 10) -> tuple[bool, int, str]:
    """
    Test if URL is accessible using curl.
    Returns: (success, http_code, error_message)
    """
    try:
        result = subprocess.run(
            ['curl', '-s', '-o', '/dev/null', '-w', '%{http_code}',
             '--max-time', str(timeout), '--location', url],
            capture_output=True,
            text=True,
            timeout=timeout + 2
        )

        http_code = result.stdout.strip()

        # Consider 2xx and 3xx as success
        if http_code and http_code[0] in ['2', '3']:
            return True, int(http_code), ''
        elif http_code == '000':
            return False, 0, 'DNS or connection failed'
        else:
            return False, int(http_code) if http_code.isdigit() else 0, f'HTTP {http_code}'

    except subprocess.TimeoutExpired:
        return False, 0, 'Timeout'
    except Exception as e:
        return False, 0, str(e)


def main():
    print("="*80)
    print("URL VERIFICATION - Batch Processing")
    print("="*80)

    # Load all config files
    configs = {
        'r1_universities.json': 'universities',
        'peer_institutions.json': 'universities',
        'major_facilities.json': 'facilities'
    }

    stats = {
        'total_tested': 0,
        'verified_success': 0,
        'verified_failed': 0,
        'already_verified': 0
    }

    failed_urls = []

    for config_file, items_key in configs.items():
        config_path = config_dir / config_file
        if not config_path.exists():
            continue

        print(f"\n📁 Processing: {config_file}")

        with open(config_path, 'r') as f:
            data = json.load(f)

        items = data.get(items_key, [])
        modified = False

        for item in items:
            news_sources = item.get('news_sources', {})
            primary = news_sources.get('primary', {})

            name = item.get('canonical_name', item.get('name', 'Unknown'))
            item_id = item.get('id')

            # Skip if already verified
            if primary.get('verified', False):
                stats['already_verified'] += 1
                continue

            url = primary.get('url', '')
            ai_url = primary.get('ai_tag_url', '')

            # Skip placeholder URLs
            if 'universityof.edu' in url.lower():
                continue

            # Test primary URL
            if url:
                print(f"  Testing [{item_id}] {name}: {url[:60]}...")
                success, code, error = test_url(url)
                stats['total_tested'] += 1

                if success:
                    primary['verified'] = True
                    primary['last_verified'] = datetime.now(timezone.utc).isoformat()
                    stats['verified_success'] += 1
                    print(f"    ✓ Success (HTTP {code})")
                    modified = True
                else:
                    primary['verified'] = False
                    stats['verified_failed'] += 1
                    print(f"    ✗ Failed: {error}")
                    failed_urls.append({
                        'config': config_file,
                        'id': item_id,
                        'name': name,
                        'url': url,
                        'error': error,
                        'http_code': code
                    })

        # Save updated config
        if modified:
            data['metadata']['last_updated'] = datetime.now(timezone.utc).isoformat()

            with open(config_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
                f.write('\n')

            print(f"  ✓ Updated {config_file}")

    # Generate report
    print("\n" + "="*80)
    print("VERIFICATION SUMMARY")
    print("="*80)
    print(f"Already verified: {stats['already_verified']}")
    print(f"Tested: {stats['total_tested']}")
    print(f"  Verified (success): {stats['verified_success']}")
    print(f"  Failed: {stats['verified_failed']}")

    if failed_urls:
        print(f"\n⚠ {len(failed_urls)} URLs failed verification:")

        # Group by error type
        by_error = defaultdict(list)
        for item in failed_urls:
            by_error[item['error']].append(item)

        for error_type, items in sorted(by_error.items()):
            print(f"\n  {error_type} ({len(items)} URLs):")
            for item in items[:5]:  # Show first 5 of each type
                print(f"    - [{item['id']}] {item['name']}: {item['url']}")
            if len(items) > 5:
                print(f"    ... and {len(items) - 5} more")

    # Save detailed failed URLs report
    if failed_urls:
        failed_report_path = config_dir / "failed_urls_report.json"
        with open(failed_report_path, 'w', encoding='utf-8') as f:
            json.dump({
                'timestamp': datetime.now(timezone.utc).isoformat(),
                'total_failed': len(failed_urls),
                'failed_urls': failed_urls
            }, f, indent=2)

        print(f"\n✓ Detailed failed URLs report: {failed_report_path}")

    print("\n" + "="*80)
    print("✓ VERIFICATION COMPLETE")
    print("="*80)


if __name__ == '__main__':
    main()
