"""
HTML Report Generator - Creates Drudge Report-style static HTML pages
"""
import calendar
import json
import os
import re
from collections import OrderedDict
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

    _NAME_OVERRIDES = {
        # Hostnames that slip through as display names
        "stories.tamu.edu": "Texas A&M University",
        "tamu.edu": "Texas A&M University",
        "usf.edu": "University of South Florida",
        "nist.gov": "NIST",
        # Blog/publication names
        "The Brink": "Boston University",
        # CamelCase concatenations
        "Universityofri": "University of Rhode Island",
        "FloridaAtlantic": "Florida Atlantic University",
        "UMassLowell": "UMass Lowell",
        # Post-cleanup matches (after suffix stripping)
        "Notre Dame": "University of Notre Dame",
    }

    def __init__(self, output_dir: str = "html_output", github_pages_dir: str = None):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

        # Optional separate output for GitHub Pages
        self.github_pages_dir = Path(github_pages_dir) if github_pages_dir else None
        if self.github_pages_dir:
            self.github_pages_dir.mkdir(parents=True, exist_ok=True)

        self.classifier = UniversityClassifier()
        self._source_count = self._count_sources()

    def _count_sources(self) -> int:
        """Count total monitored sources from config files"""
        config_dir = Path(__file__).parent.parent / 'config'
        count = 0
        for filename, key in [
            ('peer_institutions.json', 'universities'),
            ('r1_universities.json', 'universities'),
            ('major_facilities.json', 'facilities'),
            ('national_laboratories.json', 'facilities'),
            ('global_institutions.json', 'universities'),
        ]:
            try:
                with open(config_dir / filename, 'r') as f:
                    data = json.load(f)
                    count += len(data.get(key, []))
            except Exception:
                pass
        return count

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

    @staticmethod
    def clean_university_name(name: str) -> str:
        """Clean raw university names for display.

        Handles hostnames, CamelCase concatenations, blog names, and noisy suffixes.
        """
        if not name:
            return "Unknown"

        # Check explicit overrides first
        if name in HTMLReportGenerator._NAME_OVERRIDES:
            return HTMLReportGenerator._NAME_OVERRIDES[name]

        # Strip pipe-delimited suffixes: "University of Central Florida News | UCF Today" -> "University of Central Florida News"
        if ' | ' in name:
            name = name.split(' | ')[0].strip()

        # Strip common suffixes
        for suffix in [' News', ' Today', ' Newsroom', ' Stories']:
            if name.endswith(suffix):
                name = name[:-len(suffix)].strip()

        # Check overrides again after cleanup
        if name in HTMLReportGenerator._NAME_OVERRIDES:
            return HTMLReportGenerator._NAME_OVERRIDES[name]

        # Handle bare hostnames (contain dots with a TLD)
        if re.match(r'^[\w.-]+\.(edu|gov|org|com)$', name):
            clean = re.sub(r'\.(edu|gov|org|com)$', '', name)
            parts = clean.split('.')
            readable = parts[-1] if parts else clean
            return readable.replace('-', ' ').replace('_', ' ').title()

        # Fix CamelCase concatenation: "FloridaAtlantic" -> "Florida Atlantic"
        if re.search(r'[a-z][A-Z]', name):
            name = re.sub(r'([a-z])([A-Z])', r'\1 \2', name)

        return name.strip() or "Unknown"

    # ── Favicon ────────────────────────────────────────────────────────────

    @staticmethod
    def _get_favicon_link() -> str:
        return "<link rel=\"icon\" href=\"data:image/svg+xml,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 100 100'><text y='.9em' font-size='90'>&#x1F393;</text></svg>\">"

    # ── CSS Helpers ────────────────────────────────────────────────────────
    # These return plain strings (not f-strings) to avoid brace escaping.

    @staticmethod
    def _get_base_css() -> str:
        """CSS custom properties, reset, header, nav, footer, focus states"""
        return """
        :root {
            --color-bg: #ffffff;
            --color-surface: #fafafa;
            --color-surface-hover: #f0f0f0;
            --color-text: #000000;
            --color-text-secondary: #333333;
            --color-text-muted: #666666;
            --color-text-faint: #999999;
            --color-accent: #cc0000;
            --color-link: #0000cc;
            --color-link-visited: #551a8b;
            --color-border: #dddddd;
            --color-border-strong: #000000;
            --color-nav-bg: #f5f5f5;
            --color-highlight-bg: #fffbf0;

            --color-peer: #8b0000;
            --color-peer-bg: #fff5f5;
            --color-r1: #00008b;
            --color-r1-bg: #f5f5ff;
            --color-facility: #8b6914;
            --color-facility-bg: #fffbf0;
            --color-lab: #006400;
            --color-lab-bg: #f0fff0;
            --color-global: #4b0082;
            --color-global-bg: #f8f0ff;

            --shadow-sm: 0 1px 3px rgba(0,0,0,0.08);
            --shadow-md: 0 2px 8px rgba(0,0,0,0.1);
            --radius-sm: 3px;
            --radius-md: 6px;
            --transition-fast: 150ms ease;

            --space-xs: 4px;
            --space-sm: 8px;
            --space-md: 16px;
            --space-lg: 24px;
            --space-xl: 32px;
            --space-2xl: 48px;
        }

        * { margin: 0; padding: 0; box-sizing: border-box; }

        body {
            font-family: 'Courier New', Courier, monospace;
            background-color: var(--color-bg);
            color: var(--color-text);
            max-width: 1800px;
            margin: 0 auto;
            padding: 20px 40px;
            line-height: 1.5;
        }

        :focus-visible {
            outline: 2px solid var(--color-accent);
            outline-offset: 2px;
        }
        a:focus:not(:focus-visible) { outline: none; }

        /* ── Header ── */
        .header {
            text-align: center;
            border-bottom: 3px solid var(--color-border-strong);
            padding-bottom: var(--space-lg);
            margin-bottom: var(--space-xl);
        }
        .header h1 {
            font-size: 42px;
            font-weight: bold;
            letter-spacing: -1px;
            margin-bottom: var(--space-sm);
        }
        .header .tagline {
            font-size: 14px;
            color: var(--color-text-muted);
            font-style: italic;
        }
        .header .date {
            font-size: 14px;
            color: var(--color-text);
            margin-top: var(--space-md);
            font-weight: bold;
            display: inline-block;
            background: var(--color-nav-bg);
            border-radius: var(--radius-sm);
            padding: var(--space-xs) 12px;
        }

        /* ── Navigation ── */
        .nav {
            text-align: center;
            margin-bottom: var(--space-lg);
            padding: var(--space-sm);
            background-color: var(--color-nav-bg);
            border: 1px solid var(--color-border);
            border-radius: var(--radius-md);
        }
        .nav a {
            color: var(--color-accent);
            text-decoration: none;
            font-weight: bold;
            margin: 0 var(--space-xs);
            font-size: 14px;
            padding: var(--space-sm) var(--space-md);
            border-radius: var(--radius-sm);
            transition: background-color var(--transition-fast), color var(--transition-fast);
            display: inline-block;
        }
        .nav a:hover {
            background-color: var(--color-accent);
            color: #ffffff;
            text-decoration: none;
        }
        .nav a.active {
            background-color: var(--color-accent);
            color: #ffffff;
        }

        /* ── Footer ── */
        .footer {
            text-align: center;
            margin-top: var(--space-2xl);
            padding-top: var(--space-lg);
            border-top: 2px solid var(--color-border-strong);
            font-size: 12px;
            color: var(--color-text-muted);
        }
        .footer a {
            color: var(--color-text-muted);
            text-decoration: none;
            margin: 0 var(--space-sm);
            transition: color var(--transition-fast);
        }
        .footer a:hover { color: var(--color-accent); }
        .footer .footer-nav { margin-bottom: var(--space-sm); }
        .footer .footer-nav a { font-weight: bold; }
        .footer .footer-meta { margin-top: var(--space-xs); }

        .no-results {
            text-align: center;
            font-size: 18px;
            color: var(--color-text-muted);
            margin: 40px 0;
        }

        @media (max-width: 600px) {
            body { padding: 10px var(--space-md); }
            .header h1 { font-size: 28px; }
        }
        """

    @staticmethod
    def _get_main_page_css() -> str:
        """Stats pills, three-column layout, articles, responsive breakpoints"""
        return """
        /* ── Stats Pills ── */
        .stats {
            display: flex;
            justify-content: center;
            gap: var(--space-md);
            margin-bottom: var(--space-lg);
            padding: var(--space-md);
            flex-wrap: wrap;
        }
        .stat-pill {
            display: flex;
            flex-direction: column;
            align-items: center;
            padding: var(--space-sm) var(--space-lg);
            background: var(--color-surface);
            border-radius: var(--radius-md);
            border-left: 4px solid var(--color-border-strong);
            box-shadow: var(--shadow-sm);
            min-width: 80px;
        }
        .stat-pill .stat-number {
            font-size: 28px;
            font-weight: bold;
            line-height: 1;
        }
        .stat-pill .stat-label {
            font-size: 10px;
            text-transform: uppercase;
            color: var(--color-text-muted);
            letter-spacing: 1px;
            margin-top: var(--space-xs);
        }
        .stat-peer { border-left-color: var(--color-peer); }
        .stat-r1 { border-left-color: var(--color-r1); }
        .stat-facility { border-left-color: var(--color-facility); }
        .stat-lab { border-left-color: var(--color-lab); }
        .stat-global { border-left-color: var(--color-global); }

        /* ── Five-Column Layout ── */
        .five-column-layout {
            display: grid;
            grid-template-columns: repeat(5, 1fr);
            gap: var(--space-md);
            margin-top: var(--space-lg);
            align-items: start;
        }
        .column {
            border: 1px solid var(--color-border);
            padding: var(--space-md);
            background-color: var(--color-surface);
            border-radius: var(--radius-md);
            box-shadow: var(--shadow-sm);
            min-height: 120px;
        }
        .column-title {
            font-size: 16px;
            margin-bottom: var(--space-md);
            padding: var(--space-sm) var(--space-md);
            border-bottom: 3px solid var(--color-accent);
            text-align: center;
            text-transform: uppercase;
            letter-spacing: 1px;
        }
        .column-peer .column-title {
            color: var(--color-peer);
            border-bottom-color: var(--color-peer);
            background: var(--color-peer-bg);
            border-radius: var(--radius-sm);
        }
        .column-r1 .column-title {
            color: var(--color-r1);
            border-bottom-color: var(--color-r1);
            background: var(--color-r1-bg);
            border-radius: var(--radius-sm);
        }
        .column-facility .column-title {
            color: var(--color-facility);
            border-bottom-color: var(--color-facility);
            background: var(--color-facility-bg);
            border-radius: var(--radius-sm);
        }
        .column-lab .column-title {
            color: var(--color-lab);
            border-bottom-color: var(--color-lab);
            background: var(--color-lab-bg);
            border-radius: var(--radius-sm);
        }
        .column-global .column-title {
            color: var(--color-global);
            border-bottom-color: var(--color-global);
            background: var(--color-global-bg);
            border-radius: var(--radius-sm);
        }
        .no-articles {
            text-align: center;
            color: var(--color-text-faint);
            font-style: italic;
            padding: 20px;
        }

        /* ── University Sections ── */
        .university-section {
            margin-bottom: var(--space-lg);
            border-bottom: 1px solid var(--color-border);
            padding-bottom: var(--space-md);
        }
        .university-section:last-child {
            border-bottom: none;
            margin-bottom: 0;
        }
        .university-section h3 {
            font-size: 16px;
            color: var(--color-text);
            margin-bottom: var(--space-sm);
            padding-bottom: var(--space-xs);
            border-bottom: 1px solid var(--color-accent);
        }

        /* ── Article Cards ── */
        .article {
            margin-bottom: 18px;
            padding: var(--space-sm) var(--space-sm) var(--space-sm) 10px;
            border-radius: var(--radius-sm);
            transition: background-color var(--transition-fast);
        }
        .article:hover {
            background-color: var(--color-surface-hover);
        }
        .headline { margin-bottom: 3px; }
        .headline a {
            color: var(--color-link);
            text-decoration: none;
            font-size: 16px;
            font-weight: bold;
        }
        .headline a:hover {
            text-decoration: underline;
            text-underline-offset: 2px;
        }
        .headline a:visited { color: var(--color-link-visited); }
        .topics {
            display: inline;
            margin-left: var(--space-sm);
        }
        .topic-pill {
            display: inline-block;
            background: var(--color-surface-hover);
            border-radius: 2px;
            padding: 1px 5px;
            margin: 0 2px;
            font-size: 11px;
            color: var(--color-text-muted);
        }
        .meta {
            font-size: 12px;
            color: var(--color-text-muted);
            font-style: italic;
        }
        .summary {
            font-size: 13px;
            color: var(--color-text-secondary);
            margin-top: 5px;
            padding-left: 10px;
            line-height: 1.5;
        }

        /* ── Responsive ── */
        @media (min-width: 1025px) and (max-width: 1400px) {
            .five-column-layout {
                grid-template-columns: repeat(3, 1fr);
            }
        }
        @media (min-width: 769px) and (max-width: 1024px) {
            .five-column-layout {
                grid-template-columns: 1fr 1fr;
            }
        }
        @media (max-width: 768px) {
            .five-column-layout {
                grid-template-columns: 1fr;
            }
            .column { padding: 10px; }
            .headline a { font-size: 15px; }
        }
        @media (max-width: 480px) {
            .stats {
                flex-direction: column;
                align-items: center;
            }
            .stat-pill { width: 100%; }
        }
        """

    @staticmethod
    def _get_archive_page_css() -> str:
        """Monthly groupings, bar chart rows, responsive"""
        return """
        .archive-month {
            margin-bottom: var(--space-2xl);
        }
        .month-heading {
            font-size: 20px;
            font-weight: bold;
            padding-bottom: var(--space-sm);
            margin-bottom: var(--space-md);
            border-bottom: 2px solid var(--color-border-strong);
        }
        .archive-row {
            display: grid;
            grid-template-columns: 140px 1fr 60px;
            align-items: center;
            gap: var(--space-md);
            padding: var(--space-sm) var(--space-md);
            text-decoration: none;
            color: var(--color-text);
            border-radius: var(--radius-sm);
            transition: background-color var(--transition-fast);
        }
        .archive-row:hover {
            background-color: var(--color-surface-hover);
        }
        .archive-date {
            font-weight: bold;
            font-size: 14px;
            color: var(--color-link);
        }
        .archive-row:hover .archive-date {
            text-decoration: underline;
            text-underline-offset: 2px;
        }
        .archive-bar-container {
            height: 6px;
            background: var(--color-surface-hover);
            border-radius: 3px;
            overflow: hidden;
        }
        .archive-bar {
            display: block;
            height: 100%;
            background: var(--color-accent);
            border-radius: 3px;
            min-width: 0;
        }
        .archive-count {
            text-align: right;
            font-size: 14px;
            font-weight: bold;
            color: var(--color-text-secondary);
        }
        .archive-row-empty {
            opacity: 0.5;
        }
        .archive-row-empty .archive-date {
            color: var(--color-text-muted);
        }
        @media (max-width: 600px) {
            .archive-row {
                grid-template-columns: 100px 1fr 40px;
                padding: var(--space-sm);
            }
            .archive-date { font-size: 12px; }
        }
        """

    @staticmethod
    def _get_how_it_works_css() -> str:
        """Content typography, highlight box, details/summary, source lists"""
        return """
        .content {
            max-width: 900px;
            margin: 0 auto;
            padding: 20px 0;
        }
        .content h2 {
            font-size: 28px;
            color: var(--color-accent);
            margin: 30px 0 15px 0;
            padding-bottom: 8px;
            border-bottom: 2px solid var(--color-accent);
        }
        .content h3 {
            font-size: 20px;
            color: var(--color-text);
            margin: 20px 0 10px 0;
        }
        .content p {
            margin-bottom: 15px;
            font-size: 15px;
            line-height: 1.7;
        }
        .content ul, .content ol {
            margin: 15px 0 15px 30px;
        }
        .content li {
            margin-bottom: 10px;
            font-size: 15px;
            line-height: 1.7;
        }
        code {
            background-color: var(--color-nav-bg);
            padding: 2px 6px;
            border-radius: var(--radius-sm);
            font-family: 'Courier New', Courier, monospace;
        }
        .highlight-box {
            background-color: var(--color-highlight-bg);
            border-left: 4px solid var(--color-accent);
            padding: 20px;
            margin: 20px 0;
            border-radius: 0 var(--radius-md) var(--radius-md) 0;
        }
        .sources-section { margin: 20px 0; }
        details {
            margin: 15px 0;
            padding: 15px;
            background-color: var(--color-surface);
            border: 1px solid var(--color-border);
            border-radius: var(--radius-md);
        }
        summary {
            cursor: pointer;
            font-size: 18px;
            padding: 10px;
            background-color: var(--color-nav-bg);
            border-radius: var(--radius-sm);
            user-select: none;
            transition: background-color var(--transition-fast);
        }
        summary:hover { background-color: #e8e8e8; }
        .source-list {
            margin: 15px 0 0 20px;
            list-style-type: disc;
            column-count: 3;
            column-gap: 20px;
        }
        .source-list li {
            margin-bottom: 8px;
            break-inside: avoid;
        }
        @media (max-width: 1200px) {
            .source-list { column-count: 2; }
        }
        @media (max-width: 768px) {
            .source-list { column-count: 1; }
        }
        """

    # ── HTML Component Helpers ─────────────────────────────────────────────

    def _render_header(self, title: str, subtitle: str, date_str: str = None) -> str:
        date_html = f'\n        <div class="date">Updated: {date_str}</div>' if date_str else ''
        return f'''    <div class="header">
        <h1>{title}</h1>
        <div class="tagline">{subtitle}</div>{date_html}
    </div>'''

    def _render_nav(self, active_page: str = None, is_archive: bool = False) -> str:
        if is_archive:
            urls = {"today": "../index.html", "archive": "index.html", "how_it_works": "../how_it_works.html"}
        else:
            urls = {"today": "index.html", "archive": "archive/index.html", "how_it_works": "how_it_works.html"}

        def cls(page):
            return ' class="active"' if page == active_page else ''

        return f'''
    <div class="nav">
        <a href="{urls['today']}"{cls('today')}>TODAY</a>
        <a href="{urls['archive']}"{cls('archive')}>ARCHIVE</a>
        <a href="{urls['how_it_works']}"{cls('how_it_works')}>HOW IT WORKS</a>
    </div>'''

    def _render_footer(self, is_archive: bool = False, timestamp: str = None) -> str:
        if is_archive:
            urls = {"today": "../index.html", "archive": "index.html", "how_it_works": "../how_it_works.html"}
        else:
            urls = {"today": "index.html", "archive": "archive/index.html", "how_it_works": "how_it_works.html"}

        ts = timestamp or datetime.now().strftime('%I:%M %p %Z')

        return f'''
    <div class="footer">
        <div class="footer-nav">
            <a href="{urls['today']}">Today</a> &middot;
            <a href="{urls['archive']}">Archive</a> &middot;
            <a href="{urls['how_it_works']}">How It Works</a> &middot;
            <a href="https://github.com/tyson-swetnam/webcrawler" target="_blank">GitHub</a>
        </div>
        <p>Monitoring {self._source_count} sources daily</p>
        <p class="footer-meta">Last updated: {ts}</p>
    </div>'''

    # ── Public Generation Methods ──────────────────────────────────────────

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
        # Collect archive files from both output directories
        archive_files = {}

        for base_dir in [self.output_dir, self.github_pages_dir]:
            if base_dir is None:
                continue
            archive_dir = base_dir / "archive"
            if not archive_dir.exists():
                continue
            for html_file in archive_dir.glob("20*.html"):
                date_str = html_file.stem  # e.g., "2025-11-08"
                if date_str in archive_files:
                    continue
                content = html_file.read_text(encoding='utf-8')
                # Try new format first (data attribute)
                match = re.search(r'data-total-articles="(\d+)"', content)
                if not match:
                    # Try old format (text pattern)
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

    # ── Private Methods ────────────────────────────────────────────────────

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
        """Render main page with five-column layout"""
        date_str = date.strftime('%A, %B %d, %Y')
        active_page = None if is_archive_page else 'today'

        # Categorize articles by university/facility tier
        peer_articles = {}
        r1_articles = {}
        hpc_articles = {}
        lab_articles = {}
        global_articles = {}

        category_map = {
            'peer': peer_articles,
            'r1': r1_articles,
            'hpc': hpc_articles,
            'national_lab': lab_articles,
            'global': global_articles,
        }

        for article in articles:
            univ = article['university'] or 'Unknown'
            category = self.classifier.classify(univ)
            target_dict = category_map.get(category, r1_articles)

            if univ not in target_dict:
                target_dict[univ] = []
            target_dict[univ].append(article)

        # Helper function to render a column
        def render_column(articles_dict, title, css_class):
            if not articles_dict:
                return f'<div class="column {css_class}"><h2 class="column-title">{title}</h2><p class="no-articles">No articles</p></div>'

            html_parts = [f'<div class="column {css_class}"><h2 class="column-title">{title}</h2>']

            for univ, univ_articles in sorted(articles_dict.items()):
                display_name = self.clean_university_name(univ)
                html_parts.append(f'<div class="university-section"><h3>{display_name}</h3>')

                for article in univ_articles:
                    topics_html = ''
                    if article.get('topics') and isinstance(article['topics'], list):
                        clean_topics = [self.strip_markdown(str(t)) for t in article['topics'][:3] if t]
                        clean_topics = [t for t in clean_topics if t and len(t) < 50]
                        if clean_topics:
                            pills = ''.join(f'<span class="topic-pill">{t}</span>' for t in clean_topics)
                            topics_html = f'<span class="topics">{pills}</span>'

                    summary_html = ''
                    if article.get('summary'):
                        plain_summary = self.strip_markdown(article['summary'])
                        if len(plain_summary) > 200:
                            plain_summary = plain_summary[:200].rsplit(' ', 1)[0] + '...'
                        summary_html = f'<div class="summary">{plain_summary}</div>'

                    pub_date_str = ''
                    if article.get('published_date'):
                        if isinstance(article['published_date'], str):
                            pub_date_str = article['published_date']
                        else:
                            pub_date_str = article['published_date'].strftime('%B %d, %Y')

                    crawl_date_str = article['timestamp'].strftime('%B %d, %Y')

                    if pub_date_str and pub_date_str != crawl_date_str:
                        meta_html = f'<div class="meta">Published: {pub_date_str} | Crawled: {crawl_date_str}</div>'
                    elif pub_date_str:
                        meta_html = f'<div class="meta">Published: {pub_date_str}</div>'
                    else:
                        meta_html = f'<div class="meta">Crawled: {crawl_date_str}</div>'

                    html_parts.append(f'''
                        <div class="article">
                            <div class="headline">
                                <a href="{article['url']}" target="_blank">{article['title']}</a>
                                {topics_html}
                            </div>
                            {meta_html}
                            {summary_html}
                        </div>
                    ''')

                html_parts.append('</div>')

            html_parts.append('</div>')
            return '\n'.join(html_parts)

        # Build five-column HTML
        columns_html = f'''
            <div class="five-column-layout">
                {render_column(peer_articles, "Peer Institutions", "column-peer")}
                {render_column(r1_articles, "R1 Institutions", "column-r1")}
                {render_column(hpc_articles, "HPC &amp; Research Centers", "column-facility")}
                {render_column(lab_articles, "National Laboratories", "column-lab")}
                {render_column(global_articles, "Global Institutions", "column-global")}
            </div>
        '''

        # Stats pills
        total = len(articles)
        peer_count = sum(len(arts) for arts in peer_articles.values())
        r1_count = sum(len(arts) for arts in r1_articles.values())
        hpc_count = sum(len(arts) for arts in hpc_articles.values())
        lab_count = sum(len(arts) for arts in lab_articles.values())
        global_count = sum(len(arts) for arts in global_articles.values())

        stats_html = f'''
            <div class="stats" data-total-articles="{total}">
                <div class="stat-pill"><span class="stat-number">{total}</span><span class="stat-label">TOTAL</span></div>
                <div class="stat-pill stat-peer"><span class="stat-number">{peer_count}</span><span class="stat-label">PEER</span></div>
                <div class="stat-pill stat-r1"><span class="stat-number">{r1_count}</span><span class="stat-label">R1</span></div>
                <div class="stat-pill stat-facility"><span class="stat-number">{hpc_count}</span><span class="stat-label">HPC</span></div>
                <div class="stat-pill stat-lab"><span class="stat-number">{lab_count}</span><span class="stat-label">LABS</span></div>
                <div class="stat-pill stat-global"><span class="stat-number">{global_count}</span><span class="stat-label">GLOBAL</span></div>
            </div>
        '''

        articles_html = stats_html + columns_html if articles else '<p class="no-results">No AI-related articles found for this date.</p>'

        base_css = self._get_base_css()
        main_css = self._get_main_page_css()
        header_html = self._render_header("AI UNIVERSITY NEWS", "Latest AI Research &amp; Developments from Universities &amp; Labs Worldwide (Last 5 Days)", date_str)
        nav_html = self._render_nav(active_page, is_archive_page)
        footer_html = self._render_footer(is_archive_page)
        favicon = self._get_favicon_link()

        return f'''<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>AI University News - {date_str}</title>
    {favicon}
    <style>
    {base_css}
    {main_css}
    </style>
</head>
<body>
{header_html}
{nav_html}

    {articles_html}

{footer_html}
</body>
</html>'''

    def _render_archive_page(self, dates: List) -> str:
        """Render archive index page with monthly groups and bar chart"""
        # Group by month
        monthly_groups = OrderedDict()
        max_count = max((count for _, count in dates if count > 0), default=1)

        for date_obj, count in dates:
            if isinstance(date_obj, str):
                date_obj = datetime.strptime(date_obj, '%Y-%m-%d').date()
            key = (date_obj.year, date_obj.month)
            if key not in monthly_groups:
                monthly_groups[key] = []
            monthly_groups[key].append((date_obj, count))

        groups_html = []
        if not dates:
            groups_html.append('<p class="no-results">No archived reports available</p>')
        else:
            for (year, month), entries in monthly_groups.items():
                month_name = calendar.month_name[month]
                heading = f"{month_name} {year}"

                rows = []
                for date_obj, count in entries:
                    filename = f"{date_obj.strftime('%Y-%m-%d')}.html"
                    short_date = date_obj.strftime('%a, %b %d')
                    bar_width = (count / max_count * 100) if count > 0 else 0
                    row_class = "archive-row" if count > 0 else "archive-row archive-row-empty"

                    rows.append(f'''
                <a href="{filename}" class="{row_class}">
                    <span class="archive-date">{short_date}</span>
                    <span class="archive-bar-container">
                        <span class="archive-bar" style="width: {bar_width:.1f}%"></span>
                    </span>
                    <span class="archive-count">{count}</span>
                </a>''')

                groups_html.append(f'''
            <div class="archive-month">
                <h2 class="month-heading">{heading}</h2>
                {''.join(rows)}
            </div>''')

        base_css = self._get_base_css()
        archive_css = self._get_archive_page_css()
        header_html = self._render_header("AI UNIVERSITY NEWS", "Archive")
        nav_html = self._render_nav('archive', is_archive=True)
        footer_html = self._render_footer(is_archive=True)
        favicon = self._get_favicon_link()

        return f'''<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Archive - AI University News</title>
    {favicon}
    <style>
    {base_css}
    {archive_css}
    </style>
</head>
<body>
{header_html}
{nav_html}

    {''.join(groups_html)}

{footer_html}
</body>
</html>'''

    def _render_how_it_works_page(self) -> str:
        """Render 'How It Works' documentation page"""
        # Load source lists
        config_dir = Path(__file__).parent.parent / 'config'

        def load_names(filename, key, name_field='name'):
            try:
                with open(config_dir / filename, 'r') as f:
                    data = json.load(f)
                    return [item[name_field] for item in data.get(key, [])]
            except Exception:
                return []

        peer_institutions = load_names('peer_institutions.json', 'universities')
        r1_universities = load_names('r1_universities.json', 'universities')
        hpc_centers = load_names('major_facilities.json', 'facilities')
        national_labs = load_names('national_laboratories.json', 'facilities')
        global_institutions = load_names('global_institutions.json', 'universities')

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

        total_sources = len(peer_institutions) + len(r1_universities) + len(hpc_centers) + len(national_labs) + len(global_institutions)

        sources_section = f'''
        <h2>Complete Source List</h2>
        <p>
            This crawler monitors {total_sources} sources across five categories:
        </p>

        <div class="sources-section">
            {build_collapsible_list("Peer Institutions", peer_institutions, "peer")}
            {build_collapsible_list("R1 Universities", r1_universities, "r1")}
            {build_collapsible_list("HPC & Research Centers", hpc_centers, "hpc")}
            {build_collapsible_list("National Laboratories", national_labs, "labs")}
            {build_collapsible_list("Global Institutions", global_institutions, "global")}
        </div>
        '''

        base_css = self._get_base_css()
        hiw_css = self._get_how_it_works_css()
        header_html = self._render_header("AI UNIVERSITY NEWS", "How It Works")
        nav_html = self._render_nav('how_it_works', is_archive=False)
        footer_html = self._render_footer(is_archive=False)
        favicon = self._get_favicon_link()

        return f'''<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>How It Works - AI University News</title>
    {favicon}
    <style>
    {base_css}
    {hiw_css}
    </style>
</head>
<body>
{header_html}
{nav_html}

    <div class="content">
        <h2>Overview</h2>
        <p>
            AI University News is an automated web crawler that monitors press releases and news articles from
            top universities, national laboratories, and research institutions worldwide, focusing specifically on
            AI-related research and developments. The system runs daily to discover, analyze, and report the latest
            AI breakthroughs from academia and research labs.
        </p>

        <div class="highlight-box">
            <strong>What makes this unique:</strong> Unlike general news aggregators, this crawler specifically
            targets university press offices and applies multi-AI analysis to identify truly significant AI research,
            filtering out noise and delivering high-quality, relevant content.
        </div>

        <h2>How the Crawler Works</h2>

        <h3>Phase 1: Discovery &amp; Crawling</h3>
        <p>
            The crawler visits official news and press release pages from:
        </p>
        <ul>
            <li><strong>Peer Institutions:</strong> Top-tier research universities (MIT, Stanford, Carnegie Mellon, etc.)</li>
            <li><strong>R1 Universities:</strong> All Carnegie R1 research universities across the United States</li>
            <li><strong>HPC &amp; Research Centers:</strong> NSF supercomputing centers and DOE computing facilities (TACC, SDSC, NERSC, etc.)</li>
            <li><strong>National Laboratories:</strong> DOE labs, federal research labs, and FFRDCs (Argonne, DARPA, MITRE, etc.)</li>
            <li><strong>Global Institutions:</strong> Leading international universities and research organizations (Oxford, ETH Zurich, Tsinghua, etc.)</li>
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

        <h3>Phase 5: Categorization &amp; Organization</h3>
        <p>
            Articles are automatically organized into five categories:
        </p>
        <ul>
            <li><strong>Peer Institutions:</strong> Elite research universities with the highest AI research output</li>
            <li><strong>R1 Institutions:</strong> All US Carnegie R1 research universities</li>
            <li><strong>HPC &amp; Research Centers:</strong> NSF supercomputing centers and DOE computing facilities</li>
            <li><strong>National Laboratories:</strong> DOE national labs, federal government research labs, and FFRDCs</li>
            <li><strong>Global Institutions:</strong> Leading international universities and research organizations</li>
        </ul>

        <h3>Phase 6: Publishing</h3>
        <p>
            The crawler automatically generates this website with:
        </p>
        <ul>
            <li><strong>Today's Page:</strong> Latest articles from the past 3 days</li>
            <li><strong>Archive:</strong> Historical daily reports accessible by date</li>
            <li><strong>Five-Column Layout:</strong> Easy browsing by institution category</li>
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

        <h2>Cost &amp; Efficiency</h2>
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

        <h2>Updates &amp; Schedule</h2>
        <p>
            The crawler runs automatically once per day (typically early morning UTC) and this website updates
            immediately after each run completes. The archive preserves all historical daily reports for
            research and trend analysis.
        </p>
    </div>

{footer_html}
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
