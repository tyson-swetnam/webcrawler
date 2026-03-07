#!/usr/bin/env python3
"""
Update R1 universities URLs from r1_universities_verified_updated.md

This script reads the verified URLs from the markdown file and updates
the r1_universities.json configuration file.
"""

import sys
import json
import re
from pathlib import Path

# Add project to path
sys.path.insert(0, str(Path(__file__).parent.parent))

def parse_verified_urls_from_md(md_file_path):
    """Parse the markdown file and extract verified university URLs."""

    with open(md_file_path, 'r', encoding='utf-8') as f:
        content = f.read()

    # Split by university sections (### X. University Name)
    sections = re.split(r'\n### \d+\. ', content)

    universities = {}

    for section in sections[1:]:  # Skip the header section
        lines = section.split('\n')
        if not lines:
            continue

        # First line is the university name
        name = lines[0].strip()

        # Find Main News or first news URL
        news_url = None
        for line in lines:
            if line.startswith('- **Main News**:') or \
               line.startswith('- **News Home**:') or \
               line.startswith('- **YaleNews**:') or \
               line.startswith('- **UW News**:') or \
               line.startswith('- **The Hub**:') or \
               line.startswith('- **GW Today**:') or \
               line.startswith('- **The Dig**:') or \
               line.startswith('- **UDaily**:') or \
               line.startswith('- **Rice News**:') or \
               line.startswith('- **Penn Today**:') or \
               line.startswith('- **Duke Today**:') or \
               line.startswith('- **Cornell Chronicle**:') or \
               line.startswith('- **Northwestern Now**:') or \
               line.startswith('- **Vanderbilt News**:') or \
               line.startswith('- **News Center**:') or \
               line.startswith('- **UChicago News**:') or \
               line.startswith('- **CSU News**:') or \
               line.startswith('- **Newsroom**:') or \
               line.startswith('- **UCLA Newsroom**:') or \
               line.startswith('- **USC Today**:') or \
               line.startswith('- **SDSU NewsCenter**:') or \
               line.startswith('- **UCR News**:') or \
               line.startswith('- **UCSF News Center**:') or \
               line.startswith('- **UC Santa Cruz News**:') or \
               line.startswith('- **Mines Newsroom**:') or \
               line.startswith('- **The NAU Review**:') or \
               line.startswith('- **FAU News Desk**:') or \
               line.startswith('- **FIU News**:') or \
               line.startswith('- **Florida State University News**:') or \
               line.startswith('- **NSU Newsroom**:') or \
               line.startswith('- **UCF Today**:') or \
               line.startswith('- **University of Miami News**:') or \
               line.startswith('- **USF News**:') or \
               line.startswith('- **UH Manoa Newsroom**:') or \
               line.startswith('- **UGA Today**:') or \
               line.startswith('- **Georgia State News Hub**:') or \
               line.startswith('- **Georgia Tech News Center**:') or \
               line.startswith('- **This is Caltech News**:'):
                # Extract URL
                url_match = re.search(r'https?://[^\s]+', line)
                if url_match:
                    news_url = url_match.group(0).rstrip('/')
                    break

        if news_url:
            universities[name] = news_url

    return universities

def update_r1_json(json_file_path, verified_urls):
    """Update the R1 universities JSON file with verified URLs."""

    with open(json_file_path, 'r', encoding='utf-8') as f:
        data = json.load(f)

    # Create name mapping for matching
    name_variations = {
        'The University of Alabama': ['University of Alabama', 'Alabama'],
        'University of Alabama at Birmingham': ['UAB'],
        'California Institute of Technology (Caltech)': ['California Institute of Technology', 'Caltech'],
        'University of California-Berkeley': ['UC Berkeley', 'University of California, Berkeley'],
        'University of California-Davis': ['UC Davis', 'University of California, Davis'],
        'University of California-Los Angeles': ['UCLA', 'University of California, Los Angeles'],
        'University of California-Merced': ['UC Merced', 'University of California, Merced'],
        'University of California-Riverside': ['UC Riverside', 'University of California, Riverside'],
        'University of California-San Francisco': ['UCSF', 'University of California, San Francisco'],
        'University of California-Santa Cruz': ['UC Santa Cruz', 'University of California, Santa Cruz'],
        'Colorado School of Mines': ['Mines'],
        'Colorado State University-Fort Collins': ['Colorado State University', 'CSU'],
        'Massachusetts Institute of Technology': ['MIT'],
        'University of Michigan-Ann Arbor': ['University of Michigan'],
        'The University of Texas at Austin': ['University of Texas at Austin', 'UT Austin'],
        'University of Washington-Seattle Campus': ['University of Washington'],
        'University of Wisconsin-Madison': ['UW-Madison'],
        'Georgia Institute of Technology-Main Campus': ['Georgia Institute of Technology', 'Georgia Tech'],
        'Columbia University': ['Columbia University in the City of New York'],
        'University of Miami': ['University of Miami (FL)', 'Miami'],
        'Georgetown University': ['Georgetown'],
    }

    updated_count = 0
    matched = []

    for university in data['universities']:
        current_name = university['name']

        # Try exact match first
        if current_name in verified_urls:
            old_url = university.get('news_url', 'None')
            new_url = verified_urls[current_name]
            if old_url != new_url:
                university['news_url'] = new_url
                updated_count += 1
                matched.append(current_name)
                print(f"✓ Updated: {current_name}")
                print(f"  Old: {old_url}")
                print(f"  New: {new_url}")
        else:
            # Try variations
            for md_name, variations in name_variations.items():
                if md_name in verified_urls:
                    if current_name in variations or current_name == md_name:
                        old_url = university.get('news_url', 'None')
                        new_url = verified_urls[md_name]
                        if old_url != new_url:
                            university['news_url'] = new_url
                            updated_count += 1
                            matched.append(md_name)
                            print(f"✓ Updated (variation): {current_name}")
                            print(f"  Matched to: {md_name}")
                            print(f"  Old: {old_url}")
                            print(f"  New: {new_url}")
                        break

    # Check for unmatched verified URLs
    unmatched = set(verified_urls.keys()) - set(matched)
    if unmatched:
        print(f"\n⚠️  {len(unmatched)} verified URLs not matched:")
        for name in sorted(unmatched):
            print(f"  - {name}")

    return data, updated_count

def main():
    """Main function."""
    project_root = Path(__file__).parent.parent
    md_file = project_root / 'r1_universities_verified_updated.md'
    json_file = project_root / 'crawler' / 'config' / 'r1_universities.json'

    if not md_file.exists():
        print(f"❌ Markdown file not found: {md_file}")
        return 1

    if not json_file.exists():
        print(f"❌ JSON file not found: {json_file}")
        return 1

    print("Parsing verified URLs from markdown file...")
    verified_urls = parse_verified_urls_from_md(md_file)
    print(f"Found {len(verified_urls)} verified university URLs\n")

    print("Updating R1 universities JSON file...")
    updated_data, updated_count = update_r1_json(json_file, verified_urls)

    if updated_count == 0:
        print("\n✅ No updates needed - all URLs are already up to date!")
        return 0

    # Backup original file
    backup_file = json_file.with_suffix('.json.backup')
    import shutil
    shutil.copy2(json_file, backup_file)
    print(f"\n📋 Backup created: {backup_file}")

    # Write updated data
    with open(json_file, 'w', encoding='utf-8') as f:
        json.dump(updated_data, f, indent=2, ensure_ascii=False)

    print(f"\n✅ Successfully updated {updated_count} universities!")
    print(f"📝 Updated file: {json_file}")

    return 0

if __name__ == "__main__":
    sys.exit(main())
