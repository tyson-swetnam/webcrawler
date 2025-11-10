#!/usr/bin/env python3
"""
Fix Broken AI Tag URLs in Configuration Files

Based on verification findings, this script:
1. Identifies likely-broken AI tag URLs (patterns like /tag/, ?topic=, /topic/)
2. Replaces them with the base news URL
3. Sets verified=false to indicate manual verification needed
4. Generates a detailed report of all changes
"""

import json
import sys
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Tuple


class AITagURLFixer:
    """Fixes broken AI tag URLs in configuration files."""

    def __init__(self):
        self.config_dir = Path(__file__).parent.parent / "crawler" / "config"
        self.backup_dir = self.config_dir / "backups_before_url_fix"
        self.backup_dir.mkdir(exist_ok=True)

        self.changes = []
        self.stats = {
            "major_facilities": {"total": 0, "fixed": 0, "skipped": 0},
            "peer_institutions": {"total": 0, "fixed": 0, "skipped": 0},
            "r1_universities": {"total": 0, "fixed": 0, "skipped": 0}
        }

        # Patterns that are known to be broken based on verification
        self.broken_patterns = [
            "/tag/artificial-intelligence",
            "?topic=artificial-intelligence",
            "/topic/artificial-intelligence",
            "/tags/artificial-intelligence",
            "/topic/ai",
            "?topic=ai"
        ]

    def is_likely_broken(self, ai_tag_url: str, base_url: str) -> bool:
        """
        Check if an AI tag URL is likely broken based on patterns.

        Returns True if:
        1. URL matches known broken patterns
        2. URL is same as base URL (redundant)
        """
        if not ai_tag_url or ai_tag_url == base_url:
            return False

        # Check for broken patterns
        for pattern in self.broken_patterns:
            if pattern in ai_tag_url:
                return True

        return False

    def fix_institution(self, institution: dict, config_key: str) -> Tuple[dict, bool]:
        """
        Fix AI tag URL for a single institution.

        Returns: (updated_institution, was_changed)
        """
        name = institution.get("name", "Unknown")

        if "news_sources" not in institution or "primary" not in institution["news_sources"]:
            return institution, False

        primary = institution["news_sources"]["primary"]
        base_url = primary.get("url", "")
        ai_tag_url = primary.get("ai_tag_url", "")

        # Check if AI tag URL needs fixing
        if not self.is_likely_broken(ai_tag_url, base_url):
            self.stats[config_key]["skipped"] += 1
            return institution, False

        # Fix the URL
        old_ai_tag_url = ai_tag_url
        primary["ai_tag_url"] = base_url
        primary["verified"] = False

        # Add note about the change
        old_notes = primary.get("notes", "")
        if old_notes and not old_notes.endswith(" - "):
            old_notes += " - "
        primary["notes"] = f"{old_notes}AI tag URL replaced with base URL (was broken: {old_ai_tag_url.split(base_url)[-1] if base_url in old_ai_tag_url else 'different pattern'})"

        # Record the change
        self.changes.append({
            "file": config_key,
            "institution": name,
            "old_ai_tag_url": old_ai_tag_url,
            "new_ai_tag_url": base_url,
            "reason": "Known broken pattern detected"
        })

        self.stats[config_key]["fixed"] += 1
        return institution, True

    def process_file(self, filename: str, config_key: str):
        """Process a single configuration file."""
        print(f"\n{'='*80}")
        print(f"Processing: {filename}")
        print(f"{'='*80}")

        filepath = self.config_dir / filename

        # Backup original file
        backup_path = self.backup_dir / f"{filename}.{datetime.now().strftime('%Y%m%d_%H%M%S')}.bak"
        with open(filepath, 'r') as f:
            original_content = f.read()
        with open(backup_path, 'w') as f:
            f.write(original_content)
        print(f"✓ Backed up to: {backup_path}")

        # Load configuration
        with open(filepath, 'r') as f:
            config = json.load(f)

        # Determine institutions key
        if "facilities" in config:
            institutions_key = "facilities"
        elif "universities" in config:
            institutions_key = "universities"
        else:
            print(f"ERROR: Could not find institutions in {filename}")
            return

        institutions = config[institutions_key]
        self.stats[config_key]["total"] = len(institutions)

        # Process each institution
        changes_made = 0
        for i, institution in enumerate(institutions):
            updated_inst, was_changed = self.fix_institution(institution, config_key)
            config[institutions_key][i] = updated_inst
            if was_changed:
                changes_made += 1

        # Save updated configuration
        with open(filepath, 'w') as f:
            json.dump(config, f, indent=2)

        print(f"\n✓ Processed {len(institutions)} institutions")
        print(f"✓ Fixed {changes_made} AI tag URLs")
        print(f"✓ Saved to: {filepath}")

    def generate_report(self) -> str:
        """Generate a comprehensive report of changes."""
        report = []
        report.append("\n" + "="*80)
        report.append("AI TAG URL FIX REPORT")
        report.append("="*80)
        report.append(f"Generated: {datetime.now().isoformat()}")
        report.append(f"Backup Location: {self.backup_dir}\n")

        # Summary statistics
        total_institutions = sum(s["total"] for s in self.stats.values())
        total_fixed = sum(s["fixed"] for s in self.stats.values())
        total_skipped = sum(s["skipped"] for s in self.stats.values())

        report.append("SUMMARY STATISTICS")
        report.append("-" * 80)
        report.append(f"Total Institutions:     {total_institutions}")
        report.append(f"AI Tag URLs Fixed:      {total_fixed} ({total_fixed/total_institutions*100:.1f}%)")
        report.append(f"URLs Left Unchanged:    {total_skipped} ({total_skipped/total_institutions*100:.1f}%)")
        report.append("")

        # Per-file breakdown
        for config_name, stats in self.stats.items():
            if stats["total"] == 0:
                continue
            report.append(f"\n{config_name.upper().replace('_', ' ')}")
            report.append("-" * 80)
            report.append(f"Total Institutions: {stats['total']}")
            report.append(f"URLs Fixed:         {stats['fixed']}")
            report.append(f"URLs Unchanged:     {stats['skipped']}")

        # Detailed changes
        if self.changes:
            report.append("\n\nDETAILED CHANGES")
            report.append("-" * 80)
            report.append(f"Total Changes: {len(self.changes)}\n")

            for change in self.changes:
                report.append(f"\n{change['institution']} ({change['file']})")
                report.append(f"  OLD: {change['old_ai_tag_url']}")
                report.append(f"  NEW: {change['new_ai_tag_url']}")
                report.append(f"  REASON: {change['reason']}")

        # Next steps
        report.append("\n\nNEXT STEPS")
        report.append("-" * 80)
        report.append("1. Review the changes in the updated JSON files")
        report.append("2. Manually verify the fixed URLs work correctly")
        report.append("3. For institutions that were skipped, manually check if their AI tag URLs work")
        report.append("4. Consider removing AI tag URLs entirely and relying on crawler's AI classification")
        report.append("\nNOTE: All original files have been backed up to:")
        report.append(f"      {self.backup_dir}")

        report.append("\n" + "="*80)
        report.append("END OF REPORT")
        report.append("="*80 + "\n")

        return "\n".join(report)


def main():
    """Main execution."""
    print("="*80)
    print("AI TAG URL FIXER")
    print("="*80)
    print("\nThis script will:")
    print("1. Identify likely-broken AI tag URLs")
    print("2. Replace them with base news URLs")
    print("3. Mark them as unverified for manual review")
    print("4. Create backups of all original files")
    print("\nKnown broken patterns:")
    print("  - /tag/artificial-intelligence")
    print("  - ?topic=artificial-intelligence")
    print("  - /topic/artificial-intelligence")
    print("  - /tags/artificial-intelligence")
    print("="*80)

    response = input("\nProceed with fixing? (yes/no): ")
    if response.lower() not in ['yes', 'y']:
        print("Aborted.")
        return

    fixer = AITagURLFixer()

    # Process each configuration file
    fixer.process_file("major_facilities.json", "major_facilities")
    fixer.process_file("peer_institutions.json", "peer_institutions")
    fixer.process_file("r1_universities.json", "r1_universities")

    # Generate and save report
    report = fixer.generate_report()
    print(report)

    # Save report to file
    report_file = Path(__file__).parent.parent / "AI_TAG_URL_FIX_REPORT.md"
    with open(report_file, 'w') as f:
        f.write(report)
    print(f"\nReport saved to: {report_file}")
    print(f"Backups saved to: {fixer.backup_dir}")


if __name__ == "__main__":
    main()
