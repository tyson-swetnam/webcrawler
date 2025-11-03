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

    def __init__(self, output_dir: str = "html_output"):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
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

        html = self._render_main_page(articles, date)

        # Write to index.html for current day
        if date.date() == datetime.now().date():
            output_file = self.output_dir / "index.html"
        else:
            # Archive files by date
            archive_dir = self.output_dir / "archive"
            archive_dir.mkdir(exist_ok=True)
            output_file = archive_dir / f"{date.strftime('%Y-%m-%d')}.html"

        output_file.write_text(html, encoding='utf-8')
        return str(output_file)

    def generate_archive_index(self) -> str:
        """Generate archive index page listing all available dates"""
        with get_db() as session:
            # Get all unique dates with articles
            stmt = (
                select(func.date(Article.first_scraped).label('date'), func.count(Article.article_id).label('count'))
                .where(Article.is_ai_related == True)
                .group_by(func.date(Article.first_scraped))
                .order_by(func.date(Article.first_scraped).desc())
            )
            dates = session.execute(stmt).all()

        html = self._render_archive_page(dates)

        archive_dir = self.output_dir / "archive"
        archive_dir.mkdir(exist_ok=True)
        output_file = archive_dir / "index.html"
        output_file.write_text(html, encoding='utf-8')

        return str(output_file)

    def _fetch_articles_for_date(self, session: Session, date: datetime) -> List[Dict]:
        """Fetch AI-related articles for the last 3 days"""
        end_date = date.replace(hour=23, minute=59, second=59, microsecond=999999)
        start_date = end_date - timedelta(days=3)

        stmt = (
            select(Article, AIAnalysis)
            .outerjoin(AIAnalysis, Article.article_id == AIAnalysis.article_id)
            .where(
                and_(
                    Article.is_ai_related == True,
                    Article.first_scraped >= start_date,
                    Article.first_scraped <= end_date
                )
            )
            .order_by(Article.first_scraped.desc())
        )

        results = session.execute(stmt).all()

        articles = []
        for article, ai_analysis in results:
            articles.append({
                'url': article.url.url if article.url else '',
                'title': article.title or 'Untitled',
                'university': article.university_name,
                'timestamp': article.first_scraped,
                'summary': ai_analysis.consensus_summary if ai_analysis else None,
                'topics': ai_analysis.claude_key_points if ai_analysis else [],
                'category': ai_analysis.openai_category if ai_analysis else None
            })

        return articles

    def _render_main_page(self, articles: List[Dict], date: datetime) -> str:
        """Render main page with three-column layout: Peer Institutions, R1 Institutions, Major Facilities"""
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

                    html.append(f'''
                        <div class="article">
                            <div class="headline">
                                <a href="{article['url']}" target="_blank">{article['title']}</a>
                                {topics_html}
                            </div>
                            <div class="meta">{article['timestamp'].strftime('%B %d, %Y')}</div>
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
        <div class="tagline">Latest AI Research & Developments from Top Universities (Last 3 Days)</div>
        <div class="date">Updated: {date_str}</div>
    </div>

    <div class="nav">
        <a href="index.html">TODAY</a>
        <a href="archive/index.html">ARCHIVE</a>
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


def generate_all_reports(output_dir: str = "html_output"):
    """Generate all HTML reports (current day + archive)"""
    generator = HTMLReportGenerator(output_dir)

    # Generate today's report
    today_file = generator.generate_daily_report()
    print(f"Generated today's report: {today_file}")

    # Generate archive index
    archive_file = generator.generate_archive_index()
    print(f"Generated archive index: {archive_file}")

    return today_file, archive_file


if __name__ == "__main__":
    generate_all_reports()
