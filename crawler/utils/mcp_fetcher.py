"""
MCP Fetch Integration for Bypassing Bot Protection.

This module provides a fallback mechanism using MCP imageFetch tool
when Scrapy encounters 403/404 errors due to bot protection on university sites.

The MCP fetch tool can bypass common bot detection mechanisms and retrieve
content that would otherwise be blocked.
"""

import json
import logging
from typing import Optional, Dict, Any
from html import escape

logger = logging.getLogger(__name__)


class MCPFetcher:
    """
    Fallback fetcher using MCP imageFetch tool.

    Used when Scrapy encounters 403/404 errors due to bot protection.
    Converts markdown/text output to HTML-like format for Trafilatura parsing.
    """

    def __init__(self):
        """Initialize MCP fetcher."""
        self.stats = {
            'fetch_attempts': 0,
            'fetch_successes': 0,
            'fetch_failures': 0
        }
        logger.info("Initialized MCPFetcher for bot protection bypass")

    def fetch_with_mcp(self, url: str) -> Optional[str]:
        """
        Fetch content using MCP imageFetch tool.

        This method is designed to be called as a fallback when Scrapy
        encounters 403/404 errors. The MCP tool fetches the content
        and returns it in markdown format, which we convert to HTML
        for compatibility with Trafilatura.

        Args:
            url: URL to fetch

        Returns:
            HTML-formatted content or None if fetch failed
        """
        self.stats['fetch_attempts'] += 1

        try:
            logger.info(f"Attempting MCP fetch for blocked URL: {url}")

            # Import the MCP tool at runtime
            # NOTE: In the actual Claude Code environment, the MCP tool
            # is available via the function calling mechanism
            from crawler.utils.mcp_client import call_mcp_fetch

            # Call MCP imageFetch tool with text-only parameters
            result = call_mcp_fetch(
                url=url,
                images=False,  # We only need text content
                text={
                    "maxLength": 50000,  # Get up to 50k chars
                    "raw": False,  # Get markdown format
                    "startIndex": 0
                }
            )

            if not result or not result.get('html'):
                logger.warning(f"MCP fetch returned no content for {url}")
                self.stats['fetch_failures'] += 1
                return None

            # Extract the HTML content
            html_content = result.get('html', result.get('text', ''))

            # HTML is already in the right format for Trafilatura
            # No conversion needed

            self.stats['fetch_successes'] += 1
            logger.info(f"MCP fetch successful for {url} ({len(html_content)} chars)")

            return html_content

        except ImportError:
            logger.warning("MCP client not available - cannot use MCP fallback")
            self.stats['fetch_failures'] += 1
            return None
        except Exception as e:
            logger.error(f"MCP fetch failed for {url}: {e}")
            self.stats['fetch_failures'] += 1
            return None

    def _markdown_to_html(self, markdown: str, url: str) -> str:
        """
        Convert markdown content to HTML format for Trafilatura parsing.

        This creates a minimal HTML structure that Trafilatura can parse
        while preserving the content structure from the markdown.

        Args:
            markdown: Markdown content from MCP fetch
            url: Original URL (for metadata)

        Returns:
            HTML-formatted content
        """
        # Escape HTML special characters in the content
        # but preserve markdown structure for better parsing
        lines = markdown.split('\n')
        html_lines = ['<html>', '<head>', f'<meta property="og:url" content="{escape(url)}" />', '</head>', '<body>', '<article>']

        in_code_block = False
        current_paragraph = []

        for line in lines:
            stripped = line.strip()

            # Handle code blocks
            if stripped.startswith('```'):
                in_code_block = not in_code_block
                if in_code_block:
                    html_lines.append('<pre><code>')
                else:
                    html_lines.append('</code></pre>')
                continue

            if in_code_block:
                html_lines.append(escape(line))
                continue

            # Handle headers
            if stripped.startswith('# '):
                if current_paragraph:
                    html_lines.append('<p>' + ' '.join(current_paragraph) + '</p>')
                    current_paragraph = []
                html_lines.append(f'<h1>{escape(stripped[2:])}</h1>')
            elif stripped.startswith('## '):
                if current_paragraph:
                    html_lines.append('<p>' + ' '.join(current_paragraph) + '</p>')
                    current_paragraph = []
                html_lines.append(f'<h2>{escape(stripped[3:])}</h2>')
            elif stripped.startswith('### '):
                if current_paragraph:
                    html_lines.append('<p>' + ' '.join(current_paragraph) + '</p>')
                    current_paragraph = []
                html_lines.append(f'<h3>{escape(stripped[4:])}</h3>')

            # Handle list items
            elif stripped.startswith('- ') or stripped.startswith('* '):
                if current_paragraph:
                    html_lines.append('<p>' + ' '.join(current_paragraph) + '</p>')
                    current_paragraph = []
                html_lines.append(f'<li>{escape(stripped[2:])}</li>')

            # Handle links in markdown format [text](url)
            elif '[' in stripped and '](' in stripped:
                if current_paragraph:
                    html_lines.append('<p>' + ' '.join(current_paragraph) + '</p>')
                    current_paragraph = []
                # Simple link conversion (not perfect but good enough)
                import re
                converted = re.sub(
                    r'\[([^\]]+)\]\(([^\)]+)\)',
                    r'<a href="\2">\1</a>',
                    stripped
                )
                html_lines.append(f'<p>{escape(converted)}</p>')

            # Handle empty lines (paragraph breaks)
            elif not stripped:
                if current_paragraph:
                    html_lines.append('<p>' + ' '.join(current_paragraph) + '</p>')
                    current_paragraph = []

            # Regular text - accumulate into paragraph
            else:
                current_paragraph.append(escape(stripped))

        # Close any remaining paragraph
        if current_paragraph:
            html_lines.append('<p>' + ' '.join(current_paragraph) + '</p>')

        html_lines.extend(['</article>', '</body>', '</html>'])

        return '\n'.join(html_lines)

    def should_use_mcp_fallback(self, status_code: Optional[int], url: str) -> bool:
        """
        Determine if MCP fallback should be used based on error type.

        Args:
            status_code: HTTP status code from failed request
            url: URL that failed

        Returns:
            True if MCP fallback should be attempted
        """
        # Use MCP fallback for:
        # - 403 Forbidden (bot detection)
        # - 404 Not Found (might be blocking crawlers)
        # - None (connection/timeout errors)
        fallback_codes = [403, 404, None]

        should_fallback = status_code in fallback_codes

        if should_fallback:
            logger.info(f"Status code {status_code} for {url} - MCP fallback recommended")

        return should_fallback

    def get_stats(self) -> Dict[str, int]:
        """
        Get statistics about MCP fetch operations.

        Returns:
            Dictionary with fetch statistics
        """
        return self.stats.copy()


def fetch_with_mcp(url: str) -> Optional[str]:
    """
    Convenience function for fetching content with MCP.

    Args:
        url: URL to fetch

    Returns:
        HTML content or None if fetch failed
    """
    fetcher = MCPFetcher()
    return fetcher.fetch_with_mcp(url)
