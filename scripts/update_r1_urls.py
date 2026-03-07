#!/usr/bin/env python3
"""
Update R1 universities with corrected news URLs
"""
import json
from pathlib import Path

# Mapping of university names to corrected URLs
URL_CORRECTIONS = {
    "Boston College": "https://www.bc.edu/bc-web/bcnews.html",
    "Boston University": "https://www.bu.edu/today/",
    "Brandeis University": "https://www.brandeis.edu/stories/",
    "Brigham Young University": "https://news.byu.edu/",
    "Baylor University": "https://news.web.baylor.edu/",
    "Carnegie Mellon University": "https://www.cmu.edu/news/",
    "Case Western Reserve University": "https://thedaily.case.edu/",
    "Clemson University": "https://news.clemson.edu/",
    "Drexel University": "https://drexel.edu/news",
    "Kansas State University": "https://www.k-state.edu/news/",
    "Kent State University": "https://www.kent.edu/today",
    "Lehigh University": "https://news.lehigh.edu/",
    "Louisiana State University": "https://www.lsu.edu/mediacenter/news/index.php",
    "Mississippi State University": "https://www.msstate.edu/newsroom",
    "New Jersey Institute of Technology": "https://news.njit.edu/",
    "New York University": "https://www.nyu.edu/about/news-publications/news.html",
    "Northeastern University": "https://news.northeastern.edu/",
    "Ohio State University": "https://news.osu.edu/",
    "Oregon State University": "https://news.oregonstate.edu/",
    "Pennsylvania State University": "https://www.psu.edu/news",
    "Rensselaer Polytechnic Institute": "https://news.rpi.edu/",
    "Stony Brook University": "https://news.stonybrook.edu/",
    "Syracuse University": "https://news.syr.edu/",
    "Temple University": "https://news.temple.edu/",
    "Texas A&M University": "https://stories.tamu.edu/",
    "Texas A & M University-College Station": "https://stories.tamu.edu/",
    "Tufts University": "https://now.tufts.edu/",
    "Tulane University": "https://news.tulane.edu/",
    "University of Houston": "https://www.uh.edu/news-events/",
    "University of Massachusetts-Boston": "https://www.umb.edu/news/",
    "University of Massachusetts-Lowell": "https://www.uml.edu/news/",
    "University of Minnesota-Twin Cities": "https://twin-cities.umn.edu/news-events",
    "University of New Hampshire": "https://www.unh.edu/unhtoday/",
    "University of Oregon": "https://news.uoregon.edu",
    "University of Utah": "https://attheu.utah.edu/",
    "University of Virginia": "https://news.virginia.edu/",
    "Utah State University": "https://www.usu.edu/today/",
    "Virginia Tech": "https://news.vt.edu/",
    "Virginia Polytechnic Institute and State University": "https://news.vt.edu/",
    "Washington University in St Louis": "https://source.washu.edu/news",
    "Wayne State University": "https://today.wayne.edu/",
    "Worcester Polytechnic Institute": "https://www.wpi.edu/news",
}

def main():
    # Load the current JSON
    config_dir = Path(__file__).parent.parent / "crawler" / "config"
    json_path = config_dir / "r1_universities.json"

    print(f"Loading {json_path}...")
    with open(json_path, 'r') as f:
        data = json.load(f)

    universities = data.get("universities", [])
    total_updates = 0

    print(f"\nProcessing {len(universities)} universities...")

    for uni in universities:
        uni_name = uni.get("name", "")
        canonical_name = uni.get("canonical_name", "")

        # Try to match by name or canonical name
        matched_name = None
        new_url = None

        for correction_name, correction_url in URL_CORRECTIONS.items():
            # Check exact match or if correction name is contained in canonical name
            if (uni_name == correction_name or
                canonical_name == correction_name or
                correction_name in canonical_name or
                canonical_name in correction_name):
                matched_name = correction_name
                new_url = correction_url
                break

        if new_url:
            # Update the primary news source
            if "news_sources" in uni and len(uni["news_sources"]) > 0:
                old_url = uni["news_sources"][0].get("url", "")
                if old_url != new_url:
                    uni["news_sources"][0]["url"] = new_url
                    uni["news_sources"][0]["verified"] = True
                    uni["news_sources"][0]["verification_date"] = "2025-11-07"
                    total_updates += 1
                    print(f"✓ Updated {canonical_name}")
                    print(f"  Old: {old_url}")
                    print(f"  New: {new_url}")
                else:
                    print(f"- {canonical_name} already has correct URL")
            else:
                print(f"⚠ {canonical_name} has no news_sources")

    # Update metadata
    if total_updates > 0:
        from datetime import datetime, timezone
        data["metadata"]["last_updated"] = datetime.now(timezone.utc).isoformat()
        data["metadata"]["quality_notes"] = "URLs updated with verified corrections on 2025-11-07"

        # Save the updated JSON
        print(f"\nSaving updated JSON with {total_updates} changes...")
        with open(json_path, 'w') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

        print(f"✓ Successfully updated {total_updates} universities")
    else:
        print("\nNo changes needed - all URLs are already correct")

    # Report any universities from the correction list that weren't found
    print("\nVerifying all corrections were applied:")
    for correction_name in URL_CORRECTIONS.keys():
        found = False
        for uni in universities:
            if (correction_name in uni.get("canonical_name", "") or
                uni.get("canonical_name", "") in correction_name):
                found = True
                break
        if not found:
            print(f"⚠ Could not find: {correction_name}")

if __name__ == "__main__":
    main()
