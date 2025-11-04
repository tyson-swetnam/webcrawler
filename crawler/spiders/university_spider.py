"""
Scrapy spider for crawling university news sites.

This spider crawls US university news pages to discover and extract
AI-related articles with ethical rate limiting and politeness.
"""

import scrapy
from scrapy.linkextractors import LinkExtractor
from datetime import datetime, timezone
from typing import Dict, Any
import hashlib
import logging

from crawler.config.settings import settings
from crawler.db.models import URL, Article
from crawler.extractors.content import ContentExtractor
from crawler.utils.deduplication import (
    compute_url_hash,
    compute_content_hash,
    check_url_seen,
    get_or_create_url,
    normalize_url
)
from crawler.utils.mcp_fetcher import MCPFetcher

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

        # Depth limiting - prevent crawling too deep into pagination
        'DEPTH_LIMIT': 10,  # Maximum 10 levels of pagination per domain
        'DEPTH_PRIORITY': 1,

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

        # Lazy database session initialization (initialized on first access)
        self._db = None

        # Initialize content extractor
        self.content_extractor = ContentExtractor()

        # Initialize MCP fetcher for fallback
        self.mcp_fetcher = MCPFetcher()

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
                r'/(tag|category|author|archive|search|login|admin|calendar|events|galleries)/',
                r'/archives/\d{4}/',  # Exclude year-based archives (e.g., /archives/2021/)
                r'/stories/archives/',  # Exclude CMU-style archive directories
                r'\.(pdf|jpg|jpeg|png|gif|zip|rar|exe)$'
            ),
            unique=True,
            deny_domains=[]
        )

        # Build domain-to-canonical-name mapping for accurate university classification
        self.domain_to_canonical = self._build_domain_mapping()

        # Load university sources
        self.start_urls = self.load_university_sources()

        # Statistics
        self.stats = {
            'urls_discovered': 0,
            'urls_crawled': 0,
            'articles_extracted': 0,
            'duplicates_skipped': 0,
            'errors': 0,
            'mcp_fallback_attempts': 0,
            'mcp_fallback_successes': 0
        }

        logger.info(f"Initialized {self.name} spider with {len(self.start_urls)} start URLs")
        logger.info(f"Built domain mapping for {len(self.domain_to_canonical)} domains")

    @property
    def db(self):
        """
        Lazy-load database session.

        This property initializes the database connection on first access,
        which is important when running in a subprocess context where
        the database manager may not be initialized during __init__.
        """
        if self._db is None:
            from crawler.db.session import init_db, SessionLocal
            # Initialize database in subprocess if not already done
            try:
                init_db(
                    settings.database_url,
                    pool_size=settings.database_pool_size,
                    echo=settings.database_echo
                )
            except Exception as e:
                # If already initialized, this will fail silently
                logger.debug(f"Database already initialized or init failed: {e}")

            # Create session
            self._db = SessionLocal()
            logger.info("Database session created for spider")
        return self._db

    def _build_domain_mapping(self) -> Dict[str, str]:
        """
        Build a mapping from news domains to canonical university/facility names.

        This mapping is used to ensure that articles are classified with the
        canonical name from config files rather than Trafilatura's extracted sitename.

        Returns:
            Dictionary mapping domain (e.g., 'eng.auburn.edu') to canonical name
            (e.g., 'Auburn University')
        """
        import json
        from pathlib import Path
        from urllib.parse import urlparse

        domain_map = {}

        # Load R1 universities
        r1_path = Path("crawler/config/r1_universities.json")
        if r1_path.exists():
            try:
                with open(r1_path, 'r') as f:
                    data = json.load(f)
                    for univ in data.get('universities', []):
                        canonical = univ.get('canonical_name', univ.get('name'))

                        # Add primary domain
                        if 'domains' in univ and 'primary' in univ['domains']:
                            domain_map[univ['domains']['primary']] = canonical

                        # Add news domains
                        if 'domains' in univ and 'news_domains' in univ['domains']:
                            for domain in univ['domains']['news_domains']:
                                domain_map[domain] = canonical

                        # Add domains from news URLs
                        if 'news_sources' in univ and 'primary' in univ['news_sources']:
                            url = univ['news_sources']['primary'].get('url')
                            if url:
                                parsed = urlparse(url)
                                domain_map[parsed.netloc] = canonical

                            ai_url = univ['news_sources']['primary'].get('ai_tag_url')
                            if ai_url:
                                parsed = urlparse(ai_url)
                                domain_map[parsed.netloc] = canonical

                logger.info(f"Loaded {len([k for k, v in domain_map.items()])} domains from R1 universities")
            except Exception as e:
                logger.error(f"Failed to load R1 universities: {e}")

        # Load peer institutions
        peer_path = Path("crawler/config/peer_institutions.json")
        if peer_path.exists():
            try:
                with open(peer_path, 'r') as f:
                    data = json.load(f)
                    for univ in data.get('universities', []):
                        canonical = univ.get('canonical_name', univ.get('name'))

                        # Add domains from news URLs
                        if 'news_sources' in univ and 'primary' in univ['news_sources']:
                            url = univ['news_sources']['primary'].get('url')
                            if url:
                                parsed = urlparse(url)
                                domain_map[parsed.netloc] = canonical

                            ai_url = univ['news_sources']['primary'].get('ai_tag_url')
                            if ai_url:
                                parsed = urlparse(ai_url)
                                domain_map[parsed.netloc] = canonical

                logger.info(f"Loaded domains from {len(data.get('universities', []))} peer institutions")
            except Exception as e:
                logger.error(f"Failed to load peer institutions: {e}")

        # Load major facilities
        facilities_path = Path("crawler/config/major_facilities.json")
        if facilities_path.exists():
            try:
                with open(facilities_path, 'r') as f:
                    data = json.load(f)
                    for facility in data.get('facilities', []):
                        canonical = facility.get('name')

                        # Add domains from news URLs
                        if 'news_sources' in facility and 'primary' in facility['news_sources']:
                            url = facility['news_sources']['primary'].get('url')
                            if url:
                                parsed = urlparse(url)
                                domain_map[parsed.netloc] = canonical

                            ai_url = facility['news_sources']['primary'].get('ai_tag_url')
                            if ai_url:
                                parsed = urlparse(ai_url)
                                domain_map[parsed.netloc] = canonical

                logger.info(f"Loaded domains from {len(data.get('facilities', []))} major facilities")
            except Exception as e:
                logger.error(f"Failed to load major facilities: {e}")

        return domain_map

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
        Supports both Scrapy-fetched and MCP-fetched content.
        """
        url_hash = response.meta['url_hash']
        normalized_url = response.meta['normalized_url']
        is_mcp_fetched = response.meta.get('mcp_fetched', False)

        if is_mcp_fetched:
            self.logger.info(f"Extracting article (MCP-fetched): {response.url}")
        else:
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

            # Check article age - only process recent articles
            if extracted.get('date'):
                try:
                    from datetime import timedelta, timezone
                    article_date = datetime.fromisoformat(
                        extracted['date'].replace('Z', '+00:00')
                    )
                    age_limit = datetime.now(timezone.utc) - timedelta(days=settings.max_article_age_days)

                    if article_date < age_limit:
                        self.logger.info(
                            f"Skipping old article ({article_date.date()}): {extracted.get('title', response.url)}"
                        )
                        self._update_url_status(url_hash, 'excluded')
                        return
                except (ValueError, AttributeError, TypeError) as e:
                    # If date parsing fails, log but continue processing
                    self.logger.debug(f"Could not parse article date: {e}")

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
                'extracted_at': datetime.now(timezone.utc).isoformat()
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
                url_obj.last_checked = datetime.now(timezone.utc)
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

            # Determine canonical university name
            # Priority: domain mapping lookup -> sitename from Trafilatura
            canonical_name = self._get_canonical_name(
                article_data['hostname'],
                article_data.get('sitename')
            )

            # Create article entry
            article = Article(
                url_id=url_obj.url_id,
                title=article_data.get('title'),
                author=article_data.get('author'),
                published_date=published_date,
                content=article_data['content'],
                content_hash=article_data['content_hash'],
                summary=article_data.get('description'),
                university_name=canonical_name,
                language=article_data.get('language', 'en'),
                word_count=article_data.get('word_count'),
                metadata={
                    'categories': article_data.get('categories', []),
                    'tags': article_data.get('tags', []),
                    'hostname': article_data['hostname'],
                    'original_sitename': article_data.get('sitename')  # Preserve original for debugging
                },
                first_scraped=datetime.now(timezone.utc)
            )

            # Update URL status
            url_obj.status = 'crawled'
            url_obj.last_checked = datetime.now(timezone.utc)
            url_obj.content_hash = article_data['content_hash']

            self.db.add(article)
            self.db.commit()

            self.logger.debug(f"Stored article in database: {article.article_id} (university: {canonical_name})")

        except Exception as e:
            self.logger.error(f"Failed to store article in database: {e}")
            self.db.rollback()
            raise

    def _get_canonical_name(self, hostname: str, sitename: str = None) -> str:
        """
        Get canonical university/facility name from domain mapping.

        This method looks up the hostname in the domain-to-canonical mapping
        built from config files. If not found, falls back to sitename.

        Args:
            hostname: The domain from the article URL (e.g., 'eng.auburn.edu')
            sitename: The sitename extracted by Trafilatura (fallback)

        Returns:
            Canonical name from config, or sitename if no mapping exists
        """
        # Direct lookup
        if hostname in self.domain_to_canonical:
            canonical = self.domain_to_canonical[hostname]
            if sitename and canonical != sitename:
                self.logger.debug(
                    f"Mapped '{sitename}' -> '{canonical}' for domain {hostname}"
                )
            return canonical

        # Try removing 'www.' prefix
        if hostname.startswith('www.'):
            without_www = hostname[4:]
            if without_www in self.domain_to_canonical:
                canonical = self.domain_to_canonical[without_www]
                self.logger.debug(
                    f"Mapped '{sitename}' -> '{canonical}' for domain {hostname} (without www)"
                )
                return canonical

        # Try parent domain (e.g., 'eng.auburn.edu' -> 'auburn.edu')
        parts = hostname.split('.')
        if len(parts) > 2:
            parent_domain = '.'.join(parts[-2:])
            if parent_domain in self.domain_to_canonical:
                canonical = self.domain_to_canonical[parent_domain]
                self.logger.debug(
                    f"Mapped '{sitename}' -> '{canonical}' for domain {hostname} (parent domain)"
                )
                return canonical

        # No mapping found, use sitename as fallback
        if sitename:
            self.logger.debug(f"No canonical mapping found for {hostname}, using sitename: {sitename}")
            return sitename

        # Last resort: use hostname
        self.logger.warning(f"No canonical name or sitename found for {hostname}")
        return hostname

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
                url_obj.last_checked = datetime.now(timezone.utc)
                self.db.commit()
        except Exception as e:
            self.logger.error(f"Failed to update URL status: {e}")
            self.db.rollback()

    def handle_error(self, failure):
        """
        Handle request errors with MCP fallback for 403/404 errors.

        Args:
            failure: Twisted Failure object
        """
        url = failure.request.url
        self.logger.error(f"Request failed: {url}")
        self.logger.error(f"Error: {failure.value}")
        self.stats['errors'] += 1

        # Check if we should attempt MCP fallback
        status_code = None
        if hasattr(failure.value, 'response') and failure.value.response:
            status_code = failure.value.response.status

        # Try MCP fallback for 403/404 errors
        if self.mcp_fetcher.should_use_mcp_fallback(status_code, url):
            self.logger.info(f"Attempting MCP fallback for {url}")
            self.stats['mcp_fallback_attempts'] += 1

            try:
                # Fetch content using MCP
                html_content = self.mcp_fetcher.fetch_with_mcp(url)

                if html_content:
                    # Create a fake response object for processing
                    from scrapy.http import TextResponse

                    mcp_response = TextResponse(
                        url=url,
                        body=html_content.encode('utf-8'),
                        encoding='utf-8',
                        request=failure.request
                    )

                    # Copy metadata from original request
                    if 'url_hash' in failure.request.meta:
                        mcp_response.meta['url_hash'] = failure.request.meta['url_hash']
                        mcp_response.meta['normalized_url'] = failure.request.meta['normalized_url']
                    else:
                        # Generate metadata if not present
                        from crawler.utils.deduplication import compute_url_hash, normalize_url
                        normalized = normalize_url(url)
                        mcp_response.meta['url_hash'] = compute_url_hash(normalized)
                        mcp_response.meta['normalized_url'] = normalized

                    # Mark as MCP-fetched for logging
                    mcp_response.meta['mcp_fetched'] = True

                    self.stats['mcp_fallback_successes'] += 1
                    self.logger.info(f"MCP fallback successful for {url}")

                    # Process the article using normal pipeline
                    # We need to manually call parse_article since we're in error handler
                    # Use Scrapy's callback mechanism properly
                    return self.parse_article(mcp_response)

            except Exception as e:
                self.logger.error(f"MCP fallback failed for {url}: {e}")

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
  MCP Fallback Attempts: {self.stats['mcp_fallback_attempts']}
  MCP Fallback Successes: {self.stats['mcp_fallback_successes']}
""")
