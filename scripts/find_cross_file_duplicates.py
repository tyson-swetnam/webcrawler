#!/usr/bin/env python3
"""Find duplicate universities across different config files."""

import json
from pathlib import Path
from collections import defaultdict

config_dir = Path(__file__).parent.parent / "crawler" / "config"

# Load all config files
configs = {
    'r1': config_dir / "r1_universities.json",
    'peer': config_dir / "peer_institutions.json",
    'facilities': config_dir / "major_facilities.json"
}

# Track all canonical names
all_entries = defaultdict(list)

for config_name, config_path in configs.items():
    if not config_path.exists():
        continue

    with open(config_path, 'r') as f:
        data = json.load(f)

    items_key = 'universities' if 'universities' in data else 'facilities'
    items = data.get(items_key, [])

    for item in items:
        canonical = item.get('canonical_name', item.get('name', '')).strip()
        if canonical:
            all_entries[canonical].append({
                'file': config_name,
                'id': item.get('id'),
                'urls': item.get('news_sources', {}).get('primary', {}).get('url', ''),
                'ai_url': item.get('news_sources', {}).get('primary', {}).get('ai_tag_url', '')
            })

# Find cross-file duplicates
duplicates = {k: v for k, v in all_entries.items() if len(v) > 1}

print(f"Found {len(duplicates)} universities appearing in multiple config files:\n")

for name, entries in sorted(duplicates.items()):
    print(f"📍 {name}")
    for entry in entries:
        print(f"   - File: {entry['file']:12} ID: {entry['id']:3}  URL: {entry['urls']}")
        if entry['ai_url']:
            print(f"     AI URL: {entry['ai_url']}")
    print()
