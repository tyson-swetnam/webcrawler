#!/usr/bin/env python3
"""
Generate demo GitHub Pages output for testing.

This script creates sample HTML files in the docs/ directory without requiring
a database connection or actual crawl data.
"""

from pathlib import Path
from datetime import datetime


def generate_demo_index():
    """Generate a demo index.html page"""
    date_str = datetime.now().strftime('%A, %B %d, %Y')

    html = f'''<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>AI University News - {date_str}</title>
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}

        body {{
            font-family: 'Courier New', Courier, monospace;
            background-color: #ffffff;
            color: #000000;
            max-width: 900px;
            margin: 0 auto;
            padding: 20px;
            line-height: 1.5;
        }}

        .header {{
            text-align: center;
            border-bottom: 3px solid #000;
            padding-bottom: 15px;
            margin-bottom: 25px;
        }}

        .header h1 {{
            font-size: 42px;
            font-weight: bold;
            letter-spacing: -1px;
            margin-bottom: 5px;
        }}

        .header .tagline {{
            font-size: 14px;
            color: #666;
            font-style: italic;
        }}

        .header .date {{
            font-size: 16px;
            color: #000;
            margin-top: 10px;
            font-weight: bold;
        }}

        .nav {{
            text-align: center;
            margin-bottom: 20px;
            padding: 10px;
            background-color: #f5f5f5;
            border: 1px solid #ddd;
        }}

        .nav a {{
            color: #cc0000;
            text-decoration: none;
            font-weight: bold;
            margin: 0 15px;
            font-size: 14px;
        }}

        .nav a:hover {{
            text-decoration: underline;
        }}

        .stats {{
            text-align: center;
            font-size: 14px;
            color: #333;
            margin-bottom: 20px;
            padding: 10px;
            background-color: #f9f9f9;
        }}

        .three-column-layout {{
            display: grid;
            grid-template-columns: 1fr 1fr 1fr;
            gap: 20px;
            margin-top: 20px;
        }}

        .column {{
            border: 2px solid #ddd;
            padding: 15px;
            background-color: #fafafa;
            min-height: 200px;
        }}

        .column-title {{
            font-size: 22px;
            color: #cc0000;
            margin-bottom: 15px;
            padding-bottom: 10px;
            border-bottom: 3px solid #cc0000;
            text-align: center;
        }}

        .university-section {{
            margin-bottom: 30px;
            border-bottom: 1px solid #ddd;
            padding-bottom: 20px;
        }}

        .university-section h3 {{
            font-size: 18px;
            color: #000;
            margin-bottom: 12px;
            padding-bottom: 5px;
            border-bottom: 2px solid #cc0000;
        }}

        .article {{
            margin-bottom: 15px;
            padding-left: 10px;
        }}

        .headline a {{
            color: #0000cc;
            text-decoration: none;
            font-size: 18px;
            font-weight: bold;
        }}

        .headline a:hover {{
            text-decoration: underline;
        }}

        .topics {{
            font-size: 12px;
            color: #666;
            font-style: italic;
            margin-left: 8px;
        }}

        .meta {{
            font-size: 12px;
            color: #666;
            font-style: italic;
        }}

        .summary {{
            font-size: 13px;
            color: #333;
            margin-top: 5px;
            padding-left: 10px;
            line-height: 1.5;
        }}

        .footer {{
            text-align: center;
            margin-top: 40px;
            padding-top: 20px;
            border-top: 2px solid #000;
            font-size: 12px;
            color: #666;
        }}

        @media (max-width: 1024px) {{
            .three-column-layout {{
                grid-template-columns: 1fr;
            }}
        }}
    </style>
</head>
<body>
    <div class="header">
        <h1>AI UNIVERSITY NEWS</h1>
        <div class="tagline">Latest AI Research & Developments from Top Universities (Last 3 Days)</div>
        <div class="date">Updated: {date_str}</div>
    </div>

    <div class="nav">
        <a href="index.html">TODAY</a>
        <a href="archive/index.html">ARCHIVE</a>
        <a href="how_it_works.html">HOW IT WORKS</a>
    </div>

    <div class="stats">
        <strong>Total Articles:</strong> 6 |
        <strong>Peer:</strong> 3 |
        <strong>R1:</strong> 2 |
        <strong>Facilities:</strong> 1
    </div>

    <div class="three-column-layout">
        <div class="column">
            <h2 class="column-title">Peer Institutions</h2>

            <div class="university-section">
                <h3>MIT</h3>
                <div class="article">
                    <div class="headline">
                        <a href="https://news.mit.edu" target="_blank">New AI Model Achieves Breakthrough in Protein Folding</a>
                        <span class="topics">[Machine Learning, Biology, Research]</span>
                    </div>
                    <div class="meta">November 3, 2025</div>
                    <div class="summary">Researchers at MIT have developed a novel AI system that significantly improves protein structure prediction accuracy, potentially accelerating drug discovery and biological research.</div>
                </div>
            </div>

            <div class="university-section">
                <h3>Stanford University</h3>
                <div class="article">
                    <div class="headline">
                        <a href="https://news.stanford.edu" target="_blank">Quantum AI System Demonstrates Computational Advantage</a>
                        <span class="topics">[Quantum Computing, AI, Physics]</span>
                    </div>
                    <div class="meta">November 2, 2025</div>
                    <div class="summary">Stanford physicists integrate quantum computing with machine learning to solve optimization problems exponentially faster than classical approaches.</div>
                </div>
            </div>
        </div>

        <div class="column">
            <h2 class="column-title">R1 Institutions</h2>

            <div class="university-section">
                <h3>University of Arizona</h3>
                <div class="article">
                    <div class="headline">
                        <a href="https://uanews.arizona.edu" target="_blank">AI-Powered Climate Models Improve Drought Prediction</a>
                        <span class="topics">[Climate Science, Prediction, Sustainability]</span>
                    </div>
                    <div class="meta">November 1, 2025</div>
                    <div class="summary">Arizona researchers deploy machine learning to enhance drought forecasting accuracy by 40%, helping farmers and water resource managers make better decisions.</div>
                </div>
            </div>

            <div class="university-section">
                <h3>UC Berkeley</h3>
                <div class="article">
                    <div class="headline">
                        <a href="https://news.berkeley.edu" target="_blank">Robotics Lab Creates Self-Learning Manipulation System</a>
                        <span class="topics">[Robotics, Reinforcement Learning, Autonomy]</span>
                    </div>
                    <div class="meta">October 31, 2025</div>
                    <div class="summary">Berkeley roboticists develop an AI system that learns complex manipulation tasks through self-supervised exploration, reducing human training requirements.</div>
                </div>
            </div>
        </div>

        <div class="column">
            <h2 class="column-title">Major Facilities</h2>

            <div class="university-section">
                <h3>Argonne National Laboratory</h3>
                <div class="article">
                    <div class="headline">
                        <a href="https://www.anl.gov" target="_blank">AI Accelerates Materials Discovery for Clean Energy</a>
                        <span class="topics">[Materials Science, Energy, High-Performance Computing]</span>
                    </div>
                    <div class="meta">October 30, 2025</div>
                    <div class="summary">Using AI and supercomputing, Argonne scientists identify promising battery materials 100x faster, advancing renewable energy storage technology.</div>
                </div>
            </div>

            <div class="university-section">
                <h3>Los Alamos National Laboratory</h3>
                <div class="article">
                    <div class="headline">
                        <a href="https://www.lanl.gov" target="_blank">Machine Learning Detects Nuclear Material Signatures</a>
                        <span class="topics">[National Security, Detection, Physics]</span>
                    </div>
                    <div class="meta">October 29, 2025</div>
                    <div class="summary">Los Alamos develops AI algorithms for identifying radioactive materials with unprecedented sensitivity, enhancing nuclear security capabilities.</div>
                </div>
            </div>
        </div>
    </div>

    <div class="footer">
        <p>Powered by AI University News Crawler</p>
        <p>Last updated: {datetime.now().strftime('%I:%M %p UTC')}</p>
        <p><em>This is a demo page - run the crawler to generate real data</em></p>
    </div>
</body>
</html>'''

    return html


def generate_demo_archive_index():
    """Generate a demo archive index page"""
    html = '''<!DOCTYPE html>
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
            max-width: 900px;
            margin: 0 auto;
            padding: 20px;
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

    <div class="no-results">
        No archived reports available yet. Run the crawler to generate daily reports.
    </div>

    <div class="footer">
        <p>Powered by AI University News Crawler</p>
    </div>
</body>
</html>'''

    return html


def main():
    """Generate demo GitHub Pages files"""
    docs_dir = Path("docs")
    docs_dir.mkdir(parents=True, exist_ok=True)

    archive_dir = docs_dir / "archive"
    archive_dir.mkdir(parents=True, exist_ok=True)

    # Generate index.html
    index_html = generate_demo_index()
    (docs_dir / "index.html").write_text(index_html, encoding='utf-8')
    print(f"✅ Generated: docs/index.html")

    # Generate archive/index.html
    archive_html = generate_demo_archive_index()
    (archive_dir / "index.html").write_text(archive_html, encoding='utf-8')
    print(f"✅ Generated: docs/archive/index.html")

    # Copy how_it_works.html from html_output if it exists, or we'll generate it via the main generator
    print(f"\nℹ️  Note: how_it_works.html will be generated when you run the crawler")
    print(f"   Or you can run: python -c 'from crawler.utils.html_generator import HTMLReportGenerator; HTMLReportGenerator(github_pages_dir=\"docs\").generate_how_it_works()'")

    print(f"\n✅ Demo GitHub Pages files created in docs/")
    print(f"   - docs/index.html (main page with sample articles)")
    print(f"   - docs/archive/index.html (empty archive)")
    print(f"\nNext steps:")
    print(f"   1. Run the full crawler to generate real data")
    print(f"   2. Commit the docs/ directory to git")
    print(f"   3. Enable GitHub Pages in repository settings")


if __name__ == "__main__":
    main()
