#!/usr/bin/env python3
"""
Backfill script to fix misclassified university names in the database.

This script identifies articles with incorrect university names (extracted by Trafilatura)
and updates them to use canonical names from the config files based on their hostnames.

Usage:
    python scripts/backfill_university_names.py [--dry-run] [--regenerate-html]

Options:
    --dry-run           Show what would be changed without making changes
    --regenerate-html   Regenerate HTML reports after backfilling
    --all               Backfill ALL articles, not just suspicious ones
"""

import sys
import os
import argparse
import logging
from datetime import datetime
from typing import Dict, List, Tuple
from collections import defaultdict

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from crawler.config.settings import settings
from crawler.db.session import init_db, SessionLocal
from crawler.db.models import Article, URL
from crawler.utils.university_name_mapper import get_mapper
from crawler.utils.university_classifier import UniversityClassifier

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


# List of suspicious names that should be backfilled
SUSPICIOUS_NAMES = [
    'AuburnEngineers',
    'KU News',
    'UNLV',
    'UW News',
    'Utimes',
    'ou.edu',
    'psu.edu',
    'washington.edu',
    'News',  # Generic "News" sitename
    'Livermore_Lab',  # Should check if this is correct
]


def is_suspicious_name(name: str) -> bool:
    """
    Check if a university name looks suspicious and might need backfilling.

    Args:
        name: The university name to check

    Returns:
        True if name looks suspicious
    """
    if name in SUSPICIOUS_NAMES:
        return True

    # Check for domain-like names
    if name.endswith('.edu'):
        return True

    # Check for very short abbreviations that might be wrong
    if len(name) < 10 and name.isupper():
        return True

    # Check for generic names
    if name.lower() in ['news', 'university', 'college']:
        return True

    return False


def backfill_articles(dry_run: bool = False, backfill_all: bool = False) -> Dict[str, int]:
    """
    Backfill university names for articles with suspicious names.

    Args:
        dry_run: If True, show changes without committing
        backfill_all: If True, backfill all articles (not just suspicious ones)

    Returns:
        Dictionary with statistics
    """
    logger.info("=" * 80)
    logger.info("UNIVERSITY NAME BACKFILL SCRIPT")
    logger.info("=" * 80)
    logger.info(f"Mode: {'DRY RUN' if dry_run else 'LIVE UPDATE'}")
    logger.info(f"Scope: {'ALL ARTICLES' if backfill_all else 'SUSPICIOUS NAMES ONLY'}")
    logger.info("")

    # Initialize database and mapper
    init_db(settings.database_url)
    session = SessionLocal()
    mapper = get_mapper()
    classifier = UniversityClassifier()

    stats = {
        'total_checked': 0,
        'suspicious_found': 0,
        'updated': 0,
        'unchanged': 0,
        'errors': 0
    }

    changes: List[Tuple[int, str, str, str]] = []  # (article_id, old_name, new_name, url)

    try:
        # Query articles with their URLs
        logger.info("Querying articles from database...")

        if backfill_all:
            # Backfill all articles
            articles = session.query(
                Article.article_id,
                Article.university_name,
                URL.hostname,
                URL.url
            ).join(URL).filter(
                Article.university_name.isnot(None)
            ).all()
        else:
            # Only backfill suspicious names
            articles = session.query(
                Article.article_id,
                Article.university_name,
                URL.hostname,
                URL.url
            ).join(URL).filter(
                Article.university_name.isnot(None)
            ).all()

            # Filter to suspicious names only
            articles = [a for a in articles if is_suspicious_name(a.university_name)]

        stats['total_checked'] = len(articles)
        logger.info(f"Found {len(articles)} articles to check")
        logger.info("")

        # Group by old name for reporting
        by_old_name = defaultdict(list)

        for article_id, old_name, hostname, url in articles:
            if not backfill_all and not is_suspicious_name(old_name):
                stats['unchanged'] += 1
                continue

            stats['suspicious_found'] += 1

            # Get canonical name using mapper
            new_name = mapper.get_canonical_name(hostname, fallback_sitename=old_name)

            # Check if name actually changed
            if new_name == old_name:
                stats['unchanged'] += 1
                continue

            # Record change
            changes.append((article_id, old_name, new_name, url))
            by_old_name[old_name].append((article_id, new_name, url))
            stats['updated'] += 1

        # Print changes grouped by old name
        logger.info("=" * 80)
        logger.info("CHANGES TO BE MADE:")
        logger.info("=" * 80)
        logger.info("")

        for old_name in sorted(by_old_name.keys()):
            items = by_old_name[old_name]
            new_names = set(item[1] for item in items)

            logger.info(f"❌ Old Name: {old_name}")
            logger.info(f"   Articles: {len(items)}")
            logger.info(f"   → New Name(s): {', '.join(new_names)}")
            logger.info(f"   Sample URL: {items[0][2]}")
            logger.info("")

        # Apply updates if not dry run
        if not dry_run and changes:
            logger.info("=" * 80)
            logger.info("APPLYING UPDATES TO DATABASE...")
            logger.info("=" * 80)
            logger.info("")

            for article_id, old_name, new_name, url in changes:
                try:
                    article = session.query(Article).filter(
                        Article.article_id == article_id
                    ).first()

                    if article:
                        article.university_name = new_name
                        logger.debug(f"Updated article {article_id}: {old_name} → {new_name}")

                except Exception as e:
                    logger.error(f"Error updating article {article_id}: {e}")
                    stats['errors'] += 1

            # Commit changes
            try:
                session.commit()
                logger.info(f"✅ Successfully updated {len(changes)} articles")
            except Exception as e:
                session.rollback()
                logger.error(f"❌ Error committing changes: {e}")
                stats['errors'] = len(changes)
                stats['updated'] = 0

        # Print summary statistics
        logger.info("")
        logger.info("=" * 80)
        logger.info("SUMMARY STATISTICS")
        logger.info("=" * 80)
        logger.info(f"Total articles checked: {stats['total_checked']}")
        logger.info(f"Suspicious names found: {stats['suspicious_found']}")
        logger.info(f"Articles updated: {stats['updated']}")
        logger.info(f"Articles unchanged: {stats['unchanged']}")
        logger.info(f"Errors: {stats['errors']}")
        logger.info("=" * 80)

        # Verify classification distribution after changes
        if not dry_run and stats['updated'] > 0:
            logger.info("")
            logger.info("=" * 80)
            logger.info("VERIFICATION: Classification distribution after backfill")
            logger.info("=" * 80)

            unique_names = session.query(Article.university_name).filter(
                Article.university_name.isnot(None)
            ).distinct().all()

            results = {'peer': [], 'r1': [], 'facility': []}
            for row in unique_names:
                category = classifier.classify(row.university_name)
                results[category].append(row.university_name)

            logger.info(f"Peer Institutions: {len(results['peer'])} unique names")
            logger.info(f"R1 Universities: {len(results['r1'])} unique names")
            logger.info(f"Major Facilities: {len(results['facility'])} unique names")

            # Check for remaining suspicious names in facilities
            suspicious_facilities = [n for n in results['facility'] if is_suspicious_name(n)]
            if suspicious_facilities:
                logger.warning(f"\n⚠️  WARNING: {len(suspicious_facilities)} suspicious names still in facilities:")
                for name in suspicious_facilities[:10]:
                    logger.warning(f"  - {name}")
            else:
                logger.info("\n✅ No suspicious names found in Major Facilities column!")

    except Exception as e:
        logger.error(f"Fatal error during backfill: {e}")
        import traceback
        traceback.print_exc()
        stats['errors'] += 1

    finally:
        session.close()

    return stats


def regenerate_html_reports():
    """Regenerate HTML reports after backfilling."""
    logger.info("")
    logger.info("=" * 80)
    logger.info("REGENERATING HTML REPORTS")
    logger.info("=" * 80)

    try:
        from crawler.utils.html_generator import HTMLReportGenerator
        from datetime import datetime

        generator = HTMLReportGenerator()

        # Get today's date
        today = datetime.now().date()

        # Generate main page
        logger.info("Generating index.html...")
        generator.generate_html_report(today)

        # Generate archive pages for last 7 days
        logger.info("Generating archive pages...")
        for days_back in range(1, 8):
            from datetime import timedelta
            date = today - timedelta(days=days_back)
            try:
                generator.generate_html_report(date)
            except Exception as e:
                logger.warning(f"Could not generate archive for {date}: {e}")

        logger.info("✅ HTML reports regenerated successfully")

    except Exception as e:
        logger.error(f"❌ Error regenerating HTML reports: {e}")
        import traceback
        traceback.print_exc()


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description='Backfill university names in the database',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Preview changes without applying them
  python scripts/backfill_university_names.py --dry-run

  # Apply changes to suspicious names only
  python scripts/backfill_university_names.py

  # Apply changes and regenerate HTML
  python scripts/backfill_university_names.py --regenerate-html

  # Backfill all articles (not just suspicious ones)
  python scripts/backfill_university_names.py --all
        """
    )

    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='Show what would be changed without making changes'
    )

    parser.add_argument(
        '--regenerate-html',
        action='store_true',
        help='Regenerate HTML reports after backfilling'
    )

    parser.add_argument(
        '--all',
        action='store_true',
        help='Backfill ALL articles, not just suspicious ones'
    )

    args = parser.parse_args()

    # Run backfill
    stats = backfill_articles(dry_run=args.dry_run, backfill_all=args.all)

    # Regenerate HTML if requested and updates were made
    if args.regenerate_html and not args.dry_run and stats['updated'] > 0:
        regenerate_html_reports()

    # Exit with appropriate code
    if stats['errors'] > 0:
        sys.exit(1)
    else:
        sys.exit(0)


if __name__ == '__main__':
    main()
