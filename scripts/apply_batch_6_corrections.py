#!/usr/bin/env python3
"""
Apply Batch 6 URL Corrections to r1_universities.json
All 11 corrections verified with 90-100% confidence scores
"""

import json
import sys
from pathlib import Path

# File paths
CONFIG_DIR = Path("/home/tswetnam/github/webcrawler/crawler/config")
CORRECTIONS_FILE = CONFIG_DIR / "batch_6_corrections.json"
R1_CONFIG_FILE = CONFIG_DIR / "r1_universities.json"
BACKUP_FILE = CONFIG_DIR / f"r1_universities.json.backup_before_batch6"

def main():
    print("="*70)
    print("APPLYING BATCH 6 URL CORRECTIONS")
    print("="*70)
    print()

    # Load corrections
    print(f"Loading corrections from: {CORRECTIONS_FILE}")
    with open(CORRECTIONS_FILE) as f:
        batch_6_data = json.load(f)

    corrections = batch_6_data['corrections']
    print(f"✓ Loaded {len(corrections)} corrections")
    print()

    # Create backup
    print(f"Creating backup: {BACKUP_FILE}")
    with open(R1_CONFIG_FILE) as f:
        original_config = json.load(f)

    with open(BACKUP_FILE, 'w') as f:
        json.dump(original_config, f, indent=2, ensure_ascii=False)
    print(f"✓ Backup created")
    print()

    # Apply corrections
    print("Applying corrections...")
    print("-" * 70)

    applied_count = 0
    not_found = []

    for corr in corrections:
        institution = corr['institution']
        old_url = corr['old_url']
        new_url = corr['new_url']
        confidence = corr['confidence_score']

        # Find and update
        found = False
        for uni in original_config:
            if uni['name'] == institution:
                print(f"\n✓ {institution}")
                print(f"  OLD: {old_url}")
                print(f"  NEW: {new_url}")
                print(f"  Confidence: {confidence}/100")

                # Update URL
                uni['url'] = new_url

                applied_count += 1
                found = True
                break

        if not found:
            not_found.append(institution)
            print(f"\n✗ WARNING: Could not find '{institution}' in config")

    print()
    print("-" * 70)
    print(f"\nApplied {applied_count}/{len(corrections)} corrections")

    if not_found:
        print(f"\nWARNING: {len(not_found)} institutions not found:")
        for name in not_found:
            print(f"  - {name}")
        print()
        response = input("Continue saving despite warnings? (yes/no): ")
        if response.lower() != 'yes':
            print("Aborted. No changes saved.")
            sys.exit(1)

    # Save updated config
    print(f"\nSaving updated configuration to: {R1_CONFIG_FILE}")
    with open(R1_CONFIG_FILE, 'w') as f:
        json.dump(original_config, f, indent=2, ensure_ascii=False)

    print()
    print("="*70)
    print("SUCCESS - BATCH 6 CORRECTIONS APPLIED")
    print("="*70)
    print()
    print(f"✅ Updated {applied_count} URLs in r1_universities.json")
    print(f"✅ Backup saved to: {BACKUP_FILE}")
    print()
    print("Next steps:")
    print("1. Re-verify URLs: python scripts/verify_batch_6_final.py")
    print("2. Test crawler: python -m crawler --test-mode")
    print("3. Commit changes: git add crawler/config/r1_universities.json")
    print()

if __name__ == "__main__":
    main()
