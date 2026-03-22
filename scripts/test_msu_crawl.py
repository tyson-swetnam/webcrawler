#!/usr/bin/env python3
"""
Diagnostic script for MSU article coverage.

Fetches the MSU RSS feed, identifies AI-related articles,
and checks which ones were (or weren't) picked up by the crawler.

Usage:
    source venv/bin/activate && python scripts/test_msu_crawl.py
"""

import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

import feedparser
import hashlib
from datetime import datetime

from crawler.config.settings import settings


def fetch_rss_articles(rss_url):
    """Fetch and parse articles from an RSS feed."""
    print(f"Fetching RSS feed: {rss_url}")
    feed = feedparser.parse(rss_url)

    if feed.bozo:
        print(f"  Warning: feed parser encountered issues: {feed.bozo_exception}")

    articles = []
    for entry in feed.entries:
        published = None
        if hasattr(entry, "published_parsed") and entry.published_parsed:
            published = datetime(*entry.published_parsed[:6])

        articles.append({
            "title": entry.get("title", "No title"),
            "url": entry.get("link", ""),
            "published": published,
            "summary": entry.get("summary", "")[:200],
        })

    print(f"  Found {len(articles)} articles in feed")
    return articles


def check_ai_keywords(title, summary):
    """Check if an article title/summary contains AI-related keywords."""
    keywords = [
        "artificial intelligence", "machine learning", "deep learning",
        "neural network", "AI ", " AI", "LLM", "language model",
        "computer vision", "robotics", "autonomous", "semiconductor",
        "quantum computing", "data science", "algorithm",
        "generative", "chatbot", "GPT", "transformer",
    ]
    text = (title + " " + summary).lower()
    matches = [kw for kw in keywords if kw.lower() in text]
    return matches


def check_database(urls):
    """Check which URLs exist in the crawler database."""
    try:
        from crawler.db.session import init_db, get_db_manager
        from crawler.db.models import URL, Article

        init_db(
            settings.database_url,
            pool_size=2,
            echo=False,
        )
        session = get_db_manager().get_session()

        results = {}
        for url in urls:
            url_hash = hashlib.sha256(url.encode()).hexdigest()
            db_url = session.query(URL).filter(URL.url_hash == url_hash).first()
            if db_url:
                article = session.query(Article).filter(
                    Article.url_id == db_url.url_id
                ).first()
                results[url] = {
                    "in_db": True,
                    "status": db_url.status,
                    "has_article": article is not None,
                    "is_ai_related": article.is_ai_related if article else None,
                }
            else:
                results[url] = {"in_db": False}

        session.close()
        return results

    except Exception as e:
        print(f"  Database check failed: {e}")
        return {url: {"in_db": None, "error": str(e)} for url in urls}


def check_settings_config():
    """Check how MSU is configured in the settings module."""
    print("Checking MSU configuration in settings...")
    sources = settings.get_university_sources()
    msu_sources = [s for s in sources if "Michigan State" in s.get("name", "")]

    if not msu_sources:
        print("  ERROR: Michigan State University not found in sources!")
        return

    for s in msu_sources:
        print(f"  Name: {s.get('name')}")
        print(f"  Source type: {s.get('source_type')}")
        print(f"  News URL: {s.get('news_url')}")
        print(f"  RSS feed: {s.get('rss_feed')}")
        print(f"  Main URL: {s.get('main_url')}")
        print()


def main():
    print("=" * 60)
    print("MSU Article Coverage Diagnostic")
    print("=" * 60)
    print()

    # 1. Check settings config
    check_settings_config()

    # 2. Fetch RSS feed
    rss_url = "https://msutoday.msu.edu/rss"
    articles = fetch_rss_articles(rss_url)
    print()

    # 3. Check for AI-related articles
    print("AI-related articles in RSS feed:")
    print("-" * 40)
    ai_articles = []
    for art in articles:
        matches = check_ai_keywords(art["title"], art["summary"])
        if matches:
            ai_articles.append(art)
            pub = art["published"].strftime("%Y-%m-%d") if art["published"] else "unknown"
            print(f"  [{pub}] {art['title']}")
            print(f"    URL: {art['url']}")
            print(f"    Keywords: {', '.join(matches)}")
            print()

    if not ai_articles:
        print("  No AI-related articles found in current RSS feed.")
    print()

    # 4. Check database for these URLs
    print("Database coverage check:")
    print("-" * 40)
    all_urls = [a["url"] for a in articles]
    db_results = check_database(all_urls)

    in_db = sum(1 for r in db_results.values() if r.get("in_db"))
    missing = sum(1 for r in db_results.values() if r.get("in_db") is False)
    errors = sum(1 for r in db_results.values() if r.get("in_db") is None)

    print(f"  Total RSS articles: {len(articles)}")
    print(f"  In database: {in_db}")
    print(f"  Missing: {missing}")
    if errors:
        print(f"  DB errors: {errors}")
    print()

    # 5. Report missed AI articles
    if ai_articles:
        print("AI article coverage:")
        print("-" * 40)
        for art in ai_articles:
            result = db_results.get(art["url"], {})
            status = "IN DB" if result.get("in_db") else "MISSING"
            if result.get("in_db") and result.get("has_article"):
                ai_flag = "ai=yes" if result.get("is_ai_related") else "ai=no"
                status += f" ({ai_flag})"
            print(f"  [{status}] {art['title']}")
            print(f"    {art['url']}")
            print()


if __name__ == "__main__":
    main()
