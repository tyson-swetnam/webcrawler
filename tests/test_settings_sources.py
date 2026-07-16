"""Tests for multi-source normalization (schema v3.0.0 news_sources arrays)."""

from crawler.config.settings import Settings


def _make_settings(**kwargs):
    return Settings(_env_file=None, database_url="postgresql://t:t@localhost/t", **kwargs)


UNIVERSITY = {
    "name": "Test University",
    "abbreviation": "TU",
    "location": {"city": "Tucson", "state": "AZ"},
    "classification": {"institution_type": "R1"},
    "ai_research": {"ai_focus_areas": ["ml"]},
    "news_sources": [
        {
            "type": "primary",
            "url": "https://news.test.edu",
            "rss_feed": "https://news.test.edu/feed",
            "verified": True,
        },
        {
            "type": "secondary",
            "url": "https://engineering.test.edu/news",
            "verified": True,
            "sitemaps": ["https://engineering.test.edu/sitemap.xml"],
        },
        {
            "type": "ai_tag",
            "url": "https://news.test.edu/topic/ai",
            "verified": False,  # unverified — must be dropped
        },
    ],
}


def test_emits_all_verified_sources():
    s = _make_settings()
    entries = s._institution_entries(UNIVERSITY, "university")
    assert len(entries) == 2
    roles = {e["source_role"] for e in entries}
    assert roles == {"primary", "secondary"}


def test_rss_preferred_when_enabled():
    s = _make_settings(use_rss_feeds=True)
    entries = s._institution_entries(UNIVERSITY, "university")
    primary = next(e for e in entries if e["source_role"] == "primary")
    assert primary["news_url"] == "https://news.test.edu/feed"

    s2 = _make_settings(use_rss_feeds=False)
    entries2 = s2._institution_entries(UNIVERSITY, "university")
    primary2 = next(e for e in entries2 if e["source_role"] == "primary")
    assert primary2["news_url"] == "https://news.test.edu"


def test_sitemaps_carried_through():
    s = _make_settings()
    entries = s._institution_entries(UNIVERSITY, "university")
    secondary = next(e for e in entries if e["source_role"] == "secondary")
    assert secondary["sitemaps"] == ["https://engineering.test.edu/sitemap.xml"]


def test_cap_per_institution():
    many = {
        **UNIVERSITY,
        "news_sources": [
            {"type": "secondary", "url": f"https://s{i}.test.edu/news", "verified": True}
            for i in range(6)
        ],
    }
    s = _make_settings()
    entries = s._institution_entries(many, "university")
    assert len(entries) == Settings.MAX_SOURCES_PER_INSTITUTION


def test_duplicate_urls_deduped():
    dup = {
        **UNIVERSITY,
        "news_sources": [
            {"type": "primary", "url": "https://news.test.edu", "verified": True},
            {"type": "secondary", "url": "https://news.test.edu", "verified": True},
        ],
    }
    s = _make_settings(use_rss_feeds=False)
    entries = s._institution_entries(dup, "university")
    assert len(entries) == 1


def test_legacy_dict_shape_still_works():
    legacy = {
        "name": "Legacy U",
        "location": {},
        "news_sources": {"primary": {"url": "https://news.legacy.edu", "verified": True}},
    }
    s = _make_settings()
    entries = s._institution_entries(legacy, "university")
    assert len(entries) == 1
    assert entries[0]["news_url"] == "https://news.legacy.edu"
