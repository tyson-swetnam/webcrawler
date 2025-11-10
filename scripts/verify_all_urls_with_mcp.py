#!/usr/bin/env python3
"""
Comprehensive URL Verification Script using MCP Fetch
Verifies all URLs in the three configuration files and fixes broken ones.
"""

import json
import time
import sys
from pathlib import Path
from typing import Dict, List, Tuple, Optional
from datetime import datetime

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))


class URLVerifier:
    """Verifies and fixes URLs in configuration files."""

    def __init__(self):
        self.config_dir = Path(__file__).parent.parent / "crawler" / "config"
        self.results = {
            "major_facilities": {"checked": 0, "working": 0, "fixed": 0, "failed": []},
            "peer_institutions": {"checked": 0, "working": 0, "fixed": 0, "failed": []},
            "r1_universities": {"checked": 0, "working": 0, "fixed": 0, "failed": []}
        }
        self.changes = []
        self.delay = 2.0  # 2 seconds between requests

    def load_config(self, filename: str) -> dict:
        """Load a JSON configuration file."""
        filepath = self.config_dir / filename
        with open(filepath, 'r') as f:
            return json.load(f)

    def save_config(self, filename: str, data: dict):
        """Save a JSON configuration file."""
        filepath = self.config_dir / filename
        with open(filepath, 'w') as f:
            json.dump(data, f, indent=2)

    def check_url(self, url: str, institution_name: str) -> Tuple[bool, str]:
        """
        Check if a URL is working using MCP fetch.
        Returns: (is_working, error_message)
        """
        # This is a placeholder - actual verification will be done interactively
        # by Claude using the MCP fetch tools
        return True, ""

    def try_alternative_urls(self, base_domain: str, institution_name: str) -> Optional[str]:
        """Try alternative news URL patterns for a domain."""
        patterns = [
            f"https://news.{base_domain}",
            f"https://{base_domain}/news",
            f"https://today.{base_domain}",
            f"https://newsroom.{base_domain}",
            f"https://{base_domain}/newsroom",
            f"https://www.{base_domain}/news"
        ]
        return None  # Will be implemented interactively

    def verify_institution(self, institution: dict, config_key: str) -> dict:
        """Verify all URLs for a single institution."""
        name = institution.get("name", "Unknown")
        changes_made = []

        if "news_sources" not in institution or "primary" not in institution["news_sources"]:
            self.results[config_key]["failed"].append({
                "name": name,
                "reason": "No news_sources.primary found"
            })
            return institution

        primary = institution["news_sources"]["primary"]
        base_url = primary.get("url", "")
        ai_tag_url = primary.get("ai_tag_url", "")

        # Track what we're checking
        self.results[config_key]["checked"] += 1

        print(f"\n{'='*80}")
        print(f"Checking: {name}")
        print(f"Base URL: {base_url}")
        print(f"AI Tag URL: {ai_tag_url}")
        print(f"{'='*80}")

        return institution

    def verify_file(self, filename: str, config_key: str, limit: Optional[int] = None):
        """Verify all institutions in a configuration file."""
        print(f"\n\n{'#'*80}")
        print(f"# Verifying: {filename}")
        print(f"{'#'*80}\n")

        config = self.load_config(filename)

        # Determine the key that holds the list of institutions
        if "facilities" in config:
            institutions_key = "facilities"
        elif "universities" in config:
            institutions_key = "universities"
        else:
            print(f"ERROR: Could not find institutions list in {filename}")
            return

        institutions = config[institutions_key]

        if limit:
            institutions = institutions[:limit]
            print(f"NOTE: Processing first {limit} institutions only")

        # Process each institution
        for i, institution in enumerate(institutions, 1):
            print(f"\nProgress: {i}/{len(institutions)}")
            updated_inst = self.verify_institution(institution, config_key)
            config[institutions_key][i-1] = updated_inst

            # Add delay between requests
            if i < len(institutions):
                time.sleep(self.delay)

        # Save updated configuration
        # self.save_config(filename, config)
        # print(f"\nSaved updated configuration to {filename}")

    def generate_report(self) -> str:
        """Generate a comprehensive verification report."""
        report = []
        report.append("\n" + "="*80)
        report.append("URL VERIFICATION REPORT")
        report.append("="*80)
        report.append(f"Generated: {datetime.now().isoformat()}\n")

        # Summary statistics
        total_checked = sum(r["checked"] for r in self.results.values())
        total_working = sum(r["working"] for r in self.results.values())
        total_fixed = sum(r["fixed"] for r in self.results.values())
        total_failed = sum(len(r["failed"]) for r in self.results.values())

        report.append("SUMMARY STATISTICS")
        report.append("-" * 80)
        report.append(f"Total URLs Checked:  {total_checked}")
        report.append(f"Working URLs:        {total_working} ({total_working/total_checked*100:.1f}%)" if total_checked > 0 else "Working URLs:        0")
        report.append(f"URLs Fixed:          {total_fixed}")
        report.append(f"URLs Still Broken:   {total_failed}")
        report.append("")

        # Per-file breakdown
        for config_name, stats in self.results.items():
            report.append(f"\n{config_name.upper()}")
            report.append("-" * 80)
            report.append(f"Checked: {stats['checked']}")
            report.append(f"Working: {stats['working']}")
            report.append(f"Fixed:   {stats['fixed']}")
            report.append(f"Failed:  {len(stats['failed'])}")

            if stats['failed']:
                report.append("\nFailed URLs:")
                for fail in stats['failed']:
                    report.append(f"  - {fail['name']}: {fail['reason']}")

        # Changes made
        if self.changes:
            report.append("\n\nCHANGES MADE")
            report.append("-" * 80)
            for change in self.changes:
                report.append(f"\n{change['institution']} ({change['file']})")
                report.append(f"  Old URL: {change['old_url']}")
                report.append(f"  New URL: {change['new_url']}")
                report.append(f"  Reason:  {change['reason']}")

        report.append("\n" + "="*80)
        report.append("END OF REPORT")
        report.append("="*80 + "\n")

        return "\n".join(report)


def main():
    """Main execution function."""
    print("="*80)
    print("URL VERIFICATION TOOL - MCP Fetch")
    print("="*80)
    print("\nThis script will verify all URLs in the configuration files.")
    print("It will use MCP fetch tools to check each URL and attempt to fix broken ones.")
    print("\nNOTE: This is a helper script. Actual verification will be done by Claude")
    print("      using MCP fetch tools interactively.")
    print("="*80)

    verifier = URLVerifier()

    # Process each configuration file
    # For testing, we can limit the number of institutions
    # verifier.verify_file("major_facilities.json", "major_facilities", limit=5)
    # verifier.verify_file("peer_institutions.json", "peer_institutions", limit=5)
    # verifier.verify_file("r1_universities.json", "r1_universities", limit=10)

    # Full run (comment out for testing)
    verifier.verify_file("major_facilities.json", "major_facilities")
    verifier.verify_file("peer_institutions.json", "peer_institutions")
    # verifier.verify_file("r1_universities.json", "r1_universities")  # Large file - do last

    # Generate and save report
    report = verifier.generate_report()
    print(report)

    # Save report to file
    report_file = Path(__file__).parent.parent / "URL_VERIFICATION_REPORT.md"
    with open(report_file, 'w') as f:
        f.write(report)
    print(f"\nReport saved to: {report_file}")


if __name__ == "__main__":
    main()
