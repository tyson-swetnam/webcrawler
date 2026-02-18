#!/usr/bin/env python3
"""Apply manually-researched URL corrections from agent search results.

This script applies the corrections found by web search agents for the 62
entries in needs_manual_review.json. Each correction was verified via HTTP
health checks and content inspection.
"""

import json
import os
import sys
from datetime import datetime, timezone
from urllib.parse import urlparse

# All corrections compiled from 4 search agent batches
# Format: institution_name -> new_url
CORRECTIONS = {
    # === Batch 1 (a48a14e) ===
    "Stanford University": "https://news.stanford.edu",
    "University of California-Merced": "https://news.ucmerced.edu",
    "University of California-Riverside": "https://news.ucr.edu",
    "University of California-Santa Cruz": "https://news.ucsc.edu",
    "Georgetown University": "https://www.georgetown.edu/news",
    "The Catholic University of America": "https://www.catholic.edu/news",
    "University of Miami": "https://news.miami.edu",
    "Emory University": "https://news.emory.edu",
    "Georgia Institute of Technology-Main Campus": "https://news.gatech.edu",
    "University of Iowa": "https://now.uiowa.edu",
    "Loyola University Chicago": "https://news.luc.edu",
    "Indiana University\u2013Purdue University-Indianapolis": "https://news.iu.edu",
    "Purdue University-Main Campus": "https://www.purdue.edu/newsroom",
    "University of Notre Dame": "https://news.nd.edu",
    "University of Louisville": "https://news.louisville.edu",

    # === Batch 2 (a10203a) ===
    "University of Louisiana at Lafayette": "https://louisiana.edu/news",
    "University of Maryland-Baltimore County": "https://umbc.edu/news-home",
    "Michigan Technological University": "https://www.mtu.edu/news",
    "University of Michigan-Ann Arbor": "https://news.umich.edu",
    "Missouri University of Science and Technology": "https://news.mst.edu",
    "Saint Louis University": "https://www.slu.edu/news",
    "University of Missouri-Columbia": "https://showme.missouri.edu",
    "University of Missouri-Kansas City": "https://www.umkc.edu/news",
    "University of Mississippi": "https://news.olemiss.edu",
    "University of Southern Mississippi": "https://www.usm.edu/news",
    "Montana State University": "https://www.montana.edu/news",
    "East Carolina University": "https://news.ecu.edu",
    "University of North Carolina at Chapel Hill": "https://uncnews.unc.edu",
    "University of North Carolina at Charlotte": "https://inside.charlotte.edu/news-features",
    "North Dakota State University-Main Campus": "https://www.ndsu.edu/news",

    # === Batch 3 (a682f54) ===
    "University of North Dakota": "https://blogs.und.edu/und-today",
    "University of Nebraska-Lincoln": "https://news.unl.edu",
    "Rutgers University-New Brunswick": "https://www.rutgers.edu/news",
    "New Mexico State University-Main Campus": "https://newsroom.nmsu.edu",
    "University of Nevada-Reno": "https://www.unr.edu/nevada-today",
    "Binghamton University": "https://www.binghamton.edu/news",
    "CUNY Graduate School and University Center": "https://www.gc.cuny.edu/news",
    "Columbia University in the City of New York": "https://news.columbia.edu",
    "University at Albany": "https://www.albany.edu/news",
    "University at Buffalo": "https://www.buffalo.edu/news",
    "University of Rochester": "https://www.rochester.edu/newscenter",
    "Weill Medical College of Cornell University": "https://news.weill.cornell.edu",
    "Ohio University-Main Campus": "https://www.ohio.edu/news",
    "University of Cincinnati-Main Campus": "https://www.uc.edu/news.html",
    "University of Dayton": "https://udayton.edu/news/index.php",

    # === Batch 4 (a5c140b) ===
    "University of Toledo": "https://news.utoledo.edu",
    "Oklahoma State University-Main Campus": "https://news.okstate.edu",
    "University of Rhode Island": "https://www.uri.edu/news",
    "Medical University of South Carolina": "https://web.musc.edu/about/news-center",
    "The University of Tennessee Health Science Center": "https://news.uthsc.edu",
    "The University of Tennessee-Knoxville": "https://news.utk.edu",
    "University of Memphis": "https://news.memphis.edu",
    "Vanderbilt University": "https://news.vanderbilt.edu",
    "Baylor College of Medicine": "https://www.bcm.edu/news",
    "Rice University": "https://news.rice.edu",
    "Southern Methodist University": "https://www.smu.edu/news",
    "The University of Texas Health Science Center at Houston": "https://www.uthouston.edu/news",
    "The University of Texas at El Paso": "https://www.utep.edu/newsfeed",
    "University of North Texas": "https://news.unt.edu",
    "University of Texas Southwestern Medical Center": "https://www.utsouthwestern.edu/newsroom",
}

# These need special handling (major_facilities.json)
FACILITY_CORRECTIONS = {
    "Indiana University Pervasive Technology Institute": "https://news.iu.edu/it",
    "Thomas Jefferson National Accelerator Facility": "https://www.jlab.org/news",
}


def load_json(path):
    with open(path, "r") as f:
        return json.load(f)


def save_json(path, data):
    with open(path, "w") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
        f.write("\n")


def update_entry(entry, new_url, now_str):
    """Update a university/facility entry's primary news source URL."""
    parsed = urlparse(new_url)
    domain = parsed.netloc or parsed.hostname or ""

    # Update news_sources
    for source in entry.get("news_sources", []):
        if source.get("type") == "primary":
            old_url = source["url"]
            source["url"] = new_url
            source["verified"] = True
            source["last_verified"] = now_str
            break
    else:
        return None, None

    # Update domains if present
    if domain and "domains" in entry:
        entry["domains"]["primary"] = domain.replace("www.", "")
        entry["domains"]["news_domains"] = [domain]

    return old_url, new_url


def main():
    dry_run = "--dry-run" in sys.argv

    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    config_dir = os.path.join(base_dir, "crawler", "config")

    r1_path = os.path.join(config_dir, "r1_universities.json")
    facilities_path = os.path.join(config_dir, "major_facilities.json")

    r1_data = load_json(r1_path)
    facilities_data = load_json(facilities_path)

    now_str = datetime.now(timezone.utc).isoformat()
    changes = []

    # Apply R1 university corrections
    for uni in r1_data["universities"]:
        name = uni["name"]
        if name in CORRECTIONS:
            new_url = CORRECTIONS[name]
            old_url, applied_url = update_entry(uni, new_url, now_str)
            if old_url is not None:
                changes.append({
                    "institution": name,
                    "old_url": old_url,
                    "new_url": applied_url,
                    "source_file": "r1_universities.json",
                })

    # Apply facility corrections
    for facility in facilities_data["facilities"]:
        name = facility["name"]
        if name in FACILITY_CORRECTIONS:
            new_url = FACILITY_CORRECTIONS[name]
            old_url, applied_url = update_entry(facility, new_url, now_str)
            if old_url is not None:
                changes.append({
                    "institution": name,
                    "old_url": old_url,
                    "new_url": applied_url,
                    "source_file": "major_facilities.json",
                })

    print(f"\n{'DRY RUN - ' if dry_run else ''}Manual URL Corrections")
    print(f"{'=' * 60}")
    print(f"Total corrections to apply: {len(changes)}")
    print()

    for i, change in enumerate(changes, 1):
        marker = "NEW" if change["old_url"] != change["new_url"] else "VERIFY"
        print(f"  {i:2d}. [{marker}] {change['institution']}")
        if change["old_url"] != change["new_url"]:
            print(f"      OLD: {change['old_url']}")
            print(f"      NEW: {change['new_url']}")
        else:
            print(f"      URL: {change['new_url']} (set verified=true)")

    if not dry_run:
        # Update metadata timestamps
        r1_data["metadata"]["last_updated"] = now_str
        facilities_data["metadata"]["last_updated"] = now_str

        save_json(r1_path, r1_data)
        save_json(facilities_path, facilities_data)

        # Save changelog
        changelog = {
            "generated_at": now_str,
            "dry_run": False,
            "total_changes": len(changes),
            "changes": changes,
        }
        changelog_path = os.path.join(base_dir, "output", "manual_corrections_changelog.json")
        save_json(changelog_path, changelog)

        print(f"\nApplied {len(changes)} corrections.")
        print(f"Changelog: {changelog_path}")
    else:
        print(f"\nDry run complete. Run without --dry-run to apply.")

    # Count expected total verified after this
    r1_verified = sum(
        1 for u in r1_data["universities"]
        for s in u.get("news_sources", [])
        if s.get("type") == "primary" and s.get("verified")
    )
    print(f"\nR1 verified count after corrections: {r1_verified}/187")


if __name__ == "__main__":
    main()
