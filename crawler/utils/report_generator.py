"""
Report generation utilities for article summaries.

This module formats article data for Slack and email notifications
with consistent styling and presentation.
"""

from typing import List, Dict, Any
from datetime import datetime
import logging
import re

logger = logging.getLogger(__name__)


class ReportGenerator:
    """
    Generate formatted reports for notifications.

    Provides consistent formatting for article summaries across
    different notification channels (Slack, email, etc.).
    """

    def __init__(self, max_summary_length: int = 300):
        """
        Initialize report generator.

        Args:
            max_summary_length: Maximum characters for summary truncation
        """
        self.max_summary_length = max_summary_length

    @staticmethod
    def strip_markdown(text: str) -> str:
        """Strip markdown formatting from text, returning plain text only"""
        if not text:
            return ""

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

        return text.strip()

    def truncate_summary(self, summary: str, max_length: int = None) -> str:
        """
        Truncate summary to maximum length with ellipsis.

        Args:
            summary: Full summary text
            max_length: Maximum length (uses default if not provided)

        Returns:
            Truncated summary
        """
        max_len = max_length or self.max_summary_length

        if len(summary) <= max_len:
            return summary

        # Find last complete word before limit
        truncated = summary[:max_len]
        last_space = truncated.rfind(' ')

        if last_space > 0:
            truncated = truncated[:last_space]

        return truncated + '...'

    def format_article_summary(self, article: Dict[str, Any]) -> Dict[str, str]:
        """
        Format article data for display.

        Args:
            article: Article data dictionary

        Returns:
            Formatted article dictionary
        """
        # Strip markdown from summary before truncating
        raw_summary = article.get('summary', 'No summary available')
        plain_summary = self.strip_markdown(raw_summary)

        return {
            'title': article.get('title', 'Untitled'),
            'university': article.get('university_name', 'Unknown University'),
            'date': self._format_date(article.get('published_date')),
            'summary': self.truncate_summary(plain_summary),
            'url': article.get('url', ''),
            'author': article.get('author', ''),
            'word_count': article.get('word_count', 0)
        }

    def _format_date(self, date: Any) -> str:
        """
        Format date for display.

        Args:
            date: Date object or string

        Returns:
            Formatted date string
        """
        if isinstance(date, str):
            try:
                date_obj = datetime.fromisoformat(date.replace('Z', '+00:00'))
                return date_obj.strftime('%B %d, %Y')
            except (ValueError, AttributeError):
                return date

        elif isinstance(date, datetime):
            return date.strftime('%B %d, %Y')

        elif hasattr(date, 'strftime'):
            return date.strftime('%B %d, %Y')

        return str(date) if date else 'Date unknown'

    def generate_text_report(self, articles: List[Dict[str, Any]]) -> str:
        """
        Generate plain text report.

        Args:
            articles: List of article dictionaries

        Returns:
            Plain text report
        """
        if not articles:
            return "No articles found."

        lines = [
            f"AI News Digest - {datetime.utcnow().strftime('%Y-%m-%d')}",
            "=" * 60,
            f"\nFound {len(articles)} AI-related articles\n"
        ]

        for i, article in enumerate(articles, 1):
            formatted = self.format_article_summary(article)
            lines.append(f"\n{i}. {formatted['title']}")
            lines.append(f"   {formatted['university']} | {formatted['date']}")
            lines.append(f"   {formatted['summary']}")
            lines.append(f"   Read more: {formatted['url']}")

        return '\n'.join(lines)

    def generate_markdown_report(self, articles: List[Dict[str, Any]]) -> str:
        """
        Generate Markdown-formatted report.

        Args:
            articles: List of article dictionaries

        Returns:
            Markdown report
        """
        if not articles:
            return "## No articles found"

        lines = [
            f"# AI News Digest - {datetime.utcnow().strftime('%Y-%m-%d')}",
            "",
            f"**{len(articles)} AI-related articles** from US universities",
            ""
        ]

        for article in articles:
            formatted = self.format_article_summary(article)
            lines.append(f"## [{formatted['title']}]({formatted['url']})")
            lines.append(f"**{formatted['university']}** • {formatted['date']}")
            lines.append("")
            lines.append(formatted['summary'])
            lines.append("")
            lines.append("---")
            lines.append("")

        return '\n'.join(lines)

    def generate_html_report(
        self,
        articles: List[Dict[str, Any]],
        title: str = "AI News Digest"
    ) -> str:
        """
        Generate HTML-formatted report for email.

        Args:
            articles: List of article dictionaries
            title: Report title

        Returns:
            HTML report
        """
        if not articles:
            return self._generate_empty_html_report(title)

        article_html = self._generate_article_cards_html(articles)

        html = f"""
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{title}</title>
    <style>
        body {{
            font-family: 'Courier New', Courier, monospace;
            line-height: 1.6;
            color: #333;
            max-width: 800px;
            margin: 0 auto;
            padding: 20px;
            background-color: #f5f5f5;
        }}
        .header {{
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            padding: 30px;
            border-radius: 8px;
            margin-bottom: 30px;
        }}
        .header h1 {{
            margin: 0 0 10px 0;
            font-size: 28px;
        }}
        .header p {{
            margin: 0;
            opacity: 0.9;
            font-size: 16px;
        }}
        .article-card {{
            background: white;
            margin-bottom: 20px;
            padding: 25px;
            border-radius: 8px;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
            border-left: 4px solid #667eea;
        }}
        .article-title {{
            margin: 0 0 10px 0;
            font-size: 20px;
        }}
        .article-title a {{
            color: #2c3e50;
            text-decoration: none;
            transition: color 0.2s;
        }}
        .article-title a:hover {{
            color: #667eea;
        }}
        .article-meta {{
            color: #7f8c8d;
            font-size: 14px;
            margin-bottom: 15px;
        }}
        .article-meta strong {{
            color: #34495e;
        }}
        .article-summary {{
            color: #555;
            line-height: 1.7;
            margin-bottom: 15px;
        }}
        .read-more {{
            display: inline-block;
            color: #667eea;
            text-decoration: none;
            font-weight: 600;
            font-size: 14px;
        }}
        .read-more:hover {{
            text-decoration: underline;
        }}
        .footer {{
            text-align: center;
            margin-top: 40px;
            padding: 20px;
            color: #7f8c8d;
            font-size: 12px;
        }}
        .stats {{
            background: #ecf0f1;
            padding: 15px;
            border-radius: 6px;
            margin-bottom: 30px;
        }}
        .stats p {{
            margin: 5px 0;
            font-size: 14px;
        }}
    </style>
</head>
<body>
    <div class="header">
        <h1>🤖 {title}</h1>
        <p>{datetime.utcnow().strftime('%A, %B %d, %Y')}</p>
    </div>

    <div class="stats">
        <p><strong>{len(articles)} new AI-related articles</strong> from US university press releases</p>
    </div>

    {article_html}

    <div class="footer">
        <p>Generated by AI News Crawler</p>
        <p>This is an automated report. Articles are analyzed using Claude, GPT-4, and Gemini.</p>
    </div>
</body>
</html>
"""
        return html

    def _generate_article_cards_html(self, articles: List[Dict[str, Any]]) -> str:
        """Generate HTML for article cards."""
        cards = []

        for article in articles:
            formatted = self.format_article_summary(article)
            card = f"""
    <div class="article-card">
        <h2 class="article-title">
            <a href="{formatted['url']}" target="_blank">{formatted['title']}</a>
        </h2>
        <div class="article-meta">
            <strong>{formatted['university']}</strong> • {formatted['date']}
        </div>
        <div class="article-summary">
            {formatted['summary']}
        </div>
        <a href="{formatted['url']}" class="read-more" target="_blank">Read full article →</a>
    </div>
"""
            cards.append(card)

        return '\n'.join(cards)

    def _generate_empty_html_report(self, title: str) -> str:
        """Generate HTML for empty report."""
        return f"""
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <title>{title}</title>
    <style>
        body {{
            font-family: 'Courier New', Courier, monospace;
            max-width: 800px;
            margin: 50px auto;
            padding: 20px;
            text-align: center;
        }}
        .empty {{
            color: #7f8c8d;
            font-size: 18px;
        }}
    </style>
</head>
<body>
    <h1>{title}</h1>
    <p class="empty">No new articles found for today.</p>
</body>
</html>
"""

    def generate_slack_blocks(
        self,
        articles: List[Dict[str, Any]],
        max_articles: int = 10
    ) -> List[Dict]:
        """
        Generate Slack block kit format.

        Args:
            articles: List of article dictionaries
            max_articles: Maximum articles to include

        Returns:
            List of Slack block dictionaries
        """
        blocks = [
            {
                "type": "header",
                "text": {
                    "type": "plain_text",
                    "text": f"🤖 AI News Digest - {datetime.utcnow().strftime('%Y-%m-%d')}",
                    "emoji": True
                }
            },
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"*{len(articles)} new AI articles* from US universities"
                }
            },
            {"type": "divider"}
        ]

        # Add article blocks (limit to max_articles)
        for article in articles[:max_articles]:
            formatted = self.format_article_summary(article)
            blocks.extend([
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": f"*{formatted['title']}*\n{formatted['university']}\n_{formatted['summary']}_"
                    }
                },
                {
                    "type": "context",
                    "elements": [
                        {
                            "type": "mrkdwn",
                            "text": f"<{formatted['url']}|Read more> • {formatted['date']}"
                        }
                    ]
                }
            ])

        # Add footer if there are more articles
        if len(articles) > max_articles:
            blocks.append({
                "type": "context",
                "elements": [{
                    "type": "mrkdwn",
                    "text": f"_...and {len(articles) - max_articles} more articles_"
                }]
            })

        return blocks
