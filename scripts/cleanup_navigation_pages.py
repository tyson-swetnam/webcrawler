#!/usr/bin/env python3
"""
Clean up navigation/listing pages from database.

This script identifies and removes articles that are actually navigation pages
(e.g., "News & Events", "Pittwire News") rather than actual articles.
"""

import sys
import re
from pathlib import Path

# Add project to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from crawler.config.settings import settings
from crawler.db.session import init_db, get_db
from crawler.db.models import Article, URL, AIAnalysis

def is_navigation_page_title(title: str) -> bool:
    """Check if title matches navigation page patterns."""
    if not title:
        return False

    # Generic title patterns that indicate navigation pages
    generic_patterns = [
        r'^News\s*$',
        r'^News & Events',
        r'^News and Events',
        r'^Press Releases?\s*$',
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
    ]

    for pattern in generic_patterns:
        if re.match(pattern, title, re.IGNORECASE):
            return True

    return False

def is_navigation_page_url(url: str) -> bool:
    """Check if URL matches navigation page patterns."""
    if not url:
        return False

    url_navigation_patterns = [
        r'/news/?$',
        r'/news-events/?$',
        r'/news-and-events/?$',
        r'/press-releases?/?$',
        r'/features-articles/?$',
        r'/accolades-honors/?$',
        r'/media/?$',
        r'/stories/?$',
        r'/articles/?$',
    ]

    for pattern in url_navigation_patterns:
        if re.search(pattern, url, re.IGNORECASE):
            return True

    return False

def main():
    """Clean up navigation pages from database."""
    print("Initializing database connection...")
    init_db(
        settings.database_url,
        pool_size=settings.database_pool_size,
        echo=False
    )

    with get_db() as db:
        # Find all articles
        print("\nScanning articles for navigation pages...")
        all_articles = db.query(Article).all()

        to_remove = []
        for article in all_articles:
            url_str = article.url.url if article.url else ''

            if is_navigation_page_title(article.title) or is_navigation_page_url(url_str):
                to_remove.append(article)
                print(f"  - Found: {article.title} ({url_str})")

        if not to_remove:
            print("\n✅ No navigation pages found!")
            return 0

        print(f"\n⚠️  Found {len(to_remove)} navigation pages to remove")

        # Confirm with user
        response = input("\nDelete these entries? (yes/no): ")
        if response.lower() not in ['yes', 'y']:
            print("Cancelled.")
            return 0

        # Delete articles and their analyses
        print("\nRemoving entries...")
        removed_count = 0
        for article in to_remove:
            # Delete AI analyses first (foreign key constraint)
            db.query(AIAnalysis).filter(
                AIAnalysis.article_id == article.article_id
            ).delete()

            # Update URL status to excluded
            if article.url:
                article.url.status = 'excluded'

            # Delete article
            db.delete(article)
            removed_count += 1
            print(f"  ✓ Removed: {article.title}")

        db.commit()
        print(f"\n✅ Successfully removed {removed_count} navigation pages")
        print("\n💡 Next steps:")
        print("   1. Run: python scripts/regenerate_html.py")
        print("   2. Commit the updated docs/ folder")

        return 0

if __name__ == "__main__":
    sys.exit(main())
