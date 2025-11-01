"""
Rate limiting utilities for ethical web crawling.

This module implements per-domain rate limiting to ensure
politeness and respect for website resources.
"""

import time
from collections import defaultdict, deque
from datetime import datetime, timedelta
from typing import Optional
from sqlalchemy.orm import Session
from crawler.db.models import HostCrawlState
import logging

logger = logging.getLogger(__name__)


class DomainRateLimiter:
    """
    Per-domain rate limiting with configurable delays.

    Ensures requests to each domain are spaced appropriately
    according to configured crawl delays and robots.txt directives.
    """

    def __init__(self, default_delay: float = 1.0):
        """
        Initialize rate limiter.

        Args:
            default_delay: Default delay between requests in seconds
        """
        self.default_delay = default_delay
        self.domain_requests = defaultdict(deque)
        self.domain_delays = {}
        logger.info(f"Initialized DomainRateLimiter with default_delay={default_delay}s")

    def set_domain_delay(self, domain: str, delay: float):
        """
        Set custom delay for specific domain.

        Args:
            domain: Domain name (e.g., 'example.com')
            delay: Delay in seconds
        """
        self.domain_delays[domain] = delay
        logger.debug(f"Set custom delay for {domain}: {delay}s")

    def get_domain_delay(self, domain: str) -> float:
        """
        Get configured delay for domain.

        Args:
            domain: Domain name

        Returns:
            Delay in seconds
        """
        return self.domain_delays.get(domain, self.default_delay)

    def wait_if_needed(self, domain: str):
        """
        Block execution until it's safe to make request to domain.

        Args:
            domain: Domain to check
        """
        delay = self.get_domain_delay(domain)
        now = time.time()

        # Clean old requests (older than delay window)
        while (self.domain_requests[domain] and
               self.domain_requests[domain][0] <= now - delay):
            self.domain_requests[domain].popleft()

        # Check if we need to wait
        if self.domain_requests[domain]:
            last_request = self.domain_requests[domain][-1]
            time_since_last = now - last_request

            if time_since_last < delay:
                sleep_time = delay - time_since_last
                logger.debug(f"Rate limiting {domain}: sleeping {sleep_time:.2f}s")
                time.sleep(sleep_time)

        # Record this request
        self.domain_requests[domain].append(time.time())

    def can_request_now(self, domain: str) -> bool:
        """
        Check if request can be made immediately without waiting.

        Args:
            domain: Domain to check

        Returns:
            True if request can be made now, False otherwise
        """
        delay = self.get_domain_delay(domain)
        now = time.time()

        if not self.domain_requests[domain]:
            return True

        last_request = self.domain_requests[domain][-1]
        time_since_last = now - last_request

        return time_since_last >= delay

    def get_next_available_time(self, domain: str) -> float:
        """
        Get timestamp when next request to domain will be allowed.

        Args:
            domain: Domain to check

        Returns:
            Unix timestamp of next available request time
        """
        if not self.domain_requests[domain]:
            return time.time()

        delay = self.get_domain_delay(domain)
        last_request = self.domain_requests[domain][-1]
        return last_request + delay


class DatabaseRateLimiter:
    """
    Database-backed rate limiter using HostCrawlState table.

    Persists crawl state across application restarts and
    respects robots.txt delays.
    """

    def __init__(self, db: Session, default_delay: float = 1.0):
        """
        Initialize database rate limiter.

        Args:
            db: Database session
            default_delay: Default crawl delay in seconds
        """
        self.db = db
        self.default_delay = default_delay

    def get_host_state(self, hostname: str) -> Optional[HostCrawlState]:
        """
        Get crawl state for hostname from database.

        Args:
            hostname: Hostname to look up

        Returns:
            HostCrawlState instance or None
        """
        return self.db.query(HostCrawlState).filter(
            HostCrawlState.hostname == hostname
        ).first()

    def update_host_state(
        self,
        hostname: str,
        crawl_delay: Optional[timedelta] = None,
        robots_txt_delay: Optional[timedelta] = None
    ):
        """
        Update or create host crawl state.

        Args:
            hostname: Hostname to update
            crawl_delay: Optional custom crawl delay
            robots_txt_delay: Optional delay from robots.txt
        """
        state = self.get_host_state(hostname)

        if state is None:
            # Create new state
            state = HostCrawlState(
                hostname=hostname,
                last_crawl_time=datetime.utcnow(),
                crawl_delay=crawl_delay or timedelta(seconds=self.default_delay),
                robots_txt_delay=robots_txt_delay
            )
            self.db.add(state)
        else:
            # Update existing state
            state.last_crawl_time = datetime.utcnow()
            if crawl_delay is not None:
                state.crawl_delay = crawl_delay
            if robots_txt_delay is not None:
                state.robots_txt_delay = robots_txt_delay

        self.db.commit()

    def can_crawl_now(self, hostname: str) -> bool:
        """
        Check if hostname can be crawled immediately.

        Args:
            hostname: Hostname to check

        Returns:
            True if can crawl now, False otherwise
        """
        state = self.get_host_state(hostname)

        if state is None:
            return True

        # Check if blocked
        if state.blocked_until and datetime.utcnow() < state.blocked_until:
            return False

        # Get effective delay (use robots.txt if available)
        delay = state.robots_txt_delay or state.crawl_delay or timedelta(seconds=self.default_delay)

        # Check if enough time has passed
        time_since_last = datetime.utcnow() - state.last_crawl_time
        return time_since_last >= delay

    def wait_if_needed(self, hostname: str):
        """
        Wait until hostname can be crawled according to stored state.

        Args:
            hostname: Hostname to wait for
        """
        state = self.get_host_state(hostname)

        if state is None:
            return

        # Check if blocked
        if state.blocked_until and datetime.utcnow() < state.blocked_until:
            wait_time = (state.blocked_until - datetime.utcnow()).total_seconds()
            logger.warning(f"Host {hostname} blocked until {state.blocked_until}. Waiting {wait_time:.1f}s")
            time.sleep(wait_time)
            return

        # Get effective delay
        delay = state.robots_txt_delay or state.crawl_delay or timedelta(seconds=self.default_delay)

        # Calculate wait time
        time_since_last = datetime.utcnow() - state.last_crawl_time
        if time_since_last < delay:
            wait_seconds = (delay - time_since_last).total_seconds()
            logger.debug(f"Rate limiting {hostname}: waiting {wait_seconds:.2f}s")
            time.sleep(wait_seconds)

    def block_host(self, hostname: str, duration_seconds: int):
        """
        Temporarily block a host (e.g., after receiving 429 or 503).

        Args:
            hostname: Hostname to block
            duration_seconds: Block duration in seconds
        """
        state = self.get_host_state(hostname)
        blocked_until = datetime.utcnow() + timedelta(seconds=duration_seconds)

        if state is None:
            state = HostCrawlState(
                hostname=hostname,
                last_crawl_time=datetime.utcnow(),
                blocked_until=blocked_until
            )
            self.db.add(state)
        else:
            state.blocked_until = blocked_until

        self.db.commit()
        logger.warning(f"Blocked {hostname} until {blocked_until}")


class TokenBucket:
    """
    Token bucket algorithm for rate limiting.

    Allows bursts while maintaining average rate limit.
    """

    def __init__(self, rate: float, capacity: int):
        """
        Initialize token bucket.

        Args:
            rate: Tokens per second
            capacity: Maximum tokens in bucket
        """
        self.rate = rate
        self.capacity = capacity
        self.tokens = capacity
        self.last_update = time.time()

    def _refill(self):
        """Refill tokens based on time elapsed."""
        now = time.time()
        elapsed = now - self.last_update

        # Add tokens based on elapsed time
        self.tokens = min(
            self.capacity,
            self.tokens + elapsed * self.rate
        )
        self.last_update = now

    def consume(self, tokens: int = 1) -> bool:
        """
        Try to consume tokens.

        Args:
            tokens: Number of tokens to consume

        Returns:
            True if tokens consumed, False if not enough tokens
        """
        self._refill()

        if self.tokens >= tokens:
            self.tokens -= tokens
            return True
        return False

    def wait_for_tokens(self, tokens: int = 1):
        """
        Wait until tokens are available and consume them.

        Args:
            tokens: Number of tokens to wait for
        """
        while not self.consume(tokens):
            # Calculate wait time
            tokens_needed = tokens - self.tokens
            wait_time = tokens_needed / self.rate
            time.sleep(min(wait_time, 0.1))  # Sleep in small increments


# Global rate limiter instance
_rate_limiter = None


def get_rate_limiter(default_delay: float = 1.0) -> DomainRateLimiter:
    """
    Get global rate limiter instance.

    Args:
        default_delay: Default delay between requests

    Returns:
        DomainRateLimiter instance
    """
    global _rate_limiter
    if _rate_limiter is None:
        _rate_limiter = DomainRateLimiter(default_delay)
    return _rate_limiter
