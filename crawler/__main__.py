"""
Main orchestration for AI News Crawler.

This module coordinates the complete crawling, analysis, and notification pipeline.
Entry point: python -m crawler
"""

import asyncio
import sys
import logging
from datetime import datetime, timedelta
from pathlib import Path
from sqlalchemy import and_

from crawler.config.settings import settings
from crawler.db.session import init_db, get_db_manager
from crawler.db.models import Article, URL, AIAnalysis, NotificationSent
from crawler.ai.analyzer import MultiAIAnalyzer
from crawler.notifiers.slack import SlackNotifier
from crawler.notifiers.email import EmailNotifier

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

    start_time = datetime.utcnow()

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
            lookback_time = datetime.utcnow() - timedelta(days=settings.lookback_days)

            new_articles = db.query(Article).filter(
                and_(
                    Article.first_scraped >= lookback_time,
                    Article.last_analyzed == None
                )
            ).limit(settings.max_articles_per_run).all()

            logger.info(f"Found {len(new_articles)} new articles to analyze")

            if not new_articles:
                logger.info("No new articles found. Exiting.")
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
            logger.info("\n📬 Phase 4: Generating and sending notifications")
            await send_notifications(new_articles, analyses, db)

        # Phase 5: Cleanup and statistics
        duration = (datetime.utcnow() - start_time).total_seconds()
        logger.info("\n" + "=" * 60)
        logger.info(f"✅ Crawler completed successfully in {duration:.1f}s")
        logger.info(f"   Processed {len(new_articles)} articles")
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

    Returns:
        True if successful, False otherwise
    """
    try:
        from scrapy.crawler import CrawlerProcess
        from scrapy.utils.project import get_project_settings as get_scrapy_settings
        from crawler.spiders.university_spider import UniversityNewsSpider

        # Configure Scrapy
        process = CrawlerProcess({
            'LOG_LEVEL': 'INFO',
            'USER_AGENT': settings.user_agent,
            'ROBOTSTXT_OBEY': True,
            'CONCURRENT_REQUESTS': settings.max_concurrent_requests,
            'DOWNLOAD_DELAY': settings.crawl_delay,
        })

        # Run spider
        process.crawl(UniversityNewsSpider)
        process.start()  # This blocks until crawling is done

        logger.info("Crawling completed successfully")
        return True

    except Exception as e:
        logger.error(f"Crawling failed: {e}", exc_info=True)
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
            article.last_analyzed = datetime.utcnow()

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
    Send notifications via Slack and email.

    Args:
        articles: List of Article ORM objects
        analyses: List of analysis results
        db: Database session
    """
    today = datetime.utcnow().strftime('%Y-%m-%d')

    # Filter for AI-related articles only
    ai_articles = [art for art in articles if art.is_ai_related]

    if not ai_articles:
        logger.info("No AI-related articles found, skipping notifications")
        return

    logger.info(f"Preparing notifications for {len(ai_articles)} AI-related articles")

    # Prepare article data for notifications
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
            'word_count': art.word_count
        })

    # Send Slack notification
    if settings.enable_slack_notifications:
        try:
            slack = SlackNotifier()
            slack_success = slack.send_daily_report(report_articles, today)

            if slack_success:
                logger.info("✅ Slack notification sent successfully")

                # Log notification
                notification = NotificationSent(
                    notification_date=datetime.utcnow().date(),
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

    # Send email notification
    if settings.enable_email_notifications:
        try:
            email = EmailNotifier()
            email_success = email.send_daily_report(report_articles, today)

            if email_success:
                logger.info("✅ Email notification sent successfully")

                # Log notification
                notification = NotificationSent(
                    notification_date=datetime.utcnow().date(),
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

    db.commit()


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
