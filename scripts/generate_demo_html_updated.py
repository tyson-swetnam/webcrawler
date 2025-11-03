#!/usr/bin/env python3
"""
Generate demo HTML website with sample data showing the new three-column layout.
Demonstrates: Peer Institutions | R1 Institutions | Major Facilities
"""

import sys
from pathlib import Path
from datetime import datetime, timedelta

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from crawler.utils.university_classifier import UniversityClassifier


def generate_demo_html_with_three_columns(output_dir: str = "html_output"):
    """Generate demo HTML pages with sample data in three-column layout"""

    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    # Initialize classifier
    classifier = UniversityClassifier()

    # Sample articles with universities/facilities from all three categories
    sample_articles = [
        # PEER INSTITUTIONS
        {
            'url': 'https://news.stanford.edu/stories/2025/01/ai-chip-breakthrough',
            'title': 'Stanford Unveils Revolutionary AI Chip Design',
            'university': 'Stanford University',
            'timestamp': datetime.now(),
            'topics': ['AI Hardware', 'Deep Learning', 'Energy Efficiency'],
        },
        {
            'url': 'https://news.mit.edu/2025/climate-ai-model',
            'title': 'MIT AI Model Predicts Climate Change with Unprecedented Accuracy',
            'university': 'MIT',
            'timestamp': datetime.now() - timedelta(hours=2),
            'topics': ['Climate Science', 'Machine Learning'],
        },
        {
            'url': 'https://www.harvard.edu/ai-ethics',
            'title': 'Harvard Releases New AI Ethics Guidelines',
            'university': 'Harvard University',
            'timestamp': datetime.now() - timedelta(hours=4),
            'topics': ['AI Ethics', 'Policy'],
        },
        {
            'url': 'https://news.princeton.edu/ai-privacy',
            'title': 'Princeton Develops Privacy-Preserving AI Training Method',
            'university': 'Princeton University',
            'timestamp': datetime.now() - timedelta(hours=6),
            'topics': ['Privacy', 'Federated Learning'],
        },

        # R1 INSTITUTIONS
        {
            'url': 'https://news.arizona.edu/ai-desert-research',
            'title': 'University of Arizona Uses AI for Desert Ecosystem Research',
            'university': 'The University of Arizona',
            'timestamp': datetime.now() - timedelta(hours=3),
            'topics': ['Environmental Science', 'AI Applications'],
        },
        {
            'url': 'https://news.asu.edu/ai-education',
            'title': 'ASU Launches AI-Powered Personalized Learning Platform',
            'university': 'Arizona State University',
            'timestamp': datetime.now() - timedelta(hours=5),
            'topics': ['Education', 'AI Applications'],
        },
        {
            'url': 'https://news.auburn.edu/ai-agriculture',
            'title': 'Auburn Applies Machine Learning to Precision Agriculture',
            'university': 'Auburn University',
            'timestamp': datetime.now() - timedelta(hours=7),
            'topics': ['Agriculture', 'Computer Vision'],
        },
        {
            'url': 'https://news.purdue.edu/quantum-ai',
            'title': 'Purdue Advances Quantum-Enhanced Machine Learning',
            'university': 'Purdue University',
            'timestamp': datetime.now() - timedelta(hours=8),
            'topics': ['Quantum Computing', 'AI'],
        },

        # MAJOR FACILITIES
        {
            'url': 'https://www.tacc.utexas.edu/news/ai-training-frontier',
            'title': 'TACC: New Frontera AI Partition Accelerates Large Model Training',
            'university': 'Texas Advanced Computing Center',
            'timestamp': datetime.now() - timedelta(hours=1),
            'topics': ['HPC', 'AI Training', 'Supercomputing'],
        },
        {
            'url': 'https://www.anl.gov/news/aurora-ai-breakthrough',
            'title': 'Argonne: Aurora Exascale System Powers Drug Discovery AI',
            'university': 'Argonne National Laboratory',
            'timestamp': datetime.now() - timedelta(hours=3),
            'topics': ['Exascale', 'Drug Discovery', 'AI'],
        },
        {
            'url': 'https://www.ornl.gov/news/frontier-climate',
            'title': 'Oak Ridge: Frontier Supercomputer Models Climate with AI',
            'university': 'Oak Ridge National Laboratory',
            'timestamp': datetime.now() - timedelta(hours=5),
            'topics': ['Climate Modeling', 'Exascale', 'AI'],
        },
        {
            'url': 'https://www.sdsc.edu/news/expanse-genomics',
            'title': 'SDSC: Expanse Enables AI-Driven Genomics Research',
            'university': 'San Diego Supercomputer Center',
            'timestamp': datetime.now() - timedelta(hours=6),
            'topics': ['Genomics', 'Bioinformatics', 'AI'],
        },
        {
            'url': 'https://www.ncsa.illinois.edu/news/delta-ai',
            'title': 'NCSA: Delta Supercomputer Supports Large Language Model Research',
            'university': 'National Center for Supercomputing Applications',
            'timestamp': datetime.now() - timedelta(hours=9),
            'topics': ['LLMs', 'NLP', 'HPC'],
        },
        {
            'url': 'https://www.nersc.gov/news/perlmutter-materials',
            'title': 'NERSC: Perlmutter AI Accelerates Materials Discovery',
            'university': 'NERSC',
            'timestamp': datetime.now() - timedelta(hours=10),
            'topics': ['Materials Science', 'AI', 'GPU Computing'],
        },
    ]

    # Categorize articles
    peer_articles = {}
    r1_articles = {}
    facility_articles = {}

    for article in sample_articles:
        univ = article['university']
        category = classifier.classify(univ)

        if category == 'peer':
            target_dict = peer_articles
        elif category == 'r1':
            target_dict = r1_articles
        else:  # facility
            target_dict = facility_articles

        if univ not in target_dict:
            target_dict[univ] = []
        target_dict[univ].append(article)

    # Helper function to render a column
    def render_column(articles_dict, title):
        if not articles_dict:
            return f'<div class="column"><h2 class="column-title">{title}</h2><p class="no-articles">No articles</p></div>'

        html = [f'<div class="column"><h2 class="column-title">{title}</h2>']

        for univ, univ_articles in sorted(articles_dict.items()):
            html.append(f'<div class="university-section"><h3>{univ}</h3>')

            for article in univ_articles:
                topics_html = ''
                if article.get('topics'):
                    topics = ', '.join(article['topics'][:3])
                    topics_html = f'<span class="topics">[{topics}]</span>'

                html.append(f'''
                    <div class="article">
                        <div class="headline">
                            <a href="{article['url']}" target="_blank">{article['title']}</a>
                            {topics_html}
                        </div>
                        <div class="meta">{article['timestamp'].strftime('%I:%M %p')}</div>
                    </div>
                ''')

            html.append('</div>')

        html.append('</div>')
        return '\n'.join(html)

    # Build three-column HTML
    columns_html = f'''
        <div class="three-column-layout">
            {render_column(peer_articles, "Peer Institutions")}
            {render_column(r1_articles, "R1 Institutions")}
            {render_column(facility_articles, "Major Facilities")}
        </div>
    '''

    # Stats
    stats_html = f'''
        <div class="stats">
            <strong>Total Articles:</strong> {len(sample_articles)} |
            <strong>Peer:</strong> {sum(len(arts) for arts in peer_articles.values())} |
            <strong>R1:</strong> {sum(len(arts) for arts in r1_articles.values())} |
            <strong>Facilities:</strong> {sum(len(arts) for arts in facility_articles.values())}
        </div>
    '''

    today = datetime.now()
    date_str = today.strftime('%A, %B %d, %Y')

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
            max-width: 1400px;
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
            background-color: #d4edda;
            border: 2px solid #28a745;
            color: #155724;
            font-weight: bold;
        }}

        .stats {{
            text-align: center;
            font-size: 14px;
            color: #333;
            margin-bottom: 20px;
            padding: 10px;
            background-color: #f9f9f9;
        }}

        /* Three-column layout */
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
            margin-bottom: 25px;
            border-bottom: 1px solid #ddd;
            padding-bottom: 15px;
        }}

        .university-section h3 {{
            font-size: 16px;
            color: #000;
            margin-bottom: 10px;
            padding-bottom: 5px;
            border-bottom: 2px solid #ccc;
        }}

        .article {{
            margin-bottom: 12px;
            padding-left: 8px;
        }}

        .headline {{
            margin-bottom: 3px;
        }}

        .headline a {{
            color: #0000cc;
            text-decoration: none;
            font-size: 16px;
            font-weight: bold;
        }}

        .headline a:hover {{
            text-decoration: underline;
        }}

        .headline a:visited {{
            color: #551a8b;
        }}

        .topics {{
            font-size: 11px;
            color: #666;
            font-style: italic;
            margin-left: 6px;
        }}

        .meta {{
            font-size: 11px;
            color: #666;
            font-style: italic;
        }}

        .no-articles {{
            text-align: center;
            color: #999;
            font-style: italic;
            padding: 20px;
        }}

        .footer {{
            text-align: center;
            margin-top: 40px;
            padding-top: 20px;
            border-top: 2px solid #000;
            font-size: 12px;
            color: #666;
        }}

        .footer a {{
            color: #0000cc;
            text-decoration: none;
        }}

        @media (max-width: 1024px) {{
            .three-column-layout {{
                grid-template-columns: 1fr;
            }}
        }}

        @media (max-width: 600px) {{
            body {{ padding: 10px; }}
            .header h1 {{ font-size: 28px; }}
            .headline a {{ font-size: 14px; }}
            .column {{ padding: 10px; }}
        }}
    </style>
</head>
<body>
    <div class="header">
        <h1>AI UNIVERSITY NEWS</h1>
        <div class="tagline">Latest AI Research & Developments from Universities and Research Facilities</div>
        <div class="date">{date_str}</div>
    </div>

    <div class="nav">
        <a href="index.html">TODAY</a>
        <a href="archive/index.html">ARCHIVE</a>
    </div>

    <div class="demo-notice">
        📊 DEMO: Three-Column Layout with Major Facilities
    </div>

    {stats_html}
    {columns_html}

    <div class="footer">
        <p><strong>Powered by AI University News Crawler</strong></p>
        <p>Last updated: {datetime.now().strftime('%I:%M %p')}</p>
        <p style="margin-top: 10px; font-style: italic;">
            ✓ New three-column layout: Peer Institutions | R1 Institutions | Major Facilities
        </p>
        <p style="margin-top: 5px; font-style: italic;">
            This is demo data. Run the full crawler to generate real content.
        </p>
    </div>
</body>
</html>
'''

    # Write index.html
    index_path = output_path / "index.html"
    index_path.write_text(index_html, encoding='utf-8')
    print(f"✅ Created: {index_path}")

    return str(index_path)


if __name__ == "__main__":
    output_file = generate_demo_html_with_three_columns()
    print()
    print("=" * 60)
    print("✅ Demo HTML with three-column layout generated!")
    print("=" * 60)
    print()
    print("Next steps:")
    print("  1. Start the web server:")
    print("     python scripts/serve_html.py")
    print()
    print("  2. Open in browser:")
    print("     http://localhost:8000/")
    print()
    print("The new layout shows:")
    print("  • Peer Institutions (elite universities)")
    print("  • R1 Institutions (research universities)")
    print("  • Major Facilities (NSF/DOE infrastructure)")
    print()
