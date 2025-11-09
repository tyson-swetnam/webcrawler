#!/usr/bin/env python3
"""
Fix archive index by scanning existing HTML archive files.
This ensures all generated archives appear in the index, regardless of database state.
"""

import re
from pathlib import Path
from datetime import datetime

def extract_article_count(html_file: Path) -> int:
    """Extract article count from HTML file."""
    content = html_file.read_text(encoding='utf-8')

    # Look for the stats section with article counts
    match = re.search(r'<strong>Total Articles:</strong>\s*(\d+)', content)
    if match:
        return int(match.group(1))

    # If no stats section, count article divs
    article_count = len(re.findall(r'<div class="article">', content))
    return article_count


def main():
    """Generate archive index from existing HTML files."""
    # Check both output directories
    archive_dirs = [
        Path("docs/archive"),
        Path("output/archive")
    ]

    # Collect all archive files
    archive_files = {}

    for archive_dir in archive_dirs:
        if not archive_dir.exists():
            print(f"Warning: {archive_dir} does not exist")
            continue

        for html_file in archive_dir.glob("2025-*.html"):
            # Extract date from filename
            date_str = html_file.stem  # e.g., "2025-11-08"
            if date_str not in archive_files:
                article_count = extract_article_count(html_file)
                archive_files[date_str] = article_count
                print(f"Found: {date_str} with {article_count} articles")

    # Sort by date descending
    sorted_dates = sorted(archive_files.keys(), reverse=True)

    # Generate archive index HTML
    html_content = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Archive - AI University News</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }

        body {
            font-family: 'Courier New', Courier, monospace;
            background-color: #ffffff;
            color: #000000;
            max-width: 1400px;
            margin: 0 auto;
            padding: 20px 40px;
            line-height: 1.5;
        }

        .header {
            text-align: center;
            border-bottom: 3px solid #000;
            padding-bottom: 15px;
            margin-bottom: 25px;
        }

        .header h1 {
            font-size: 42px;
            font-weight: bold;
            letter-spacing: -1px;
            margin-bottom: 5px;
        }

        .header .tagline {
            font-size: 14px;
            color: #666;
            font-style: italic;
        }

        .nav {
            text-align: center;
            margin-bottom: 30px;
            padding: 10px;
            background-color: #f5f5f5;
            border: 1px solid #ddd;
        }

        .nav a {
            color: #cc0000;
            text-decoration: none;
            font-weight: bold;
            margin: 0 15px;
            font-size: 14px;
        }

        .nav a:hover {
            text-decoration: underline;
        }

        table {
            width: 100%;
            border-collapse: collapse;
            margin-top: 20px;
        }

        th {
            background-color: #000;
            color: #fff;
            padding: 12px;
            text-align: left;
            font-size: 16px;
        }

        td {
            border-bottom: 1px solid #ddd;
            padding: 12px;
        }

        tr:hover {
            background-color: #f9f9f9;
        }

        .date-cell a {
            color: #0000cc;
            text-decoration: none;
            font-size: 18px;
            font-weight: bold;
        }

        .date-cell a:hover {
            text-decoration: underline;
        }

        .count-cell {
            text-align: right;
            color: #666;
            font-size: 14px;
        }

        .no-results {
            text-align: center;
            padding: 40px;
            color: #666;
        }

        .footer {
            text-align: center;
            margin-top: 40px;
            padding-top: 20px;
            border-top: 2px solid #000;
            font-size: 12px;
            color: #666;
        }
    </style>
</head>
<body>
    <div class="header">
        <h1>AI UNIVERSITY NEWS</h1>
        <div class="tagline">Archive</div>
    </div>

    <div class="nav">
        <a href="../index.html">TODAY</a>
        <a href="index.html">ARCHIVE</a>
        <a href="../how_it_works.html">HOW IT WORKS</a>
    </div>

    <table>
        <thead>
            <tr>
                <th>Date</th>
                <th style="text-align: right;">Articles</th>
            </tr>
        </thead>
        <tbody>
            """

    # Add rows for each date
    for date_str in sorted_dates:
        # Parse date and format it nicely
        try:
            date_obj = datetime.strptime(date_str, "%Y-%m-%d")
            formatted_date = date_obj.strftime("%A, %B %d, %Y")
        except ValueError:
            formatted_date = date_str

        article_count = archive_files[date_str]
        article_word = "article" if article_count == 1 else "articles"

        html_content += f"""
                <tr>
                    <td class="date-cell"><a href="{date_str}.html">{formatted_date}</a></td>
                    <td class="count-cell">{article_count} {article_word}</td>
                </tr>
            """

    html_content += """
        </tbody>
    </table>

    <div class="footer">
        <p>Powered by AI University News Crawler</p>
    </div>
</body>
</html>
"""

    # Write to both archive directories
    for archive_dir in archive_dirs:
        if archive_dir.exists():
            output_file = archive_dir / "index.html"
            output_file.write_text(html_content, encoding='utf-8')
            print(f"\nWrote archive index to: {output_file}")
            print(f"Total dates included: {len(sorted_dates)}")


if __name__ == "__main__":
    main()
