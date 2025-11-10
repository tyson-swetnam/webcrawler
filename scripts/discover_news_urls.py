#!/usr/bin/env python3
"""
Discover correct news URLs for universities with failed verification.

This script generates a manual review list with suggested URLs based on:
1. University domains from their primary domain field
2. Common news site patterns
3. Manual lookup suggestions
"""

import json
from pathlib import Path
from urllib.parse import urlparse

config_dir = Path(__file__).parent.parent / "crawler" / "config"
failed_report_path = config_dir / "failed_urls_report.json"
r1_path = config_dir / "r1_universities.json"

# Common news site URL patterns
NEWS_PATTERNS = [
    "https://{domain}/news",
    "https://news.{domain}",
    "https://{domain}/newsroom",
    "https://today.{domain}",
    "https://{domain}/about/news",
    "https://www.{domain}/news",
]

AI_TAG_PATTERNS = [
    "/topic/artificial-intelligence",
    "/tag/artificial-intelligence",
    "/tags/artificial-intelligence",
    "/category/artificial-intelligence",
    "/news/topic/artificial-intelligence",
]

# Load failed URLs
with open(failed_report_path, 'r') as f:
    failed_data = json.load(f)

failed_urls = failed_data['failed_urls']

# Load R1 config to get domain information
with open(r1_path, 'r') as f:
    r1_config = json.load(f)

# Build index by ID
r1_by_id = {uni['id']: uni for uni in r1_config['universities']}

# Generate discovery suggestions
suggestions = []

for failed in failed_urls:
    if failed['config'] != 'r1_universities.json':
        continue

    uni_id = failed['id']
    uni = r1_by_id.get(uni_id)

    if not uni:
        continue

    name = uni['canonical_name']
    domain_info = uni.get('domains', {})
    primary_domain = domain_info.get('primary', '')

    # Skip if already has correct domain
    if not primary_domain or 'universityof.edu' in primary_domain:
        continue

    # Generate suggestions
    suggested_urls = []
    for pattern in NEWS_PATTERNS:
        url = pattern.format(domain=primary_domain)
        suggested_urls.append(url)

    suggestions.append({
        'id': uni_id,
        'name': name,
        'current_url': failed['url'],
        'error': failed['error'],
        'primary_domain': primary_domain,
        'suggested_urls': suggested_urls,
        'ai_tag_suggestions': [
            suggested_urls[0] + pattern for pattern in AI_TAG_PATTERNS
        ] if suggested_urls else []
    })

# Save suggestions
suggestions_path = config_dir / "url_discovery_suggestions.json"
with open(suggestions_path, 'w', encoding='utf-8') as f:
    json.dump({
        'total_failed': len(failed_urls),
        'r1_failures': len(suggestions),
        'suggestions': suggestions
    }, f, indent=2)

print(f"Generated {len(suggestions)} URL discovery suggestions")
print(f"Saved to: {suggestions_path}")

# Print sample
print("\nSample suggestions (first 10):")
for s in suggestions[:10]:
    print(f"\n{s['id']}. {s['name']}")
    print(f"   Domain: {s['primary_domain']}")
    print(f"   Current (failed): {s['current_url']}")
    print(f"   Suggested:")
    for url in s['suggested_urls'][:3]:
        print(f"     - {url}")
