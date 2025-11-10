#!/usr/bin/env python3
"""Collect all URLs from config files that need verification."""

import json
from pathlib import Path

config_dir = Path(__file__).parent.parent / "crawler" / "config"

configs = {
    'r1_universities.json': 'universities',
    'peer_institutions.json': 'universities',
    'major_facilities.json': 'facilities'
}

all_urls = []

for config_file, items_key in configs.items():
    config_path = config_dir / config_file
    if not config_path.exists():
        continue

    with open(config_path, 'r') as f:
        data = json.load(f)

    items = data.get(items_key, [])

    for item in items:
        news_sources = item.get('news_sources', {})
        primary = news_sources.get('primary', {})

        canonical_name = item.get('canonical_name', item.get('name', 'Unknown'))
        url = primary.get('url', '')
        ai_url = primary.get('ai_tag_url', '')
        verified = primary.get('verified', False)

        # Skip placeholder URLs
        if url and 'universityof.edu' not in url.lower():
            all_urls.append({
                'source': config_file,
                'name': canonical_name,
                'id': item.get('id'),
                'url': url,
                'type': 'primary',
                'verified': verified
            })

        if ai_url and 'universityof.edu' not in ai_url.lower():
            all_urls.append({
                'source': config_file,
                'name': canonical_name,
                'id': item.get('id'),
                'url': ai_url,
                'type': 'ai_tag',
                'verified': verified
            })

# Save to JSON for processing
output = {
    'total_urls': len(all_urls),
    'urls': all_urls
}

output_path = config_dir / 'urls_to_verify.json'
with open(output_path, 'w', encoding='utf-8') as f:
    json.dump(output, f, indent=2)

print(f"Collected {len(all_urls)} URLs for verification")
print(f"Saved to: {output_path}")

# Print summary by source
from collections import Counter
by_source = Counter(u['source'] for u in all_urls)
print("\nURLs by source:")
for source, count in sorted(by_source.items()):
    print(f"  {source}: {count}")

# Print verification status
verified_count = sum(1 for u in all_urls if u['verified'])
unverified_count = len(all_urls) - verified_count
print(f"\nVerification status:")
print(f"  Verified: {verified_count}")
print(f"  Unverified: {unverified_count}")
