#!/usr/bin/env python3
"""
Batch verify URLs and generate verification report.
This script prepares data for manual verification using MCP Fetch tool.
"""

import json
from pathlib import Path
from datetime import datetime, timezone

config_dir = Path(__file__).parent.parent / "crawler" / "config"
urls_file = config_dir / "urls_to_verify.json"

# Load URLs to verify
with open(urls_file, 'r') as f:
    data = json.load(f)

urls = data['urls']

# Filter to unverified URLs only
unverified = [u for u in urls if not u['verified']]

print(f"Total URLs: {len(urls)}")
print(f"Already verified: {len(urls) - len(unverified)}")
print(f"Need verification: {len(unverified)}")

# Generate verification batches for manual processing
batch_size = 20
batches = [unverified[i:i+batch_size] for i in range(0, len(unverified), batch_size)]

print(f"\nURLs split into {len(batches)} batches of up to {batch_size} URLs each")

# Save batches for processing
output_dir = config_dir / "verification_batches"
output_dir.mkdir(exist_ok=True)

for i, batch in enumerate(batches, 1):
    batch_file = output_dir / f"batch_{i:02d}.json"

    batch_data = {
        'batch_number': i,
        'total_batches': len(batches),
        'urls_in_batch': len(batch),
        'urls': batch
    }

    with open(batch_file, 'w', encoding='utf-8') as f:
        json.dump(batch_data, f, indent=2)

print(f"\nBatches saved to: {output_dir}/")
print(f"\nSample of first 10 unverified URLs:")
for u in unverified[:10]:
    print(f"  - {u['name']}: {u['url']}")

# Generate shell script for testing with curl
test_script = output_dir / "test_urls.sh"
with open(test_script, 'w') as f:
    f.write("#!/bin/bash\n")
    f.write("# Quick URL verification test using curl\n\n")

    for i, url_info in enumerate(unverified[:50], 1):  # First 50 only
        url = url_info['url']
        f.write(f'echo "Testing {i}: {url}"\n')
        f.write(f'curl -s -o /dev/null -w "%{{http_code}}" --max-time 10 "{url}" || echo " FAILED"\n')
        f.write('echo ""\n')

test_script.chmod(0o755)
print(f"\nGenerated test script: {test_script}")
print("Run it with: bash", test_script)
