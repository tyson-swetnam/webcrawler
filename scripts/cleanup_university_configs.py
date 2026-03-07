#!/usr/bin/env python3
"""
Clean up and verify university news source configurations.

This script performs three phases:
1. De-duplication: Merge duplicate university entries
2. URL Verification: Test all URLs with Fetch MCP
3. Discovery: Find real URLs for placeholder entries
"""

import json
import sys
from pathlib import Path
from collections import defaultdict
from datetime import datetime, timezone
from typing import Dict, List, Tuple, Set

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))


class UniversityConfigCleaner:
    """Clean and verify university news configurations."""

    def __init__(self):
        self.config_dir = project_root / "crawler" / "config"
        self.r1_path = self.config_dir / "r1_universities.json"
        self.peer_path = self.config_dir / "peer_institutions.json"
        self.facilities_path = self.config_dir / "major_facilities.json"

        self.stats = {
            "duplicates_found": 0,
            "duplicates_merged": 0,
            "urls_verified": 0,
            "urls_failed": 0,
            "placeholders_found": 0,
            "placeholders_fixed": 0,
        }

        self.issues = []

    def load_config(self, path: Path) -> Dict:
        """Load a JSON configuration file."""
        with open(path, 'r', encoding='utf-8') as f:
            return json.load(f)

    def save_config(self, path: Path, data: Dict):
        """Save configuration with proper formatting."""
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
            f.write('\n')  # Add trailing newline

    def find_duplicates(self, config: Dict, config_name: str) -> Dict[str, List[Dict]]:
        """Find duplicate entries by canonical_name."""
        duplicates = defaultdict(list)

        # Handle both 'universities' and 'facilities' keys
        items_key = 'universities' if 'universities' in config else 'facilities'
        items = config.get(items_key, [])

        for item in items:
            canonical = item.get('canonical_name', item.get('name', '')).strip()
            if canonical:
                duplicates[canonical].append(item)

        # Filter to only actual duplicates (2+ entries)
        return {k: v for k, v in duplicates.items() if len(v) > 1}

    def merge_duplicate_entry(self, entries: List[Dict]) -> Dict:
        """Merge duplicate entries, preserving all URLs."""
        # Start with first entry as base
        merged = entries[0].copy()

        # Collect all unique URLs
        primary_urls = set()
        ai_tag_urls = set()
        additional_sources = []

        for entry in entries:
            news_sources = entry.get('news_sources', {})
            primary = news_sources.get('primary', {})

            if primary.get('url'):
                primary_urls.add(primary['url'])
            if primary.get('ai_tag_url'):
                ai_tag_urls.add(primary['ai_tag_url'])

            # Collect any additional sources
            if 'additional_sources' in news_sources:
                additional_sources.extend(news_sources['additional_sources'])

        # Build merged news_sources
        primary_urls_list = sorted(list(primary_urls))
        ai_tag_urls_list = sorted(list(ai_tag_urls))

        if primary_urls_list:
            merged['news_sources'] = {
                'primary': {
                    'url': primary_urls_list[0],
                    'ai_tag_url': ai_tag_urls_list[0] if ai_tag_urls_list else None,
                    'verified': entries[0].get('news_sources', {}).get('primary', {}).get('verified', False),
                    'crawl_priority': max(
                        e.get('news_sources', {}).get('primary', {}).get('crawl_priority', 100)
                        for e in entries
                    )
                }
            }

            # Add alternate URLs if there are multiple
            if len(primary_urls_list) > 1 or len(ai_tag_urls_list) > 1:
                alternates = []
                for url in primary_urls_list[1:]:
                    alternates.append({'url': url, 'type': 'general_news'})
                for url in ai_tag_urls_list[1:]:
                    alternates.append({'url': url, 'type': 'ai_specific'})

                if alternates:
                    merged['news_sources']['additional_sources'] = alternates

        # Use highest verification status
        merged['news_sources']['primary']['verified'] = any(
            e.get('news_sources', {}).get('primary', {}).get('verified', False)
            for e in entries
        )

        return merged

    def phase1_deduplicate(self):
        """Phase 1: Find and merge duplicate entries."""
        print("\n" + "="*80)
        print("PHASE 1: DE-DUPLICATION")
        print("="*80)

        for config_path, config_name in [
            (self.r1_path, "R1 Universities"),
            (self.peer_path, "Peer Institutions"),
            (self.facilities_path, "Major Facilities")
        ]:
            print(f"\nProcessing: {config_name}")
            config = self.load_config(config_path)

            # Find duplicates
            duplicates = self.find_duplicates(config, config_name)

            if not duplicates:
                print(f"  No duplicates found in {config_name}")
                continue

            print(f"  Found {len(duplicates)} duplicate university names:")
            for name, entries in duplicates.items():
                print(f"    - {name}: {len(entries)} entries")
                self.stats['duplicates_found'] += len(entries) - 1

            # Merge duplicates
            items_key = 'universities' if 'universities' in config else 'facilities'
            items = config[items_key]

            # Build mapping of canonical names to merged entries
            merged_entries = {}
            for name, entries in duplicates.items():
                merged = self.merge_duplicate_entry(entries)
                merged_entries[name] = merged
                self.stats['duplicates_merged'] += 1

            # Rebuild items list, keeping one merged entry per duplicate
            seen_canonical = set()
            new_items = []

            for item in items:
                canonical = item.get('canonical_name', item.get('name', '')).strip()

                if canonical in merged_entries and canonical not in seen_canonical:
                    # Add merged entry
                    new_items.append(merged_entries[canonical])
                    seen_canonical.add(canonical)
                    print(f"    ✓ Merged: {canonical}")
                elif canonical not in merged_entries:
                    # Not a duplicate, keep as-is
                    new_items.append(item)
                # else: skip additional duplicate entries

            # Update config
            config[items_key] = new_items
            config['metadata']['total_institutions'] = len(new_items)
            config['metadata']['last_updated'] = datetime.now(timezone.utc).isoformat()

            # Save
            self.save_config(config_path, config)
            print(f"  ✓ Updated {config_name}: {len(items)} → {len(new_items)} entries")

        print(f"\n✓ Phase 1 Complete: Found {self.stats['duplicates_found']} duplicates, merged into {self.stats['duplicates_merged']} entries")

    def find_placeholder_urls(self, config: Dict) -> List[Tuple[int, str, str]]:
        """Find entries with placeholder URLs (universityof.edu pattern)."""
        placeholders = []
        items_key = 'universities' if 'universities' in config else 'facilities'
        items = config.get(items_key, [])

        for item in items:
            news_sources = item.get('news_sources', {})
            primary = news_sources.get('primary', {})
            url = primary.get('url', '')

            # Check for placeholder patterns
            if ('universityof.edu' in url.lower() or
                url == '' or
                'placeholder' in url.lower() or
                'example.com' in url.lower()):
                placeholders.append((
                    item.get('id'),
                    item.get('canonical_name', item.get('name')),
                    url
                ))

        return placeholders

    def phase3_discover_placeholders(self):
        """Phase 3: Find and update placeholder URLs."""
        print("\n" + "="*80)
        print("PHASE 3: DISCOVER PLACEHOLDER URLs")
        print("="*80)

        # Only check R1 universities for now (peer and facilities should be clean)
        config = self.load_config(self.r1_path)

        placeholders = self.find_placeholder_urls(config)
        self.stats['placeholders_found'] = len(placeholders)

        if not placeholders:
            print("  ✓ No placeholder URLs found")
            return

        print(f"\nFound {len(placeholders)} placeholder URLs in R1 Universities:")
        for item_id, name, url in placeholders:
            print(f"  - [{item_id}] {name}: {url}")
            self.issues.append({
                'type': 'placeholder_url',
                'university': name,
                'current_url': url,
                'status': 'needs_manual_discovery'
            })

        print(f"\n⚠ {len(placeholders)} universities need manual URL discovery")
        print("  These will be logged in the final report for manual review.")

    def generate_report(self):
        """Generate final summary report."""
        print("\n" + "="*80)
        print("CLEANUP SUMMARY REPORT")
        print("="*80)

        print(f"\nPhase 1 - De-duplication:")
        print(f"  Duplicates found: {self.stats['duplicates_found']}")
        print(f"  Duplicates merged: {self.stats['duplicates_merged']}")

        print(f"\nPhase 2 - URL Verification:")
        print(f"  URLs verified: {self.stats['urls_verified']}")
        print(f"  URLs failed: {self.stats['urls_failed']}")
        print(f"  (Verification delegated to MCP Fetch tool)")

        print(f"\nPhase 3 - Placeholder Discovery:")
        print(f"  Placeholders found: {self.stats['placeholders_found']}")
        print(f"  Placeholders fixed: {self.stats['placeholders_fixed']}")

        if self.issues:
            print(f"\nIssues Requiring Manual Review ({len(self.issues)}):")
            for issue in self.issues:
                print(f"  - [{issue['type']}] {issue['university']}")
                if issue.get('current_url'):
                    print(f"    Current URL: {issue['current_url']}")
                if issue.get('error'):
                    print(f"    Error: {issue['error']}")

        # Save detailed report
        report_path = self.config_dir / "cleanup_report.json"
        report = {
            'timestamp': datetime.now(timezone.utc).isoformat(),
            'statistics': self.stats,
            'issues': self.issues
        }

        with open(report_path, 'w', encoding='utf-8') as f:
            json.dump(report, f, indent=2, ensure_ascii=False)

        print(f"\n✓ Detailed report saved to: {report_path}")

    def run(self):
        """Run all cleanup phases."""
        try:
            self.phase1_deduplicate()
            print("\n⚠ Phase 2 (URL Verification) will be handled by Claude using MCP Fetch tool")
            self.phase3_discover_placeholders()
            self.generate_report()

            print("\n" + "="*80)
            print("✓ CLEANUP COMPLETE")
            print("="*80)
            print("\nNext Steps:")
            print("1. Use MCP Fetch tool to verify all URLs in config files")
            print("2. Manually discover URLs for placeholder entries")
            print("3. Review cleanup_report.json for issues")

        except Exception as e:
            print(f"\n✗ Error during cleanup: {e}")
            import traceback
            traceback.print_exc()
            return 1

        return 0


if __name__ == '__main__':
    cleaner = UniversityConfigCleaner()
    sys.exit(cleaner.run())
