#!/usr/bin/env python3
"""
De-duplicate universities appearing in multiple config files.

Strategy:
- Keep entries in R1 Universities (canonical source for all R1 schools)
- Merge URLs from peer_institutions into R1 entries as additional_sources
- Remove duplicates from peer_institutions
- Update peer_institutions metadata to reflect changes
"""

import json
from pathlib import Path
from datetime import datetime, timezone
from collections import defaultdict

config_dir = Path(__file__).parent.parent / "crawler" / "config"

r1_path = config_dir / "r1_universities.json"
peer_path = config_dir / "peer_institutions.json"

print("="*80)
print("CROSS-FILE DE-DUPLICATION")
print("="*80)

# Load both configs
with open(r1_path, 'r') as f:
    r1_config = json.load(f)

with open(peer_path, 'r') as f:
    peer_config = json.load(f)

# Build index of R1 universities by canonical name
r1_index = {}
for uni in r1_config['universities']:
    canonical = uni.get('canonical_name', '').strip()
    if canonical:
        r1_index[canonical] = uni

# Find duplicates and merge URLs
duplicates_found = []
universities_to_remove = []

for peer_uni in peer_config['universities']:
    canonical = peer_uni.get('canonical_name', '').strip()

    if canonical in r1_index:
        duplicates_found.append(canonical)
        r1_uni = r1_index[canonical]

        # Get URLs from both sources
        r1_primary = r1_uni.get('news_sources', {}).get('primary', {})
        peer_primary = peer_uni.get('news_sources', {}).get('primary', {})

        r1_url = r1_primary.get('url', '')
        r1_ai_url = r1_primary.get('ai_tag_url', '')
        peer_url = peer_primary.get('url', '')
        peer_ai_url = peer_primary.get('ai_tag_url', '')

        # Collect unique URLs
        all_urls = set()
        all_ai_urls = set()

        if r1_url:
            all_urls.add(r1_url)
        if peer_url and peer_url != r1_url:
            all_urls.add(peer_url)
        if r1_ai_url:
            all_ai_urls.add(r1_ai_url)
        if peer_ai_url and peer_ai_url != r1_ai_url:
            all_ai_urls.add(peer_ai_url)

        print(f"\n📍 {canonical}")
        print(f"   R1 URL:   {r1_url}")
        print(f"   R1 AI:    {r1_ai_url}")
        print(f"   Peer URL: {peer_url}")
        print(f"   Peer AI:  {peer_ai_url}")

        # Decide which URLs to use as primary
        # Priority: Use peer URLs if verified, otherwise keep R1
        use_peer_as_primary = peer_primary.get('verified', False) and not r1_primary.get('verified', False)

        if use_peer_as_primary:
            r1_uni['news_sources']['primary']['url'] = peer_url
            r1_uni['news_sources']['primary']['ai_tag_url'] = peer_ai_url
            r1_uni['news_sources']['primary']['verified'] = True
            r1_uni['news_sources']['primary']['crawl_priority'] = peer_primary.get('crawl_priority', 150)
            print(f"   ✓ Updated primary URL from peer (verified)")

            # Add old R1 URLs as alternates if different
            if r1_url and r1_url != peer_url:
                additional = r1_uni['news_sources'].get('additional_sources', [])
                additional.append({
                    'url': r1_url,
                    'type': 'alternate_news',
                    'verified': False
                })
                r1_uni['news_sources']['additional_sources'] = additional
                print(f"   ✓ Added R1 URL as alternate")

        else:
            # Keep R1 as primary, add peer URLs as alternates if different
            if peer_url and peer_url != r1_url:
                additional = r1_uni['news_sources'].get('additional_sources', [])
                additional.append({
                    'url': peer_url,
                    'type': 'alternate_news',
                    'verified': peer_primary.get('verified', False)
                })
                if peer_ai_url and peer_ai_url != r1_ai_url:
                    additional.append({
                        'url': peer_ai_url,
                        'type': 'ai_specific',
                        'verified': peer_primary.get('verified', False)
                    })
                r1_uni['news_sources']['additional_sources'] = additional
                print(f"   ✓ Added peer URLs as alternates")

        # Mark for removal from peer institutions
        universities_to_remove.append(peer_uni['id'])

print(f"\n\nSummary:")
print(f"  - Found {len(duplicates_found)} duplicate universities")
print(f"  - Merged URLs into R1 entries")
print(f"  - Removing {len(universities_to_remove)} entries from peer_institutions")

# Remove duplicates from peer institutions
original_peer_count = len(peer_config['universities'])
peer_config['universities'] = [
    uni for uni in peer_config['universities']
    if uni['id'] not in universities_to_remove
]
new_peer_count = len(peer_config['universities'])

print(f"  - Peer institutions: {original_peer_count} → {new_peer_count}")

# Update metadata
r1_config['metadata']['last_updated'] = datetime.now(timezone.utc).isoformat()
peer_config['metadata']['last_updated'] = datetime.now(timezone.utc).isoformat()
peer_config['metadata']['total_institutions'] = new_peer_count

# Add de-duplication note
if 'quality_notes' not in peer_config['metadata']:
    peer_config['metadata']['quality_notes'] = []
elif isinstance(peer_config['metadata']['quality_notes'], str):
    peer_config['metadata']['quality_notes'] = [peer_config['metadata']['quality_notes']]

peer_config['metadata']['quality_notes'].append(
    f"Removed {len(universities_to_remove)} R1 duplicates on {datetime.now(timezone.utc).date().isoformat()}"
)

# Save updated configs
print("\nSaving updated configurations...")

with open(r1_path, 'w', encoding='utf-8') as f:
    json.dump(r1_config, f, indent=2, ensure_ascii=False)
    f.write('\n')

with open(peer_path, 'w', encoding='utf-8') as f:
    json.dump(peer_config, f, indent=2, ensure_ascii=False)
    f.write('\n')

print(f"✓ Updated: {r1_path}")
print(f"✓ Updated: {peer_path}")

print("\n" + "="*80)
print("✓ CROSS-FILE DE-DUPLICATION COMPLETE")
print("="*80)

print("\nDuplicates removed from peer_institutions.json:")
for name in duplicates_found:
    print(f"  - {name}")
