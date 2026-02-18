#!/usr/bin/env python3
"""
URL Correction Script for University News Crawler

Applies corrections in tiered order:
1. Batch corrections from batch_6_corrections.json
2. Legacy news_url field migration
3. Cross-reference peer institutions
4. Candidate URL probing
5. Manual review queue for remaining

Usage:
    python scripts/fix_university_urls.py --dry-run
    python scripts/fix_university_urls.py
    python scripts/fix_university_urls.py --tier 1  # Only apply tier 1
"""

import argparse
import asyncio
import json
import re
import socket
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse

import httpx

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

CONFIG_DIR = PROJECT_ROOT / "crawler" / "config"

# Placeholder domain patterns (same as test script)
PLACEHOLDER_PATTERNS = [
    r"universityof\.edu",
    r"universityat\.edu",
    r"theuniversity\.edu",
    r"stateuniversity\.edu",
    r"university-main\.edu",
]


def load_json(filepath: Path) -> dict:
    with open(filepath, "r") as f:
        return json.load(f)


def save_json(filepath: Path, data: dict):
    with open(filepath, "w") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
        f.write("\n")  # trailing newline


def is_placeholder(url: str) -> bool:
    if not url:
        return True
    url_lower = url.lower()
    for pattern in PLACEHOLDER_PATTERNS:
        if re.search(pattern, url_lower):
            return True
    if "&" in urlparse(url).netloc:
        return True
    return False


def get_primary_source(entry: dict) -> Optional[dict]:
    """Get the primary news_source from an entry."""
    news_sources = entry.get("news_sources", [])
    if isinstance(news_sources, list):
        for ns in news_sources:
            if ns.get("type") == "primary":
                return ns
        if news_sources:
            return news_sources[0]
    return None


def normalize_name(name: str) -> str:
    """Normalize institution name for matching."""
    name = name.lower().strip()
    name = re.sub(r"^the\s+", "", name)
    name = re.sub(r"\s+", " ", name)
    return name


async def check_url(url: str, timeout: int = 15, client: httpx.AsyncClient = None) -> dict:
    """Check if a URL is reachable. Returns dict with status info."""
    try:
        headers = {
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        }
        if client:
            resp = await client.get(url, follow_redirects=True)
        else:
            async with httpx.AsyncClient(
                headers=headers, timeout=httpx.Timeout(timeout), verify=False
            ) as c:
                resp = await c.get(url, follow_redirects=True)
        body = ""
        if resp.status_code == 200:
            try:
                body = resp.text[:5000]
            except Exception:
                pass
        return {
            "status": resp.status_code,
            "final_url": str(resp.url),
            "working": resp.status_code == 200,
            "body_snippet": body,
        }
    except Exception as e:
        return {"status": None, "working": False, "error": str(e)[:200]}


def apply_update(source: dict, new_url: str, tier: str, dry_run: bool) -> dict:
    """Apply a URL update to a news_source entry. Returns change record."""
    old_url = source.get("url", "")
    change = {
        "old_url": old_url,
        "new_url": new_url,
        "tier": tier,
        "applied": not dry_run,
    }
    if not dry_run:
        source["url"] = new_url
        source["verified"] = True
        source["last_verified"] = datetime.now(timezone.utc).isoformat()
    return change


class URLFixer:
    def __init__(self, dry_run: bool = True, max_tier: int = 5, timeout: int = 15, concurrency: int = 20):
        self.dry_run = dry_run
        self.max_tier = max_tier
        self.timeout = timeout
        self.concurrency = concurrency
        self.changes = []
        self.manual_review = []

        # Load all config files
        self.r1_data = load_json(CONFIG_DIR / "r1_universities.json")
        self.peer_data = load_json(CONFIG_DIR / "peer_institutions.json")
        self.facility_data = load_json(CONFIG_DIR / "major_facilities.json")

        # Load batch corrections
        batch_path = CONFIG_DIR / "batch_6_corrections.json"
        self.batch_corrections = load_json(batch_path)["corrections"] if batch_path.exists() else []

    def _find_entry_by_name(self, entries: list, target_name: str) -> Optional[dict]:
        """Find an entry by fuzzy name matching."""
        target_norm = normalize_name(target_name)
        for entry in entries:
            if normalize_name(entry.get("name", "")) == target_norm:
                return entry
            if normalize_name(entry.get("canonical_name", "")) == target_norm:
                return entry
        return None

    def tier1_batch_corrections(self):
        """Tier 1: Apply known corrections from batch_6_corrections.json."""
        print("\n--- Tier 1: Applying batch corrections ---")
        applied = 0
        for correction in self.batch_corrections:
            name = correction["institution"]
            new_url = correction["new_url"]

            # Search in R1 universities
            entry = self._find_entry_by_name(self.r1_data["universities"], name)
            if not entry:
                # Try facilities
                entry = self._find_entry_by_name(self.facility_data.get("facilities", []), name)
            if not entry:
                # Try peers
                entry = self._find_entry_by_name(self.peer_data["universities"], name)

            if entry:
                source = get_primary_source(entry)
                if source:
                    old_url = source.get("url", "")
                    change = apply_update(source, new_url, "tier1_batch", self.dry_run)
                    change["institution"] = name
                    self.changes.append(change)
                    applied += 1

                    # Also update data_quality if present
                    if not self.dry_run and "data_quality" in entry:
                        entry["data_quality"]["verification_status"] = "verified"
                        entry["data_quality"]["needs_manual_review"] = False
                        entry["data_quality"]["last_verified"] = datetime.now(timezone.utc).isoformat()

                    action = "WOULD APPLY" if self.dry_run else "APPLIED"
                    print(f"  {action}: {name}: {old_url} -> {new_url}")
                else:
                    print(f"  SKIP: {name}: no primary news_source found")
            else:
                print(f"  SKIP: {name}: not found in any config file")

        print(f"  Tier 1 total: {applied} corrections")

    async def tier2_legacy_news_url(self):
        """Tier 2: Migrate legacy news_url field where primary is broken."""
        print("\n--- Tier 2: Migrating legacy news_url fields ---")
        candidates = []

        for entry in self.r1_data["universities"]:
            source = get_primary_source(entry)
            if not source:
                continue
            current_url = source.get("url", "")
            legacy_url = entry.get("news_url")

            # Skip if already verified and working, or no legacy URL, or same URL
            if source.get("verified", False):
                continue
            if not legacy_url or legacy_url == current_url:
                continue
            if is_placeholder(legacy_url):
                continue

            candidates.append((entry, source, legacy_url))

        if not candidates:
            print("  No candidates found")
            return

        print(f"  Testing {len(candidates)} legacy news_url candidates...")

        semaphore = asyncio.Semaphore(self.concurrency)

        async with httpx.AsyncClient(
            timeout=httpx.Timeout(self.timeout), verify=False,
            limits=httpx.Limits(max_connections=self.concurrency),
            headers={"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"},
        ) as client:
            async def test_one(entry, source, legacy_url):
                async with semaphore:
                    result = await check_url(legacy_url, self.timeout, client)
                    return entry, source, legacy_url, result

            tasks = [test_one(e, s, u) for e, s, u in candidates]
            raw_results = await asyncio.gather(*tasks)

        applied = 0
        for entry, source, legacy_url, result in raw_results:
            name = entry.get("name", "Unknown")
            if result.get("working"):
                old_url = source.get("url", "")
                change = apply_update(source, legacy_url, "tier2_legacy", self.dry_run)
                change["institution"] = name
                self.changes.append(change)
                applied += 1

                if not self.dry_run and "data_quality" in entry:
                    entry["data_quality"]["verification_status"] = "verified"
                    entry["data_quality"]["needs_manual_review"] = False
                    entry["data_quality"]["last_verified"] = datetime.now(timezone.utc).isoformat()

                action = "WOULD APPLY" if self.dry_run else "APPLIED"
                print(f"  {action}: {name}: {old_url} -> {legacy_url}")
            else:
                status = result.get("status", "error")
                print(f"  SKIP: {name}: legacy URL {legacy_url} returned {status}")

        print(f"  Tier 2 total: {applied} migrations")

    def tier3_cross_reference(self):
        """Tier 3: Copy working URLs from peer_institutions to R1."""
        print("\n--- Tier 3: Cross-referencing peer institutions ---")
        applied = 0

        for peer_entry in self.peer_data["universities"]:
            peer_source = get_primary_source(peer_entry)
            if not peer_source or not peer_source.get("verified", False):
                continue

            peer_name = peer_entry.get("name", "")
            peer_url = peer_source.get("url", "")

            # Find matching R1 entry
            r1_entry = self._find_entry_by_name(self.r1_data["universities"], peer_name)
            if not r1_entry:
                # Try canonical_name
                canonical = peer_entry.get("canonical_name", "")
                if canonical:
                    r1_entry = self._find_entry_by_name(self.r1_data["universities"], canonical)

            if not r1_entry:
                continue

            r1_source = get_primary_source(r1_entry)
            if not r1_source:
                continue

            # Skip if R1 entry is already verified and has same URL
            if r1_source.get("verified", False):
                continue

            r1_url = r1_source.get("url", "")
            if r1_url == peer_url:
                # Same URL, just mark verified
                if not self.dry_run:
                    r1_source["verified"] = True
                    r1_source["last_verified"] = datetime.now(timezone.utc).isoformat()
                continue

            change = apply_update(r1_source, peer_url, "tier3_crossref", self.dry_run)
            change["institution"] = r1_entry.get("name", "")
            self.changes.append(change)
            applied += 1

            if not self.dry_run and "data_quality" in r1_entry:
                r1_entry["data_quality"]["verification_status"] = "verified"
                r1_entry["data_quality"]["needs_manual_review"] = False
                r1_entry["data_quality"]["last_verified"] = datetime.now(timezone.utc).isoformat()

            action = "WOULD APPLY" if self.dry_run else "APPLIED"
            print(f"  {action}: {r1_entry.get('name')}: {r1_url} -> {peer_url}")

        print(f"  Tier 3 total: {applied} cross-references")

    async def tier4_candidate_probing(self):
        """Tier 4: Probe candidate URLs for remaining broken entries."""
        print("\n--- Tier 4: Probing candidate URLs ---")
        candidates = []

        for entry in self.r1_data["universities"]:
            source = get_primary_source(entry)
            if not source:
                continue
            if source.get("verified", False):
                continue

            current_url = source.get("url", "")
            name = entry.get("name", "")
            abbreviation = entry.get("abbreviation", "")
            domains = entry.get("domains", {})
            primary_domain = domains.get("primary", "")

            # Generate candidate URLs
            candidates_for_entry = []

            # From primary domain
            if primary_domain and not is_placeholder(f"https://{primary_domain}"):
                candidates_for_entry.extend([
                    f"https://news.{primary_domain}",
                    f"https://www.{primary_domain}/news",
                    f"https://www.{primary_domain}/news/",
                    f"https://newsroom.{primary_domain}",
                    f"https://today.{primary_domain}",
                    f"https://{primary_domain}/news",
                ])

            # From abbreviation (common patterns like news.mit.edu)
            if abbreviation and len(abbreviation) <= 10:
                abbr_lower = abbreviation.lower().replace(" ", "")
                # Only try if it looks like a real abbreviation
                if re.match(r'^[a-z]+$', abbr_lower):
                    candidates_for_entry.extend([
                        f"https://news.{abbr_lower}.edu",
                        f"https://www.{abbr_lower}.edu/news",
                        f"https://newsroom.{abbr_lower}.edu",
                        f"https://today.{abbr_lower}.edu",
                    ])

            # Deduplicate, skip current broken URL
            seen = set()
            unique_candidates = []
            for c in candidates_for_entry:
                c_norm = c.rstrip("/")
                if c_norm not in seen and c_norm != current_url.rstrip("/"):
                    seen.add(c_norm)
                    unique_candidates.append(c)

            if unique_candidates:
                candidates.append((entry, source, unique_candidates))

        if not candidates:
            print("  No candidates to probe")
            return

        print(f"  Probing candidates for {len(candidates)} entries...")

        semaphore = asyncio.Semaphore(self.concurrency)
        applied = 0

        async with httpx.AsyncClient(
            timeout=httpx.Timeout(self.timeout), verify=False,
            limits=httpx.Limits(max_connections=self.concurrency),
            headers={"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"},
        ) as client:
            async def probe_entry(entry, source, urls):
                name = entry.get("name", "")
                for url in urls:
                    async with semaphore:
                        result = await check_url(url, self.timeout, client)
                        if result.get("working"):
                            body = result.get("body_snippet", "").lower()
                            # Require at least one distinctive name word in page content
                            name_words = [w for w in name.lower().split() if len(w) > 3 and w not in ("the", "university", "of", "at", "and", "state", "main", "campus")]
                            if name_words and any(w in body for w in name_words):
                                return entry, source, url, True
                return entry, source, None, False

            tasks = [probe_entry(e, s, u) for e, s, u in candidates]
            raw_results = await asyncio.gather(*tasks)

        for entry, source, found_url, success in raw_results:
            name = entry.get("name", "Unknown")
            if success and found_url:
                old_url = source.get("url", "")
                change = apply_update(source, found_url, "tier4_probed", self.dry_run)
                change["institution"] = name
                self.changes.append(change)
                applied += 1

                if not self.dry_run and "data_quality" in entry:
                    entry["data_quality"]["verification_status"] = "verified"
                    entry["data_quality"]["needs_manual_review"] = False
                    entry["data_quality"]["last_verified"] = datetime.now(timezone.utc).isoformat()

                action = "WOULD APPLY" if self.dry_run else "APPLIED"
                print(f"  {action}: {name}: {old_url} -> {found_url}")

        print(f"  Tier 4 total: {applied} URLs discovered")

    def tier5_manual_review(self):
        """Tier 5: Generate manual review queue for remaining broken entries."""
        print("\n--- Tier 5: Generating manual review queue ---")
        remaining = []

        for entry in self.r1_data["universities"]:
            source = get_primary_source(entry)
            if not source:
                continue
            if source.get("verified", False):
                continue

            remaining.append({
                "name": entry.get("name"),
                "abbreviation": entry.get("abbreviation"),
                "current_url": source.get("url", ""),
                "legacy_news_url": entry.get("news_url"),
                "is_placeholder": is_placeholder(source.get("url", "")),
                "domains": entry.get("domains", {}),
            })

        # Also check facilities
        for entry in self.facility_data.get("facilities", []):
            source = get_primary_source(entry)
            if not source:
                continue
            if source.get("verified", False):
                continue
            remaining.append({
                "name": entry.get("name"),
                "abbreviation": entry.get("abbreviation"),
                "current_url": source.get("url", ""),
                "is_placeholder": is_placeholder(source.get("url", "")),
                "source_file": "major_facilities.json",
            })

        # Check peers
        for entry in self.peer_data["universities"]:
            source = get_primary_source(entry)
            if not source:
                continue
            if source.get("verified", False):
                continue
            remaining.append({
                "name": entry.get("name"),
                "abbreviation": entry.get("abbreviation"),
                "current_url": source.get("url", ""),
                "is_placeholder": is_placeholder(source.get("url", "")),
                "source_file": "peer_institutions.json",
            })

        self.manual_review = remaining
        print(f"  {len(remaining)} entries need manual review")

        if remaining:
            output_path = PROJECT_ROOT / "output" / "needs_manual_review.json"
            output_path.parent.mkdir(parents=True, exist_ok=True)
            with open(output_path, "w") as f:
                json.dump(remaining, f, indent=2)
            print(f"  Saved to: {output_path}")

    def save_all(self):
        """Save all modified config files."""
        if self.dry_run:
            print("\n--- DRY RUN: No files modified ---")
            return

        now = datetime.now(timezone.utc).isoformat()

        # Update metadata timestamps
        self.r1_data["metadata"]["last_updated"] = now
        self.peer_data["metadata"]["last_updated"] = now
        self.facility_data["metadata"]["last_updated"] = now

        save_json(CONFIG_DIR / "r1_universities.json", self.r1_data)
        save_json(CONFIG_DIR / "peer_institutions.json", self.peer_data)
        save_json(CONFIG_DIR / "major_facilities.json", self.facility_data)

        print(f"\n--- Saved all config files ---")

    def print_summary(self):
        """Print summary of all changes."""
        print("\n" + "=" * 70)
        print("FIX SUMMARY")
        print("=" * 70)
        print(f"Total changes: {len(self.changes)}")

        by_tier = {}
        for c in self.changes:
            by_tier.setdefault(c["tier"], []).append(c)
        for tier in sorted(by_tier.keys()):
            print(f"  {tier}: {len(by_tier[tier])} changes")

        print(f"Manual review needed: {len(self.manual_review)}")

        if self.dry_run:
            print("\n*** DRY RUN — no files were modified ***")
            print("*** Run without --dry-run to apply changes ***")

    async def run(self):
        """Run all correction tiers."""
        if self.max_tier >= 1:
            self.tier1_batch_corrections()
        if self.max_tier >= 2:
            await self.tier2_legacy_news_url()
        if self.max_tier >= 3:
            self.tier3_cross_reference()
        if self.max_tier >= 4:
            await self.tier4_candidate_probing()
        if self.max_tier >= 5:
            self.tier5_manual_review()

        self.save_all()
        self.print_summary()

        # Save change log
        change_log_path = PROJECT_ROOT / "output" / "url_fix_changelog.json"
        change_log_path.parent.mkdir(parents=True, exist_ok=True)
        with open(change_log_path, "w") as f:
            json.dump({
                "generated_at": datetime.now(timezone.utc).isoformat(),
                "dry_run": self.dry_run,
                "total_changes": len(self.changes),
                "changes": self.changes,
            }, f, indent=2)
        print(f"\nChange log saved to: {change_log_path}")


def main():
    parser = argparse.ArgumentParser(description="Fix university news URLs")
    parser.add_argument("--dry-run", action="store_true", help="Print changes without modifying files")
    parser.add_argument("--tier", type=int, default=5, help="Max correction tier to apply (1-5, default: 5)")
    parser.add_argument("--timeout", type=int, default=15, help="HTTP timeout in seconds (default: 15)")
    parser.add_argument("--concurrency", type=int, default=20, help="Max concurrent requests (default: 20)")
    args = parser.parse_args()

    fixer = URLFixer(
        dry_run=args.dry_run,
        max_tier=args.tier,
        timeout=args.timeout,
        concurrency=args.concurrency,
    )
    asyncio.run(fixer.run())


if __name__ == "__main__":
    main()
