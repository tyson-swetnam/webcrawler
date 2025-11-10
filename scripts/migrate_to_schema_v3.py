#!/usr/bin/env python3
"""
Migrate JSON configuration files from schema v2.0.0 to v3.0.0

This script:
1. Converts news_sources from object to array structure
2. Removes broken ai_tag_url field
3. Adds new required fields (type, description, last_verified)
4. Updates schema version to 3.0.0
"""

import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Any


# Mapping of institutions to their additional AI-specific sources
MULTI_SOURCE_INSTITUTIONS = {
    "Stanford University": [
        {
            "type": "ai_research",
            "url": "https://hai.stanford.edu/news",
            "description": "Stanford HAI (Human-Centered AI Institute) news",
            "verified": True,
            "crawl_priority": 250
        },
        {
            "type": "engineering",
            "url": "https://engineering.stanford.edu/news",
            "description": "Stanford School of Engineering news",
            "verified": True,
            "crawl_priority": 180
        }
    ],
    "Massachusetts Institute of Technology": [
        {
            "type": "ai_research",
            "url": "https://www.csail.mit.edu/news",
            "description": "MIT CSAIL - Computer Science & AI Lab news",
            "verified": True,
            "crawl_priority": 250
        },
        {
            "type": "college_specific",
            "url": "https://www.eecs.mit.edu/news-events/",
            "description": "MIT EECS Department news and events",
            "verified": True,
            "crawl_priority": 220
        }
    ],
    "Carnegie Mellon University": [
        {
            "type": "cs_department",
            "url": "https://www.cs.cmu.edu/news",
            "description": "CMU School of Computer Science news",
            "verified": True,
            "crawl_priority": 240
        }
    ],
    "University of California, Berkeley": [
        {
            "type": "ai_research",
            "url": "https://bair.berkeley.edu/blog/",
            "description": "Berkeley AI Research (BAIR) blog",
            "verified": True,
            "crawl_priority": 250
        }
    ],
    "Cornell University": [
        {
            "type": "cs_department",
            "url": "https://www.cs.cornell.edu/information/news",
            "description": "Cornell Computer Science news",
            "verified": True,
            "crawl_priority": 220
        }
    ],
    "Georgia Institute of Technology": [
        {
            "type": "college_specific",
            "url": "https://www.cc.gatech.edu/news",
            "description": "Georgia Tech College of Computing news",
            "verified": True,
            "crawl_priority": 240
        }
    ],
    "Princeton University": [
        {
            "type": "cs_department",
            "url": "https://www.cs.princeton.edu/news",
            "description": "Princeton Computer Science news",
            "verified": True,
            "crawl_priority": 220
        }
    ],
    "University of Chicago": [
        {
            "type": "ai_research",
            "url": "https://cdac.uchicago.edu/news/",
            "description": "UChicago Data Science Institute news",
            "verified": True,
            "crawl_priority": 220
        }
    ]
}


def get_source_description(url: str, institution_name: str, facility_type: str = None) -> str:
    """Generate a descriptive name for the news source."""
    if "hai.stanford.edu" in url:
        return "Stanford HAI (Human-Centered AI Institute) news"
    elif "csail.mit.edu" in url:
        return "MIT CSAIL - Computer Science & AI Lab news"
    elif "bair.berkeley.edu" in url:
        return "Berkeley AI Research (BAIR) blog"
    elif "eecs.mit.edu" in url:
        return "MIT EECS Department news and events"
    elif "/engineering" in url:
        return f"{institution_name} School of Engineering news"
    elif "/cs." in url or "/computer-science" in url:
        return f"{institution_name} Computer Science news"
    elif facility_type:
        return f"{institution_name} - {facility_type} news and updates"
    else:
        return f"{institution_name} official news and press releases"


def convert_news_source_v2_to_v3(old_source: Dict[str, Any], institution_name: str,
                                  facility_type: str = None) -> Dict[str, Any]:
    """Convert a single news source from v2.0.0 format to v3.0.0 format."""
    current_time = datetime.now(timezone.utc).isoformat()

    # Extract URL - use the primary URL, NOT the broken ai_tag_url
    url = old_source.get("url", "")

    # Determine if this was verified (some had last_verified timestamp)
    verified = old_source.get("verified", False)
    last_verified = old_source.get("last_verified", current_time if verified else None)

    # Generate description
    description = get_source_description(url, institution_name, facility_type)

    new_source = {
        "type": "primary",
        "url": url,
        "description": description,
        "verified": verified,
        "crawl_priority": old_source.get("crawl_priority", 150),
        "last_verified": last_verified or current_time
    }

    return new_source


def migrate_institution(institution: Dict[str, Any], is_facility: bool = False) -> Dict[str, Any]:
    """Migrate a single institution/facility from v2.0.0 to v3.0.0."""
    institution_name = institution.get("name", "Unknown")
    facility_type = institution.get("facility_type") if is_facility else None

    # Convert old news_sources structure to new array structure
    old_news_sources = institution.get("news_sources", {})
    new_news_sources = []

    # Convert primary source if it exists
    if "primary" in old_news_sources:
        primary_source = convert_news_source_v2_to_v3(
            old_news_sources["primary"],
            institution_name,
            facility_type
        )
        new_news_sources.append(primary_source)

    # Add any additional verified sources for multi-source institutions
    if institution_name in MULTI_SOURCE_INSTITUTIONS:
        additional_sources = MULTI_SOURCE_INSTITUTIONS[institution_name]
        current_time = datetime.now(timezone.utc).isoformat()

        for source in additional_sources:
            source_with_timestamp = source.copy()
            source_with_timestamp["last_verified"] = current_time
            new_news_sources.append(source_with_timestamp)

    # Update the institution with new news_sources array
    institution["news_sources"] = new_news_sources

    return institution


def migrate_file(input_path: Path, output_path: Path, is_facility: bool = False):
    """Migrate a complete JSON configuration file."""
    print(f"Migrating {input_path.name}...")

    # Read input file
    with open(input_path, 'r', encoding='utf-8') as f:
        data = json.load(f)

    # Update metadata
    data["metadata"]["schema_version"] = "3.0.0"
    data["metadata"]["last_updated"] = datetime.now(timezone.utc).isoformat()

    # Add migration note
    if "migration_notes" not in data["metadata"]:
        data["metadata"]["migration_notes"] = []
    data["metadata"]["migration_notes"].append(
        "Migrated to schema v3.0.0 on 2025-11-04: Converted news_sources to array structure, "
        "removed broken ai_tag_url field, added multi-source support for AI research institutions"
    )

    # Migrate each institution/facility
    key = "facilities" if is_facility else "universities"
    if key in data:
        migrated_items = []
        for item in data[key]:
            migrated_item = migrate_institution(item, is_facility)
            migrated_items.append(migrated_item)
        data[key] = migrated_items

    # Write output file
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

    # Count statistics
    total_items = len(data.get(key, []))
    multi_source_count = sum(
        1 for item in data.get(key, [])
        if len(item.get("news_sources", [])) > 1
    )
    total_sources = sum(
        len(item.get("news_sources", []))
        for item in data.get(key, [])
    )

    print(f"  ✓ Migrated {total_items} {key}")
    print(f"  ✓ Total news sources: {total_sources}")
    print(f"  ✓ Multi-source {key}: {multi_source_count}")
    print(f"  ✓ Saved to {output_path}")
    print()


def main():
    """Main migration script."""
    # Define paths
    config_dir = Path(__file__).parent.parent / "crawler" / "config"

    files_to_migrate = [
        ("major_facilities.json", True),  # (filename, is_facility)
        ("peer_institutions.json", False),
        ("r1_universities.json", False)
    ]

    print("=" * 70)
    print("JSON Schema Migration: v2.0.0 → v3.0.0")
    print("=" * 70)
    print()

    # Backup existing files
    print("Creating backups...")
    for filename, _ in files_to_migrate:
        input_path = config_dir / filename
        backup_path = config_dir / f"{filename}.v2.bak"

        if input_path.exists():
            with open(input_path, 'r') as src, open(backup_path, 'w') as dst:
                dst.write(src.read())
            print(f"  ✓ Backed up {filename} → {backup_path.name}")
    print()

    # Migrate each file
    for filename, is_facility in files_to_migrate:
        input_path = config_dir / filename
        output_path = config_dir / filename

        if not input_path.exists():
            print(f"⚠ Warning: {filename} not found, skipping...")
            continue

        try:
            migrate_file(input_path, output_path, is_facility)
        except Exception as e:
            print(f"✗ Error migrating {filename}: {e}")
            print(f"  Restoring from backup...")
            backup_path = config_dir / f"{filename}.v2.bak"
            if backup_path.exists():
                with open(backup_path, 'r') as src, open(output_path, 'w') as dst:
                    dst.write(src.read())
            raise

    print("=" * 70)
    print("Migration completed successfully!")
    print("=" * 70)
    print()
    print("Next steps:")
    print("1. Review the migrated files")
    print("2. Update crawler code to handle array-based news_sources")
    print("3. Test with a small subset of universities")
    print("4. Commit changes to git")
    print()
    print("Backup files location:")
    print(f"  {config_dir}/*.v2.bak")


if __name__ == "__main__":
    main()
