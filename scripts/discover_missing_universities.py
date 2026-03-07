#!/usr/bin/env python3
"""
Missing University Discovery Script

Identifies R1 universities not yet in any config file and discovers their news URLs.
Uses the Carnegie Classification 2025 R1 list as the authoritative reference.

Usage:
    python scripts/discover_missing_universities.py
    python scripts/discover_missing_universities.py --carnegie-csv /path/to/carnegie.csv
    python scripts/discover_missing_universities.py --output-dir output/
"""

import argparse
import asyncio
import json
import re
import sys
import time
from datetime import datetime, timezone
from difflib import SequenceMatcher
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse

import httpx

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

CONFIG_DIR = PROJECT_ROOT / "crawler" / "config"

# Carnegie Classification 2025 R1 Universities
# This is the authoritative list. Institutions already in config files will be skipped.
# Sources: carnegieclassifications.acenet.edu, 2025 RAD Public Data File
CARNEGIE_R1_2025 = [
    # Alabama
    "Auburn University",
    "The University of Alabama",
    "The University of Alabama at Birmingham",
    "The University of Alabama in Huntsville",
    # Alaska
    "University of Alaska Fairbanks",
    # Arizona
    "Arizona State University",
    "Northern Arizona University",
    "The University of Arizona",
    # Arkansas
    "University of Arkansas",
    "University of Arkansas at Little Rock",
    # California
    "California Institute of Technology",
    "Claremont Graduate University",
    "Loma Linda University",
    "Naval Postgraduate School",
    "San Diego State University",
    "Stanford University",
    "University of California, Berkeley",
    "University of California, Davis",
    "University of California, Irvine",
    "University of California, Los Angeles",
    "University of California, Merced",
    "University of California, Riverside",
    "University of California, San Diego",
    "University of California, San Francisco",
    "University of California, Santa Barbara",
    "University of California, Santa Cruz",
    "University of Southern California",
    # Colorado
    "Colorado School of Mines",
    "Colorado State University",
    "University of Colorado Boulder",
    "University of Colorado Denver",
    "University of Denver",
    # Connecticut
    "University of Connecticut",
    "Yale University",
    # Delaware
    "University of Delaware",
    # DC
    "Georgetown University",
    "George Washington University",
    "Howard University",
    # Florida
    "Florida Atlantic University",
    "Florida International University",
    "Florida State University",
    "University of Central Florida",
    "University of Florida",
    "University of Miami",
    "University of South Florida",
    # Georgia
    "Emory University",
    "Georgia Institute of Technology",
    "Georgia State University",
    "University of Georgia",
    # Hawaii
    "University of Hawaii at Manoa",
    # Idaho
    "Boise State University",
    "University of Idaho",
    # Illinois
    "Illinois Institute of Technology",
    "Loyola University Chicago",
    "Northern Illinois University",
    "Northwestern University",
    "Southern Illinois University Carbondale",
    "University of Chicago",
    "University of Illinois Chicago",
    "University of Illinois Urbana-Champaign",
    # Indiana
    "Indiana University Bloomington",
    "Indiana University-Purdue University Indianapolis",
    "Purdue University",
    "University of Notre Dame",
    # Iowa
    "Iowa State University",
    "University of Iowa",
    # Kansas
    "Kansas State University",
    "University of Kansas",
    # Kentucky
    "University of Kentucky",
    "University of Louisville",
    # Louisiana
    "Louisiana State University",
    "Tulane University",
    "University of Louisiana at Lafayette",
    "University of New Orleans",
    # Maine
    "University of Maine",
    # Maryland
    "Johns Hopkins University",
    "University of Maryland, Baltimore",
    "University of Maryland, Baltimore County",
    "University of Maryland, College Park",
    # Massachusetts
    "Boston College",
    "Boston University",
    "Brandeis University",
    "Harvard University",
    "Massachusetts Institute of Technology",
    "Northeastern University",
    "Tufts University",
    "University of Massachusetts Amherst",
    "University of Massachusetts Lowell",
    "Worcester Polytechnic Institute",
    # Michigan
    "Central Michigan University",
    "Michigan State University",
    "Michigan Technological University",
    "University of Michigan",
    "Wayne State University",
    "Western Michigan University",
    # Minnesota
    "University of Minnesota",
    # Mississippi
    "Jackson State University",
    "Mississippi State University",
    "University of Mississippi",
    "University of Southern Mississippi",
    # Missouri
    "Missouri University of Science and Technology",
    "Saint Louis University",
    "University of Missouri",
    "University of Missouri-Kansas City",
    "Washington University in St. Louis",
    # Montana
    "Montana State University",
    "University of Montana",
    # Nebraska
    "University of Nebraska-Lincoln",
    # Nevada
    "University of Nevada, Las Vegas",
    "University of Nevada, Reno",
    # New Hampshire
    "Dartmouth College",
    "University of New Hampshire",
    # New Jersey
    "New Jersey Institute of Technology",
    "Princeton University",
    "Rutgers University-New Brunswick",
    "Stevens Institute of Technology",
    # New Mexico
    "New Mexico State University",
    "University of New Mexico",
    # New York
    "Binghamton University",
    "City University of New York Graduate Center",
    "Clarkson University",
    "Columbia University",
    "Cornell University",
    "New York University",
    "Rensselaer Polytechnic Institute",
    "Rochester Institute of Technology",
    "Stony Brook University",
    "Syracuse University",
    "University at Albany",
    "University at Buffalo",
    "University of Rochester",
    "Yeshiva University",
    # North Carolina
    "Duke University",
    "East Carolina University",
    "North Carolina A&T State University",
    "North Carolina State University",
    "University of North Carolina at Chapel Hill",
    "University of North Carolina at Charlotte",
    "University of North Carolina at Greensboro",
    "Wake Forest University",
    # North Dakota
    "North Dakota State University",
    "University of North Dakota",
    # Ohio
    "Bowling Green State University",
    "Case Western Reserve University",
    "Cleveland State University",
    "Kent State University",
    "Ohio State University",
    "Ohio University",
    "University of Akron",
    "University of Cincinnati",
    "University of Dayton",
    "University of Toledo",
    "Wright State University",
    # Oklahoma
    "Oklahoma State University",
    "University of Oklahoma",
    "University of Tulsa",
    # Oregon
    "Oregon Health & Science University",
    "Oregon State University",
    "Portland State University",
    "University of Oregon",
    # Pennsylvania
    "Carnegie Mellon University",
    "Drexel University",
    "Lehigh University",
    "Pennsylvania State University",
    "Temple University",
    "Thomas Jefferson University",
    "University of Pennsylvania",
    "University of Pittsburgh",
    # Rhode Island
    "Brown University",
    "University of Rhode Island",
    # South Carolina
    "Clemson University",
    "Medical University of South Carolina",
    "University of South Carolina",
    # South Dakota
    "South Dakota State University",
    "University of South Dakota",
    # Tennessee
    "University of Memphis",
    "University of Tennessee, Knoxville",
    "Vanderbilt University",
    # Texas
    "Baylor University",
    "Rice University",
    "Texas A&M University",
    "Texas State University",
    "Texas Tech University",
    "University of Houston",
    "University of North Texas",
    "University of Texas at Arlington",
    "University of Texas at Austin",
    "University of Texas at Dallas",
    "University of Texas at El Paso",
    "University of Texas at San Antonio",
    "University of Texas Health Science Center at Houston",
    # Utah
    "Brigham Young University",
    "University of Utah",
    "Utah State University",
    # Vermont
    "University of Vermont",
    # Virginia
    "George Mason University",
    "Old Dominion University",
    "University of Virginia",
    "Virginia Commonwealth University",
    "Virginia Polytechnic Institute and State University",
    "William & Mary",
    # Washington
    "University of Washington",
    "Washington State University",
    # West Virginia
    "West Virginia University",
    # Wisconsin
    "Marquette University",
    "Medical College of Wisconsin",
    "University of Wisconsin-Madison",
    "University of Wisconsin-Milwaukee",
    # Wyoming
    "University of Wyoming",
]


def normalize_name(name: str) -> str:
    """Normalize institution name for matching."""
    name = name.lower().strip()
    name = re.sub(r"^the\s+", "", name)
    name = re.sub(r"\s+", " ", name)
    # Normalize common variations
    name = name.replace("–", "-").replace("—", "-")
    name = name.replace(",", "")
    name = name.replace("&", "and")
    return name


def fuzzy_match(name1: str, name2: str, threshold: float = 0.85) -> bool:
    """Check if two names match using fuzzy matching."""
    n1 = normalize_name(name1)
    n2 = normalize_name(name2)
    if n1 == n2:
        return True
    # Also check if one contains the other
    if n1 in n2 or n2 in n1:
        return True
    return SequenceMatcher(None, n1, n2).ratio() >= threshold


def load_existing_institutions() -> set[str]:
    """Load all institution names from existing config files."""
    existing = set()
    files = [
        (CONFIG_DIR / "peer_institutions.json", "universities"),
        (CONFIG_DIR / "r1_universities.json", "universities"),
        (CONFIG_DIR / "major_facilities.json", "facilities"),
    ]
    for fpath, key in files:
        if fpath.exists():
            with open(fpath) as f:
                data = json.load(f)
            for entry in data.get(key, []):
                name = entry.get("name", "")
                if name:
                    existing.add(normalize_name(name))
                canonical = entry.get("canonical_name", "")
                if canonical:
                    existing.add(normalize_name(canonical))
    return existing


def find_missing(existing: set[str]) -> list[str]:
    """Find Carnegie R1 institutions not in existing config."""
    missing = []
    for name in CARNEGIE_R1_2025:
        norm = normalize_name(name)
        # Check exact match
        if norm in existing:
            continue
        # Check fuzzy match against all existing
        found = False
        for ex in existing:
            if fuzzy_match(name, ex, threshold=0.85):
                found = True
                break
        if not found:
            missing.append(name)
    return missing


async def probe_news_url(name: str, timeout: int = 15, client: httpx.AsyncClient = None) -> Optional[str]:
    """Try to discover the news URL for an institution."""
    # Generate candidate domains from institution name
    candidates = []

    # Try common abbreviation patterns
    words = name.split()
    # Simple abbreviation: first letter of each significant word
    sig_words = [w for w in words if w.lower() not in ("the", "of", "at", "in", "and", "&")]
    if sig_words:
        abbrev = "".join(w[0].lower() for w in sig_words)
        candidates.extend([
            f"https://news.{abbrev}.edu",
            f"https://www.{abbrev}.edu/news",
            f"https://newsroom.{abbrev}.edu",
        ])

    for url in candidates:
        try:
            resp = await client.get(url, follow_redirects=True)
            if resp.status_code == 200:
                body_lower = resp.text[:5000].lower()
                name_words = [w.lower() for w in name.split() if len(w) > 3 and w.lower() not in ("the", "university", "of", "at", "and")]
                if any(w in body_lower for w in name_words):
                    return url
        except Exception:
            continue

    return None


def generate_entry(name: str, news_url: Optional[str]) -> dict:
    """Generate a schema v3.0.0 entry for a university."""
    entry = {
        "name": name,
        "abbreviation": "",
        "canonical_name": name.replace("The ", ""),
        "location": {
            "city": "",
            "state": "",
            "state_full": "",
            "region": "",
            "country": "US",
        },
        "classification": {
            "carnegie_r1": True,
            "institution_type": "unknown",
            "year_classified": 2025,
        },
        "news_sources": [
            {
                "type": "primary",
                "url": news_url or "",
                "description": f"{name} official news",
                "verified": False,
                "crawl_priority": 100,
            }
        ],
        "data_quality": {
            "completeness_score": 0.3,
            "last_updated": datetime.now(timezone.utc).isoformat(),
            "verified_by": "automated_discovery",
            "verification_status": "unverified",
            "needs_manual_review": True,
        },
    }
    return entry


async def run_discovery(timeout: int, concurrency: int, output_dir: Path):
    """Run the full discovery process."""
    print("Loading existing institutions...")
    existing = load_existing_institutions()
    print(f"Found {len(existing)} existing institution name variants")

    print(f"\nCarnegie R1 2025 list: {len(CARNEGIE_R1_2025)} institutions")
    missing = find_missing(existing)
    print(f"Missing from config: {len(missing)} institutions")

    if not missing:
        print("\nAll Carnegie R1 institutions are already in the config files!")
        return

    print(f"\nMissing institutions:")
    for name in missing:
        print(f"  - {name}")

    print(f"\nProbing for news URLs (concurrency={concurrency})...")
    semaphore = asyncio.Semaphore(concurrency)

    async with httpx.AsyncClient(
        timeout=httpx.Timeout(timeout), verify=False,
        limits=httpx.Limits(max_connections=concurrency),
        headers={
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        },
    ) as client:
        async def probe_one(name):
            async with semaphore:
                url = await probe_news_url(name, timeout, client)
                return name, url

        tasks = [probe_one(name) for name in missing]
        results = await asyncio.gather(*tasks)

    # Generate entries
    entries = []
    found_count = 0
    for name, url in results:
        entry = generate_entry(name, url)
        entries.append(entry)
        if url:
            found_count += 1
            print(f"  FOUND: {name} -> {url}")
        else:
            print(f"  NOT FOUND: {name}")

    # Save report
    output_dir.mkdir(parents=True, exist_ok=True)
    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "carnegie_r1_total": len(CARNEGIE_R1_2025),
        "existing_in_config": len(CARNEGIE_R1_2025) - len(missing),
        "missing_count": len(missing),
        "urls_discovered": found_count,
        "missing_institutions": missing,
        "generated_entries": entries,
    }

    report_path = output_dir / "discovery_report.json"
    with open(report_path, "w") as f:
        json.dump(report, f, indent=2)
    print(f"\nReport saved to: {report_path}")

    print(f"\n{'=' * 60}")
    print(f"DISCOVERY SUMMARY")
    print(f"{'=' * 60}")
    print(f"Carnegie R1 2025 total:    {len(CARNEGIE_R1_2025)}")
    print(f"Already in config:         {len(CARNEGIE_R1_2025) - len(missing)}")
    print(f"Missing from config:       {len(missing)}")
    print(f"News URLs discovered:      {found_count}")
    print(f"Still need manual lookup:  {len(missing) - found_count}")


def main():
    parser = argparse.ArgumentParser(description="Discover missing R1 universities")
    parser.add_argument("--timeout", type=int, default=15, help="HTTP timeout in seconds")
    parser.add_argument("--concurrency", type=int, default=20, help="Max concurrent requests")
    parser.add_argument("--output-dir", type=str, default=str(PROJECT_ROOT / "output"), help="Output directory")
    parser.add_argument("--list-only", action="store_true", help="Only list missing, don't probe URLs")
    args = parser.parse_args()

    if args.list_only:
        existing = load_existing_institutions()
        missing = find_missing(existing)
        print(f"Missing from config ({len(missing)}):")
        for name in missing:
            print(f"  - {name}")
        return

    asyncio.run(run_discovery(args.timeout, args.concurrency, Path(args.output_dir)))


if __name__ == "__main__":
    main()
