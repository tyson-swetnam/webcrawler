#!/usr/bin/env python3
"""
Test script to verify domain-to-canonical mapping in spider.

This script tests that domains are correctly mapped to canonical university names,
specifically testing the Auburn University case (eng.auburn.edu -> Auburn University).
"""

import sys
import json
from pathlib import Path
from urllib.parse import urlparse


def build_domain_mapping():
    """
    Build domain mapping similar to spider implementation.
    """
    domain_map = {}

    # Load R1 universities
    r1_path = Path("crawler/config/r1_universities.json")
    if r1_path.exists():
        with open(r1_path, 'r') as f:
            data = json.load(f)
            for univ in data.get('universities', []):
                canonical = univ.get('canonical_name', univ.get('name'))

                # Add primary domain
                if 'domains' in univ and 'primary' in univ['domains']:
                    domain_map[univ['domains']['primary']] = canonical

                # Add news domains
                if 'domains' in univ and 'news_domains' in univ['domains']:
                    for domain in univ['domains']['news_domains']:
                        domain_map[domain] = canonical

                # Add domains from news URLs
                if 'news_sources' in univ and 'primary' in univ['news_sources']:
                    url = univ['news_sources']['primary'].get('url')
                    if url:
                        parsed = urlparse(url)
                        domain_map[parsed.netloc] = canonical

                    ai_url = univ['news_sources']['primary'].get('ai_tag_url')
                    if ai_url:
                        parsed = urlparse(ai_url)
                        domain_map[parsed.netloc] = canonical

        print(f"Loaded {len([k for k, v in domain_map.items()])} domains from R1 universities")

    # Load peer institutions
    peer_path = Path("crawler/config/peer_institutions.json")
    if peer_path.exists():
        with open(peer_path, 'r') as f:
            data = json.load(f)
            for univ in data.get('universities', []):
                canonical = univ.get('canonical_name', univ.get('name'))

                # Add domains from news URLs
                if 'news_sources' in univ and 'primary' in univ['news_sources']:
                    url = univ['news_sources']['primary'].get('url')
                    if url:
                        parsed = urlparse(url)
                        domain_map[parsed.netloc] = canonical

                    ai_url = univ['news_sources']['primary'].get('ai_tag_url')
                    if ai_url:
                        parsed = urlparse(ai_url)
                        domain_map[parsed.netloc] = canonical

        print(f"Loaded domains from {len(data.get('universities', []))} peer institutions")

    # Load major facilities
    facilities_path = Path("crawler/config/major_facilities.json")
    if facilities_path.exists():
        with open(facilities_path, 'r') as f:
            data = json.load(f)
            for facility in data.get('facilities', []):
                canonical = facility.get('name')

                # Add domains from news URLs
                if 'news_sources' in facility and 'primary' in facility['news_sources']:
                    url = facility['news_sources']['primary'].get('url')
                    if url:
                        parsed = urlparse(url)
                        domain_map[parsed.netloc] = canonical

                    ai_url = facility['news_sources']['primary'].get('ai_tag_url')
                    if ai_url:
                        parsed = urlparse(ai_url)
                        domain_map[parsed.netloc] = canonical

        print(f"Loaded domains from {len(data.get('facilities', []))} major facilities")

    return domain_map


def get_canonical_name(domain_map, hostname, sitename=None):
    """
    Get canonical name for a hostname (mimics spider logic).
    """
    # Direct lookup
    if hostname in domain_map:
        return domain_map[hostname]

    # Try removing 'www.' prefix
    if hostname.startswith('www.'):
        without_www = hostname[4:]
        if without_www in domain_map:
            return domain_map[without_www]

    # Try parent domain (e.g., 'eng.auburn.edu' -> 'auburn.edu')
    parts = hostname.split('.')
    if len(parts) > 2:
        parent_domain = '.'.join(parts[-2:])
        if parent_domain in domain_map:
            return domain_map[parent_domain]

    # No mapping found, use sitename as fallback
    if sitename:
        return sitename

    # Last resort: use hostname
    return hostname


def test_auburn_mapping():
    """
    Test that Auburn University domains are correctly mapped.
    """
    print("\n" + "="*70)
    print("Testing Auburn University Domain Mapping")
    print("="*70 + "\n")

    domain_map = build_domain_mapping()

    # Test cases
    test_cases = [
        ("eng.auburn.edu", "AuburnEngineers", "Auburn University"),
        ("news.auburnuniversity.edu", "Auburn News", "Auburn University"),
        ("auburnuniversity.edu", "Auburn", "Auburn University"),
        ("news.arizona.edu", "Arizona News", "University of Arizona"),
        ("www.tacc.utexas.edu", "TACC", "Texas Advanced Computing Center"),
    ]

    print("Testing domain-to-canonical mappings:\n")

    all_passed = True
    for hostname, sitename, expected_canonical in test_cases:
        canonical = get_canonical_name(domain_map, hostname, sitename)
        passed = canonical == expected_canonical
        all_passed = all_passed and passed

        status = "PASS" if passed else "FAIL"
        print(f"[{status}] {hostname}")
        print(f"      Sitename: {sitename}")
        print(f"      Expected: {expected_canonical}")
        print(f"      Got:      {canonical}")
        print()

    # Print Auburn-specific mappings
    print("\nAuburn University domains in mapping:")
    auburn_domains = {k: v for k, v in domain_map.items() if 'auburn' in k.lower()}
    for domain, canonical in sorted(auburn_domains.items()):
        print(f"  {domain} -> {canonical}")

    print("\n" + "="*70)
    if all_passed:
        print("ALL TESTS PASSED")
        return 0
    else:
        print("SOME TESTS FAILED")
        return 1


if __name__ == '__main__':
    sys.exit(test_auburn_mapping())
