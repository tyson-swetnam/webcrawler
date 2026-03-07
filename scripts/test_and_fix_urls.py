#!/usr/bin/env python3
"""
Test suggested URLs and automatically update config with working ones.
"""

import json
import subprocess
from pathlib import Path
from datetime import datetime, timezone

config_dir = Path(__file__).parent.parent / "crawler" / "config"
suggestions_path = config_dir / "url_discovery_suggestions.json"
r1_path = config_dir / "r1_universities.json"

def test_url(url: str, timeout: int = 10) -> tuple[bool, int]:
    """Test if URL is accessible. Returns (success, http_code)."""
    try:
        result = subprocess.run(
            ['curl', '-s', '-o', '/dev/null', '-w', '%{http_code}',
             '--max-time', str(timeout), '--location', url],
            capture_output=True,
            text=True,
            timeout=timeout + 2
        )
        http_code = result.stdout.strip()
        if http_code and http_code[0] in ['2', '3']:
            return True, int(http_code)
        return False, int(http_code) if http_code.isdigit() else 0
    except:
        return False, 0

# Load suggestions
with open(suggestions_path, 'r') as f:
    data = json.load(f)

suggestions = data['suggestions']

# Load R1 config
with open(r1_path, 'r') as f:
    r1_config = json.load(f)

# Build index
r1_by_id = {uni['id']: uni for uni in r1_config['universities']}

print("="*80)
print("TESTING SUGGESTED URLs AND AUTO-FIXING")
print("="*80)

fixed_count = 0
tested_count = 0

for s in suggestions[:50]:  # Test first 50 to avoid timeout
    uni_id = s['id']
    uni = r1_by_id.get(uni_id)

    if not uni:
        continue

    print(f"\n[{uni_id}] {s['name']}")
    print(f"  Current (failed): {s['current_url']}")

    # Test each suggested URL
    working_url = None
    for suggested in s['suggested_urls']:
        tested_count += 1
        success, code = test_url(suggested)

        if success:
            print(f"  ✓ WORKS: {suggested} (HTTP {code})")
            working_url = suggested
            break
        else:
            print(f"  ✗ Failed: {suggested}")

    # Update if we found a working URL
    if working_url:
        uni['news_sources']['primary']['url'] = working_url
        uni['news_sources']['primary']['verified'] = True
        uni['news_sources']['primary']['last_verified'] = datetime.now(timezone.utc).isoformat()

        # Also try AI tag URL
        for ai_pattern in ["/topic/artificial-intelligence", "/tag/artificial-intelligence",
                           "/tags/artificial-intelligence"]:
            ai_url = working_url.rstrip('/') + ai_pattern
            success, code = test_url(ai_url)
            if success:
                uni['news_sources']['primary']['ai_tag_url'] = ai_url
                print(f"  ✓ AI Tag: {ai_url}")
                break

        fixed_count += 1

print(f"\n{'='*80}")
print(f"SUMMARY: Tested {tested_count} URLs, fixed {fixed_count} entries")
print(f"{'='*80}")

# Save updated config
if fixed_count > 0:
    r1_config['metadata']['last_updated'] = datetime.now(timezone.utc).isoformat()

    with open(r1_path, 'w', encoding='utf-8') as f:
        json.dump(r1_config, f, indent=2, ensure_ascii=False)
        f.write('\n')

    print(f"\n✓ Updated {r1_path} with {fixed_count} fixes")
else:
    print("\n⚠ No fixes applied")
