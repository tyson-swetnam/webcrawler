"""
University name mapper to convert hostnames to canonical university names.

This module helps standardize university names across different sources by mapping
hostnames to canonical names from the configuration files.
"""

import json
import logging
from pathlib import Path
from typing import Dict, Optional
from urllib.parse import urlparse

logger = logging.getLogger(__name__)


class UniversityNameMapper:
    """Maps hostnames to canonical university names."""

    # Source files to load: (filename, key_for_entries, name_field)
    SOURCE_FILES = [
        ("universities.json", None, "name"),               # Legacy format (list of dicts)
        ("peer_institutions.json", "universities", "name"),
        ("r1_universities.json", "universities", "name"),
        ("major_facilities.json", "facilities", "name"),
        ("national_laboratories.json", "facilities", "name"),
        ("global_institutions.json", "universities", "name"),
    ]

    def __init__(self, config_path: Optional[Path] = None):
        """
        Initialize the mapper with university configuration.

        Args:
            config_path: Path to config directory. If None, uses default location.
        """
        if config_path is None:
            config_dir = Path(__file__).parent.parent / "config"
        else:
            # Support both file path (legacy) and directory path
            config_dir = config_path if config_path.is_dir() else config_path.parent

        self.hostname_to_name: Dict[str, str] = {}
        self._load_all_sources(config_dir)

    def _load_all_sources(self, config_dir: Path) -> None:
        """
        Load all source configuration files and build hostname mapping.

        Args:
            config_dir: Path to the config directory
        """
        total_loaded = 0

        for filename, entries_key, name_field in self.SOURCE_FILES:
            filepath = config_dir / filename
            if not filepath.exists():
                continue

            try:
                with open(filepath, 'r', encoding='utf-8') as f:
                    data = json.load(f)

                # Get the entries list
                if entries_key is None:
                    # Legacy format: top-level list
                    if isinstance(data, list):
                        entries = data
                    else:
                        continue
                else:
                    entries = data.get(entries_key, [])

                count = self._process_entries(entries, name_field)
                total_loaded += count
                logger.debug(f"Loaded {count} mappings from {filename}")

            except Exception as e:
                logger.warning(f"Failed to load {filename}: {e}")

        logger.info(f"Loaded {len(self.hostname_to_name)} hostname mappings from {total_loaded} sources")

        # High-priority overrides — applied last so they always win.
        # Needed when a lab subdomain (e.g. ll.mit.edu) gets processed before
        # the main news subdomain and pollutes the base-domain mapping.
        OVERRIDES: Dict[str, str] = {
            # MIT
            "news.mit.edu": "Massachusetts Institute of Technology",
            "www.mit.edu": "Massachusetts Institute of Technology",
            "mit.edu": "Massachusetts Institute of Technology",
            "www.csail.mit.edu": "Massachusetts Institute of Technology",
            "csail.mit.edu": "Massachusetts Institute of Technology",
            "www.eecs.mit.edu": "Massachusetts Institute of Technology",
            # Stanford
            "news.stanford.edu": "Stanford University",
            "stanford.edu": "Stanford University",
            "hai.stanford.edu": "Stanford University",
            "engineering.stanford.edu": "Stanford University",
            # CMU
            "www.cmu.edu": "Carnegie Mellon University",
            "cmu.edu": "Carnegie Mellon University",
            "today.cmu.edu": "Carnegie Mellon University",
            "news.cmu.edu": "Carnegie Mellon University",
            "www.cs.cmu.edu": "Carnegie Mellon University",
            # Berkeley
            "news.berkeley.edu": "University of California-Berkeley",
            "berkeley.edu": "University of California-Berkeley",
            # Caltech
            "www.caltech.edu": "California Institute of Technology",
            "caltech.edu": "California Institute of Technology",
            # Georgia Tech
            "news.gatech.edu": "Georgia Institute of Technology",
            "gatech.edu": "Georgia Institute of Technology",
            # UMich
            "news.umich.edu": "University of Michigan-Ann Arbor",
            "umich.edu": "University of Michigan-Ann Arbor",
            # Yale
            "news.yale.edu": "Yale University",
            "yale.edu": "Yale University",
            # Cornell
            "news.cornell.edu": "Cornell University",
            "cornell.edu": "Cornell University",
            # Columbia
            "news.columbia.edu": "Columbia University in the City of New York",
            "columbia.edu": "Columbia University in the City of New York",
            # UW
            "www.washington.edu": "University of Washington-Seattle Campus",
            "washington.edu": "University of Washington-Seattle Campus",
            "cs.washington.edu": "University of Washington-Seattle Campus",
            # UIUC
            "news.illinois.edu": "University of Illinois Urbana-Champaign",
            "illinois.edu": "University of Illinois Urbana-Champaign",
            # Harvard
            "news.harvard.edu": "Harvard University",
            "harvard.edu": "Harvard University",
            "www.harvard.edu": "Harvard University",
        }
        self.hostname_to_name.update(OVERRIDES)

    def _process_entries(self, entries: list, name_field: str) -> int:
        """
        Process a list of entries and add hostname mappings.

        Args:
            entries: List of source dictionaries
            name_field: Key to use for the institution name

        Returns:
            Number of entries processed
        """
        count = 0
        for entry in entries:
            name = entry.get(name_field)
            if not name:
                continue

            # Get URL from various formats
            news_url = self._extract_news_url(entry)
            if not news_url:
                continue

            # Parse the news URL to get the hostname
            parsed = urlparse(news_url)
            hostname = parsed.netloc.lower()
            if not hostname:
                continue

            # Store full hostname mapping
            self.hostname_to_name[hostname] = name

            # Also store base domain mapping (e.g., stanford.edu)
            parts = hostname.split('.')
            if len(parts) >= 2:
                base_domain = '.'.join(parts[-2:])
                if base_domain not in self.hostname_to_name:
                    self.hostname_to_name[base_domain] = name

            count += 1

        return count

    @staticmethod
    def _extract_news_url(entry: dict) -> Optional[str]:
        """Extract the primary news URL from various source formats."""
        # Legacy format: direct news_url field
        if 'news_url' in entry:
            return entry['news_url']

        # Schema v3.0.0: news_sources array
        news_sources = entry.get('news_sources', [])
        if isinstance(news_sources, list) and news_sources:
            # Find primary source
            for ns in news_sources:
                if ns.get('type') == 'primary':
                    return ns.get('url')
            # Fallback to first source
            return news_sources[0].get('url')

        # Legacy nested format
        if 'news' in entry:
            news = entry['news']
            return news.get('main_url') or news.get('url')

        return None

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
