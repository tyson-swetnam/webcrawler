"""
Scrapy spider for crawling university news sites.

This spider crawls US university news pages to discover and extract
AI-related articles with ethical rate limiting and politeness.
"""

import gzip
import scrapy
from scrapy.linkextractors import LinkExtractor
from scrapy.utils.sitemap import Sitemap, sitemap_urls_from_robots
from datetime import datetime, timedelta, timezone
from typing import Dict, Any, Optional
from urllib.parse import urlparse
import hashlib
import json
import logging
import os
import re

import feedparser

from crawler.config.settings import settings
from crawler.config.scrapy_defaults import build_scrapy_settings
from crawler.db.models import URL, Article
from crawler.extractors.content import ContentExtractor
from crawler.utils.deduplication import (
    compute_url_hash,
    compute_content_hash,
    check_url_seen,
    get_or_create_url,
    normalize_url
)
from crawler.utils.source_health import SourceHealthTracker
from crawler.utils.university_name_mapper import get_mapper

logger = logging.getLogger(__name__)

# URL patterns that look like individual articles — used to decide whether an
# undated sitemap URL is worth fetching.
ARTICLE_URL_PATTERNS = (
    r'/news/.+',
    r'/press-releases?/.+',
    r'/stories?/.+',
    r'/articles?/.+',
    r'/\d{4}/\d{2}/',
    r'/posts?/.+',
    r'/features?/.+',
)

MAX_SITEMAP_URLS = 50        # article URLs taken per sitemap file
MAX_SITEMAP_CHILDREN = 5     # child sitemaps followed per sitemap index
MAX_SITEMAP_DEPTH = 2        # sitemapindex recursion depth


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

    # Shared Scrapy config (crawler/config/scrapy_defaults.py) plus
    # spider-specific handler/middleware overrides.
    custom_settings = {
        **build_scrapy_settings(),

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

        # Initialize university name mapper for fixing sitename extraction issues
        self.name_mapper = get_mapper()

        # Rolling source health (auto-disables repeatedly failing domains)
        self.health_tracker = SourceHealthTracker()

        # RSS/Atom feeds discovered via <link rel="alternate"> during the run
        self.discovered_feeds: Dict[str, str] = {}  # feed_url -> page it was found on
        self._followed_feeds: set = set()

        # Article-URL regexes for judging undated sitemap entries
        self._article_url_res = [re.compile(p, re.IGNORECASE) for p in ARTICLE_URL_PATTERNS]

        # Link extractor for news pages
        self.link_extractor = LinkExtractor(
            allow=(
                r'/news/',
                r'/press-releases?/',
                r'/media/',
                r'/research/',
                r'/stories?/',
                r'/articles?/',
                r'/\d{4}/\d{2}/',
                r'/posts?/',
                r'/features?/',
            ),
            deny=(
                r'/(tag|category|author|archive|section|search|login|admin|calendar|events|galleries)/',
                r'/archives/\d{4}/',  # Exclude year-based archives (e.g., /archives/2021/)
                r'/stories/archives/',  # Exclude CMU-style archive directories
                # Exclude navigation/listing pages (end with these terms)
                r'/news/?$',  # Just "/news" or "/news/"
                r'/news-events/?$',
                r'/news-and-events/?$',
                r'/press-releases/?$',
                r'/features-articles/?$',
                r'/accolades-honors/?$',
                r'/news/(features|accolades|honors|announcements|updates)/?$',
                r'/articles/?$',  # Just "/articles" or "/articles/"
                r'/stories/?$',  # Just "/stories" or "/stories/"
                r'\.(pdf|jpg|jpeg|png|gif|zip|rar|exe)$'
            ),
            unique=True,
            deny_domains=[]
        )

        # Statistics (initialized before source loading, which counts skips)
        self.stats = {
            'urls_discovered': 0,
            'urls_crawled': 0,
            'articles_extracted': 0,
            'duplicates_skipped': 0,
            'errors': 0,
            'sitemap_urls': 0,
            'feeds_discovered': 0,
            'sources_skipped_health': 0,
        }

        # Load university sources (full entries — start_requests fans out
        # front page + sitemaps + robots.txt per source)
        self.sources = self.load_university_sources()
        self.start_urls = [s['news_url'] for s in self.sources]

        # Per-domain tracking
        self.domain_stats = {}  # hostname -> {'urls': 0, 'articles': 0, 'errors': 0}
        self.sources_attempted = set()
        self.sources_succeeded = set()

        logger.info(f"Initialized {self.name} spider with {len(self.start_urls)} start URLs")

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

    def load_university_sources(self) -> list:
        """
        Load university news source entries from configuration.

        Returns:
            List of normalized source dicts (news_url, rss_feed, sitemaps, ...)
        """
        try:
            universities = settings.get_university_sources()
            sources = []

            for univ in universities:
                url = univ.get('news_url')
                if not url:
                    continue

                domain = urlparse(url).netloc
                if self.health_tracker.should_skip(domain):
                    self.stats['sources_skipped_health'] += 1
                    logger.info(f"Skipping auto-disabled source: {domain} ({univ.get('name')})")
                    continue

                sources.append(univ)
                # Add domain to allowed_domains
                if domain not in self.allowed_domains:
                    self.allowed_domains.append(domain)
                for sitemap_url in univ.get('sitemaps') or []:
                    sitemap_domain = urlparse(sitemap_url).netloc
                    if sitemap_domain and sitemap_domain not in self.allowed_domains:
                        self.allowed_domains.append(sitemap_domain)

            logger.info(
                f"Loaded {len(sources)} university source entries "
                f"({self.stats['sources_skipped_health']} skipped by health tracker)"
            )
            return sources

        except Exception as e:
            logger.error(f"Failed to load university sources: {e}")
            return []

    async def start(self):
        """Scrapy >= 2.13 entry point.

        Modern Scrapy no longer calls start_requests(); its default start()
        implementation reads only start_urls — which would silently skip the
        whole sitemap/robots fanout below.
        """
        for request in self.start_requests():
            yield request

    def start_requests(self):
        """Fan out discovery per source: front page/feed, sitemaps, robots.txt.

        The old behavior only requested each source's single news_url, so
        anything not linked from the front page was invisible. Sitemaps give
        dated coverage of the whole site; robots.txt frequently advertises
        them.
        """
        seen_hosts = set()

        for source in self.sources:
            news_url = source['news_url']
            yield scrapy.Request(
                news_url,
                callback=self.parse,
                errback=self.handle_error,
                meta={'source_name': source.get('name')},
            )

            parsed = urlparse(news_url)
            host_root = f"{parsed.scheme}://{parsed.netloc}"

            # Explicit sitemaps from the source config (schema field that was
            # previously never read)
            explicit_sitemaps = list(source.get('sitemaps') or [])[:MAX_SITEMAP_CHILDREN]
            for sitemap_url in explicit_sitemaps:
                yield scrapy.Request(
                    sitemap_url,
                    callback=self.parse_sitemap,
                    errback=self.handle_sitemap_error,
                    meta={'sitemap_depth': 0},
                )

            if parsed.netloc in seen_hosts:
                continue
            seen_hosts.add(parsed.netloc)

            # robots.txt advertises sitemaps for most university CMSes
            yield scrapy.Request(
                f"{host_root}/robots.txt",
                callback=self.parse_robots_for_sitemaps,
                errback=self.handle_sitemap_error,
                meta={'host_root': host_root},
            )

            # Conventional fallback location
            if not explicit_sitemaps:
                yield scrapy.Request(
                    f"{host_root}/sitemap.xml",
                    callback=self.parse_sitemap,
                    errback=self.handle_sitemap_error,
                    meta={'sitemap_depth': 0},
                )

    # ─────────────────────────── sitemap discovery ───────────────────────────

    def parse_robots_for_sitemaps(self, response):
        """Follow `Sitemap:` lines found in robots.txt."""
        try:
            sitemap_urls = list(sitemap_urls_from_robots(response.text, base_url=response.url))
        except Exception as e:
            self.logger.debug(f"Could not parse robots.txt at {response.url}: {e}")
            return

        for sitemap_url in sitemap_urls[:MAX_SITEMAP_CHILDREN]:
            yield scrapy.Request(
                sitemap_url,
                callback=self.parse_sitemap,
                errback=self.handle_sitemap_error,
                meta={'sitemap_depth': 0},
            )

    def parse_sitemap(self, response):
        """Parse a sitemap or sitemap index, yielding recent article URLs.

        Entries with a <lastmod> inside the freshness window are fetched
        directly (the date rides along in meta as a fallback published date).
        Undated entries must look like article URLs to be worth a request.
        """
        depth = response.meta.get('sitemap_depth', 0)

        body = response.body
        if response.url.endswith('.gz'):
            try:
                body = gzip.decompress(body)
            except OSError:
                pass  # server may have already decoded it

        try:
            sitemap = Sitemap(body)
        except Exception as e:
            self.logger.debug(f"Not a parseable sitemap: {response.url} ({e})")
            return

        age_limit = datetime.now(timezone.utc) - timedelta(days=settings.max_article_age_days)

        if sitemap.type == 'sitemapindex':
            if depth >= MAX_SITEMAP_DEPTH:
                return
            children = list(sitemap)
            # Prefer recently-modified child sitemaps. Paginated CMS sitemaps
            # (sitemap.xml?page=N) often stamp every page with the same
            # lastmod while ordering content oldest-first — tiebreak on the
            # page number so the newest pages win.
            children.sort(key=self._sitemap_child_sort_key, reverse=True)
            followed = 0
            for entry in children:
                loc = entry.get('loc')
                if not loc:
                    continue
                lastmod = self._parse_lastmod(entry.get('lastmod'))
                if lastmod and lastmod < age_limit:
                    continue
                yield scrapy.Request(
                    loc,
                    callback=self.parse_sitemap,
                    errback=self.handle_sitemap_error,
                    meta={'sitemap_depth': depth + 1},
                )
                followed += 1
                if followed >= MAX_SITEMAP_CHILDREN:
                    break
            return

        # urlset
        taken = 0
        entries = list(sitemap)
        entries.sort(key=lambda e: e.get('lastmod') or '', reverse=True)
        for entry in entries:
            loc = entry.get('loc')
            if not loc or self._is_navigation_page('', loc):
                continue

            lastmod = self._parse_lastmod(entry.get('lastmod'))
            if lastmod is not None:
                if lastmod < age_limit:
                    continue
            elif not any(rx.search(loc) for rx in self._article_url_res):
                # Undated and doesn't look like an article URL — skip.
                continue

            normalized = normalize_url(loc)
            url_hash = compute_url_hash(normalized)
            try:
                if check_url_seen(self.db, url_hash):
                    self.stats['duplicates_skipped'] += 1
                    continue
            except Exception as e:
                self.logger.warning(f"DB dedup check failed for {loc}, proceeding: {e}")
                self.db.rollback()

            self.stats['urls_discovered'] += 1
            self.stats['sitemap_urls'] += 1
            yield scrapy.Request(
                loc,
                callback=self.parse_article,
                errback=self.handle_error,
                meta={
                    'url_hash': url_hash,
                    'normalized_url': normalized,
                    'discovered_via': 'sitemap',
                    'fallback_date': lastmod.isoformat() if lastmod else None,
                },
            )
            taken += 1
            if taken >= MAX_SITEMAP_URLS:
                break

    @staticmethod
    def _sitemap_child_sort_key(entry: Dict[str, Any]) -> tuple:
        """Sort key for sitemap-index children: (lastmod, page number)."""
        loc = entry.get('loc') or ''
        page = 0
        match = re.search(r'(?:page=|[-_])(\d+)(?:\.xml(?:\.gz)?)?$', loc)
        if match:
            try:
                page = int(match.group(1))
            except ValueError:
                page = 0
        return (entry.get('lastmod') or '', page)

    @staticmethod
    def _parse_lastmod(raw: Optional[str]) -> Optional[datetime]:
        """Parse a sitemap <lastmod> value into an aware datetime."""
        if not raw:
            return None
        try:
            parsed = datetime.fromisoformat(raw.strip().replace('Z', '+00:00'))
        except (ValueError, AttributeError):
            return None
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed

    def handle_sitemap_error(self, failure):
        """Sitemap/robots fetch failures are expected (404s) — log quietly."""
        self.logger.debug(f"Discovery request failed (non-fatal): {failure.request.url}")

    def _is_rss_feed(self, response) -> bool:
        """Detect if the response is an RSS/Atom feed."""
        content_type = response.headers.get('Content-Type', b'').decode('utf-8', errors='ignore').lower()
        if any(ct in content_type for ct in ('xml', 'rss', 'atom', 'feed')):
            return True
        # Body sniffing for feeds served as text/html
        body_start = response.text[:500].strip() if hasattr(response, 'text') else ''
        return body_start.startswith('<?xml') or '<rss' in body_start or '<feed' in body_start

    def _parse_rss_feed(self, response):
        """Parse RSS/Atom feed and yield requests for each article entry."""
        self.logger.info(f"Parsing RSS feed: {response.url}")
        feed = feedparser.parse(response.text)

        if not feed.entries:
            self.logger.warning(f"No entries found in feed: {response.url}")
            return

        self.logger.info(f"Found {len(feed.entries)} entries in RSS feed: {response.url}")

        for entry in feed.entries:
            link = entry.get('link')
            if not link:
                continue

            # Feed-level publication date — used both to skip stale entries
            # here and as a fallback published_date for pages whose HTML
            # carries no parseable date.
            pubdate = None
            for key in ('published_parsed', 'updated_parsed'):
                parsed_time = entry.get(key)
                if parsed_time:
                    pubdate = datetime(*parsed_time[:6], tzinfo=timezone.utc)
                    break

            if pubdate is not None:
                age_limit = datetime.now(timezone.utc) - timedelta(days=settings.max_article_age_days)
                if pubdate < age_limit:
                    self.logger.debug(f"Skipping stale feed entry ({pubdate.date()}): {link}")
                    continue

            self.stats['urls_discovered'] += 1

            # Skip navigation pages
            if self._is_navigation_page('', link):
                self.logger.debug(f"Skipping navigation URL from feed: {link}")
                continue

            # Dedup check
            normalized = normalize_url(link)
            url_hash = compute_url_hash(normalized)

            try:
                if check_url_seen(self.db, url_hash):
                    self.stats['duplicates_skipped'] += 1
                    self.logger.debug(f"Skipping duplicate feed URL: {link}")
                    continue
            except Exception as e:
                self.logger.warning(f"DB dedup check failed for {link}, proceeding: {e}")
                self.db.rollback()

            # Dynamically add article domain to allowed_domains
            domain = urlparse(link).netloc
            if domain and domain not in self.allowed_domains:
                self.allowed_domains.append(domain)
                self.logger.debug(f"Added domain from feed entry: {domain}")

            yield scrapy.Request(
                link,
                callback=self.parse_article,
                meta={
                    'url_hash': url_hash,
                    'normalized_url': normalized,
                    'discovered_via': 'rss',
                    'fallback_date': pubdate.isoformat() if pubdate else None,
                },
                errback=self.handle_error
            )

    def parse(self, response):
        """
        Parse news listing page.

        Extracts article links and follows pagination.
        Detects RSS/Atom feeds and routes to feed parser.
        """
        # RSS/Atom feed detection — route to feed parser
        if self._is_rss_feed(response):
            yield from self._parse_rss_feed(response)
            return

        self.logger.info(f"Parsing listing page: {response.url}")
        domain = urlparse(response.url).netloc
        self.sources_attempted.add(domain)

        # RSS/Atom feed autodiscovery: many newsrooms advertise a feed in
        # <link rel="alternate"> that isn't in our config. Follow it this run
        # and record it in docs/data/discovered_feeds.json for promotion into
        # the source JSONs offline.
        for href in response.css(
            'link[rel="alternate"][type*="rss"]::attr(href), '
            'link[rel="alternate"][type*="atom"]::attr(href)'
        ).getall():
            feed_url = response.urljoin(href)
            if feed_url in self.discovered_feeds:
                continue
            self.discovered_feeds[feed_url] = response.url
            self.stats['feeds_discovered'] += 1
            if feed_url not in self._followed_feeds:
                self._followed_feeds.add(feed_url)
                yield scrapy.Request(
                    feed_url,
                    callback=self.parse,
                    errback=self.handle_sitemap_error,
                )

        # Extract article links
        for link in self.link_extractor.extract_links(response):
            self.stats['urls_discovered'] += 1

            # Pre-filter obvious listing/navigation pages by URL pattern
            # This prevents them from even entering the database
            if self._is_navigation_page('', link.url):
                self.logger.debug(f"Skipping navigation/listing page URL: {link.url}")
                continue

            # Check if URL already seen (fast bloom filter check)
            normalized = normalize_url(link.url)
            url_hash = compute_url_hash(normalized)

            try:
                url_seen = check_url_seen(self.db, url_hash)
            except Exception as e:
                self.logger.warning(f"DB dedup check failed for {link.url}, proceeding: {e}")
                self.db.rollback()
                url_seen = False

            if not url_seen:
                yield scrapy.Request(
                    link.url,
                    callback=self.parse_article,
                    meta={
                        'url_hash': url_hash,
                        'normalized_url': normalized,
                        'discovered_via': 'frontpage',
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
        discovered_via = response.meta.get('discovered_via', 'frontpage')

        self.logger.info(f"Extracting article ({discovered_via}): {response.url}")

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
                min_words=settings.min_article_words
            ):
                self.logger.info(f"Content quality check failed for {response.url}")
                self._update_url_status(url_hash, 'excluded')
                return

            # Check for generic navigation page titles
            if self._is_navigation_page(extracted.get('title', ''), response.url):
                self.logger.info(f"Skipping navigation/listing page: {extracted.get('title', 'Untitled')}")
                self._update_url_status(url_hash, 'excluded')
                return

            # Resolve a publication date, in order of trust:
            # 1. Trafilatura's extracted date
            # 2. htmldate scan of the raw HTML
            # 3. the discovery channel's date (RSS pubDate / sitemap lastmod)
            # Undated articles used to bypass the age filter entirely, letting
            # years-old pages into the daily report — now no date means no
            # article.
            date_estimated = False
            article_date = self._parse_article_date(extracted.get('date'))

            if article_date is None:
                article_date = self._parse_article_date(self._htmldate_fallback(response))
                date_estimated = article_date is not None

            if article_date is None and response.meta.get('fallback_date'):
                article_date = self._parse_article_date(response.meta['fallback_date'])
                date_estimated = article_date is not None

            if article_date is None:
                self.logger.info(
                    f"Skipping undated article: {extracted.get('title', response.url)}"
                )
                self._update_url_status(url_hash, 'excluded')
                return

            age_limit = datetime.now(timezone.utc) - timedelta(days=settings.max_article_age_days)
            if article_date < age_limit:
                self.logger.info(
                    f"Skipping old article ({article_date.date()}): {extracted.get('title', response.url)}"
                )
                self._update_url_status(url_hash, 'excluded')
                return

            extracted['date'] = article_date.isoformat()

            # Compute content hash for deduplication
            content_hash = compute_content_hash(extracted['text'])

            # Extract hostname
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
                'date_estimated': date_estimated,
                'discovered_via': discovered_via,
                'extracted_at': datetime.now(timezone.utc).isoformat()
            }

            # Store in database
            self._store_article(article_data)

            self.stats['articles_extracted'] += 1
            domain = urlparse(response.url).netloc
            self.sources_succeeded.add(domain)
            if domain not in self.domain_stats:
                self.domain_stats[domain] = {'urls': 0, 'articles': 0, 'errors': 0}
            self.domain_stats[domain]['articles'] += 1
            self.logger.info(f"Successfully extracted article: {extracted.get('title', 'Untitled')}")

            yield article_data

        except Exception as e:
            self.logger.error(f"Error parsing article {response.url}: {e}")
            self.stats['errors'] += 1
            self._update_url_status(url_hash, 'failed')

    @staticmethod
    def _parse_article_date(raw: Optional[str]) -> Optional[datetime]:
        """Parse an ISO-ish date string into an aware datetime, else None."""
        if not raw:
            return None
        try:
            parsed = datetime.fromisoformat(str(raw).replace('Z', '+00:00'))
        except (ValueError, AttributeError, TypeError):
            return None
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed

    def _htmldate_fallback(self, response) -> Optional[str]:
        """Scan raw HTML for a publication date when Trafilatura found none."""
        try:
            from htmldate import find_date
            return find_date(response.text, url=response.url, original_date=True)
        except Exception as e:
            self.logger.debug(f"htmldate fallback failed for {response.url}: {e}")
            return None

    def _store_article(self, article_data: Dict[str, Any]):
        """
        Store article in database using a savepoint so failures don't poison the session.

        Args:
            article_data: Article data dictionary
        """
        try:
            # Use a savepoint so a failure here doesn't abort the entire session
            nested = self.db.begin_nested()

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
                nested.commit()
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

            canonical_name = self.name_mapper.get_canonical_name(
                hostname=article_data['hostname'],
                fallback_sitename=article_data.get('sitename')
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
                # NB: the column is article_metadata — passing `metadata=`
                # silently shadowed SQLAlchemy's Base.metadata and stored
                # nothing at all.
                article_metadata={
                    'categories': article_data.get('categories', []),
                    'tags': article_data.get('tags', []),
                    'hostname': article_data['hostname'],
                    'date_estimated': article_data.get('date_estimated', False),
                    'discovered_via': article_data.get('discovered_via', 'frontpage'),
                },
                first_scraped=datetime.now(timezone.utc)
            )

            # Update URL status
            url_obj.status = 'crawled'
            url_obj.last_checked = datetime.now(timezone.utc)
            url_obj.content_hash = article_data['content_hash']

            self.db.add(article)
            nested.commit()
            self.db.commit()

            self.logger.debug(f"Stored article in database: {article.article_id}")

        except Exception as e:
            self.logger.error(f"Failed to store article in database: {e}")
            self.db.rollback()

    def _is_navigation_page(self, title: str, url: str) -> bool:
        """
        Check if this is a navigation/listing page rather than an article.

        Args:
            title: Page title
            url: Page URL

        Returns:
            True if this appears to be a navigation page
        """
        if not title:
            return False

        # Generic title patterns that indicate navigation pages
        generic_patterns = [
            r'^News\s*$',
            r'^News & Events',
            r'^News and Events',
            r'^Press Releases?\s*$',
            r'^News Releases?\s*$',  # Added for UW and similar sites
            r'^Media\s*$',
            r'^Stories\s*$',
            r'^Articles\s*$',
            r'^Latest News',
            r'^Latest Stories',
            r'^All News',
            r'^All Stories',
            r'^\w+\s+News\s*$',  # e.g., "Pittwire News", "University News"
            r'^Features & Articles',
            r'^Accolades & Honors',
            r'^The Latest News',  # Added for UW-style pages
            r'^Recent News',
            r'^Archive',
            r'^News Archive',
            r'Archives?\s*$',  # Titles ending with "Archive" or "Archives"
        ]

        import re
        for pattern in generic_patterns:
            if re.match(pattern, title, re.IGNORECASE):
                return True

        # Check URL patterns too
        url_navigation_patterns = [
            r'/news/?$',
            r'/news-events/?$',
            r'/press-releases?/?$',
            r'/news-releases?/?$',  # Added for consistency
            r'/media/?$',
            r'/stories/?$',
            r'/articles/?$',
            r'/category/[^/]+/?$',  # Category pages (e.g., /category/news-releases/)
            r'/tag/[^/]+/?$',  # Tag pages
            r'/archive/?$',  # Archive pages
            r'/latest[^/]*/?$',  # Latest news pages (e.g., /latest/, /latest-news/)
            r'/the-latest[^/]*/?$',  # UW-style "the-latest-news-from" pages
            r'/all-news/?$',
            r'/recent[^/]*/?$',  # Recent news pages
            r'/section/[^/]+/?$',  # Section listing pages (e.g., /news/section/engineering/)
        ]

        for pattern in url_navigation_patterns:
            if re.search(pattern, url, re.IGNORECASE):
                return True

        return False

    def _update_url_status(self, url_hash: str, status: str):
        """
        Update URL status in database using a savepoint for isolation.

        Args:
            url_hash: URL hash
            status: New status
        """
        try:
            nested = self.db.begin_nested()
            url_obj = self.db.query(URL).filter(URL.url_hash == url_hash).first()
            if url_obj:
                url_obj.status = status
                url_obj.last_checked = datetime.now(timezone.utc)
            nested.commit()
            self.db.commit()
        except Exception as e:
            self.logger.error(f"Failed to update URL status: {e}")
            self.db.rollback()

    def handle_error(self, failure):
        """
        Record request errors for the health report.

        (The old "MCP fallback" — a second plain HTTP request with a spoofed
        Chrome User-Agent from the same IP — was removed: it never beat real
        bot protection and fired even on timeouts. Retries are handled by
        Scrapy's RetryMiddleware; persistent failures feed the source-health
        loop, which eventually disables the source.)
        """
        url = failure.request.url
        self.logger.error(f"Request failed: {url}")
        self.logger.error(f"Error: {failure.value}")
        self.stats['errors'] += 1
        domain = urlparse(url).netloc
        if domain not in self.domain_stats:
            self.domain_stats[domain] = {'urls': 0, 'articles': 0, 'errors': 0}
        self.domain_stats[domain]['errors'] += 1

    def closed(self, reason):
        """
        Clean up when spider closes. Writes health stats to JSON file.

        Args:
            reason: Reason for spider closure
        """
        self.logger.info(f"Spider closing: {reason}")
        self.logger.info(f"Statistics: {self.stats}")

        # Build health report
        failed_domains = {
            domain: stats for domain, stats in self.domain_stats.items()
            if stats.get('errors', 0) > 0 and stats.get('articles', 0) == 0
        }

        health_report = {
            'stats': self.stats,
            'sources_attempted': len(self.sources_attempted),
            'sources_succeeded': len(self.sources_succeeded),
            'domain_stats': self.domain_stats,
            'failed_domains': list(failed_domains.keys())[:20],
            'closed_reason': reason,
            'timestamp': datetime.now(timezone.utc).isoformat(),
        }

        # Write health report to file for main pipeline to read. Each spider
        # group gets its own file (they used to overwrite each other's).
        stats_dir = os.environ.get('CRAWLER_STATS_DIR', 'output')
        group_name = os.environ.get('CRAWLER_GROUP_NAME', 'default')
        os.makedirs(stats_dir, exist_ok=True)
        stats_file = os.path.join(stats_dir, f'spider_health_{group_name}.json')
        try:
            with open(stats_file, 'w') as f:
                json.dump(health_report, f, indent=2)
            self.logger.info(f"Health report written to {stats_file}")
        except Exception as e:
            self.logger.error(f"Failed to write health report: {e}")

        # Persist RSS/Atom feeds discovered this run as promotion suggestions
        # (never mutates the source configs mid-run).
        if self.discovered_feeds:
            feeds_path = os.path.join('docs', 'data', 'discovered_feeds.json')
            try:
                os.makedirs(os.path.dirname(feeds_path), exist_ok=True)
                existing = {}
                if os.path.exists(feeds_path):
                    with open(feeds_path) as f:
                        existing = json.load(f)
                for feed_url, found_on in self.discovered_feeds.items():
                    existing.setdefault(feed_url, {
                        'found_on': found_on,
                        'first_seen': datetime.now(timezone.utc).isoformat(timespec='seconds'),
                    })
                with open(feeds_path, 'w') as f:
                    json.dump(existing, f, indent=2, sort_keys=True)
                self.logger.info(
                    f"Recorded {len(self.discovered_feeds)} discovered feeds to {feeds_path}"
                )
            except Exception as e:
                self.logger.error(f"Failed to write discovered feeds: {e}")

        # Close database session
        if self._db is not None:
            self._db.close()

        # Log final stats
        logger.info(f"""
=== SPIDER HEALTH REPORT ===
Sources Attempted: {len(self.sources_attempted)}
Sources Succeeded: {len(self.sources_succeeded)}
Sources Skipped (health): {self.stats['sources_skipped_health']}
URLs Discovered: {self.stats['urls_discovered']}
  via sitemaps: {self.stats['sitemap_urls']}
Feeds Autodiscovered: {self.stats['feeds_discovered']}
URLs Crawled: {self.stats['urls_crawled']}
Articles Extracted: {self.stats['articles_extracted']}
Duplicates Skipped: {self.stats['duplicates_skipped']}
Errors: {self.stats['errors']}
Failed Domains: {', '.join(list(failed_domains.keys())[:10]) or 'None'}
============================
""")
