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
