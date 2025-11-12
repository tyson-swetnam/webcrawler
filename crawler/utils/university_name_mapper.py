"""
University name mapper to convert hostnames to canonical university names.

This module helps standardize university names across different sources by mapping
hostnames to canonical names from the universities.json configuration file.
"""

import json
import logging
from pathlib import Path
from typing import Dict, Optional
from urllib.parse import urlparse

logger = logging.getLogger(__name__)


class UniversityNameMapper:
    """Maps hostnames to canonical university names."""

    def __init__(self, config_path: Optional[Path] = None):
        """
        Initialize the mapper with university configuration.

        Args:
            config_path: Path to universities.json file. If None, uses default location.
        """
        if config_path is None:
            # Default to the config directory
            config_path = Path(__file__).parent.parent / "config" / "universities.json"

        self.hostname_to_name: Dict[str, str] = {}
        self._load_universities(config_path)

    def _load_universities(self, config_path: Path) -> None:
        """
        Load university configuration and build hostname mapping.

        Args:
            config_path: Path to universities.json file
        """
        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                universities = json.load(f)

            for university in universities:
                name = university.get('name')
                news_url = university.get('news_url')

                if not name or not news_url:
                    continue

                # Parse the news URL to get the hostname
                parsed = urlparse(news_url)
                hostname = parsed.netloc.lower()

                # Store full hostname mapping
                self.hostname_to_name[hostname] = name

                # Also store base domain mapping (e.g., stanford.edu)
                # This handles cases where articles might come from different subdomains
                parts = hostname.split('.')
                if len(parts) >= 2:
                    # Get the base domain (last two parts)
                    base_domain = '.'.join(parts[-2:])
                    # Only add if not already present (avoid overwriting)
                    if base_domain not in self.hostname_to_name:
                        self.hostname_to_name[base_domain] = name

            logger.info(f"Loaded {len(self.hostname_to_name)} hostname mappings for {len(universities)} universities")

        except Exception as e:
            logger.error(f"Failed to load university configuration: {e}")
            # Continue with empty mapping rather than crashing

    def get_canonical_name(self, hostname: str, fallback_sitename: Optional[str] = None) -> str:
        """
        Get the canonical university name for a given hostname.

        Args:
            hostname: The hostname to look up (e.g., 'news.stanford.edu')
            fallback_sitename: Optional fallback name if hostname not found

        Returns:
            The canonical university name, fallback sitename, or the hostname if neither found
        """
        if not hostname:
            return fallback_sitename or "Unknown"

        # Normalize hostname
        hostname = hostname.lower().strip()

        # Try exact match first
        if hostname in self.hostname_to_name:
            return self.hostname_to_name[hostname]

        # Try extracting base domain and matching
        parts = hostname.split('.')
        if len(parts) >= 2:
            base_domain = '.'.join(parts[-2:])
            if base_domain in self.hostname_to_name:
                return self.hostname_to_name[base_domain]

        # If no match found, use fallback or hostname
        if fallback_sitename:
            logger.debug(f"No mapping found for {hostname}, using fallback: {fallback_sitename}")
            return fallback_sitename
        else:
            logger.debug(f"No mapping found for {hostname}, using hostname as name")
            return hostname


# Global mapper instance
_mapper_instance: Optional[UniversityNameMapper] = None


def get_mapper() -> UniversityNameMapper:
    """
    Get the global UniversityNameMapper instance.

    Returns:
        The singleton mapper instance
    """
    global _mapper_instance
    if _mapper_instance is None:
        _mapper_instance = UniversityNameMapper()
    return _mapper_instance
