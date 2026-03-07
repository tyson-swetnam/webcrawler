#!/usr/bin/env python3
"""
Simple script to deduplicate university entries in config files.

Merges duplicate entries by keeping primary URL and adding alternates.
"""

import json
from pathlib import Path
from collections import defaultdict

def dedupe_config_file(file_path: str, key: str = 'universities'):
    """
    Deduplicate entries in a config file.

    Args:
        file_path: Path to JSON config file
        key: Key containing the array ('universities' or 'facilities')
    """
    path = Path(file_path)

    if not path.exists():
        print(f"⚠️  File not found: {file_path}")
        return

    # Load data
    with open(path, 'r') as f:
        data = json.load(f)

    if key not in data:
        print(f"⚠️  Key '{key}' not found in {file_path}")
        return

    entries = data[key]
    original_count = len(entries)

    # Group by canonical name
    grouped = defaultdict(list)
    for entry in entries:
        name = entry.get('canonical_name') or entry.get('name')
        grouped[name].append(entry)

    # Find and merge duplicates
    deduped = []
    duplicates_found = 0

    for name, entry_list in grouped.items():
        if len(entry_list) == 1:
            # No duplicate, keep as-is
            deduped.append(entry_list[0])
        else:
            # Duplicate found - merge
            duplicates_found += len(entry_list) - 1
            print(f"\n🔄 Merging {len(entry_list)} entries for: {name}")

            # Use first entry as base
            merged = entry_list[0].copy()

            # Collect all URLs
            all_urls = []
            for entry in entry_list:
                news_sources = entry.get('news_sources', {})
                primary = news_sources.get('primary', {})
                url = primary.get('url') or primary.get('ai_tag_url')
                if url:
                    all_urls.append({
                        'url': url,
                        'ai_tag_url': primary.get('ai_tag_url'),
                        'verified': primary.get('verified', False),
                        'notes': primary.get('notes', '')
                    })

            # Set best URL as primary (prefer AI-specific and verified)
            best_url = None
            best_score = -1

            for url_info in all_urls:
                score = 0
                if url_info.get('ai_tag_url'):
                    score += 2  # AI-specific is preferred
                if url_info.get('verified'):
                    score += 1  # Verified is better

                if score > best_score:
                    best_score = score
                    best_url = url_info

            if best_url:
                merged['news_sources'] = {
                    'primary': {
                        'url': best_url['url'],
                        'ai_tag_url': best_url.get('ai_tag_url'),
                        'verified': best_url.get('verified', False),
                        'notes': f"Merged from {len(entry_list)} entries"
                    },
                    'alternates': [u for u in all_urls if u['url'] != best_url['url']]
                }

                print(f"   Primary: {best_url['url']}")
                print(f"   Alternates: {len(merged['news_sources']['alternates'])}")

            deduped.append(merged)

    # Update data
    data[key] = deduped

    # Write back
    backup_path = path.with_suffix('.json.bak')
    path.rename(backup_path)

    with open(path, 'w') as f:
        json.dump(data, f, indent=2)

    print(f"\n✅ {file_path}")
    print(f"   Original: {original_count} entries")
    print(f"   Deduped: {len(deduped)} entries")
    print(f"   Removed: {duplicates_found} duplicates")
    print(f"   Backup: {backup_path}")

def main():
    print("=" * 60)
    print("University Config Deduplication")
    print("=" * 60)

    # Dedupe each config file
    dedupe_config_file('crawler/config/peer_institutions.json', 'universities')
    dedupe_config_file('crawler/config/r1_universities.json', 'universities')
    dedupe_config_file('crawler/config/major_facilities.json', 'facilities')

    print("\n" + "=" * 60)
    print("✅ Deduplication complete!")
    print("=" * 60)
    print("\nBackup files created with .bak extension")
    print("Test the crawler, then delete .bak files if satisfied")

if __name__ == '__main__':
    main()
