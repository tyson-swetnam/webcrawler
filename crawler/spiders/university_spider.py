"""
Scrapy spider for crawling university news sites.

This spider crawls US university news pages to discover and extract
AI-related articles with ethical rate limiting and politeness.
"""

import scrapy
from scrapy.linkextractors import LinkExtractor
from datetime import datetime
from typing import Dict, Any
import hashlib
import logging

from crawler.config.settings import settings
from crawler.db.session import SessionLocal
from crawler.db.models import URL, Article
from crawler.extractors.content import ContentExtractor
from crawler.utils.deduplication import (
    compute_url_hash,
    compute_content_hash,
    check_url_seen,
    get_or_create_url,
    normalize_url
)

logger = logging.getLogger(__name__)


class UniversityNewsSpider(scrapy.Spider):
    """
    Spider for crawling university news sites.

    Features:
    - Respects robots.txt and crawl delays
    - Extracts content using Trafilatura
    - Hash-based deduplication
    - Stores results in PostgreSQL database
    """

    name = 'university_news'
    allowed_domains = []  # Set dynamically from config

    custom_settings = {
        'DOWNLOAD_DELAY': settings.crawl_delay,
        'CONCURRENT_REQUESTS_PER_DOMAIN': 1,
        'CONCURRENT_REQUESTS': settings.max_concurrent_requests,
        'AUTOTHROTTLE_ENABLED': True,
        'AUTOTHROTTLE_START_DELAY': 1.0,
        'AUTOTHROTTLE_MAX_DELAY': 10.0,
        'AUTOTHROTTLE_TARGET_CONCURRENCY': 2.0,
        'ROBOTSTXT_OBEY': True,
        'USER_AGENT': settings.user_agent,
        'DOWNLOAD_TIMEOUT': settings.request_timeout,
        'RETRY_TIMES': 3,
        'RETRY_HTTP_CODES': [500, 502, 503, 504, 408, 429],

        # Compression
        'COMPRESSION_ENABLED': True,

        # Cookies
        'COOKIES_ENABLED': False,

        # Download handlers
        'DOWNLOAD_HANDLERS': {
            'http': 'scrapy.core.downloader.handlers.http.HTTPDownloadHandler',
            'https': 'scrapy.core.downloader.handlers.http.HTTPDownloadHandler',
        },

        # Middlewares
        'DOWNLOADER_MIDDLEWARES': {
            'scrapy.downloadermiddlewares.useragent.UserAgentMiddleware': None,
            'scrapy.downloadermiddlewares.retry.RetryMiddleware': 90,
            'scrapy.downloadermiddlewares.httpcompression.HttpCompressionMiddleware': 810,
        }
    }

    def __init__(self, *args, **kwargs):
        """Initialize spider with configuration."""
        super().__init__(*args, **kwargs)

        # Initialize database session
        self.db = SessionLocal()

        # Initialize content extractor
        self.content_extractor = ContentExtractor()

        # Link extractor for news pages
        self.link_extractor = LinkExtractor(
            allow=(
                r'/news/',
                r'/press-releases?/',
                r'/media/',
                r'/research/',
                r'/stories/',
                r'/articles/'
            ),
            deny=(
                r'/(tag|category|author|archive|search|login|admin)/',
                r'\.(pdf|jpg|jpeg|png|gif|zip|rar|exe)$'
            ),
            unique=True,
            deny_domains=[]
        )

        # Load university sources
        self.start_urls = self.load_university_sources()

        # Statistics
        self.stats = {
            'urls_discovered': 0,
            'urls_crawled': 0,
            'articles_extracted': 0,
            'duplicates_skipped': 0,
            'errors': 0
        }

        logger.info(f"Initialized {self.name} spider with {len(self.start_urls)} start URLs")

    def load_university_sources(self) -> list:
        """
        Load university news URLs from configuration.

        Returns:
            List of start URLs
        """
        try:
            universities = settings.get_university_sources()
            urls = []

            for univ in universities:
                url = univ.get('news_url')
                if url:
                    urls.append(url)
                    # Add domain to allowed_domains
                    from urllib.parse import urlparse
                    domain = urlparse(url).netloc
                    if domain not in self.allowed_domains:
                        self.allowed_domains.append(domain)

            logger.info(f"Loaded {len(urls)} university sources")
            return urls

        except Exception as e:
            logger.error(f"Failed to load university sources: {e}")
            return []

    def parse(self, response):
        """
        Parse news listing page.

        Extracts article links and follows pagination.
        """
        self.logger.info(f"Parsing listing page: {response.url}")

        # Extract article links
        for link in self.link_extractor.extract_links(response):
            self.stats['urls_discovered'] += 1

            # Check if URL already seen (fast bloom filter check)
            normalized = normalize_url(link.url)
            url_hash = compute_url_hash(normalized)

            if not check_url_seen(self.db, url_hash):
                yield scrapy.Request(
                    link.url,
                    callback=self.parse_article,
                    meta={
                        'url_hash': url_hash,
                        'normalized_url': normalized
                    },
                    errback=self.handle_error
                )
            else:
                self.stats['duplicates_skipped'] += 1
                self.logger.debug(f"Skipping duplicate URL: {link.url}")

        # Follow pagination
        pagination_selectors = [
            'a.next::attr(href)',
            'a[rel="next"]::attr(href)',
            'a.pagination__next::attr(href)',
            'link[rel="next"]::attr(href)',
            '.pagination a:contains("Next")::attr(href)',
            '.pager-next a::attr(href)'
        ]

        for selector in pagination_selectors:
            next_page = response.css(selector).get()
            if next_page:
                self.logger.debug(f"Following pagination: {next_page}")
                yield response.follow(next_page, self.parse)
                break

    def parse_article(self, response):
        """
        Extract article content from article page.

        Uses Trafilatura for high-quality content extraction.
        """
        url_hash = response.meta['url_hash']
        normalized_url = response.meta['normalized_url']

        self.logger.info(f"Extracting article: {response.url}")
        self.stats['urls_crawled'] += 1

        try:
            # Extract content using Trafilatura
            extracted = self.content_extractor.extract_from_html(
                response.text,
                url=response.url
            )

            if not extracted:
                self.logger.warning(f"Failed to extract content from {response.url}")
                self._update_url_status(url_hash, 'failed')
                return

            # Validate content quality
            if not self.content_extractor.is_content_valid(
                extracted,
                min_words=settings.min_article_length
            ):
                self.logger.info(f"Content quality check failed for {response.url}")
                self._update_url_status(url_hash, 'excluded')
                return

            # Compute content hash for deduplication
            content_hash = compute_content_hash(extracted['text'])

            # Extract hostname
            from urllib.parse import urlparse
            hostname = urlparse(response.url).netloc

            # Prepare article data
            article_data = {
                'url': response.url,
                'url_hash': url_hash,
                'normalized_url': normalized_url,
                'hostname': hostname,
                'title': extracted.get('title'),
                'author': extracted.get('author'),
                'published_date': extracted.get('date'),
                'content': extracted['text'],
                'content_hash': content_hash,
                'description': extracted.get('description'),
                'sitename': extracted.get('sitename'),
                'language': extracted.get('language', 'en'),
                'word_count': extracted.get('word_count'),
                'categories': extracted.get('categories', []),
                'tags': extracted.get('tags', []),
                'extracted_at': datetime.utcnow().isoformat()
            }

            # Store in database
            self._store_article(article_data)

            self.stats['articles_extracted'] += 1
            self.logger.info(f"Successfully extracted article: {extracted.get('title', 'Untitled')}")

            yield article_data

        except Exception as e:
            self.logger.error(f"Error parsing article {response.url}: {e}")
            self.stats['errors'] += 1
            self._update_url_status(url_hash, 'failed')

    def _store_article(self, article_data: Dict[str, Any]):
        """
        Store article in database.

        Args:
            article_data: Article data dictionary
        """
        try:
            # Get or create URL entry
            url_obj, created = get_or_create_url(
                self.db,
                article_data['url'],
                article_data['hostname'],
                commit=False
            )

            # Check for content duplicate
            from crawler.utils.deduplication import check_content_duplicate
            existing_article = check_content_duplicate(
                self.db,
                article_data['content_hash']
            )

            if existing_article:
                self.logger.debug(f"Duplicate content detected for {article_data['url']}")
                url_obj.status = 'crawled'
                url_obj.last_checked = datetime.utcnow()
                self.db.commit()
                return

            # Parse published date
            published_date = None
            if article_data.get('published_date'):
                try:
                    published_date = datetime.fromisoformat(
                        article_data['published_date'].replace('Z', '+00:00')
                    ).date()
                except (ValueError, AttributeError):
                    pass

            # Create article entry
            article = Article(
                url_id=url_obj.url_id,
                title=article_data.get('title'),
                author=article_data.get('author'),
                published_date=published_date,
                content=article_data['content'],
                content_hash=article_data['content_hash'],
                summary=article_data.get('description'),
                university_name=article_data.get('sitename'),
                language=article_data.get('language', 'en'),
                word_count=article_data.get('word_count'),
                metadata={
                    'categories': article_data.get('categories', []),
                    'tags': article_data.get('tags', []),
                    'hostname': article_data['hostname']
                },
                first_scraped=datetime.utcnow()
            )

            # Update URL status
            url_obj.status = 'crawled'
            url_obj.last_checked = datetime.utcnow()
            url_obj.content_hash = article_data['content_hash']

            self.db.add(article)
            self.db.commit()

            self.logger.debug(f"Stored article in database: {article.article_id}")

        except Exception as e:
            self.logger.error(f"Failed to store article in database: {e}")
            self.db.rollback()
            raise

    def _update_url_status(self, url_hash: str, status: str):
        """
        Update URL status in database.

        Args:
            url_hash: URL hash
            status: New status
        """
        try:
            url_obj = self.db.query(URL).filter(URL.url_hash == url_hash).first()
            if url_obj:
                url_obj.status = status
                url_obj.last_checked = datetime.utcnow()
                self.db.commit()
        except Exception as e:
            self.logger.error(f"Failed to update URL status: {e}")
            self.db.rollback()

    def handle_error(self, failure):
        """
        Handle request errors.

        Args:
            failure: Twisted Failure object
        """
        self.logger.error(f"Request failed: {failure.request.url}")
        self.logger.error(f"Error: {failure.value}")
        self.stats['errors'] += 1

    def closed(self, reason):
        """
        Clean up when spider closes.

        Args:
            reason: Reason for spider closure
        """
        self.logger.info(f"Spider closing: {reason}")
        self.logger.info(f"Statistics: {self.stats}")

        # Close database session
        self.db.close()

        # Log final stats
        logger.info(f"""
Spider Statistics:
  URLs Discovered: {self.stats['urls_discovered']}
  URLs Crawled: {self.stats['urls_crawled']}
  Articles Extracted: {self.stats['articles_extracted']}
  Duplicates Skipped: {self.stats['duplicates_skipped']}
  Errors: {self.stats['errors']}
""")
