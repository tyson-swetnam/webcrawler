"""
HTML Report Generator - Creates Drudge Report-style static HTML pages
"""
import os
import re
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Dict, Optional
from sqlalchemy import select, func, and_
from sqlalchemy.orm import Session

from crawler.db.models import Article, AIAnalysis
from crawler.db.session import get_db
from crawler.utils.university_classifier import UniversityClassifier


class HTMLReportGenerator:
    """Generates Drudge Report-style HTML pages for crawl results"""

    def __init__(self, output_dir: str = "html_output", github_pages_dir: str = None):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

        # Optional separate output for GitHub Pages
        self.github_pages_dir = Path(github_pages_dir) if github_pages_dir else None
        if self.github_pages_dir:
            self.github_pages_dir.mkdir(parents=True, exist_ok=True)

        self.classifier = UniversityClassifier()

    @staticmethod
    def strip_markdown(text: str) -> str:
        """Strip markdown formatting and structured data from text, returning clean plain text"""
        if not text:
            return ""

        # Remove code blocks (triple backticks) - everything between ```
        text = re.sub(r'```[a-zA-Z]*\n?.*?```', '', text, flags=re.DOTALL)
        text = re.sub(r'```', '', text)

        # Handle structured list formatting like [**Key**: Description, **Key2**: Description]
        # Extract title (before the bracket) and first description only
        match = re.match(r'^([^\[]+)\s*\[', text)
        if match:
            # Keep just the title text before the structured list
            text = match.group(1).strip()
        else:
            # If no structured list, process normally
            # Remove square brackets but keep content
            text = re.sub(r'[\[\]]', '', text)

        # Remove markdown links [text](url) -> text
        text = re.sub(r'\[([^\]]+)\]\([^\)]+\)', r'\1', text)

        # Remove bold **text** or __text__ -> text
        text = re.sub(r'\*\*([^\*]+)\*\*', r'\1', text)
        text = re.sub(r'__([^_]+)__', r'\1', text)

        # Remove italics *text* or _text_ -> text
        text = re.sub(r'\*([^\*]+)\*', r'\1', text)
        text = re.sub(r'_([^_]+)_', r'\1', text)

        # Remove inline code `text` -> text
        text = re.sub(r'`([^`]+)`', r'\1', text)

        # Remove headers ### text -> text
        text = re.sub(r'^#{1,6}\s+', '', text, flags=re.MULTILINE)

        # Remove horizontal rules
        text = re.sub(r'^[-*_]{3,}$', '', text, flags=re.MULTILINE)

        # Remove HTML tags
        text = re.sub(r'<[^>]+>', '', text)

        # Clean up extra whitespace
        text = re.sub(r'\s+', ' ', text)

        return text.strip()

    def generate_daily_report(self, date: Optional[datetime] = None) -> str:
        """Generate HTML report for a specific date (default: today)"""
        if date is None:
            date = datetime.now()

        with get_db() as session:
            articles = self._fetch_articles_for_date(session, date)

        # Write to index.html for current day
        if date.date() == datetime.now().date():
            # Main page (root level) - use relative paths without ../
            html = self._render_main_page(articles, date, is_archive_page=False)
            output_file = self.output_dir / "index.html"
            output_file.write_text(html, encoding='utf-8')

            # ALSO save dated archive file for today (in archive/ dir)
            html_archive = self._render_main_page(articles, date, is_archive_page=True)
            archive_dir = self.output_dir / "archive"
            archive_dir.mkdir(exist_ok=True)
            archive_file = archive_dir / f"{date.strftime('%Y-%m-%d')}.html"
            archive_file.write_text(html_archive, encoding='utf-8')
        else:
            # Archive files by date (in archive/ dir)
            html = self._render_main_page(articles, date, is_archive_page=True)
            archive_dir = self.output_dir / "archive"
            archive_dir.mkdir(exist_ok=True)
            output_file = archive_dir / f"{date.strftime('%Y-%m-%d')}.html"
            output_file.write_text(html, encoding='utf-8')

        # Also write to GitHub Pages directory if configured
        if self.github_pages_dir:
            if date.date() == datetime.now().date():
                # Main page for GitHub Pages
                html_main = self._render_main_page(articles, date, is_archive_page=False)
                gh_output_file = self.github_pages_dir / "index.html"
                gh_output_file.write_text(html_main, encoding='utf-8')

                # Archive file for today
                html_archive = self._render_main_page(articles, date, is_archive_page=True)
                gh_archive_dir = self.github_pages_dir / "archive"
                gh_archive_dir.mkdir(exist_ok=True)
                gh_archive_file = gh_archive_dir / f"{date.strftime('%Y-%m-%d')}.html"
                gh_archive_file.write_text(html_archive, encoding='utf-8')
            else:
                # Archive file for past date
                html = self._render_main_page(articles, date, is_archive_page=True)
                gh_archive_dir = self.github_pages_dir / "archive"
                gh_archive_dir.mkdir(exist_ok=True)
                gh_output_file = gh_archive_dir / f"{date.strftime('%Y-%m-%d')}.html"
                gh_output_file.write_text(html, encoding='utf-8')

        return str(output_file)

    def generate_archive_index(self) -> str:
        """Generate archive index page listing all available dates

        This method scans existing archive HTML files rather than querying the database,
        ensuring all generated archives appear in the index regardless of whether they
        contain AI-related articles.
        """
        import re
        from datetime import datetime

        # Collect archive files from both output directories
        archive_files = {}

        # Check output directory
        archive_dir = self.output_dir / "archive"
        if archive_dir.exists():
            for html_file in archive_dir.glob("20*.html"):
                date_str = html_file.stem  # e.g., "2025-11-08"
                if date_str not in archive_files:
                    # Extract article count from HTML file
                    content = html_file.read_text(encoding='utf-8')
                    match = re.search(r'<strong>Total Articles:</strong>\s*(\d+)', content)
                    if match:
                        count = int(match.group(1))
                    else:
                        # Fallback: count article divs
                        count = len(re.findall(r'<div class="article">', content))

                    try:
                        date_obj = datetime.strptime(date_str, '%Y-%m-%d').date()
                        archive_files[date_str] = (date_obj, count)
                    except ValueError:
                        pass  # Skip invalid date formats

        # Also check GitHub Pages directory if configured
        if self.github_pages_dir:
            gh_archive_dir = self.github_pages_dir / "archive"
            if gh_archive_dir.exists():
                for html_file in gh_archive_dir.glob("20*.html"):
                    date_str = html_file.stem
                    if date_str not in archive_files:
                        content = html_file.read_text(encoding='utf-8')
                        match = re.search(r'<strong>Total Articles:</strong>\s*(\d+)', content)
                        if match:
                            count = int(match.group(1))
                        else:
                            count = len(re.findall(r'<div class="article">', content))

                        try:
                            date_obj = datetime.strptime(date_str, '%Y-%m-%d').date()
                            archive_files[date_str] = (date_obj, count)
                        except ValueError:
                            pass

        # Sort by date descending
        dates = sorted(archive_files.values(), key=lambda x: x[0], reverse=True)

        html = self._render_archive_page(dates)

        archive_dir = self.output_dir / "archive"
        archive_dir.mkdir(exist_ok=True)
        output_file = archive_dir / "index.html"
        output_file.write_text(html, encoding='utf-8')

        # Also write to GitHub Pages directory if configured
        if self.github_pages_dir:
            gh_archive_dir = self.github_pages_dir / "archive"
            gh_archive_dir.mkdir(exist_ok=True)
            gh_output_file = gh_archive_dir / "index.html"
            gh_output_file.write_text(html, encoding='utf-8')

        return str(output_file)

    def generate_how_it_works(self) -> str:
        """Generate 'How It Works' documentation page"""
        html = self._render_how_it_works_page()

        output_file = self.output_dir / "how_it_works.html"
        output_file.write_text(html, encoding='utf-8')

        # Also write to GitHub Pages directory if configured
        if self.github_pages_dir:
            gh_output_file = self.github_pages_dir / "how_it_works.html"
            gh_output_file.write_text(html, encoding='utf-8')

        return str(output_file)

    def _fetch_articles_for_date(self, session: Session, date: datetime) -> List[Dict]:
        """Fetch AI-related articles published in the last 5 days"""
        end_date = date.replace(hour=23, minute=59, second=59, microsecond=999999)
        start_date = end_date - timedelta(days=5)

        stmt = (
            select(Article, AIAnalysis)
            .outerjoin(AIAnalysis, Article.article_id == AIAnalysis.article_id)
            .where(
                and_(
                    Article.is_ai_related == True,
                    Article.published_date >= start_date,
                    Article.published_date <= end_date
                )
            )
            .order_by(Article.published_date.desc())
        )

        results = session.execute(stmt).all()

        articles = []
        for article, ai_analysis in results:
            articles.append({
                'url': article.url.url if article.url else '',
                'title': article.title or 'Untitled',
                'university': article.university_name,
                'timestamp': article.first_scraped,
                'published_date': article.published_date,
                'summary': ai_analysis.consensus_summary if ai_analysis else None,
                'topics': ai_analysis.claude_key_points if ai_analysis else [],
                'category': ai_analysis.openai_category if ai_analysis else None
            })

        return articles

    def _render_main_page(self, articles: List[Dict], date: datetime, is_archive_page: bool = False) -> str:
        """Render main page with three-column layout: Peer Institutions, R1 Institutions, Major Facilities

        Args:
            articles: List of article dictionaries
            date: Date for the report
            is_archive_page: If True, generates URLs for pages in archive/ folder (need ../ prefix)
        """
        date_str = date.strftime('%A, %B %d, %Y')

        # Categorize articles by university/facility tier
        peer_articles = {}
        r1_articles = {}
        facility_articles = {}

        for article in articles:
            univ = article['university'] or 'Unknown'
            category = self.classifier.classify(univ)

            # Select the appropriate dictionary
            if category == 'peer':
                target_dict = peer_articles
            elif category == 'r1':
                target_dict = r1_articles
            else:  # 'facility'
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
                    if article.get('topics') and isinstance(article['topics'], list):
                        # Clean topics - strip markdown and use only simple text
                        clean_topics = [self.strip_markdown(str(t)) for t in article['topics'][:3] if t]
                        # Filter out empty or very long topics
                        clean_topics = [t for t in clean_topics if t and len(t) < 50]
                        if clean_topics:
                            topics = ', '.join(clean_topics)
                            topics_html = f'<span class="topics">[{topics}]</span>'

                    # Strip markdown from summary if it exists
                    summary_html = ''
                    if article.get('summary'):
                        plain_summary = self.strip_markdown(article['summary'])
                        # Truncate to 200 chars
                        if len(plain_summary) > 200:
                            plain_summary = plain_summary[:200].rsplit(' ', 1)[0] + '...'
                        summary_html = f'<div class="summary">{plain_summary}</div>'

                    # Format dates
                    pub_date_str = ''
                    if article.get('published_date'):
                        if isinstance(article['published_date'], str):
                            pub_date_str = article['published_date']
                        else:
                            pub_date_str = article['published_date'].strftime('%B %d, %Y')

                    crawl_date_str = article['timestamp'].strftime('%B %d, %Y')

                    # Build meta line with both dates
                    if pub_date_str and pub_date_str != crawl_date_str:
                        meta_html = f'<div class="meta">Published: {pub_date_str} | Crawled: {crawl_date_str}</div>'
                    elif pub_date_str:
                        meta_html = f'<div class="meta">Published: {pub_date_str}</div>'
                    else:
                        meta_html = f'<div class="meta">Crawled: {crawl_date_str}</div>'

                    html.append(f'''
                        <div class="article">
                            <div class="headline">
                                <a href="{article['url']}" target="_blank">{article['title']}</a>
                                {topics_html}
                            </div>
                            {meta_html}
                            {summary_html}
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
                <strong>Total Articles:</strong> {len(articles)} |
                <strong>Peer:</strong> {sum(len(arts) for arts in peer_articles.values())} |
                <strong>R1:</strong> {sum(len(arts) for arts in r1_articles.values())} |
                <strong>Facilities:</strong> {sum(len(arts) for arts in facility_articles.values())}
            </div>
        '''

        articles_html = stats_html + columns_html if articles else '<p class="no-results">No AI-related articles found for this date.</p>'

        # Set navigation URLs based on page location
        if is_archive_page:
            # Archive pages are in archive/ subfolder, need ../ to go up
            nav_today_url = "../index.html"
            nav_archive_url = "index.html"
            nav_how_it_works_url = "../how_it_works.html"
        else:
            # Main index.html is at root level
            nav_today_url = "index.html"
            nav_archive_url = "archive/index.html"
            nav_how_it_works_url = "how_it_works.html"

        return f'''<!DOCTYPE html>
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
            max-width: 1400px;
            margin: 0 auto;
            padding: 20px 40px;
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

        .summary {{
            font-size: 13px;
            color: #333;
            margin-top: 5px;
            padding-left: 10px;
            line-height: 1.5;
        }}

        .no-results {{
            text-align: center;
            font-size: 18px;
            color: #666;
            margin: 40px 0;
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

        .no-articles {{
            text-align: center;
            color: #999;
            font-style: italic;
            padding: 20px;
        }}

        @media (max-width: 1024px) {{
            .three-column-layout {{
                grid-template-columns: 1fr;
            }}
        }}

        @media (max-width: 600px) {{
            body {{ padding: 10px; }}
            .header h1 {{ font-size: 28px; }}
            .headline a {{ font-size: 16px; }}
            .column {{ padding: 10px; }}
        }}
    </style>
</head>
<body>
    <div class="header">
        <h1>AI UNIVERSITY NEWS</h1>
        <div class="tagline">Latest AI Research & Developments from Top Universities (Last 5 Days)</div>
        <div class="date">Updated: {date_str}</div>
    </div>

    <div class="nav">
        <a href="{nav_today_url}">TODAY</a>
        <a href="{nav_archive_url}">ARCHIVE</a>
        <a href="{nav_how_it_works_url}">HOW IT WORKS</a>
    </div>

    {articles_html}

    <div class="footer">
        <p>Powered by AI University News Crawler</p>
        <p>Last updated: {datetime.now().strftime('%I:%M %p %Z')}</p>
    </div>
</body>
</html>'''

    def _render_archive_page(self, dates: List) -> str:
        """Render archive index page"""
        rows_html = []

        for date_obj, count in dates:
            if isinstance(date_obj, str):
                date_obj = datetime.strptime(date_obj, '%Y-%m-%d').date()

            date_str = date_obj.strftime('%A, %B %d, %Y')
            filename = f"{date_obj.strftime('%Y-%m-%d')}.html"

            rows_html.append(f'''
                <tr>
                    <td class="date-cell"><a href="{filename}">{date_str}</a></td>
                    <td class="count-cell">{count} articles</td>
                </tr>
            ''')

        if not rows_html:
            rows_html.append('<tr><td colspan="2" class="no-results">No archived reports available</td></tr>')

        return f'''<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Archive - AI University News</title>
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}

        body {{
            font-family: 'Courier New', Courier, monospace;
            background-color: #ffffff;
            color: #000000;
            max-width: 1400px;
            margin: 0 auto;
            padding: 20px 40px;
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

        .no-results {{
            text-align: center;
            padding: 40px;
            color: #666;
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
            {''.join(rows_html)}
        </tbody>
    </table>

    <div class="footer">
        <p>Powered by AI University News Crawler</p>
    </div>
</body>
</html>'''


    def _render_how_it_works_page(self) -> str:
        """Render 'How It Works' documentation page"""
        # Load source lists
        import json
        from pathlib import Path

        config_dir = Path(__file__).parent.parent / 'config'

        # Load peer institutions
        peer_institutions = []
        try:
            with open(config_dir / 'peer_institutions.json', 'r') as f:
                peer_data = json.load(f)
                peer_institutions = [u['name'] for u in peer_data.get('universities', [])]
        except Exception as e:
            print(f"Error loading peer institutions: {e}")

        # Load R1 universities
        r1_universities = []
        try:
            with open(config_dir / 'r1_universities.json', 'r') as f:
                r1_data = json.load(f)
                r1_universities = [u['name'] for u in r1_data.get('universities', [])]
        except Exception as e:
            print(f"Error loading R1 universities: {e}")

        # Load major facilities
        major_facilities = []
        try:
            with open(config_dir / 'major_facilities.json', 'r') as f:
                facilities_data = json.load(f)
                major_facilities = [f['name'] for f in facilities_data.get('facilities', [])]
        except Exception as e:
            print(f"Error loading major facilities: {e}")

        # Build source lists HTML
        def build_collapsible_list(title, items, section_id):
            if not items:
                return f'<p><em>No {title.lower()} available</em></p>'

            items_html = ''.join([f'<li>{item}</li>' for item in sorted(items)])
            return f'''
                <details>
                    <summary><strong>{title}</strong> ({len(items)} sources)</summary>
                    <ul class="source-list">
                        {items_html}
                    </ul>
                </details>
            '''

        sources_section = f'''
        <h2>Complete Source List</h2>
        <p>
            This crawler monitors {len(peer_institutions) + len(r1_universities) + len(major_facilities)} sources across three categories:
        </p>

        <div class="sources-section">
            {build_collapsible_list("Peer Institutions", peer_institutions, "peer")}
            {build_collapsible_list("R1 Universities", r1_universities, "r1")}
            {build_collapsible_list("Major Research Facilities", major_facilities, "facilities")}
        </div>
        '''

        return f'''<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>How It Works - AI University News</title>
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}

        body {{
            font-family: 'Courier New', Courier, monospace;
            background-color: #ffffff;
            color: #000000;
            max-width: 1400px;
            margin: 0 auto;
            padding: 20px 40px;
            line-height: 1.6;
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

        .content {{
            padding: 20px 0;
        }}

        h2 {{
            font-size: 28px;
            color: #cc0000;
            margin: 30px 0 15px 0;
            padding-bottom: 8px;
            border-bottom: 2px solid #cc0000;
        }}

        h3 {{
            font-size: 20px;
            color: #000;
            margin: 20px 0 10px 0;
        }}

        p {{
            margin-bottom: 15px;
            font-size: 15px;
        }}

        ul, ol {{
            margin: 15px 0 15px 30px;
        }}

        li {{
            margin-bottom: 10px;
            font-size: 15px;
        }}

        code {{
            background-color: #f5f5f5;
            padding: 2px 6px;
            border-radius: 3px;
            font-family: 'Courier New', Courier, monospace;
        }}

        .highlight-box {{
            background-color: #fffbf0;
            border: 2px solid #cc0000;
            padding: 20px;
            margin: 20px 0;
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

        .sources-section {{
            margin: 20px 0;
        }}

        details {{
            margin: 15px 0;
            padding: 15px;
            background-color: #f9f9f9;
            border: 1px solid #ddd;
            border-radius: 5px;
        }}

        summary {{
            cursor: pointer;
            font-size: 18px;
            padding: 10px;
            background-color: #f5f5f5;
            border-radius: 3px;
            user-select: none;
        }}

        summary:hover {{
            background-color: #e8e8e8;
        }}

        .source-list {{
            margin: 15px 0 0 20px;
            list-style-type: disc;
            column-count: 3;
            column-gap: 20px;
        }}

        .source-list li {{
            margin-bottom: 8px;
            break-inside: avoid;
        }}

        @media (max-width: 1200px) {{
            .source-list {{
                column-count: 2;
            }}
        }}

        @media (max-width: 768px) {{
            .source-list {{
                column-count: 1;
            }}
        }}
    </style>
</head>
<body>
    <div class="header">
        <h1>AI UNIVERSITY NEWS</h1>
        <div class="tagline">How It Works</div>
    </div>

    <div class="nav">
        <a href="index.html">TODAY</a>
        <a href="archive/index.html">ARCHIVE</a>
        <a href="how_it_works.html">HOW IT WORKS</a>
    </div>

    <div class="content">
        <h2>Overview</h2>
        <p>
            AI University News is an automated web crawler that monitors press releases and news articles from
            top US universities and major research facilities, focusing specifically on AI-related research and
            developments. The system runs daily to discover, analyze, and report the latest AI breakthroughs
            from the academic world.
        </p>

        <div class="highlight-box">
            <strong>What makes this unique:</strong> Unlike general news aggregators, this crawler specifically
            targets university press offices and applies multi-AI analysis to identify truly significant AI research,
            filtering out noise and delivering high-quality, relevant content.
        </div>

        <h2>How the Crawler Works</h2>

        <h3>Phase 1: Discovery & Crawling</h3>
        <p>
            The crawler visits official news and press release pages from:
        </p>
        <ul>
            <li><strong>Peer Institutions:</strong> Top-tier research universities (MIT, Stanford, Carnegie Mellon, etc.)</li>
            <li><strong>R1 Universities:</strong> All Carnegie R1 research universities across the United States</li>
            <li><strong>Major Facilities:</strong> National labs and research centers (Argonne, Los Alamos, NIST, etc.)</li>
        </ul>
        <p>
            Using the Scrapy framework, the system respectfully crawls these sites following robots.txt rules,
            implementing politeness delays between requests, and using proper identification.
        </p>

        <h3>Phase 2: Content Extraction</h3>
        <p>
            When new articles are discovered, the crawler uses Trafilatura (a state-of-the-art content extraction
            library) to extract clean article text, metadata, publication dates, and author information with
            95%+ accuracy.
        </p>

        <h3>Phase 3: Deduplication</h3>
        <p>
            The system maintains a PostgreSQL database tracking every URL and content hash to ensure:
        </p>
        <ul>
            <li>No duplicate URLs are processed</li>
            <li>Updated articles are detected through content hash comparison</li>
            <li>Fast O(1) lookups using SHA-256 hashing</li>
        </ul>

        <h3>Phase 4: AI Analysis</h3>
        <p>
            This is where the magic happens. Each new article is analyzed by three different AI systems:
        </p>
        <ul>
            <li><strong>Claude (Sonnet-4-5):</strong> Primary analysis for deep research understanding</li>
            <li><strong>OpenAI (GPT-4):</strong> Secondary analysis for categorization and validation</li>
            <li><strong>Google Gemini (2.5 Flash):</strong> Fast initial filtering and topic extraction</li>
        </ul>
        <p>
            The system builds a consensus summary from all three AI engines, with Claude's analysis taking priority
            due to its superior research comprehension. Articles are classified by relevance, key topics are extracted,
            and confidence scores are assigned.
        </p>

        <h3>Phase 5: Categorization & Organization</h3>
        <p>
            Articles are automatically organized into three categories:
        </p>
        <ul>
            <li><strong>Peer Institutions:</strong> Elite research universities with the highest AI research output</li>
            <li><strong>R1 Institutions:</strong> Other top-tier research universities</li>
            <li><strong>Major Facilities:</strong> Government labs and national research centers</li>
        </ul>

        <h3>Phase 6: Publishing</h3>
        <p>
            The crawler automatically generates this website with:
        </p>
        <ul>
            <li><strong>Today's Page:</strong> Latest articles from the past 3 days</li>
            <li><strong>Archive:</strong> Historical daily reports accessible by date</li>
            <li><strong>Three-Column Layout:</strong> Easy browsing by institution category</li>
        </ul>
        <p>
            Results can also be delivered via Slack webhooks and email notifications for real-time updates.
        </p>

        <h2>Technical Architecture</h2>

        <h3>Technology Stack</h3>
        <ul>
            <li><strong>Language:</strong> Python 3.11+</li>
            <li><strong>Crawling:</strong> Scrapy 2.11+ with custom spiders</li>
            <li><strong>Content Extraction:</strong> Trafilatura 2.0+ with htmldate</li>
            <li><strong>Database:</strong> PostgreSQL 15+ for metadata and tracking</li>
            <li><strong>AI APIs:</strong> Anthropic Claude, OpenAI GPT, Google Gemini</li>
            <li><strong>Deployment:</strong> Systemd service with daily automated runs</li>
        </ul>

        <h3>Ethical Crawling</h3>
        <p>
            This crawler follows web crawling best practices:
        </p>
        <ul>
            <li>Always respects robots.txt directives</li>
            <li>Implements per-domain rate limiting (1 request/second default)</li>
            <li>Uses descriptive User-Agent with contact information</li>
            <li>Implements exponential backoff for failed requests</li>
            <li>Never attempts to bypass access controls or paywalls</li>
        </ul>

        <h2>Cost & Efficiency</h2>
        <p>
            The system is designed to be cost-effective:
        </p>
        <ul>
            <li><strong>Estimated monthly cost:</strong> ~$36/month for AI API usage (100 articles/day)</li>
            <li><strong>Optimization:</strong> Uses fast Gemini Flash for initial filtering before expensive Claude/GPT-4 calls</li>
            <li><strong>Caching:</strong> All AI responses stored to avoid reprocessing</li>
            <li><strong>Smart limits:</strong> Token limits and max articles per run prevent runaway costs</li>
        </ul>

        <h2>Source Code</h2>
        <p>
            This is an open-source project. The complete source code, documentation, and deployment guides
            are available on GitHub. The system is designed as a standalone Linux application that can be
            deployed on any server with Python 3.11+ and PostgreSQL.
        </p>

        {sources_section}

        <h2>Updates & Schedule</h2>
        <p>
            The crawler runs automatically once per day (typically early morning UTC) and this website updates
            immediately after each run completes. The archive preserves all historical daily reports for
            research and trend analysis.
        </p>
    </div>

    <div class="footer">
        <p>Powered by AI University News Crawler</p>
        <p>Open source project - Built with Scrapy, PostgreSQL, and multi-AI analysis</p>
    </div>
</body>
</html>'''


def generate_all_reports(output_dir: str = "html_output", github_pages_dir: str = None):
    """Generate all HTML reports (current day + archive + how it works)"""
    generator = HTMLReportGenerator(output_dir, github_pages_dir)

    # Generate today's report
    today_file = generator.generate_daily_report()
    print(f"Generated today's report: {today_file}")

    # Generate archive index
    archive_file = generator.generate_archive_index()
    print(f"Generated archive index: {archive_file}")

    # Generate how it works page
    how_it_works_file = generator.generate_how_it_works()
    print(f"Generated how it works page: {how_it_works_file}")

    return today_file, archive_file, how_it_works_file


if __name__ == "__main__":
    generate_all_reports()
