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
            --color-surface: #f8f9fa;
            --color-surface-alt: #f1f3f5;
            --color-surface-hover: #e9ecef;
            --color-border: #dee2e6;
            --color-text: #212529;
            --color-text-secondary: #495057;
            --color-text-muted: #868e96;
            --color-text-faint: #adb5bd;
            --color-link: #1a1a2e;
            --color-link-visited: #3d3d5c;
            --color-focus: #4dabf7;
            --color-highlight-bg: #f8f9fa;

            --color-peer: #7c3aed;
            --color-r1: #2563eb;
            --color-hpc: #d97706;
            --color-lab: #059669;
            --color-global: #dc2626;

            --radius-sm: 4px;
            --radius-md: 6px;
            --transition-fast: 150ms ease;

            --space-xs: 4px;
            --space-sm: 8px;
            --space-md: 16px;
            --space-lg: 24px;
            --space-xl: 32px;
        }

        * { margin: 0; padding: 0; box-sizing: border-box; }

        body {
            font-family: 'DM Sans', system-ui, -apple-system, sans-serif;
            background-color: var(--color-bg);
            color: var(--color-text);
            max-width: 1200px;
            margin: 0 auto;
            padding: 0 var(--space-lg);
            line-height: 1.5;
            font-size: 14px;
        }

        :focus-visible {
            outline: 2px solid var(--color-focus);
            outline-offset: 2px;
        }
        a:focus:not(:focus-visible) { outline: none; }

        /* ── Compact Header ── */
        .header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            padding: 12px 0;
            border-bottom: 1px solid var(--color-border);
            margin-bottom: var(--space-md);
            min-height: 48px;
        }
        .header h1 {
            font-size: 16px;
            font-weight: 700;
            letter-spacing: 0.08em;
            text-transform: uppercase;
            color: var(--color-text);
            white-space: nowrap;
        }
        .header-right {
            display: flex;
            align-items: center;
            gap: var(--space-md);
            font-size: 13px;
            color: var(--color-text-muted);
        }
        .header-meta {
            white-space: nowrap;
        }
        .header-nav a {
            color: var(--color-text-muted);
            text-decoration: none;
            font-size: 13px;
            font-weight: 500;
            transition: color var(--transition-fast);
        }
        .header-nav a:hover { color: var(--color-text); }
        .header-nav a.active {
            color: var(--color-text);
            font-weight: 600;
        }

        /* ── Footer ── */
        .footer {
            text-align: center;
            margin-top: var(--space-xl);
            padding: var(--space-md) 0;
            border-top: 1px solid var(--color-border);
            font-size: 12px;
            color: var(--color-text-muted);
        }
        .footer a {
            color: var(--color-text-muted);
            text-decoration: none;
            transition: color var(--transition-fast);
        }
        .footer a:hover { color: var(--color-text); }

        .no-results {
            text-align: center;
            font-size: 15px;
            color: var(--color-text-muted);
            margin: 60px 0;
        }

        @media (max-width: 600px) {
            body { padding: 0 var(--space-md); }
            .header { flex-direction: column; gap: var(--space-sm); align-items: flex-start; }
            .header-right { flex-wrap: wrap; }
        }
        """

    @staticmethod
    def _get_main_page_css() -> str:
        """Tab bar, article rows, expand panels, show-more, responsive"""
        return """
        /* ── Stats Line ── */
        .stats-line {
            font-size: 13px;
            color: var(--color-text-muted);
            margin-bottom: var(--space-md);
            display: flex;
            align-items: center;
            gap: var(--space-sm);
            flex-wrap: wrap;
        }
        .stats-line .cat-dot {
            display: inline-block;
            width: 6px;
            height: 6px;
            border-radius: 50%;
            margin-right: 2px;
            vertical-align: middle;
        }
        .dot-peer { background: var(--color-peer); }
        .dot-r1 { background: var(--color-r1); }
        .dot-hpc { background: var(--color-hpc); }
        .dot-lab { background: var(--color-lab); }
        .dot-global { background: var(--color-global); }

        /* ── Tab Bar ── */
        .tab-bar {
            display: flex;
            gap: 0;
            border-bottom: 1px solid var(--color-border);
            margin-bottom: 0;
            overflow-x: auto;
            -webkit-overflow-scrolling: touch;
        }
        .tab-btn {
            padding: 10px var(--space-md);
            border: none;
            background: none;
            font-family: 'DM Sans', system-ui, sans-serif;
            font-size: 13px;
            font-weight: 600;
            color: var(--color-text-muted);
            cursor: pointer;
            white-space: nowrap;
            border-bottom: 2px solid transparent;
            transition: color var(--transition-fast), border-color var(--transition-fast);
        }
        .tab-btn:hover { color: var(--color-text-secondary); }
        .tab-btn.active {
            color: var(--color-text);
            border-bottom-color: var(--color-text);
        }
        .tab-btn.tab-empty {
            opacity: 0.4;
            cursor: default;
        }
        .tab-count {
            font-weight: 400;
            font-size: 12px;
            color: var(--color-text-faint);
            margin-left: 3px;
        }

        /* ── Article List ── */
        .article-list {
            margin: 0;
        }

        /* ── University Group Subheader ── */
        .univ-group-header {
            font-size: 11px;
            font-weight: 600;
            text-transform: uppercase;
            letter-spacing: 0.05em;
            color: var(--color-text-muted);
            padding: var(--space-sm) 0 var(--space-xs) 0;
            margin-top: var(--space-sm);
            border-bottom: 1px solid var(--color-surface-alt);
        }
        .univ-group-header:first-child { margin-top: 0; }

        /* ── Article Row ── */
        .article-row {
            display: grid;
            grid-template-columns: 8px 1fr auto auto 20px;
            align-items: center;
            gap: var(--space-sm);
            padding: 10px var(--space-sm);
            border-bottom: 1px solid var(--color-surface-alt);
            cursor: pointer;
            transition: background-color var(--transition-fast);
            min-height: 40px;
        }
        .article-row:hover { background-color: var(--color-surface); }
        .article-row .cat-dot {
            display: inline-block;
            width: 6px;
            height: 6px;
            border-radius: 50%;
        }
        .article-row .headline-link {
            font-size: 14px;
            font-weight: 500;
            color: var(--color-link);
            text-decoration: none;
            overflow: hidden;
            text-overflow: ellipsis;
            white-space: nowrap;
        }
        .article-row .headline-link:hover { text-decoration: underline; text-underline-offset: 2px; }
        .article-row .headline-link:visited { color: var(--color-link-visited); }
        .article-row .univ-label {
            font-size: 12px;
            color: var(--color-text-muted);
            white-space: nowrap;
        }
        .article-row .date-label {
            font-size: 12px;
            color: var(--color-text-faint);
            white-space: nowrap;
        }
        .article-row .chevron {
            display: flex;
            align-items: center;
            justify-content: center;
            width: 20px;
            font-size: 10px;
            color: var(--color-text-faint);
            transition: transform 0.2s ease;
        }
        .article-row.expanded .chevron { transform: rotate(90deg); }

        /* ── Article Detail (expand panel) ── */
        .article-detail {
            display: none;
            padding: var(--space-sm) var(--space-md) var(--space-md) 22px;
            border-bottom: 1px solid var(--color-surface-alt);
            background: var(--color-surface);
        }
        .article-detail.open { display: block; }
        .article-detail .summary {
            font-size: 13px;
            color: var(--color-text-secondary);
            line-height: 1.6;
            margin-bottom: var(--space-sm);
        }
        .article-detail .detail-meta {
            font-size: 12px;
            color: var(--color-text-muted);
            margin-bottom: var(--space-sm);
        }
        .article-detail .topics { margin-bottom: var(--space-sm); }
        .topic-pill {
            display: inline-block;
            background: var(--color-surface-alt);
            border-radius: var(--radius-sm);
            padding: 2px 8px;
            margin: 2px 3px 2px 0;
            font-size: 11px;
            color: var(--color-text-secondary);
        }
        .article-detail .detail-link a {
            font-size: 12px;
            color: var(--color-link);
            text-decoration: none;
            font-weight: 500;
        }
        .article-detail .detail-link a:hover { text-decoration: underline; }

        /* ── Show More ── */
        .article-overflow { display: none; }
        .article-overflow.shown { display: grid; }
        .show-more-btn {
            display: block;
            width: 100%;
            padding: 10px;
            margin-top: var(--space-xs);
            background: var(--color-surface);
            border: 1px solid var(--color-border);
            border-radius: var(--radius-sm);
            cursor: pointer;
            font-family: 'DM Sans', system-ui, sans-serif;
            font-size: 13px;
            font-weight: 500;
            color: var(--color-text-secondary);
            text-align: center;
            transition: background-color var(--transition-fast);
        }
        .show-more-btn:hover { background: var(--color-surface-hover); }

        /* ── Responsive ── */
        @media (max-width: 768px) {
            .article-row {
                grid-template-columns: 6px 1fr 20px;
                gap: var(--space-xs);
                padding: var(--space-sm) var(--space-xs);
            }
            .article-row .univ-label,
            .article-row .date-label { display: none; }
            .article-row .headline-link {
                white-space: normal;
                font-size: 13px;
            }
            .tab-bar { gap: 0; }
            .tab-btn { padding: 8px 10px; font-size: 12px; }
        }
        @media (max-width: 480px) {
            .stats-line { font-size: 12px; }
        }
        """

    @staticmethod
    def _get_archive_page_css() -> str:
        """Monthly groupings, bar chart rows, responsive"""
        return """
        .archive-month {
            margin-bottom: var(--space-xl);
        }
        .month-heading {
            font-size: 15px;
            font-weight: 600;
            padding-bottom: var(--space-sm);
            margin-bottom: var(--space-sm);
            border-bottom: 1px solid var(--color-border);
            color: var(--color-text);
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
            background-color: var(--color-surface);
        }
        .archive-date {
            font-weight: 500;
            font-size: 14px;
            color: var(--color-link);
        }
        .archive-row:hover .archive-date {
            text-decoration: underline;
            text-underline-offset: 2px;
        }
        .archive-bar-container {
            height: 4px;
            background: var(--color-surface-alt);
            border-radius: 2px;
            overflow: hidden;
        }
        .archive-bar {
            display: block;
            height: 100%;
            background: var(--color-text-muted);
            border-radius: 2px;
            min-width: 0;
        }
        .archive-count {
            text-align: right;
            font-size: 14px;
            font-weight: 600;
            color: var(--color-text-secondary);
        }
        .archive-row-empty {
            opacity: 0.4;
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
            font-size: 22px;
            font-weight: 600;
            color: var(--color-text);
            margin: 30px 0 15px 0;
            padding-bottom: 8px;
            border-bottom: 1px solid var(--color-border);
        }
        .content h3 {
            font-size: 17px;
            font-weight: 600;
            color: var(--color-text-secondary);
            margin: 20px 0 10px 0;
        }
        .content p {
            margin-bottom: 15px;
            font-size: 15px;
            line-height: 1.7;
            color: var(--color-text-secondary);
        }
        .content ul, .content ol {
            margin: 15px 0 15px 30px;
        }
        .content li {
            margin-bottom: 10px;
            font-size: 15px;
            line-height: 1.7;
            color: var(--color-text-secondary);
        }
        code {
            background-color: var(--color-surface);
            padding: 2px 6px;
            border-radius: var(--radius-sm);
            font-family: 'DM Mono', 'Courier New', monospace;
            font-size: 13px;
        }
        .highlight-box {
            background-color: var(--color-highlight-bg);
            border-left: 3px solid var(--color-text-muted);
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
            font-size: 15px;
            font-weight: 500;
            padding: 10px;
            background-color: var(--color-surface);
            border-radius: var(--radius-sm);
            user-select: none;
            transition: background-color var(--transition-fast);
        }
        summary:hover { background-color: var(--color-surface-hover); }
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
        .source-list a {
            color: var(--color-link);
            text-decoration: none;
        }
        .source-list a:hover {
            text-decoration: underline;
        }
        @media (max-width: 1200px) {
            .source-list { column-count: 2; }
        }
        @media (max-width: 768px) {
            .source-list { column-count: 1; }
        }
        """

    # ── HTML Component Helpers ─────────────────────────────────────────────

    def _render_header(self, title: str, meta_text: str = None,
                       active_page: str = None, is_archive: bool = False) -> str:
        """Compact single-row header with title left, meta + nav right"""
        if is_archive:
            urls = {"today": "../index.html", "archive": "index.html", "how_it_works": "../how_it_works.html"}
        else:
            urls = {"today": "index.html", "archive": "archive/index.html", "how_it_works": "how_it_works.html"}

        def cls(page):
            return ' class="active"' if page == active_page else ''

        meta_html = f'<span class="header-meta">{meta_text}</span>' if meta_text else ''

        return f'''    <div class="header">
        <h1>{title}</h1>
        <div class="header-right">
            {meta_html}
            <span class="header-nav">
                <a href="{urls['today']}"{cls('today')}>Today</a>
                &middot;
                <a href="{urls['archive']}"{cls('archive')}>Archive</a>
                &middot;
                <a href="{urls['how_it_works']}"{cls('how_it_works')}>How It Works</a>
            </span>
        </div>
    </div>'''

    def _render_footer(self, is_archive: bool = False, timestamp: str = None) -> str:
        if is_archive:
            urls = {"today": "../index.html", "archive": "index.html", "how_it_works": "../how_it_works.html"}
        else:
            urls = {"today": "index.html", "archive": "archive/index.html", "how_it_works": "how_it_works.html"}

        ts = timestamp or datetime.now().strftime('%I:%M %p')

        return f'''
    <div class="footer">
        <a href="{urls['today']}">Today</a> &middot;
        <a href="{urls['archive']}">Archive</a> &middot;
        <a href="{urls['how_it_works']}">How It Works</a> &middot;
        <a href="https://github.com/tyson-swetnam/webcrawler" target="_blank">GitHub</a>
        &nbsp;|&nbsp; {self._source_count} sources &middot; Updated {ts}
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

        # Deduplicate by URL — keep the most recently scraped version
        seen_urls = {}
        for article, ai_analysis in results:
            url = article.url.url if article.url else ''
            if url in seen_urls:
                existing = seen_urls[url]
                if article.first_scraped > existing[0].first_scraped:
                    seen_urls[url] = (article, ai_analysis)
            else:
                seen_urls[url] = (article, ai_analysis)

        articles = []
        for url, (article, ai_analysis) in seen_urls.items():
            articles.append({
                'url': url,
                'title': article.title or 'Untitled',
                'university': article.university_name,
                'timestamp': article.first_scraped,
                'published_date': article.published_date,
                'summary': ai_analysis.consensus_summary if ai_analysis else None,
                'topics': ai_analysis.claude_key_points if ai_analysis else [],
                'category': ai_analysis.openai_category if ai_analysis else None
            })

        # Re-sort by published_date descending (dict iteration lost ordering)
        articles.sort(key=lambda a: a['published_date'] or datetime.min, reverse=True)

        return articles

    @staticmethod
    def _get_google_fonts_link() -> str:
        return ('<link rel="preconnect" href="https://fonts.googleapis.com">'
                '<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>'
                '<link href="https://fonts.googleapis.com/css2?family=DM+Sans:wght@400;500;600;700&display=swap" rel="stylesheet">')

    def _render_main_page(self, articles: List[Dict], date: datetime, is_archive_page: bool = False) -> str:
        """Render main page with tabbed dense-list layout"""
        date_str = date.strftime('%A, %B %d, %Y')
        short_date = date.strftime('%b %d')
        active_page = None if is_archive_page else 'today'

        # Categorize articles
        category_key_map = {
            'peer': 'peer',
            'r1': 'r1',
            'hpc': 'hpc',
            'national_lab': 'lab',
            'global': 'global',
        }
        dot_class_map = {
            'peer': 'dot-peer',
            'r1': 'dot-r1',
            'hpc': 'dot-hpc',
            'lab': 'dot-lab',
            'global': 'dot-global',
        }

        # Annotate each article with its category and display name
        annotated = []
        for article in articles:
            univ = article['university'] or 'Unknown'
            raw_cat = self.classifier.classify(univ)
            cat = category_key_map.get(raw_cat, 'r1')
            display_name = self.clean_university_name(univ)
            annotated.append({**article, '_cat': cat, '_display_univ': display_name})

        # Count per category
        counts = {'peer': 0, 'r1': 0, 'hpc': 0, 'lab': 0, 'global': 0}
        for a in annotated:
            counts[a['_cat']] = counts.get(a['_cat'], 0) + 1
        total = len(annotated)

        # Stats line
        stats_html = (
            f'<div class="stats-line" data-total-articles="{total}">'
            f'{total} articles &middot; '
            f'<span class="cat-dot dot-peer"></span>&nbsp;Peer&nbsp;{counts["peer"]} &middot; '
            f'<span class="cat-dot dot-r1"></span>&nbsp;R1&nbsp;{counts["r1"]} &middot; '
            f'<span class="cat-dot dot-hpc"></span>&nbsp;HPC&nbsp;{counts["hpc"]} &middot; '
            f'<span class="cat-dot dot-lab"></span>&nbsp;Labs&nbsp;{counts["lab"]} &middot; '
            f'<span class="cat-dot dot-global"></span>&nbsp;Global&nbsp;{counts["global"]}'
            f'</div>'
        )

        # Tab bar
        tab_labels = [
            ('all', 'All', total),
            ('peer', 'Peer', counts['peer']),
            ('r1', 'R1', counts['r1']),
            ('hpc', 'HPC', counts['hpc']),
            ('lab', 'Labs', counts['lab']),
            ('global', 'Global', counts['global']),
        ]
        tab_buttons = []
        for tab_id, label, count in tab_labels:
            active_cls = ' active' if tab_id == 'all' else ''
            empty_cls = ' tab-empty' if count == 0 and tab_id != 'all' else ''
            tab_buttons.append(
                f'<button class="tab-btn{active_cls}{empty_cls}" data-tab="{tab_id}" '
                f'onclick="switchTab(\'{tab_id}\')">{label}<span class="tab-count">({count})</span></button>'
            )
        tab_bar_html = '<div class="tab-bar">' + ''.join(tab_buttons) + '</div>'

        # Build article rows
        MAX_VISIBLE = 25
        article_rows = []
        row_index = 0

        # For category tabs: group by university within each category
        # We'll emit all articles in chronological order (already sorted) with data-category
        # For grouped views, JS handles university subheader visibility
        # Build a map of university -> articles per category for grouped view
        cat_univ_map = {}  # cat -> OrderedDict(univ -> [articles])
        for a in annotated:
            cat = a['_cat']
            univ = a['_display_univ']
            if cat not in cat_univ_map:
                cat_univ_map[cat] = OrderedDict()
            if univ not in cat_univ_map[cat]:
                cat_univ_map[cat][univ] = []
            cat_univ_map[cat][univ].append(a)

        def render_article_row(article, idx):
            cat = article['_cat']
            display_name = article['_display_univ']
            dot_cls = dot_class_map.get(cat, 'dot-r1')
            overflow_cls = ' article-overflow' if idx >= MAX_VISIBLE else ''

            # Short date for the row
            pub_short = ''
            if article.get('published_date'):
                if isinstance(article['published_date'], str):
                    pub_short = article['published_date']
                else:
                    pub_short = article['published_date'].strftime('%b %d')
            else:
                pub_short = article['timestamp'].strftime('%b %d')

            # Detail panel content
            summary_html = ''
            if article.get('summary'):
                plain_summary = self.strip_markdown(article['summary'])
                if len(plain_summary) > 300:
                    plain_summary = plain_summary[:300].rsplit(' ', 1)[0] + '...'
                summary_html = f'<div class="summary">{plain_summary}</div>'

            topics_html = ''
            if article.get('topics') and isinstance(article['topics'], list):
                clean_topics = [self.strip_markdown(str(t)) for t in article['topics'][:4] if t]
                clean_topics = [t for t in clean_topics if t and len(t) < 50]
                if clean_topics:
                    pills = ''.join(f'<span class="topic-pill">{t}</span>' for t in clean_topics)
                    topics_html = f'<div class="topics">{pills}</div>'

            # Full dates for detail
            pub_date_long = ''
            if article.get('published_date'):
                if isinstance(article['published_date'], str):
                    pub_date_long = article['published_date']
                else:
                    pub_date_long = article['published_date'].strftime('%B %d, %Y')
            crawl_date_long = article['timestamp'].strftime('%B %d, %Y')
            meta_parts = []
            if pub_date_long:
                meta_parts.append(f'Published: {pub_date_long}')
            meta_parts.append(f'Crawled: {crawl_date_long}')
            detail_meta = ' &middot; '.join(meta_parts)

            row_html = (
                f'<div class="article-row{overflow_cls}" data-category="{cat}" onclick="toggleDetail(this)">'
                f'<span class="cat-dot {dot_cls}"></span>'
                f'<a class="headline-link" href="{article["url"]}" target="_blank" onclick="event.stopPropagation()">{article["title"]}</a>'
                f'<span class="univ-label">{display_name}</span>'
                f'<span class="date-label">{pub_short}</span>'
                f'<span class="chevron">&#9654;</span>'
                f'</div>'
                f'<div class="article-detail" data-category="{cat}">'
                f'{summary_html}'
                f'{topics_html}'
                f'<div class="detail-meta">{detail_meta}</div>'
                f'<div class="detail-link"><a href="{article["url"]}" target="_blank">Read full article &rarr;</a></div>'
                f'</div>'
            )
            return row_html

        # Render flat chronological list (for "All" tab — default view)
        for idx, article in enumerate(annotated):
            article_rows.append(render_article_row(article, idx))

        overflow_count = max(0, total - MAX_VISIBLE)
        show_more_html = ''
        if overflow_count > 0:
            show_more_html = (
                f'<button class="show-more-btn" onclick="toggleMore(this)" '
                f'data-expanded="false" data-show-text="Show {overflow_count} more" '
                f'data-hide-text="Show fewer">'
                f'Show {overflow_count} more</button>'
            )

        list_html = '<div class="article-list">' + ''.join(article_rows) + show_more_html + '</div>'

        if not articles:
            articles_html = '<p class="no-results">No AI-related articles found for this date.</p>'
        else:
            articles_html = stats_html + tab_bar_html + list_html

        base_css = self._get_base_css()
        main_css = self._get_main_page_css()
        meta_text = f'{total} articles &middot; {short_date}'
        header_html = self._render_header("AI University News", meta_text=meta_text, active_page=active_page, is_archive=is_archive_page)
        footer_html = self._render_footer(is_archive_page)
        favicon = self._get_favicon_link()
        fonts = self._get_google_fonts_link()

        # JavaScript — plain string (no f-string) to avoid brace escaping
        page_js = '''<script>
function switchTab(cat) {
    var btns = document.querySelectorAll('.tab-btn');
    btns.forEach(function(b) { b.classList.toggle('active', b.getAttribute('data-tab') === cat); });
    var rows = document.querySelectorAll('.article-row');
    var details = document.querySelectorAll('.article-detail');
    rows.forEach(function(r) {
        var match = (cat === 'all' || r.getAttribute('data-category') === cat);
        if (match) {
            r.style.removeProperty('display');
        } else {
            r.style.display = 'none';
            r.classList.remove('expanded');
        }
    });
    details.forEach(function(d) {
        var match = (cat === 'all' || d.getAttribute('data-category') === cat);
        if (!match) {
            d.classList.remove('open');
            d.style.display = 'none';
        } else {
            d.style.removeProperty('display');
        }
    });
    // Reset show-more when switching tabs
    var overflows = document.querySelectorAll('.article-overflow');
    overflows.forEach(function(el) { el.classList.remove('shown'); });
    var btn = document.querySelector('.show-more-btn');
    if (btn) {
        btn.setAttribute('data-expanded', 'false');
        // Update count for current tab
        var hidden = 0;
        overflows.forEach(function(el) {
            if (cat === 'all' || el.getAttribute('data-category') === cat) hidden++;
        });
        if (hidden > 0) {
            btn.style.display = '';
            btn.setAttribute('data-show-text', 'Show ' + hidden + ' more');
            btn.textContent = 'Show ' + hidden + ' more';
        } else {
            btn.style.display = 'none';
        }
    }
}
function toggleDetail(row) {
    var detail = row.nextElementSibling;
    if (detail && detail.classList.contains('article-detail')) {
        var isOpen = detail.classList.contains('open');
        detail.classList.toggle('open');
        row.classList.toggle('expanded');
    }
}
function toggleMore(btn) {
    var showing = btn.getAttribute('data-expanded') === 'true';
    var activeTab = document.querySelector('.tab-btn.active');
    var cat = activeTab ? activeTab.getAttribute('data-tab') : 'all';
    var overflows = document.querySelectorAll('.article-overflow');
    overflows.forEach(function(el) {
        if (cat === 'all' || el.getAttribute('data-category') === cat) {
            if (showing) {
                el.classList.remove('shown');
                // Collapse any open detail panels for hidden overflow rows
                var next = el.nextElementSibling;
                if (next && next.classList.contains('article-detail')) {
                    next.classList.remove('open');
                    el.classList.remove('expanded');
                }
            } else {
                el.classList.add('shown');
            }
        }
    });
    btn.setAttribute('data-expanded', showing ? 'false' : 'true');
    btn.textContent = showing ? btn.getAttribute('data-show-text') : btn.getAttribute('data-hide-text');
}
</script>'''

        return f'''<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>AI University News - {date_str}</title>
    {favicon}
    {fonts}
    <style>
    {base_css}
    {main_css}
    </style>
</head>
<body>
{header_html}

    {articles_html}

{footer_html}
{page_js}
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
        header_html = self._render_header("AI University News", meta_text="Archive", active_page='archive', is_archive=True)
        footer_html = self._render_footer(is_archive=True)
        favicon = self._get_favicon_link()
        fonts = self._get_google_fonts_link()

        return f'''<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Archive - AI University News</title>
    {favicon}
    {fonts}
    <style>
    {base_css}
    {archive_css}
    </style>
</head>
<body>
{header_html}

    {''.join(groups_html)}

{footer_html}
</body>
</html>'''

    def _render_how_it_works_page(self) -> str:
        """Render 'How It Works' documentation page"""
        # Load source lists
        config_dir = Path(__file__).parent.parent / 'config'

        def load_names_with_urls(filename, key, name_field='name'):
            """Load institution names and their primary news URLs."""
            try:
                with open(config_dir / filename, 'r') as f:
                    data = json.load(f)
                    results = []
                    for item in data.get(key, []):
                        name = item[name_field]
                        url = ''
                        news_sources = item.get('news_sources', [])
                        if news_sources:
                            url = news_sources[0].get('url', '')
                        results.append((name, url))
                    return results
            except Exception:
                return []

        peer_institutions = load_names_with_urls('peer_institutions.json', 'universities')
        r1_universities = load_names_with_urls('r1_universities.json', 'universities')
        hpc_centers = load_names_with_urls('major_facilities.json', 'facilities')
        national_labs = load_names_with_urls('national_laboratories.json', 'facilities')
        global_institutions = load_names_with_urls('global_institutions.json', 'universities')

        # Build source lists HTML
        def build_collapsible_list(title, items, section_id):
            if not items:
                return f'<p><em>No {title.lower()} available</em></p>'

            def make_li(name, url):
                if url:
                    return f'<li><a href="{url}" target="_blank" rel="noopener">{name}</a></li>'
                return f'<li>{name}</li>'

            items_html = ''.join([make_li(name, url) for name, url in sorted(items, key=lambda x: x[0])])
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
        header_html = self._render_header("AI University News", meta_text="How It Works", active_page='how_it_works', is_archive=False)
        footer_html = self._render_footer(is_archive=False)
        favicon = self._get_favicon_link()
        fonts = self._get_google_fonts_link()

        return f'''<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>How It Works - AI University News</title>
    {favicon}
    {fonts}
    <style>
    {base_css}
    {hiw_css}
    </style>
</head>
<body>
{header_html}

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
            This is where the magic happens. Each new article is analyzed by Claude (Sonnet 4.6),
            Anthropic's frontier model for deep research understanding. Articles are classified by
            relevance, key topics are extracted, summaries are generated, and confidence scores
            are assigned.
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
            <li><strong>AI APIs:</strong> Anthropic Claude (Sonnet 4.6)</li>
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
            <li><strong>Optimization:</strong> Claude Sonnet 4.6 handles all analysis in a single pass, minimizing redundant API calls</li>
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
