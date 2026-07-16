"""
Single source of truth for Scrapy runtime settings.

Both the spider's `custom_settings` and the per-group subprocess script in
crawler/__main__.py import from here, so the crawl behaves identically no
matter how it is launched. (Previously three diverging copies existed.)
"""

from crawler.config.settings import settings


def build_scrapy_settings() -> dict:
    """Return the Scrapy settings dict used by every crawl."""
    return {
        'LOG_LEVEL': 'INFO',
        'USER_AGENT': settings.user_agent,
        'ROBOTSTXT_OBEY': True,

        # Concurrency & politeness
        'CONCURRENT_REQUESTS': settings.max_concurrent_requests,
        'CONCURRENT_REQUESTS_PER_DOMAIN': 1,
        'DOWNLOAD_DELAY': settings.crawl_delay,
        'AUTOTHROTTLE_ENABLED': True,
        'AUTOTHROTTLE_START_DELAY': 1.0,
        'AUTOTHROTTLE_MAX_DELAY': 10.0,
        'AUTOTHROTTLE_TARGET_CONCURRENCY': 2.0,

        # Networking
        'DOWNLOAD_TIMEOUT': settings.request_timeout,
        'RETRY_TIMES': 3,
        'RETRY_HTTP_CODES': [500, 502, 503, 504, 408, 429],
        'COOKIES_ENABLED': False,
        'COMPRESSION_ENABLED': True,

        # Depth limiting - prevent crawling too deep into pagination
        'DEPTH_LIMIT': 10,
        'DEPTH_PRIORITY': 1,
    }
