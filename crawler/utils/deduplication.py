"""
Deduplication utilities using hash-based fingerprinting.

This module provides functions for URL and content deduplication using
SHA-256 hashing for efficient O(1) lookups.
"""

import hashlib
from typing import Optional
from sqlalchemy.orm import Session
from crawler.db.models import URL, Article
import logging

logger = logging.getLogger(__name__)


def compute_url_hash(url: str) -> str:
    """
    Compute SHA-256 hash of a URL.

    Args:
        url: URL string to hash

    Returns:
        64-character hexadecimal hash string
    """
    return hashlib.sha256(url.encode('utf-8')).hexdigest()


def compute_content_hash(content: str) -> str:
    """
    Compute SHA-256 hash of article content.

    Args:
        content: Article text content

    Returns:
        64-character hexadecimal hash string
    """
    return hashlib.sha256(content.encode('utf-8')).hexdigest()


def normalize_url(url: str) -> str:
    """
    Normalize URL for consistent comparison.

    Removes trailing slashes, converts to lowercase, removes common
    tracking parameters, etc.

    Args:
        url: Raw URL string

    Returns:
        Normalized URL string
    """
    from urllib.parse import urlparse, urlunparse, parse_qs, urlencode

    # Parse URL
    parsed = urlparse(url.lower())

    # Remove tracking parameters
    tracking_params = {
        'utm_source', 'utm_medium', 'utm_campaign', 'utm_term', 'utm_content',
        'fbclid', 'gclid', 'mc_cid', 'mc_eid'
    }

    query_params = parse_qs(parsed.query)
    cleaned_params = {
        k: v for k, v in query_params.items()
        if k not in tracking_params
    }

    # Rebuild query string
    new_query = urlencode(cleaned_params, doseq=True) if cleaned_params else ''

    # Remove trailing slash from path
    path = parsed.path.rstrip('/') if parsed.path != '/' else parsed.path

    # Rebuild URL
    normalized = urlunparse((
        parsed.scheme,
        parsed.netloc,
        path,
        parsed.params,
        new_query,
        ''  # Remove fragment
    ))

    return normalized


def check_url_seen(db: Session, url_hash: str) -> bool:
    """
    Check if URL hash exists in database.

    Args:
        db: Database session
        url_hash: SHA-256 hash of URL

    Returns:
        True if URL already exists, False otherwise
    """
    exists = db.query(URL).filter(URL.url_hash == url_hash).first() is not None
    return exists


def check_content_duplicate(db: Session, content_hash: str) -> Optional[Article]:
    """
    Check if content hash exists in database.

    Args:
        db: Database session
        content_hash: SHA-256 hash of content

    Returns:
        Article instance if duplicate found, None otherwise
    """
    return db.query(Article).filter(Article.content_hash == content_hash).first()


def get_or_create_url(
    db: Session,
    url: str,
    hostname: str,
    commit: bool = True
) -> tuple[URL, bool]:
    """
    Get existing URL or create new one.

    Args:
        db: Database session
        url: URL string
        hostname: Hostname extracted from URL
        commit: Whether to commit the transaction

    Returns:
        Tuple of (URL instance, created_flag)
    """
    normalized = normalize_url(url)
    url_hash = compute_url_hash(normalized)

    # Check if exists
    existing = db.query(URL).filter(URL.url_hash == url_hash).first()
    if existing:
        return existing, False

    # Create new URL
    new_url = URL(
        url=url,
        url_hash=url_hash,
        normalized_url=normalized,
        hostname=hostname,
        status='pending'
    )

    db.add(new_url)

    if commit:
        db.commit()
        db.refresh(new_url)

    logger.debug(f"Created new URL entry: {hostname}")
    return new_url, True


class BloomFilter:
    """
    Space-efficient probabilistic data structure for deduplication.

    Used for fast pre-filtering before database lookups.
    Note: This is a simple implementation. For production, consider
    using a Redis-backed bloom filter for persistence.
    """

    def __init__(self, size: int = 1000000, hash_count: int = 3):
        """
        Initialize bloom filter.

        Args:
            size: Bit array size (larger = fewer false positives)
            hash_count: Number of hash functions to use
        """
        self.size = size
        self.hash_count = hash_count
        self.bit_array = [False] * size
        self.item_count = 0

    def _hash(self, item: str, seed: int) -> int:
        """
        Compute hash with seed for multiple hash functions.

        Args:
            item: String to hash
            seed: Seed value for hash function

        Returns:
            Hash value modulo filter size
        """
        h = hashlib.sha256(f"{item}{seed}".encode('utf-8'))
        return int(h.hexdigest(), 16) % self.size

    def add(self, item: str):
        """
        Add item to bloom filter.

        Args:
            item: String to add (typically a URL or content hash)
        """
        for i in range(self.hash_count):
            index = self._hash(item, i)
            self.bit_array[index] = True
        self.item_count += 1

    def contains(self, item: str) -> bool:
        """
        Check if item might be in the set.

        Args:
            item: String to check

        Returns:
            True if item might exist (or false positive),
            False if definitely doesn't exist
        """
        for i in range(self.hash_count):
            index = self._hash(item, i)
            if not self.bit_array[index]:
                return False
        return True

    @property
    def false_positive_rate(self) -> float:
        """
        Estimate current false positive rate.

        Returns:
            Approximate false positive probability
        """
        # Calculate based on theoretical formula
        # FPR ≈ (1 - e^(-kn/m))^k
        # where k = hash_count, n = item_count, m = size
        import math
        if self.item_count == 0:
            return 0.0

        exponent = -(self.hash_count * self.item_count) / self.size
        try:
            fpr = (1 - math.exp(exponent)) ** self.hash_count
            return fpr
        except (OverflowError, ValueError):
            return 1.0

    def __len__(self):
        """Return approximate number of items added."""
        return self.item_count


# Global bloom filter for URL deduplication (in-memory)
# For production, consider Redis-backed persistence
_url_bloom_filter = None


def get_url_bloom_filter() -> BloomFilter:
    """
    Get global URL bloom filter instance.

    Returns:
        BloomFilter instance
    """
    global _url_bloom_filter
    if _url_bloom_filter is None:
        _url_bloom_filter = BloomFilter(size=10000000, hash_count=3)
        logger.info("Initialized URL bloom filter")
    return _url_bloom_filter


def is_url_likely_seen(url: str) -> bool:
    """
    Fast check if URL was likely seen before.

    Uses bloom filter for O(1) lookup. May have false positives,
    so always verify with database for critical operations.

    Args:
        url: URL to check

    Returns:
        True if likely seen, False if definitely not seen
    """
    normalized = normalize_url(url)
    bloom = get_url_bloom_filter()
    return bloom.contains(normalized)


def mark_url_seen(url: str):
    """
    Mark URL as seen in bloom filter.

    Args:
        url: URL to mark
    """
    normalized = normalize_url(url)
    bloom = get_url_bloom_filter()
    bloom.add(normalized)
