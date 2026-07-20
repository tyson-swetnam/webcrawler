"""Tests for spider date parsing and CLI quota detection (no network/DB)."""

from datetime import datetime, timezone

from crawler.ai.claude_cli import _detect_quota_exhaustion
from crawler.spiders.university_spider import UniversityNewsSpider


def test_parse_article_date_iso_variants():
    parse = UniversityNewsSpider._parse_article_date
    assert parse("2026-07-01").date().isoformat() == "2026-07-01"
    assert parse("2026-07-01T10:00:00Z").tzinfo is not None
    assert parse("2026-07-01T10:00:00+02:00").tzinfo is not None
    assert parse(None) is None
    assert parse("not a date") is None


def test_parse_article_date_naive_becomes_utc():
    parsed = UniversityNewsSpider._parse_article_date("2026-07-01T10:00:00")
    assert parsed.tzinfo == timezone.utc


def test_parse_lastmod():
    parse = UniversityNewsSpider._parse_lastmod
    assert parse("2026-07-10") == datetime(2026, 7, 10, tzinfo=timezone.utc)
    assert parse("2026-07-10T08:30:00Z") is not None
    assert parse("") is None
    assert parse("garbage") is None


def test_quota_detection():
    assert _detect_quota_exhaustion("You've hit your session limit · resets 3:45pm")
    assert _detect_quota_exhaustion("you've HIT YOUR WEEKLY LIMIT")
    assert not _detect_quota_exhaustion('{"result": "all good"}')


def test_non_article_url_blocks_directory_sections():
    is_non_article = UniversityNewsSpider._is_non_article_url
    # aalto.fi staff directories in all three locales (the July 2026 pollution)
    assert is_non_article("https://www.aalto.fi/en/people/pekka-malo")
    assert is_non_article("https://www.aalto.fi/fi/ihmiset/pekka-malo")
    assert is_non_article("https://www.aalto.fi/sv/personer/pekka-malo")
    # service catalogs, degree catalogs, job boards
    assert is_non_article("https://www.aalto.fi/en/services/it-services-for-research")
    assert is_non_article("https://www.aalto.fi/fi/palvelut/it-ja-digikoulutus")
    assert is_non_article("https://www.aalto.fi/fi/koulutustarjonta/some-degree")
    assert is_non_article("https://www.aalto.fi/en/open-positions/a-doctoral-researcher")
    assert is_non_article("https://www.aalto.fi/fi/avoimet-tyopaikat/tutkija")
    # non-locale-prefixed equivalents on other sites
    assert is_non_article("https://example.edu/people/jane-doe")
    assert is_non_article("https://example.edu/staff/jane-doe")
    assert is_non_article("https://example.edu/jobs/opening-123")


def test_non_article_url_allows_news_articles():
    is_non_article = UniversityNewsSpider._is_non_article_url
    assert not is_non_article("https://www.aalto.fi/en/news/deans-impact-award")
    assert not is_non_article("https://www.aalto.fi/fi/uutiset/marginaalista-liiketoiminnan-ytimeen")
    assert not is_non_article("https://news.mit.edu/2026/some-ai-story-0715")
    # "people" as a news category deeper in the path is legitimate news
    assert not is_non_article("https://news.example.edu/news/people/professor-wins-award")
    # listing pages are still rejected
    assert is_non_article("https://news.example.edu/news/")
    assert is_non_article("https://news.example.edu/category/research/")


def test_navigation_page_checks_url_even_without_title():
    # Regression: an empty title used to short-circuit the URL checks,
    # making the sitemap/RSS call sites no-ops.
    spider_check = UniversityNewsSpider._is_non_article_url
    assert spider_check("https://www.aalto.fi/en/people/anyone")
    assert UniversityNewsSpider._has_navigation_title("Latest News")
    assert not UniversityNewsSpider._has_navigation_title("Pekka Malo | Aalto University")
