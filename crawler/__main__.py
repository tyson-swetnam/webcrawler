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


def _log_spider_health():
    """Read and log spider health reports if available."""
    import json
    health_file = Path(settings.local_output_dir) / 'spider_health.json'
    if not health_file.exists():
        logger.info("No spider health report found")
        return

    try:
        with open(health_file) as f:
            report = json.load(f)

        stats = report.get('stats', {})
        logger.info("\n" + "=" * 50)
        logger.info("=== CRAWL HEALTH REPORT ===")
        logger.info(f"Sources attempted: {report.get('sources_attempted', '?')}")
        logger.info(f"Sources succeeded: {report.get('sources_succeeded', '?')}")
        logger.info(f"URLs discovered: {stats.get('urls_discovered', '?')}")
        logger.info(f"URLs crawled: {stats.get('urls_crawled', '?')}")
        logger.info(f"Articles extracted: {stats.get('articles_extracted', '?')}")
        logger.info(f"Duplicates skipped: {stats.get('duplicates_skipped', '?')}")
        logger.info(f"Errors: {stats.get('errors', '?')}")

        failed = report.get('failed_domains', [])
        if failed:
            logger.warning(f"Failed domains ({len(failed)}): {', '.join(failed[:10])}")

        logger.info("=" * 50)
    except Exception as e:
        logger.warning(f"Could not read spider health report: {e}")


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
        db_manager = get_db_manager()
        db_manager.create_tables()
        logger.info("Database tables verified/created")

        # Phase 1+2: Crawl and analyze concurrently
        logger.info("\n📡 Phase 1: Crawling university news sites (parallel spiders + overlapping AI analysis)")
        crawl_success = await run_crawl_with_analysis()

        if not crawl_success:
            logger.error("Crawling phase failed")
            return 1

        # Log spider health reports if available
        _log_spider_health()

        # Phase 3: Final analysis pass — pick up any articles missed during overlap
        logger.info("\n📚 Phase 3: Final analysis pass for remaining articles")
        db_manager = get_db_manager()

        with db_manager.session_scope() as db:
            lookback_time = datetime.now(timezone.utc) - timedelta(days=settings.lookback_days)
            age_limit_date = (datetime.now(timezone.utc) - timedelta(days=settings.max_article_age_days)).date()

            new_articles = db.query(Article).filter(
                and_(
                    Article.first_scraped >= lookback_time,
                    Article.last_analyzed == None,
                    (Article.published_date == None) | (Article.published_date >= age_limit_date)
                )
            ).limit(settings.max_articles_per_run).all()

            if new_articles:
                logger.info(f"Found {len(new_articles)} remaining unanalyzed articles")
                if settings.enable_ai_analysis:
                    analyses = await analyze_articles(new_articles, db)
                    logger.info(f"Completed {len(analyses)} final AI analyses")
                else:
                    analyses = []
            else:
                logger.info("All articles already analyzed during crawl")
                analyses = []

            # Re-query all recently analyzed articles for reporting
            all_recent = db.query(Article).filter(
                and_(
                    Article.first_scraped >= lookback_time,
                    Article.last_analyzed != None,
                    (Article.published_date == None) | (Article.published_date >= age_limit_date)
                )
            ).limit(settings.max_articles_per_run).all()

            if not all_recent:
                logger.info("No articles found to report on.")
                logger.info("\n📬 Phase 4: Generating HTML reports")
                await send_notifications([], [], db)
                return 0

            logger.info(f"Total articles for reporting: {len(all_recent)}")

            # Phase 3.5: Editorial Curation for Top News
            editorial_picks = []
            if settings.enable_ai_analysis:
                try:
                    from crawler.ai.editor import EditorialCurator
                    curator = EditorialCurator()

                    candidates = []
                    for art in all_recent:
                        analysis = db.query(AIAnalysis).filter(
                            AIAnalysis.article_id == art.article_id
                        ).order_by(AIAnalysis.analyzed_at.desc()).first()
                        candidates.append({
                            'article_id': art.article_id,
                            'title': art.title,
                            'url': art.url.url if art.url else '',
                            'university_name': art.university_name,
                            'published_date': str(art.published_date) if art.published_date else '',
                            'consensus_summary': analysis.consensus_summary if analysis else '',
                            'article_metadata': art.article_metadata or {},
                        })

                    logger.info("\n⭐ Phase 3.5: Editorial curation for Top News")
                    editorial_picks = await curator.curate_top_news(candidates)
                    if editorial_picks:
                        logger.info(f"Editorial curation selected {len(editorial_picks)} top stories")
                    else:
                        logger.info("Editorial curation: no top stories selected (low-impact day)")
                except Exception as e:
                    logger.warning(f"Editorial curation failed (non-fatal): {e}")

            # Phase 4: Generate and send reports
            logger.info("\n📬 Phase 4: Generating and sending notifications/exports")
            exported_files = await send_notifications(all_recent, analyses, db, editorial_picks=editorial_picks)

        # Phase 5: Summary and statistics
        duration = (datetime.now(timezone.utc) - start_time).total_seconds()
        logger.info("\n" + "=" * 60)
        logger.info(f"✅ Crawler completed successfully in {duration:.1f}s")
        logger.info(f"   Processed {len(all_recent)} articles")

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


def _make_spider_script() -> str:
    """Return the Python script run inside each Scrapy subprocess."""
    return """
import sys
from scrapy.crawler import CrawlerProcess
from crawler.spiders.university_spider import UniversityNewsSpider
from crawler.config.settings import settings
from crawler.db.session import init_db, get_db_manager

if __name__ == '__main__':
    init_db(
        settings.database_url,
        pool_size=settings.database_pool_size,
        echo=settings.database_echo
    )
    get_db_manager().create_tables()

    process = CrawlerProcess({
        'LOG_LEVEL': 'INFO',
        'USER_AGENT': settings.user_agent,
        'ROBOTSTXT_OBEY': True,
        'CONCURRENT_REQUESTS': settings.max_concurrent_requests,
        'DOWNLOAD_DELAY': settings.crawl_delay,
        'CONCURRENT_REQUESTS_PER_DOMAIN': 1,
        'AUTOTHROTTLE_ENABLED': True,
        'AUTOTHROTTLE_START_DELAY': 0.5,
        'AUTOTHROTTLE_MAX_DELAY': 10.0,
        'AUTOTHROTTLE_TARGET_CONCURRENCY': 2.0,
        'DOWNLOAD_TIMEOUT': 30,
        'RETRY_TIMES': 3,
        'RETRY_HTTP_CODES': [500, 502, 503, 504, 408, 429],
        'COOKIES_ENABLED': False,
        'DEPTH_LIMIT': 10,
        'DEPTH_PRIORITY': 1,
    })

    process.crawl(UniversityNewsSpider)
    process.start()
"""


# Source groups for parallel crawling — each maps to one or more JSON config files
CRAWL_GROUPS = {
    "peer": ["crawler/config/peer_institutions.json"],
    "r1": ["crawler/config/r1_universities.json"],
    "facilities": [
        "crawler/config/major_facilities.json",
        "crawler/config/national_laboratories.json",
        "crawler/config/global_institutions.json",
    ],
}


async def _run_spider_subprocess(group_name: str, source_files: list[str]) -> bool:
    """
    Launch a single Scrapy spider subprocess for a source group.

    Args:
        group_name: Human-readable label (for logging)
        source_files: List of JSON config file paths

    Returns:
        True if the subprocess exited successfully
    """
    import os

    env = os.environ.copy()
    env["CRAWLER_SOURCE_FILES"] = ",".join(source_files)

    script = _make_spider_script()

    proc = await asyncio.create_subprocess_exec(
        sys.executable, "-u", "-c", script,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        env=env,
    )

    logger.info(f"[{group_name}] Spider subprocess started (PID {proc.pid})")

    try:
        stdout, stderr = await asyncio.wait_for(
            proc.communicate(),
            timeout=3600,  # 60 min per group
        )
    except asyncio.TimeoutError:
        logger.error(f"[{group_name}] Spider timed out after 60 minutes")
        proc.kill()
        await proc.wait()
        return False

    if stdout:
        for line in stdout.decode().strip().split("\n"):
            if line:
                logger.info(f"[{group_name}] {line}")

    if stderr:
        for line in stderr.decode().strip().split("\n"):
            if line and "DeprecationWarning" not in line:
                logger.warning(f"[{group_name} stderr] {line}")

    if proc.returncode == 0:
        logger.info(f"[{group_name}] Spider completed successfully")
        return True
    else:
        logger.error(f"[{group_name}] Spider failed with exit code {proc.returncode}")
        return False


async def run_crawler() -> bool:
    """
    Run Scrapy crawlers in parallel — one subprocess per source group.

    Launches peer, r1, and facilities spiders concurrently via asyncio.gather().
    Succeeds if ANY subprocess succeeds (partial results are still useful).

    Returns:
        True if at least one group succeeded, False if all failed
    """
    try:
        logger.info(f"Starting {len(CRAWL_GROUPS)} parallel spider subprocesses...")

        tasks = [
            _run_spider_subprocess(name, files)
            for name, files in CRAWL_GROUPS.items()
        ]

        results = await asyncio.gather(*tasks, return_exceptions=True)

        successes = 0
        for (name, _), result in zip(CRAWL_GROUPS.items(), results):
            if isinstance(result, Exception):
                logger.error(f"[{name}] Spider raised exception: {result}")
            elif result:
                successes += 1
            else:
                logger.warning(f"[{name}] Spider returned failure")

        logger.info(f"Crawling finished: {successes}/{len(CRAWL_GROUPS)} groups succeeded")
        return successes > 0

    except Exception as e:
        logger.error(f"Crawling failed with exception: {e}", exc_info=True)
        return False


async def run_crawl_with_analysis() -> bool:
    """
    Run crawling and AI analysis concurrently.

    Launches all spider subprocesses, then starts analyzing articles as they
    arrive in the database — overlapping crawl I/O with AI API calls.

    Returns:
        True if crawling succeeded (analysis failures are non-fatal)
    """
    crawl_tasks = [
        _run_spider_subprocess(name, files)
        for name, files in CRAWL_GROUPS.items()
    ]

    # Wrap each crawl task so we can track completion
    crawl_done = asyncio.Event()
    crawl_results: list = []

    async def crawl_all():
        results = await asyncio.gather(*crawl_tasks, return_exceptions=True)
        crawl_results.extend(results)
        crawl_done.set()

    async def incremental_analysis():
        """Analyze articles as they appear in the DB while crawling continues."""
        if not settings.enable_ai_analysis:
            return

        # Wait for initial articles to accumulate
        await asyncio.sleep(60)

        analyzer = MultiAIAnalyzer()
        db_manager = get_db_manager()
        total_analyzed = 0
        consecutive_errors = 0
        MAX_CONSECUTIVE_ERRORS = 5

        while True:
            try:
                with db_manager.session_scope() as db:
                    lookback_time = datetime.now(timezone.utc) - timedelta(days=settings.lookback_days)
                    age_limit_date = (datetime.now(timezone.utc) - timedelta(days=settings.max_article_age_days)).date()

                    batch = db.query(Article).filter(
                        and_(
                            Article.first_scraped >= lookback_time,
                            Article.last_analyzed == None,
                            (Article.published_date == None) | (Article.published_date >= age_limit_date),
                        )
                    ).limit(100).all()

                    if not batch:
                        if crawl_done.is_set():
                            logger.info(f"Incremental analysis complete — {total_analyzed} articles analyzed during crawl")
                            return
                        await asyncio.sleep(30)
                        continue

                    logger.info(f"Incremental analysis: processing {len(batch)} articles...")

                    articles_data = [
                        {
                            "article_id": art.article_id,
                            "title": art.title or "Untitled",
                            "content": art.content or "",
                            "url": art.url.url if art.url else "",
                        }
                        for art in batch
                    ]

                    analyses = await analyzer.batch_analyze(
                        articles_data,
                        max_concurrent=settings.ai_analysis_batch_size,
                    )

                    for i, analysis in enumerate(analyses):
                        article = batch[i]
                        ai_analysis = AIAnalysis(
                            article_id=article.article_id,
                            claude_summary=analysis.get("claude", {}).get("summary") if analysis.get("claude") else None,
                            claude_key_points=analysis.get("claude", {}).get("key_points", []) if analysis.get("claude") else None,
                            openai_summary=analysis.get("openai", {}).get("summary") if analysis.get("openai") else None,
                            openai_category=analysis.get("openai", {}).get("category") if analysis.get("openai") else None,
                            gemini_summary=analysis.get("gemini", {}).get("summary") if analysis.get("gemini") else None,
                            consensus_summary=analysis["consensus"]["summary"],
                            relevance_score=analysis["consensus"].get("relevance_score"),
                            processing_time_ms=analysis.get("processing_time_ms"),
                        )
                        article.is_ai_related = analysis["consensus"]["is_ai_related"]
                        article.ai_confidence_score = analysis["consensus"]["confidence"]
                        article.last_analyzed = datetime.now(timezone.utc)
                        db.add(ai_analysis)

                        # Store impact scores in article metadata
                        impact_scores = analysis.get('claude', {}).get('impact_scores') if analysis.get('claude') else None
                        if impact_scores:
                            article.article_metadata = {
                                **(article.article_metadata or {}),
                                'impact_scores': impact_scores
                            }

                    db.commit()
                    total_analyzed += len(batch)
                    consecutive_errors = 0
                    logger.info(f"Incremental analysis: {total_analyzed} total articles analyzed so far")

            except Exception as e:
                consecutive_errors += 1
                logger.error(f"Incremental analysis batch error ({consecutive_errors}/{MAX_CONSECUTIVE_ERRORS}): {e}", exc_info=True)
                if consecutive_errors >= MAX_CONSECUTIVE_ERRORS:
                    logger.error("Incremental analysis giving up after too many consecutive errors")
                    return
                if crawl_done.is_set():
                    return
                await asyncio.sleep(30)

    # Run crawling and analysis concurrently
    await asyncio.gather(crawl_all(), incremental_analysis())

    # Evaluate crawl results
    successes = 0
    failed_groups = []
    for (name, _), result in zip(CRAWL_GROUPS.items(), crawl_results):
        if isinstance(result, Exception):
            logger.error(f"[{name}] Spider raised exception: {result}")
            failed_groups.append(name)
        elif result:
            successes += 1
        else:
            logger.warning(f"[{name}] Spider returned failure")
            failed_groups.append(name)

    if failed_groups:
        logger.warning(f"Failed spider groups: {', '.join(failed_groups)}")

    logger.info(f"Crawling finished: {successes}/{len(CRAWL_GROUPS)} groups succeeded")
    return successes > 0


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

            # Store impact scores in article metadata
            impact_scores = analysis.get('claude', {}).get('impact_scores') if analysis.get('claude') else None
            if impact_scores:
                article.article_metadata = {
                    **(article.article_metadata or {}),
                    'impact_scores': impact_scores
                }

            db.add(ai_analysis)

        db.commit()
        logger.info(f"Stored {len(analyses)} AI analyses in database")

        return analyses

    except Exception as e:
        logger.error(f"AI analysis failed: {e}", exc_info=True)
        db.rollback()
        return []


async def send_notifications(articles, analyses, db, editorial_picks=None):
    """
    Send notifications via Slack and email, and/or export to local files.

    Args:
        articles: List of Article ORM objects
        analyses: List of analysis results
        db: Database session
        editorial_picks: Optional list of editorial top news picks

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
                github_pages_dir="docs",
                editorial_picks=editorial_picks
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
            github_pages_dir="docs",
            editorial_picks=editorial_picks
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
