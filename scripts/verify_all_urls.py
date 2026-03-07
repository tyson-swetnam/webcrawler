#!/usr/bin/env python3
"""
Comprehensive URL Verification Script
Verifies all URLs in major_facilities.json, peer_institutions.json, and r1_universities.json
Replaces broken ai_tag_urls with base urls when needed
"""

import json
import time
import requests
from typing import Dict, List, Tuple
from pathlib import Path

# Configuration
CONFIG_DIR = Path("/home/tswetnam/github/webcrawler/crawler/config")
FILES_TO_CHECK = [
    "major_facilities.json",
    "peer_institutions.json",
    "r1_universities.json"
]

# HTTP settings
TIMEOUT = 10
DELAY_BETWEEN_REQUESTS = 0.5  # Be polite
USER_AGENT = "Mozilla/5.0 (compatible; AINewsCrawler/1.0; +https://github.com/tswetnam/webcrawler)"
HEADERS = {
    "User-Agent": USER_AGENT,
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}

# Results tracking
results = {
    "total_urls_checked": 0,
    "broken_ai_tag_urls": [],
    "changes_made": [],
    "both_failed": [],
    "files_processed": {}
}


def check_url(url: str) -> Tuple[bool, int, str]:
    """
    Check if a URL is accessible
    Returns: (success, status_code, error_message)
    """
    try:
        response = requests.head(url, headers=HEADERS, timeout=TIMEOUT, allow_redirects=True)
        # Accept 2xx and 3xx as success
        if 200 <= response.status_code < 400:
            return True, response.status_code, ""
        return False, response.status_code, f"HTTP {response.status_code}"
    except requests.exceptions.SSLError as e:
        # Try without SSL verification
        try:
            response = requests.head(url, headers=HEADERS, timeout=TIMEOUT, allow_redirects=True, verify=False)
            if 200 <= response.status_code < 400:
                return True, response.status_code, "SSL Warning (but accessible)"
            return False, response.status_code, f"HTTP {response.status_code} (SSL issue)"
        except Exception as e2:
            return False, 0, f"SSL Error: {str(e)}"
    except requests.exceptions.Timeout:
        return False, 0, "Timeout"
    except requests.exceptions.ConnectionError as e:
        return False, 0, f"Connection Error: {str(e)[:100]}"
    except Exception as e:
        return False, 0, f"Error: {str(e)[:100]}"


def process_entry(entry: Dict, file_name: str, entry_type: str = "university") -> bool:
    """
    Process a single entry (university or facility)
    Returns True if changes were made
    """
    global results

    # Get name
    name = entry.get("name", "Unknown")

    # Get URLs
    news_sources = entry.get("news_sources", {})
    primary = news_sources.get("primary", {})

    base_url = primary.get("url", "")
    ai_tag_url = primary.get("ai_tag_url", "")

    if not base_url or not ai_tag_url:
        return False

    print(f"\n{'='*80}")
    print(f"Checking: {name}")
    print(f"Base URL: {base_url}")
    print(f"AI Tag URL: {ai_tag_url}")

    # Check base URL
    results["total_urls_checked"] += 1
    base_success, base_status, base_error = check_url(base_url)
    print(f"  Base URL: {'✓ OK' if base_success else f'✗ FAILED'} ({base_status if base_status else base_error})")
    time.sleep(DELAY_BETWEEN_REQUESTS)

    # Check AI tag URL
    results["total_urls_checked"] += 1
    ai_success, ai_status, ai_error = check_url(ai_tag_url)
    print(f"  AI Tag URL: {'✓ OK' if ai_success else f'✗ FAILED'} ({ai_status if ai_status else ai_error})")
    time.sleep(DELAY_BETWEEN_REQUESTS)

    # Decision logic
    if not ai_success and base_success:
        # AI tag URL is broken, but base URL works - replace it
        print(f"  → FIXING: Replacing broken ai_tag_url with base url")

        results["broken_ai_tag_urls"].append({
            "file": file_name,
            "name": name,
            "old_ai_tag_url": ai_tag_url,
            "base_url": base_url,
            "error": ai_error or f"HTTP {ai_status}"
        })

        results["changes_made"].append({
            "file": file_name,
            "name": name,
            "old_url": ai_tag_url,
            "new_url": base_url,
            "reason": f"ai_tag_url failed ({ai_error or f'HTTP {ai_status}'}), using base url"
        })

        # Update the entry
        entry["news_sources"]["primary"]["ai_tag_url"] = base_url
        entry["news_sources"]["primary"]["verified"] = False
        entry["news_sources"]["primary"]["notes"] = entry["news_sources"]["primary"].get("notes", "") + f" | ai_tag_url replaced with base url due to error: {ai_error or f'HTTP {ai_status}'}"

        return True

    elif not ai_success and not base_success:
        # Both URLs failed
        print(f"  → WARNING: Both URLs failed!")
        results["both_failed"].append({
            "file": file_name,
            "name": name,
            "base_url": base_url,
            "base_error": base_error or f"HTTP {base_status}",
            "ai_tag_url": ai_tag_url,
            "ai_error": ai_error or f"HTTP {ai_status}"
        })
        return False

    elif ai_success:
        print(f"  → OK: ai_tag_url is working")
        return False

    return False


def process_file(file_name: str) -> Dict:
    """Process a single JSON configuration file"""
    file_path = CONFIG_DIR / file_name

    print(f"\n{'#'*80}")
    print(f"# Processing: {file_name}")
    print(f"{'#'*80}")

    # Read file
    with open(file_path, 'r') as f:
        data = json.load(f)

    # Determine the key for entries
    if "facilities" in data:
        entries_key = "facilities"
        entry_type = "facility"
    elif "universities" in data:
        entries_key = "universities"
        entry_type = "university"
    else:
        print(f"ERROR: Could not find entries in {file_name}")
        return {"entries_processed": 0, "changes_made": 0}

    entries = data.get(entries_key, [])
    total_entries = len(entries)
    changes_count = 0

    print(f"Found {total_entries} {entry_type} entries")

    # Process each entry
    for entry in entries:
        if process_entry(entry, file_name, entry_type):
            changes_count += 1

    # Update metadata
    from datetime import datetime, timezone
    data["metadata"]["last_updated"] = datetime.now(timezone.utc).isoformat()

    # Write back if changes were made
    if changes_count > 0:
        print(f"\n{'='*80}")
        print(f"Writing {changes_count} changes back to {file_name}")
        with open(file_path, 'w') as f:
            json.dump(data, f, indent=2)
        print(f"✓ File updated successfully")
    else:
        print(f"\n{'='*80}")
        print(f"No changes needed for {file_name}")

    return {
        "entries_processed": total_entries,
        "changes_made": changes_count
    }


def main():
    """Main execution"""
    print("=" * 80)
    print("URL VERIFICATION AND REPAIR TOOL")
    print("=" * 80)
    print(f"Checking {len(FILES_TO_CHECK)} configuration files...")
    print(f"Request delay: {DELAY_BETWEEN_REQUESTS}s between requests")
    print("=" * 80)

    # Process each file
    for file_name in FILES_TO_CHECK:
        file_stats = process_file(file_name)
        results["files_processed"][file_name] = file_stats

    # Generate summary report
    print("\n" + "=" * 80)
    print("VERIFICATION SUMMARY")
    print("=" * 80)

    print(f"\nTotal URLs Checked: {results['total_urls_checked']}")
    print(f"Broken AI Tag URLs Found: {len(results['broken_ai_tag_urls'])}")
    print(f"Changes Made: {len(results['changes_made'])}")
    print(f"Entries Where Both URLs Failed: {len(results['both_failed'])}")

    # File-by-file summary
    print("\nPer-File Summary:")
    for file_name, stats in results["files_processed"].items():
        print(f"  {file_name}:")
        print(f"    - Entries processed: {stats['entries_processed']}")
        print(f"    - Changes made: {stats['changes_made']}")

    # Detailed changes
    if results["changes_made"]:
        print("\n" + "=" * 80)
        print("DETAILED CHANGES")
        print("=" * 80)
        for change in results["changes_made"]:
            print(f"\nFile: {change['file']}")
            print(f"Institution: {change['name']}")
            print(f"Old URL: {change['old_url']}")
            print(f"New URL: {change['new_url']}")
            print(f"Reason: {change['reason']}")

    # Both failed
    if results["both_failed"]:
        print("\n" + "=" * 80)
        print("ENTRIES WHERE BOTH URLs FAILED")
        print("=" * 80)
        for failure in results["both_failed"]:
            print(f"\nFile: {failure['file']}")
            print(f"Institution: {failure['name']}")
            print(f"Base URL: {failure['base_url']}")
            print(f"  Error: {failure['base_error']}")
            print(f"AI Tag URL: {failure['ai_tag_url']}")
            print(f"  Error: {failure['ai_error']}")

    # Save detailed report to JSON
    report_path = CONFIG_DIR / "url_verification_report.json"
    with open(report_path, 'w') as f:
        json.dump(results, f, indent=2)
    print(f"\n{'='*80}")
    print(f"Detailed report saved to: {report_path}")
    print("=" * 80)


if __name__ == "__main__":
    main()
