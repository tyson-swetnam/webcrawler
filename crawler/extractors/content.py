"""
Content extraction using Trafilatura.

This module provides high-quality content extraction from HTML
with 95%+ accuracy for article text, metadata, and dates.
"""

from typing import Optional, Dict, Any
from datetime import datetime
import trafilatura
from trafilatura import bare_extraction, extract
from trafilatura.settings import use_config
import logging

logger = logging.getLogger(__name__)


class ContentExtractor:
    """
    Extract clean article content from HTML using Trafilatura.

    Provides high-accuracy extraction of article text, title, author,
    date, and other metadata from news articles.
    """

    def __init__(self, include_comments: bool = False, include_tables: bool = True):
        """
        Initialize content extractor.

        Args:
            include_comments: Whether to extract comment sections
            include_tables: Whether to include table data
        """
        self.include_comments = include_comments
        self.include_tables = include_tables

        # Configure Trafilatura for optimal extraction
        self.config = use_config()
        self.config.set('DEFAULT', 'EXTRACTION_TIMEOUT', '30')

        logger.debug(f"Initialized ContentExtractor (tables={include_tables})")

    def extract_from_html(
        self,
        html: str,
        url: Optional[str] = None
    ) -> Optional[Dict[str, Any]]:
        """
        Extract structured content from HTML.

        Args:
            html: Raw HTML content
            url: Original URL (helps with metadata extraction)

        Returns:
            Dictionary with extracted content or None if extraction failed
        """
        try:
            # Use bare_extraction for complete metadata
            result = bare_extraction(
                html,
                url=url,
                with_metadata=True,
                include_comments=self.include_comments,
                include_tables=self.include_tables,
                output_format='python',
                config=self.config
            )

            if not result:
                logger.warning(f"Trafilatura extraction returned None for {url}")
                return None

            # Validate minimum content requirements
            text = result.get('text', '')
            if not text or len(text.strip()) < 50:
                logger.warning(f"Extracted content too short for {url}: {len(text)} chars")
                return None

            # Build standardized result
            extracted = {
                'title': result.get('title'),
                'author': result.get('author'),
                'date': result.get('date'),
                'text': text,
                'description': result.get('description'),
                'sitename': result.get('sitename'),
                'language': result.get('language', 'en'),
                'url': result.get('url') or url,
                'hostname': result.get('hostname'),
                'categories': result.get('categories', []),
                'tags': result.get('tags', []),
                'license': result.get('license'),
                'word_count': len(text.split()),
                'extraction_successful': True
            }

            logger.debug(f"Successfully extracted {extracted['word_count']} words from {url}")
            return extracted

        except Exception as e:
            logger.error(f"Content extraction failed for {url}: {e}")
            return None

    def extract_text_only(self, html: str, url: Optional[str] = None) -> Optional[str]:
        """
        Extract only the main text content (fast extraction).

        Args:
            html: Raw HTML content
            url: Original URL

        Returns:
            Extracted text or None
        """
        try:
            text = extract(
                html,
                url=url,
                include_comments=self.include_comments,
                include_tables=self.include_tables,
                config=self.config
            )
            return text
        except Exception as e:
            logger.error(f"Fast text extraction failed for {url}: {e}")
            return None

    def is_content_valid(self, extracted: Dict[str, Any], min_words: int = 100) -> bool:
        """
        Validate extracted content meets quality requirements.

        Args:
            extracted: Extracted content dictionary
            min_words: Minimum word count requirement

        Returns:
            True if content is valid, False otherwise
        """
        if not extracted or not extracted.get('text'):
            return False

        # Check word count
        word_count = extracted.get('word_count', 0)
        if word_count < min_words:
            logger.debug(f"Content invalid: {word_count} words < {min_words} minimum")
            return False

        # Check for title
        if not extracted.get('title'):
            logger.debug("Content invalid: missing title")
            return False

        return True


class DateExtractor:
    """
    Extract and parse publication dates from HTML.

    Uses htmldate library for accurate date extraction.
    """

    def __init__(self):
        """Initialize date extractor."""
        self.logger = logger

    def extract_date(
        self,
        html: str,
        url: Optional[str] = None,
        original_date: bool = True
    ) -> Optional[datetime]:
        """
        Extract publication date from HTML.

        Args:
            html: Raw HTML content
            url: Original URL (helps with date extraction)
            original_date: Prefer original publication date over modification date

        Returns:
            Datetime object or None if no date found
        """
        try:
            from htmldate import find_date

            date_str = find_date(
                html,
                url=url,
                original_date=original_date,
                outputformat='%Y-%m-%d'
            )

            if date_str:
                return datetime.strptime(date_str, '%Y-%m-%d')

            logger.debug(f"No date found for {url}")
            return None

        except Exception as e:
            logger.error(f"Date extraction failed for {url}: {e}")
            return None


def extract_from_url(url: str, timeout: int = 30) -> Optional[Dict[str, Any]]:
    """
    Fetch and extract content from URL in one step.

    Args:
        url: URL to fetch and extract
        timeout: Request timeout in seconds

    Returns:
        Extracted content dictionary or None
    """
    try:
        downloaded = trafilatura.fetch_url(url, timeout=timeout)

        if not downloaded:
            logger.warning(f"Failed to download {url}")
            return None

        extractor = ContentExtractor()
        return extractor.extract_from_html(downloaded, url)

    except Exception as e:
        logger.error(f"URL extraction failed for {url}: {e}")
        return None
