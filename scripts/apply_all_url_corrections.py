#!/usr/bin/env python3
"""
Apply all URL corrections from verification batches 1-6.

This script consolidates corrections from all verification reports and applies them
to the config files (peer_institutions.json, r1_universities.json, major_facilities.json).
"""

import sys
import os
import json
import shutil
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Tuple

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

def load_batch_1_2_corrections() -> List[Dict]:
    """Load corrections from Batches 1-2 report."""
    corrections = []

    report_path = Path('crawler/config/url_verification_report_batches_1_2.json')
    if not report_path.exists():
        return corrections

    with open(report_path) as f:
        report = json.load(f)

    # Extract broken URLs from Batch 1 (Peer)
    for item in report.get('batch_1_peer_institutions', {}).get('broken_urls', []):
        corrections.append({
            'name': item['name'],
            'old_url': item.get('original_url', ''),
            'new_url': item.get('corrected_url', ''),
            'category': 'peer'
        })

    # Extract broken URLs from Batch 2 (Facilities)
    for item in report.get('batch_2_major_facilities', {}).get('broken_urls', []):
        corrections.append({
            'name': item['name'],
            'old_url': item.get('original_url', ''),
            'new_url': item.get('corrected_url', ''),
            'category': 'facility'
        })

    return corrections

def load_batch_3_corrections() -> List[Dict]:
    """Load corrections from Batch 3 report."""
    corrections = []

    report_path = Path('crawler/config/batch_3_verification_report.json')
    if not report_path.exists():
        return corrections

    with open(report_path) as f:
        report = json.load(f)

    for item in report.get('broken_urls', []):
        corrections.append({
            'name': item['name'],
            'old_url': item['url'],
            'new_url': item['correct_url'],
            'category': 'r1'
        })

    return corrections

def load_batch_4_corrections() -> List[Dict]:
    """Load corrections from Batch 4 report."""
    corrections = []

    report_path = Path('crawler/config/batch_4_verification_report.json')
    if not report_path.exists():
        return corrections

    with open(report_path) as f:
        report = json.load(f)

    for item in report.get('verified_urls', []):
        if item.get('status') == 'corrected':
            corrections.append({
                'name': item['name'],
                'old_url': item.get('original_url', ''),
                'new_url': item['url'],
                'category': 'r1'
            })

    return corrections

def load_batch_5_corrections() -> List[Dict]:
    """Load corrections from Batch 5 report."""
    corrections = []

    report_path = Path('crawler/config/batch_5_verification_report.json')
    if not report_path.exists():
        return corrections

    with open(report_path) as f:
        report = json.load(f)

    for item in report.get('verified_urls', []):
        if item.get('status') == 'corrected':
            corrections.append({
                'name': item['name'],
                'old_url': item.get('original_url', ''),
                'new_url': item['url'],
                'category': 'r1'
            })

    return corrections

def load_batch_6_corrections() -> List[Dict]:
    """Load corrections from Batch 6 corrections file."""
    corrections = []

    corrections_path = Path('crawler/config/batch_6_corrections.json')
    if not corrections_path.exists():
        return corrections

    with open(corrections_path) as f:
        batch_6 = json.load(f)

    for item in batch_6.get('corrections', []):
        corrections.append({
            'name': item['university'],
            'old_url': item['original_url'],
            'new_url': item['corrected_url'],
            'category': 'r1'
        })

    return corrections

def apply_corrections_to_config(filepath: Path, corrections: List[Dict], item_key: str) -> Tuple[int, List[str]]:
    """Apply corrections to a config file."""

    # Load config
    with open(filepath) as f:
        data = json.load(f)

    applied = 0
    changes = []

    for item in data.get(item_key, []):
        name = item.get('name') or item.get('canonical_name')

        # Find matching correction
        for correction in corrections:
            if correction['name'] == name or name in correction['name'] or correction['name'] in name:
                news_sources = item.get('news_sources', [])
                if news_sources:
                    old_url = news_sources[0].get('url')
                    new_url = correction['new_url']

                    if old_url != new_url:
                        news_sources[0]['url'] = new_url
                        news_sources[0]['verified'] = True
                        news_sources[0]['last_verified'] = datetime.now().isoformat()

                        applied += 1
                        changes.append(f"{name}: {old_url} → {new_url}")
                        break

    # Save updated config
    if applied > 0:
        with open(filepath, 'w') as f:
            json.dump(data, f, indent=2)

    return applied, changes

def main():
    """Main execution."""
    print("=" * 80)
    print("APPLYING ALL URL CORRECTIONS FROM VERIFICATION BATCHES 1-6")
    print("=" * 80)
    print()

    # Load all corrections
    print("Loading corrections from all batches...")
    all_corrections = []

    batch_1_2 = load_batch_1_2_corrections()
    all_corrections.extend(batch_1_2)
    print(f"  Batch 1-2: {len(batch_1_2)} corrections")

    batch_3 = load_batch_3_corrections()
    all_corrections.extend(batch_3)
    print(f"  Batch 3: {len(batch_3)} corrections")

    batch_4 = load_batch_4_corrections()
    all_corrections.extend(batch_4)
    print(f"  Batch 4: {len(batch_4)} corrections")

    batch_5 = load_batch_5_corrections()
    all_corrections.extend(batch_5)
    print(f"  Batch 5: {len(batch_5)} corrections")

    batch_6 = load_batch_6_corrections()
    all_corrections.extend(batch_6)
    print(f"  Batch 6: {len(batch_6)} corrections")

    print(f"\nTotal corrections to apply: {len(all_corrections)}")
    print()

    # Group by category
    by_category = {'peer': [], 'r1': [], 'facility': []}
    for correction in all_corrections:
        by_category[correction['category']].append(correction)

    print(f"Peer Institutions: {len(by_category['peer'])} corrections")
    print(f"R1 Universities: {len(by_category['r1'])} corrections")
    print(f"Major Facilities: {len(by_category['facility'])} corrections")
    print()

    # Create backups
    print("Creating backups...")
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_dir = Path(f'crawler/config/backups_{timestamp}')
    backup_dir.mkdir(exist_ok=True)

    for config_file in ['peer_institutions.json', 'r1_universities.json', 'major_facilities.json']:
        src = Path('crawler/config') / config_file
        dst = backup_dir / config_file
        shutil.copy2(src, dst)
        print(f"  ✓ Backed up {config_file}")
    print()

    # Apply corrections
    print("Applying corrections...")
    print()

    total_applied = 0

    # Peer Institutions
    if by_category['peer']:
        print("Updating peer_institutions.json...")
        applied, changes = apply_corrections_to_config(
            Path('crawler/config/peer_institutions.json'),
            by_category['peer'],
            'universities'
        )
        total_applied += applied
        for change in changes:
            print(f"  ✓ {change}")
        print()

    # R1 Universities
    if by_category['r1']:
        print("Updating r1_universities.json...")
        applied, changes = apply_corrections_to_config(
            Path('crawler/config/r1_universities.json'),
            by_category['r1'],
            'universities'
        )
        total_applied += applied
        for change in changes[:10]:  # Show first 10
            print(f"  ✓ {change}")
        if len(changes) > 10:
            print(f"  ... and {len(changes) - 10} more corrections")
        print()

    # Major Facilities
    if by_category['facility']:
        print("Updating major_facilities.json...")
        applied, changes = apply_corrections_to_config(
            Path('crawler/config/major_facilities.json'),
            by_category['facility'],
            'facilities'
        )
        total_applied += applied
        for change in changes:
            print(f"  ✓ {change}")
        print()

    # Summary
    print("=" * 80)
    print("SUMMARY")
    print("=" * 80)
    print(f"Total corrections applied: {total_applied}")
    print(f"Backups saved to: {backup_dir}")
    print()
    print("✅ All corrections have been applied successfully!")
    print()
    print("Next steps:")
    print("  1. Review the changes in the config files")
    print("  2. Run a test crawl to verify URLs work")
    print("  3. Regenerate HTML reports")
    print("=" * 80)

if __name__ == '__main__':
    main()
