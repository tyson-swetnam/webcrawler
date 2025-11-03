#!/usr/bin/env python3
"""
Generate HTML Report from Database

This script queries the database for articles and generates
an HTML report without running the full crawler.

Usage:
    python scripts/generate_html_report.py                 # Last 24 hours
    python scripts/generate_html_report.py --days 7        # Last 7 days
    python scripts/generate_html_report.py --date 2025-10-31  # Specific date
    python scripts/generate_html_report.py --all-ai        # All AI articles
"""

import sys
import argparse
from pathlib import Path
from datetime import datetime, timedelta
from sqlalchemy import and_, or_

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from crawler.config.settings import settings
from crawler.db.session import init_db, get_db_manager
from crawler.db.models import Article, AIAnalysis
from crawler.utils.local_exporter import LocalExporter
from crawler.utils.report_generator import ReportGenerator


def parse_args():
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(
        description='Generate HTML report from database articles'
    )

    group = parser.add_mutually_exclusive_group()
    group.add_argument(
        '--days',
        type=int,
        default=1,
        help='Number of days to look back (default: 1)'
    )
    group.add_argument(
        '--date',
        type=str,
        help='Specific date (YYYY-MM-DD format)'
    )
    group.add_argument(
        '--all-ai',
        action='store_true',
        help='Generate report for all AI-related articles'
    )

    parser.add_argument(
        '--output',
        type=str,
        help='Output file path (default: output/reports/report_DATE.html)'
    )

    parser.add_argument(
        '--min-confidence',
        type=float,
        default=0.0,
        help='Minimum AI confidence score (0.0-1.0, default: 0.0)'
    )

    parser.add_argument(
        '--format',
        choices=['html', 'json', 'csv', 'text', 'all'],
        default='html',
        help='Output format (default: html)'
    )

    parser.add_argument(
        '--open',
        action='store_true',
        help='Open HTML report in browser after generation'
    )

    return parser.parse_args()


def get_articles(db, args):
    """
    Query database for articles based on arguments.

    Args:
        db: Database session
        args: Parsed command-line arguments

    Returns:
        List of Article ORM objects
    """
    query = db.query(Article)

    # Filter by date range
    if args.all_ai:
        # Get all AI-related articles
        query = query.filter(Article.is_ai_related == True)
    elif args.date:
        # Specific date
        target_date = datetime.strptime(args.date, '%Y-%m-%d').date()
        query = query.filter(
            and_(
                Article.published_date >= target_date,
                Article.published_date < target_date + timedelta(days=1)
            )
        )
    else:
        # Last N days
        lookback_time = datetime.utcnow() - timedelta(days=args.days)
        query = query.filter(Article.first_scraped >= lookback_time)

    # Filter by AI confidence if specified
    if args.min_confidence > 0:
        query = query.filter(
            and_(
                Article.is_ai_related == True,
                Article.ai_confidence_score >= args.min_confidence
            )
        )

    # Order by date
    articles = query.order_by(Article.published_date.desc()).all()

    return articles


def prepare_article_data(articles, db):
    """
    Convert Article ORM objects to dictionaries for export.

    Args:
        articles: List of Article ORM objects
        db: Database session

    Returns:
        List of article dictionaries
    """
    report_articles = []

    for art in articles:
        # Get AI analysis for this article
        analysis = db.query(AIAnalysis).filter(
            AIAnalysis.article_id == art.article_id
        ).order_by(AIAnalysis.analyzed_at.desc()).first()

        summary = analysis.consensus_summary if analysis else (art.summary or "No summary available")

        report_articles.append({
            'title': art.title or 'Untitled',
            'university_name': art.university_name or 'Unknown University',
            'published_date': str(art.published_date) if art.published_date else 'Unknown date',
            'url': art.url.url if art.url else '',
            'summary': summary,
            'author': art.author,
            'word_count': art.word_count,
            'is_ai_related': art.is_ai_related,
            'ai_confidence_score': art.ai_confidence_score
        })

    return report_articles


def main():
    """Main execution function."""
    args = parse_args()

    # Initialize database
    print("Connecting to database...")
    init_db(
        settings.database_url,
        pool_size=settings.database_pool_size,
        echo=False
    )

    db_manager = get_db_manager()

    try:
        with db_manager.session_scope() as db:
            # Query articles
            print(f"Querying articles...")
            articles = get_articles(db, args)

            if not articles:
                print("No articles found matching criteria")
                return 1

            print(f"Found {len(articles)} articles")

            # Prepare article data
            report_articles = prepare_article_data(articles, db)

            # Determine output date
            if args.date:
                output_date = args.date
            else:
                output_date = datetime.utcnow().strftime('%Y-%m-%d')

            # Generate reports
            exporter = LocalExporter()

            if args.format == 'html' or args.format == 'all':
                # Generate HTML
                if args.output and args.format == 'html':
                    output_path = Path(args.output)
                else:
                    output_path = exporter.output_dir / "reports" / f"report_{output_date}.html"

                report_gen = ReportGenerator()
                html_content = report_gen.generate_html_report(
                    report_articles,
                    title=f"AI News Report - {output_date}"
                )

                output_path.parent.mkdir(parents=True, exist_ok=True)
                with open(output_path, 'w', encoding='utf-8') as f:
                    f.write(html_content)

                print(f"✓ HTML report: {output_path}")

                # Open in browser if requested
                if args.open:
                    import webbrowser
                    webbrowser.open(f"file://{output_path.absolute()}")
                    print("✓ Opened in browser")

            if args.format == 'json' or args.format == 'all':
                json_path = exporter.export_json(report_articles, None, output_date)
                print(f"✓ JSON export: {json_path}")

            if args.format == 'csv' or args.format == 'all':
                csv_path = exporter.export_csv(report_articles, output_date)
                print(f"✓ CSV export: {csv_path}")

            if args.format == 'text' or args.format == 'all':
                text_path = exporter.export_text_summary(report_articles, output_date)
                print(f"✓ Text summary: {text_path}")

            # Summary statistics
            ai_count = sum(1 for art in report_articles if art.get('is_ai_related', False))
            print(f"\nSummary:")
            print(f"  Total articles: {len(report_articles)}")
            print(f"  AI-related: {ai_count}")

            if ai_count > 0:
                avg_confidence = sum(
                    art.get('ai_confidence_score', 0)
                    for art in report_articles
                    if art.get('is_ai_related', False)
                ) / ai_count
                print(f"  Average AI confidence: {avg_confidence:.2f}")

            return 0

    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        return 1

    finally:
        db_manager.close()


if __name__ == "__main__":
    sys.exit(main())
