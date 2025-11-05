"""
Main orchestration for AI News Crawler.

This module coordinates the complete crawling, analysis, and notification pipeline.
Entry point: python -m crawler
"""

import asyncio
import sys
import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path
from sqlalchemy import and_

from crawler.config.settings import settings
from crawler.db.session import init_db, get_db_manager
from crawler.db.models import Article, URL, AIAnalysis, NotificationSent
from crawler.ai.analyzer import MultiAIAnalyzer
from crawler.notifiers.slack import SlackNotifier
from crawler.notifiers.email import EmailNotifier
from crawler.utils.local_exporter import LocalExporter
from crawler.utils.html_generator import HTMLReportGenerator

# Configure logging
logging.basicConfig(
    level=getattr(logging, settings.log_level),
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler('crawler.log') if settings.debug else logging.NullHandler()
    ]
)

logger = logging.getLogger(__name__)


async def main():
    """
    Main orchestration function.

    Coordinates the complete pipeline:
    1. Crawl university news sites
    2. Extract and store articles
    3. Analyze with AI APIs
    4. Send notifications
    """
    logger.info("=" * 60)
    logger.info("Starting AI News Crawler")
    logger.info("=" * 60)

    start_time = datetime.now(timezone.utc)

    try:
        # Initialize database
        logger.info("Initializing database connection...")
        init_db(
            settings.database_url,
            pool_size=settings.database_pool_size,
            echo=settings.database_echo
        )

        # Phase 1: Crawl new articles
        logger.info("\n📡 Phase 1: Crawling university news sites")
        crawl_success = await run_crawler()

        if not crawl_success:
            logger.error("Crawling phase failed")
            return 1

        # Phase 2: Get new articles from database
        logger.info("\n📚 Phase 2: Retrieving new articles from database")
        db_manager = get_db_manager()

        with db_manager.session_scope() as db:
            lookback_time = datetime.now(timezone.utc) - timedelta(days=settings.lookback_days)
            age_limit_date = (datetime.now(timezone.utc) - timedelta(days=settings.max_article_age_days)).date()

            new_articles = db.query(Article).filter(
                and_(
                    Article.first_scraped >= lookback_time,
                    Article.last_analyzed == None,
                    # Also filter by published date to exclude old articles
                    # Allow NULL published_date (some articles may not have it)
                    (Article.published_date == None) | (Article.published_date >= age_limit_date)
                )
            ).limit(settings.max_articles_per_run).all()

            logger.info(f"Found {len(new_articles)} new articles to analyze")

            if not new_articles:
                logger.info("No new articles found to analyze.")
                # Still generate HTML reports for docs/ folder
                logger.info("\n📬 Phase 4: Generating HTML reports")
                await send_notifications([], [], db)
                return 0

            # Phase 3: AI Analysis (if enabled)
            if settings.enable_ai_analysis:
                logger.info(f"\n🤖 Phase 3: Analyzing {len(new_articles)} articles with AI")
                analyses = await analyze_articles(new_articles, db)
                logger.info(f"Completed {len(analyses)} AI analyses")
            else:
                logger.info("\n⏭️  Phase 3: AI analysis disabled, skipping")
                analyses = []

            # Phase 4: Generate and send reports
            logger.info("\n📬 Phase 4: Generating and sending notifications/exports")
            exported_files = await send_notifications(new_articles, analyses, db)

        # Phase 5: Summary and statistics
        duration = (datetime.now(timezone.utc) - start_time).total_seconds()
        logger.info("\n" + "=" * 60)
        logger.info(f"✅ Crawler completed successfully in {duration:.1f}s")
        logger.info(f"   Processed {len(new_articles)} articles")

        # Show export summary
        if exported_files:
            logger.info("\n📁 Results saved to:")
            for format_type, file_path in exported_files.items():
                logger.info(f"   {format_type.upper()}: {file_path}")

        # Show notification status
        logger.info("\n📬 Notification status:")
        if settings.enable_slack_notifications:
            logger.info("   Slack: ENABLED")
        else:
            logger.info("   Slack: DISABLED")

        if settings.enable_email_notifications:
            logger.info("   Email: ENABLED")
        else:
            logger.info("   Email: DISABLED")

        logger.info("=" * 60)

        return 0

    except Exception as e:
        logger.error(f"❌ Fatal error in main pipeline: {e}", exc_info=True)

        # Send error notification
        try:
            if settings.enable_slack_notifications:
                slack = SlackNotifier()
                slack.send_error_notification(str(e), details=str(e.__traceback__))
        except:
            pass

        return 1

    finally:
        # Cleanup
        try:
            db_manager = get_db_manager()
            db_manager.close()
        except:
            pass


async def run_crawler() -> bool:
    """
    Run Scrapy crawler to fetch new articles.

    Uses subprocess to avoid asyncio event loop conflicts with Twisted reactor.

    Returns:
        True if successful, False otherwise
    """
    try:
        import subprocess
        import sys

        logger.info("Starting Scrapy spider in subprocess...")

        # Create a subprocess to run Scrapy independently
        # This avoids event loop conflicts between asyncio and Twisted
        script = """
import sys
from scrapy.crawler import CrawlerProcess
from crawler.spiders.university_spider import UniversityNewsSpider
from crawler.config.settings import settings
from crawler.db.session import init_db

if __name__ == '__main__':
    # Initialize database in subprocess
    init_db(
        settings.database_url,
        pool_size=settings.database_pool_size,
        echo=settings.database_echo
    )

    process = CrawlerProcess({
        'LOG_LEVEL': 'INFO',
        'USER_AGENT': settings.user_agent,
        'ROBOTSTXT_OBEY': True,
        'CONCURRENT_REQUESTS': settings.max_concurrent_requests,
        'DOWNLOAD_DELAY': settings.crawl_delay,
        'CONCURRENT_REQUESTS_PER_DOMAIN': 1,
        'AUTOTHROTTLE_ENABLED': True,
        'AUTOTHROTTLE_START_DELAY': 1.0,
        'AUTOTHROTTLE_MAX_DELAY': 10.0,
        'AUTOTHROTTLE_TARGET_CONCURRENCY': 2.0,
        'DOWNLOAD_TIMEOUT': 30,
        'RETRY_TIMES': 3,
        'RETRY_HTTP_CODES': [500, 502, 503, 504, 408, 429],
        'COOKIES_ENABLED': False,
        # Depth limiting - prevent crawling too deep (max 10 pages of pagination)
        'DEPTH_LIMIT': 10,
        'DEPTH_PRIORITY': 1,
    })

    process.crawl(UniversityNewsSpider)
    process.start()
"""

        # Run in subprocess with proper asyncio handling
        # Use -u flag for unbuffered output to see real-time progress
        proc = await asyncio.create_subprocess_exec(
            sys.executable, '-u', '-c', script,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )

        logger.info("Waiting for spider to complete (timeout: 30 minutes)...")

        # Add timeout to prevent indefinite hanging (30 minutes should be enough)
        try:
            stdout, stderr = await asyncio.wait_for(
                proc.communicate(),
                timeout=1800  # 30 minutes timeout
            )
        except asyncio.TimeoutError:
            logger.error("Crawling timed out after 30 minutes")
            proc.kill()
            await proc.wait()
            return False

        # Log output
        if stdout:
            output_lines = stdout.decode().strip().split('\n')
            logger.info(f"Scrapy output ({len(output_lines)} lines):")
            for line in output_lines:
                if line:
                    logger.info(f"[Scrapy] {line}")

        if stderr:
            error_lines = stderr.decode().strip().split('\n')
            for line in error_lines:
                if line and 'DeprecationWarning' not in line:  # Filter out deprecation warnings
                    logger.warning(f"[Scrapy stderr] {line}")

        if proc.returncode == 0:
            logger.info("✅ Crawling completed successfully")
            return True
        else:
            logger.error(f"❌ Crawling failed with exit code {proc.returncode}")
            # Log the last few lines for debugging
            if stderr:
                logger.error("Last stderr output:")
                for line in stderr.decode().strip().split('\n')[-10:]:
                    if line:
                        logger.error(f"  {line}")
            return False

    except Exception as e:
        logger.error(f"❌ Crawling failed with exception: {e}", exc_info=True)
        return False


async def analyze_articles(articles, db) -> list:
    """
    Analyze articles using multi-AI engine.

    Args:
        articles: List of Article ORM objects
        db: Database session

    Returns:
        List of analysis results
    """
    try:
        analyzer = MultiAIAnalyzer()

        # Convert articles to dictionaries for AI processing
        articles_data = [
            {
                'article_id': art.article_id,
                'title': art.title or 'Untitled',
                'content': art.content or '',
                'url': art.url.url if art.url else ''
            }
            for art in articles
        ]

        # Batch analyze with rate limiting
        analyses = await analyzer.batch_analyze(
            articles_data,
            max_concurrent=settings.ai_analysis_batch_size
        )

        # Store analyses in database
        for i, analysis in enumerate(analyses):
            article = articles[i]

            # Create AI analysis record
            ai_analysis = AIAnalysis(
                article_id=article.article_id,
                claude_summary=analysis.get('claude', {}).get('summary') if analysis.get('claude') else None,
                claude_key_points=analysis.get('claude', {}).get('key_points', []) if analysis.get('claude') else None,
                openai_summary=analysis.get('openai', {}).get('summary') if analysis.get('openai') else None,
                openai_category=analysis.get('openai', {}).get('category') if analysis.get('openai') else None,
                gemini_summary=analysis.get('gemini', {}).get('summary') if analysis.get('gemini') else None,
                consensus_summary=analysis['consensus']['summary'],
                relevance_score=analysis['consensus'].get('relevance_score'),
                processing_time_ms=analysis.get('processing_time_ms')
            )

            # Update article with AI results
            article.is_ai_related = analysis['consensus']['is_ai_related']
            article.ai_confidence_score = analysis['consensus']['confidence']
            article.last_analyzed = datetime.now(timezone.utc)

            db.add(ai_analysis)

        db.commit()
        logger.info(f"Stored {len(analyses)} AI analyses in database")

        return analyses

    except Exception as e:
        logger.error(f"AI analysis failed: {e}", exc_info=True)
        db.rollback()
        return []


async def send_notifications(articles, analyses, db):
    """
    Send notifications via Slack and email, and/or export to local files.

    Args:
        articles: List of Article ORM objects
        analyses: List of analysis results
        db: Database session

    Returns:
        Dictionary of exported file paths
    """
    today = datetime.now(timezone.utc).strftime('%Y-%m-%d')
    exported_files = {}

    # Filter for AI-related articles only
    ai_articles = [art for art in articles if art.is_ai_related]

    if not ai_articles:
        logger.info("No AI-related articles found")
        # Still export empty results if enabled
        if settings.save_results_to_file:
            try:
                exporter = LocalExporter()
                exported_files = exporter.export_all([], [], today)
                logger.info("Exported empty results to local files")
            except Exception as e:
                logger.error(f"Failed to export empty results: {e}")

        # Generate HTML report even with no AI articles (for docs/ folder)
        try:
            logger.info("Generating HTML report website (empty results)...")
            html_gen = HTMLReportGenerator(
                output_dir=settings.local_output_dir,
                github_pages_dir="docs"
            )
            today_file = html_gen.generate_daily_report()
            archive_file = html_gen.generate_archive_index()
            how_it_works_file = html_gen.generate_how_it_works()
            logger.info(f"✅ HTML report generated: {today_file}")
            logger.info(f"✅ Archive index generated: {archive_file}")
            logger.info(f"✅ How It Works page generated: {how_it_works_file}")
            logger.info(f"✅ GitHub Pages output: docs/")
            exported_files['html'] = today_file
            exported_files['html_archive'] = archive_file
            exported_files['html_how_it_works'] = how_it_works_file
        except Exception as e:
            logger.error(f"HTML generation error: {e}", exc_info=True)

        return exported_files

    logger.info(f"Processing {len(ai_articles)} AI-related articles")

    # Prepare article data for notifications/export
    report_articles = []
    for art in ai_articles:
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

    # Export to local files (always runs if enabled)
    if settings.save_results_to_file:
        try:
            logger.info("Exporting results to local files...")
            exporter = LocalExporter()
            exported_files = exporter.export_all(report_articles, analyses, today)
            logger.info(f"✅ Exported {len(exported_files)} file formats")
        except Exception as e:
            logger.error(f"Local export error: {e}", exc_info=True)

    # Generate HTML report (Drudge Report-style website)
    try:
        logger.info("Generating HTML report website...")
        # Generate to both html_output/ (for local viewing) and docs/ (for GitHub Pages)
        html_gen = HTMLReportGenerator(
            output_dir=settings.local_output_dir,
            github_pages_dir="docs"
        )
        today_file = html_gen.generate_daily_report()
        archive_file = html_gen.generate_archive_index()
        how_it_works_file = html_gen.generate_how_it_works()
        logger.info(f"✅ HTML report generated: {today_file}")
        logger.info(f"✅ Archive index generated: {archive_file}")
        logger.info(f"✅ How It Works page generated: {how_it_works_file}")
        logger.info(f"✅ GitHub Pages output: docs/")
        exported_files['html'] = today_file
        exported_files['html_archive'] = archive_file
        exported_files['html_how_it_works'] = how_it_works_file
    except Exception as e:
        logger.error(f"HTML generation error: {e}", exc_info=True)

    # Send Slack notification
    if settings.enable_slack_notifications:
        try:
            logger.info("Sending Slack notification...")
            slack = SlackNotifier()
            slack_success = slack.send_daily_report(report_articles, today)

            if slack_success:
                logger.info("✅ Slack notification sent successfully")

                # Log notification
                notification = NotificationSent(
                    notification_date=datetime.now(timezone.utc).date(),
                    channel='slack',
                    articles_count=len(ai_articles),
                    recipients=[],  # Slack webhooks don't expose recipients
                    status='success'
                )
                db.add(notification)
            else:
                logger.warning("⚠️  Slack notification failed")

        except Exception as e:
            logger.error(f"Slack notification error: {e}", exc_info=True)
    else:
        logger.info("ℹ️  Slack notifications disabled")

    # Send email notification
    if settings.enable_email_notifications:
        try:
            logger.info("Sending email notification...")
            email = EmailNotifier()
            email_success = email.send_daily_report(report_articles, today)

            if email_success:
                logger.info("✅ Email notification sent successfully")

                # Log notification
                notification = NotificationSent(
                    notification_date=datetime.now(timezone.utc).date(),
                    channel='email',
                    articles_count=len(ai_articles),
                    recipients=settings.email_to,
                    status='success'
                )
                db.add(notification)
            else:
                logger.warning("⚠️  Email notification failed")

        except Exception as e:
            logger.error(f"Email notification error: {e}", exc_info=True)
    else:
        logger.info("ℹ️  Email notifications disabled")

    db.commit()
    return exported_files


def cli():
    """Command-line interface entry point."""
    try:
        exit_code = asyncio.run(main())
        sys.exit(exit_code)
    except KeyboardInterrupt:
        logger.info("\nInterrupted by user")
        sys.exit(130)
    except Exception as e:
        logger.error(f"Unexpected error: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    cli()
