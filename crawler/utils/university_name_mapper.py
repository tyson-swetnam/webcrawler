"""
University name mapper - maps hostnames to canonical university names.

This module provides hostname-to-canonical-name mapping to fix the issue where
Trafilatura extracts inconsistent sitenames (e.g., "AuburnEngineers", "ou.edu", "psu.edu")
that don't match the canonical names in our config files.

The mapper loads all three config files (peer_institutions, r1_universities, major_facilities)
and builds a lookup table based on the hostnames in their news URLs.
"""

import json
import logging
from pathlib import Path
from urllib.parse import urlparse
from typing import Dict, Optional, Tuple

logger = logging.getLogger(__name__)


class UniversityNameMapper:
    """
    Maps hostnames to canonical university/facility names.

    This class solves the column misassignment problem by providing a reliable
    way to get the correct university name regardless of what Trafilatura extracts
    from the HTML.
    """

    def __init__(self):
        """Initialize the mapper by loading all config files."""
        self.hostname_to_name: Dict[str, Tuple[str, str]] = {}  # hostname -> (canonical_name, category)
        self._load_mappings()

    def _load_mappings(self):
        """Load mappings from all config files."""
        config_dir = Path(__file__).parent.parent / 'config'

        # Load peer institutions (27 universities)
        self._load_config_file(
            config_dir / 'peer_institutions.json',
            'universities',
            'peer'
        )

        # Load R1 universities (187 universities)
        self._load_config_file(
            config_dir / 'r1_universities.json',
            'universities',
            'r1'
        )

        # Load major facilities (27 facilities)
        self._load_config_file(
            config_dir / 'major_facilities.json',
            'facilities',
            'facility'
        )

        logger.info(f"Loaded {len(self.hostname_to_name)} hostname mappings")

    def _load_config_file(self, filepath: Path, key: str, category: str):
        """
        Load a single config file and extract hostname mappings.

        Args:
            filepath: Path to the JSON config file
            key: Key in JSON that contains the array (e.g., 'universities' or 'facilities')
            category: Category type ('peer', 'r1', or 'facility')
        """
        if not filepath.exists():
            logger.warning(f"Config file not found: {filepath}")
            return

        try:
            with open(filepath, 'r') as f:
                data = json.load(f)

            items = data.get(key, [])

            for item in items:
                # Get canonical name
                canonical_name = item.get('name') or item.get('canonical_name')
                if not canonical_name:
                    continue

                # Extract hostnames from news_sources array
                news_sources = item.get('news_sources', [])

                for source in news_sources:
                    url = source.get('url')
                    if url:
                        hostname = self._extract_hostname(url)
                        if hostname:
                            self.hostname_to_name[hostname] = (canonical_name, category)

                # Also check legacy "news" field for backward compatibility
                news = item.get('news', {})
                if news:
                    for url_key in ['url', 'main_url', 'ai_tag_url']:
                        url = news.get(url_key)
                        if url:
                            hostname = self._extract_hostname(url)
                            if hostname:
                                self.hostname_to_name[hostname] = (canonical_name, category)

            logger.debug(f"Loaded {len(items)} entries from {filepath.name}")

        except Exception as e:
            logger.error(f"Error loading config file {filepath}: {e}")

    def _extract_hostname(self, url: str) -> Optional[str]:
        """
        Extract hostname from URL.

        Args:
            url: The URL to extract hostname from

        Returns:
            Hostname (e.g., 'news.stanford.edu') or None if invalid
        """
        try:
            parsed = urlparse(url)
            return parsed.netloc.lower()
        except Exception:
            return None

    def get_canonical_name(self, hostname: str, fallback_sitename: Optional[str] = None) -> str:
        """
        Get canonical university name for a given hostname.

        This method looks up the hostname in our config files to find the correct
        canonical name. If not found, it falls back to the sitename from Trafilatura.

        Args:
            hostname: The hostname of the article URL (e.g., 'eng.auburn.edu')
            fallback_sitename: Fallback name from Trafilatura if hostname not found

        Returns:
            Canonical university/facility name

        Examples:
            >>> mapper.get_canonical_name('eng.auburn.edu')
            'Auburn University'
            >>> mapper.get_canonical_name('www.ou.edu')
            'University of Oklahoma'
            >>> mapper.get_canonical_name('unknown.edu', 'Unknown University')
            'Unknown University'
        """
        if not hostname:
            return fallback_sitename or 'Unknown'

        hostname = hostname.lower()

        # Direct lookup
        if hostname in self.hostname_to_name:
            canonical_name, category = self.hostname_to_name[hostname]
            logger.debug(f"Mapped {hostname} -> {canonical_name} ({category})")
            return canonical_name

        # Try matching any registered hostname that shares the same institutional domain
        # This handles cases like:
        # - eng.auburn.edu matches news.auburn.edu (both *.auburn.edu)
        # - www.utimes.pitt.edu matches www.pittwire.pitt.edu (both *.pitt.edu)
        parts = hostname.split('.')
        if len(parts) >= 2:
            # Extract institutional domain (last two parts: e.g., 'auburn.edu', 'pitt.edu')
            institutional_domain = '.'.join(parts[-2:])

            # Search through all registered hostnames for matches
            for registered_hostname, (canonical_name, category) in self.hostname_to_name.items():
                registered_parts = registered_hostname.split('.')
                if len(registered_parts) >= 2:
                    registered_institutional_domain = '.'.join(registered_parts[-2:])
                    if institutional_domain == registered_institutional_domain:
                        logger.debug(f"Mapped {hostname} -> {canonical_name} ({category}) via institutional domain {institutional_domain}")
                        return canonical_name

        # Try adding 'www.' prefix
        www_hostname = f'www.{hostname}'
        if www_hostname in self.hostname_to_name:
            canonical_name, category = self.hostname_to_name[www_hostname]
            logger.debug(f"Mapped {hostname} -> {canonical_name} ({category}) via www prefix")
            return canonical_name

        # Fallback to sitename from Trafilatura
        if fallback_sitename:
            logger.debug(f"No mapping found for {hostname}, using fallback: {fallback_sitename}")
            return fallback_sitename

        logger.warning(f"No mapping found for {hostname} and no fallback provided")
        return 'Unknown'

    def get_category(self, hostname: str) -> Optional[str]:
        """
        Get the category (peer, r1, or facility) for a given hostname.

        Args:
            hostname: The hostname to look up

        Returns:
            Category string ('peer', 'r1', 'facility') or None if not found
        """
        hostname = hostname.lower()

        if hostname in self.hostname_to_name:
            _, category = self.hostname_to_name[hostname]
            return category

        # Try parent domain
        parts = hostname.split('.')
        if len(parts) > 2:
            parent_domain = '.'.join(parts[-2:])
            if parent_domain in self.hostname_to_name:
                _, category = self.hostname_to_name[parent_domain]
                return category

        return None


# Global instance for reuse
_mapper_instance = None


def get_mapper() -> UniversityNameMapper:
    """
    Get the global UniversityNameMapper instance.

    This function implements a singleton pattern to avoid reloading
    config files multiple times.

    Returns:
        UniversityNameMapper instance
    """
    global _mapper_instance
    if _mapper_instance is None:
        _mapper_instance = UniversityNameMapper()
    return _mapper_instance
