#!/usr/bin/env python3
"""
Generate demo HTML website with sample data.

This creates a demo version of the website without needing database access.
Perfect for testing the HTML layout and web server functionality.
"""

import sys
from pathlib import Path
from datetime import datetime, timedelta

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))


def generate_demo_html(output_dir: str = "html_output"):
    """Generate demo HTML pages with sample data"""

    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    # Sample articles data
    sample_articles = [
        {
            'url': 'https://news.stanford.edu/stories/2025/01/ai-chip-breakthrough',
            'title': 'Stanford Researchers Unveil Revolutionary AI Chip Design',
            'university': 'Stanford University',
            'timestamp': datetime.now(),
            'summary': 'A team at Stanford has developed a new chip architecture that reduces AI training time by 60% while consuming 40% less power.',
            'topics': ['AI Hardware', 'Deep Learning', 'Energy Efficiency'],
            'sentiment': 'positive'
        },
        {
            'url': 'https://news.mit.edu/2025/climate-ai-model',
            'title': 'MIT AI Model Predicts Climate Change with Unprecedented Accuracy',
            'university': 'MIT',
            'timestamp': datetime.now() - timedelta(hours=2),
            'summary': None,
            'topics': ['Climate Science', 'Machine Learning'],
            'sentiment': 'neutral'
        },
        {
            'url': 'https://www.cs.cmu.edu/news/autonomous-vehicle-safety',
            'title': 'Carnegie Mellon Advances Autonomous Vehicle Safety Through AI',
            'university': 'Carnegie Mellon University',
            'timestamp': datetime.now() - timedelta(hours=5),
            'summary': None,
            'topics': ['Autonomous Vehicles', 'Computer Vision', 'Safety'],
            'sentiment': 'positive'
        },
        {
            'url': 'https://news.berkeley.edu/ai-ethics-framework',
            'title': 'UC Berkeley Releases Comprehensive AI Ethics Framework',
            'university': 'UC Berkeley',
            'timestamp': datetime.now() - timedelta(hours=7),
            'summary': None,
            'topics': ['AI Ethics', 'Policy'],
            'sentiment': 'neutral'
        },
        {
            'url': 'https://ai.caltech.edu/quantum-ml',
            'title': 'Caltech Demonstrates Quantum Machine Learning Breakthrough',
            'university': 'California Institute of Technology',
            'timestamp': datetime.now() - timedelta(hours=10),
            'summary': None,
            'topics': ['Quantum Computing', 'Machine Learning'],
            'sentiment': 'positive'
        },
        {
            'url': 'https://news.cornell.edu/nlp-research',
            'title': 'Cornell Researchers Improve Natural Language Processing Accuracy',
            'university': 'Cornell University',
            'timestamp': datetime.now() - timedelta(hours=12),
            'summary': None,
            'topics': ['NLP', 'Language Models'],
            'sentiment': 'neutral'
        },
        {
            'url': 'https://news.columbia.edu/medical-ai',
            'title': 'Columbia AI System Achieves 95% Accuracy in Early Disease Detection',
            'university': 'Columbia University',
            'timestamp': datetime.now() - timedelta(hours=14),
            'summary': None,
            'topics': ['Medical AI', 'Diagnostics'],
            'sentiment': 'positive'
        },
        {
            'url': 'https://news.princeton.edu/ai-privacy',
            'title': 'Princeton Develops Privacy-Preserving AI Training Method',
            'university': 'Princeton University',
            'timestamp': datetime.now() - timedelta(hours=16),
            'summary': None,
            'topics': ['Privacy', 'Federated Learning'],
            'sentiment': 'neutral'
        },
    ]

    # Generate today's report
    today = datetime.now()
    date_str = today.strftime('%A, %B %d, %Y')

    # Group by university
    by_university = {}
    for article in sample_articles:
        univ = article['university']
        if univ not in by_university:
            by_university[univ] = []
        by_university[univ].append(article)

    # Build article HTML
    articles_html = []

    # Top headline
    top = sample_articles[0]
    articles_html.append(f'''
        <div class="top-headline">
            <h2><a href="{top['url']}" target="_blank">{top['title']}</a></h2>
            <div class="meta">{top['university']} | {top['timestamp'].strftime('%I:%M %p')}</div>
            {f'<p class="summary">{top["summary"]}</p>' if top.get('summary') else ''}
        </div>
    ''')

    # Grouped articles
    for univ, univ_articles in sorted(by_university.items()):
        articles_html.append(f'<div class="university-section"><h3>{univ}</h3>')

        for article in univ_articles[1:] if univ == sample_articles[0]['university'] else univ_articles:
            topics_html = ''
            if article.get('topics'):
                topics = ', '.join(article['topics'][:3])
                topics_html = f'<span class="topics">[{topics}]</span>'

            articles_html.append(f'''
                <div class="article">
                    <div class="headline">
                        <a href="{article['url']}" target="_blank">{article['title']}</a>
                        {topics_html}
                    </div>
                    <div class="meta">{article['timestamp'].strftime('%I:%M %p')}</div>
                </div>
            ''')

        articles_html.append('</div>')

    # Create index.html
    index_html = f'''<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>AI University News - {date_str}</title>
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}

        body {{
            font-family: Georgia, 'Times New Roman', serif;
            background-color: #ffffff;
            color: #000000;
            max-width: 900px;
            margin: 0 auto;
            padding: 20px;
            line-height: 1.4;
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

        .demo-notice {{
            text-align: center;
            padding: 15px;
            margin-bottom: 20px;
            background-color: #fff3cd;
            border: 2px dashed #856404;
            color: #856404;
            font-weight: bold;
        }}

        .top-headline {{
            text-align: center;
            border: 2px solid #000;
            padding: 20px;
            margin-bottom: 30px;
            background-color: #fffbf0;
        }}

        .top-headline h2 {{
            font-size: 32px;
            margin-bottom: 10px;
            line-height: 1.2;
        }}

        .top-headline h2 a {{
            color: #cc0000;
            text-decoration: none;
        }}

        .top-headline h2 a:hover {{
            text-decoration: underline;
        }}

        .top-headline .summary {{
            margin-top: 15px;
            font-size: 16px;
            line-height: 1.5;
            color: #333;
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

        .headline {{
            margin-bottom: 3px;
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

        .headline a:visited {{
            color: #551a8b;
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

        .stats {{
            text-align: center;
            font-size: 14px;
            color: #333;
            margin-bottom: 20px;
            padding: 10px;
            background-color: #f9f9f9;
        }}

        .footer {{
            text-align: center;
            margin-top: 40px;
            padding-top: 20px;
            border-top: 2px solid #000;
            font-size: 12px;
            color: #666;
        }}

        @media (max-width: 600px) {{
            body {{ padding: 10px; }}
            .header h1 {{ font-size: 28px; }}
            .top-headline h2 {{ font-size: 22px; }}
            .headline a {{ font-size: 16px; }}
        }}
    </style>
</head>
<body>
    <div class="header">
        <h1>AI UNIVERSITY NEWS</h1>
        <div class="tagline">Latest AI Research & Developments from Top Universities</div>
        <div class="date">{date_str}</div>
    </div>

    <div class="nav">
        <a href="index.html">TODAY</a>
        <a href="archive/index.html">ARCHIVE</a>
    </div>

    <div class="demo-notice">
        DEMO VERSION - Sample data for testing
    </div>

    <div class="stats">
        <strong>{len(sample_articles)} AI-related articles</strong> found from <strong>{len(by_university)} universities</strong>
    </div>

    {''.join(articles_html)}

    <div class="footer">
        <p>Powered by AI University News Crawler</p>
        <p>Last updated: {datetime.now().strftime('%I:%M %p')}</p>
        <p style="margin-top: 10px; font-style: italic;">This is a demo page with sample data. Run the crawler to generate real content.</p>
    </div>
</body>
</html>'''

    # Write index.html
    index_file = output_path / "index.html"
    index_file.write_text(index_html, encoding='utf-8')
    print(f"✅ Created: {index_file}")

    # Create archive directory and index
    archive_dir = output_path / "archive"
    archive_dir.mkdir(exist_ok=True)

    # Sample archive data
    archive_dates = [
        (datetime.now().date(), len(sample_articles)),
        ((datetime.now() - timedelta(days=1)).date(), 12),
        ((datetime.now() - timedelta(days=2)).date(), 15),
        ((datetime.now() - timedelta(days=3)).date(), 8),
        ((datetime.now() - timedelta(days=4)).date(), 10),
    ]

    archive_rows = []
    for date_obj, count in archive_dates:
        date_str_fmt = date_obj.strftime('%A, %B %d, %Y')
        filename = f"{date_obj.strftime('%Y-%m-%d')}.html"

        archive_rows.append(f'''
            <tr>
                <td class="date-cell"><a href="{filename}">{date_str_fmt}</a></td>
                <td class="count-cell">{count} articles</td>
            </tr>
        ''')

    archive_html = f'''<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Archive - AI University News</title>
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}

        body {{
            font-family: Georgia, 'Times New Roman', serif;
            background-color: #ffffff;
            color: #000000;
            max-width: 900px;
            margin: 0 auto;
            padding: 20px;
            line-height: 1.4;
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

        .nav {{
            text-align: center;
            margin-bottom: 30px;
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

        .demo-notice {{
            text-align: center;
            padding: 15px;
            margin-bottom: 20px;
            background-color: #fff3cd;
            border: 2px dashed #856404;
            color: #856404;
            font-weight: bold;
        }}

        table {{
            width: 100%;
            border-collapse: collapse;
            margin-top: 20px;
        }}

        th {{
            background-color: #000;
            color: #fff;
            padding: 12px;
            text-align: left;
            font-size: 16px;
        }}

        td {{
            border-bottom: 1px solid #ddd;
            padding: 12px;
        }}

        tr:hover {{
            background-color: #f9f9f9;
        }}

        .date-cell a {{
            color: #0000cc;
            text-decoration: none;
            font-size: 18px;
            font-weight: bold;
        }}

        .date-cell a:hover {{
            text-decoration: underline;
        }}

        .count-cell {{
            text-align: right;
            color: #666;
            font-size: 14px;
        }}

        .footer {{
            text-align: center;
            margin-top: 40px;
            padding-top: 20px;
            border-top: 2px solid #000;
            font-size: 12px;
            color: #666;
        }}
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
    </div>

    <div class="demo-notice">
        DEMO VERSION - Sample archive data
    </div>

    <table>
        <thead>
            <tr>
                <th>Date</th>
                <th style="text-align: right;">Articles</th>
            </tr>
        </thead>
        <tbody>
            {''.join(archive_rows)}
        </tbody>
    </table>

    <div class="footer">
        <p>Powered by AI University News Crawler</p>
        <p style="margin-top: 10px; font-style: italic;">This is a demo page. Run the crawler to generate real archive.</p>
    </div>
</body>
</html>'''

    archive_file = archive_dir / "index.html"
    archive_file.write_text(archive_html, encoding='utf-8')
    print(f"✅ Created: {archive_file}")

    print()
    print("=" * 60)
    print("✅ Demo HTML website generated!")
    print("=" * 60)
    print()
    print("Files created:")
    print(f"  - {output_path}/index.html")
    print(f"  - {output_path}/archive/index.html")
    print()
    print("Next steps:")
    print("  1. Start the web server:")
    print("     python scripts/serve_html.py")
    print()
    print("  2. Open in browser:")
    print("     http://localhost:8000/")
    print()
    print("  3. To generate real content:")
    print("     - Set up the database (see DATABASE_SETUP.md)")
    print("     - Run the crawler: python -m crawler")
    print()


if __name__ == "__main__":
    generate_demo_html()
