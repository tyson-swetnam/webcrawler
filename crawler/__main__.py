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
from crawler.ai.claude_code_analyzer import ClaudeCodeAnalyzer
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
    """Read and log the per-group spider health reports if available."""
    from crawler.utils.source_health import collect_spider_reports

    reports = collect_spider_reports(settings.local_output_dir)
    if not reports:
        logger.info("No spider health reports found")
        return

    logger.info("\n" + "=" * 50)
    logger.info("=== CRAWL HEALTH REPORT ===")
    totals = {}
    failed = []
    attempted = succeeded = 0
    for report in reports:
        for key, value in (report.get('stats') or {}).items():
            if isinstance(value, (int, float)):
                totals[key] = totals.get(key, 0) + value
        attempted += report.get('sources_attempted', 0) or 0
        succeeded += report.get('sources_succeeded', 0) or 0
        failed.extend(report.get('failed_domains', []))

    logger.info(f"Sources attempted: {attempted}")
    logger.info(f"Sources succeeded: {succeeded}")
    logger.info(f"URLs discovered: {totals.get('urls_discovered', '?')}")
    logger.info(f"  via sitemaps: {totals.get('sitemap_urls', 0)}")
    logger.info(f"Feeds autodiscovered: {totals.get('feeds_discovered', 0)}")
    logger.info(f"URLs crawled: {totals.get('urls_crawled', '?')}")
    logger.info(f"Articles extracted: {totals.get('articles_extracted', '?')}")
    logger.info(f"Duplicates skipped: {totals.get('duplicates_skipped', '?')}")
    logger.info(f"Errors: {totals.get('errors', '?')}")
    if failed:
        logger.warning(f"Failed domains ({len(failed)}): {', '.join(failed[:10])}")
    logger.info("=" * 50)


def _update_source_health():
    """Merge this run's spider reports into the rolling source-health file."""
    from crawler.utils.source_health import SourceHealthTracker, collect_spider_reports

    reports = collect_spider_reports(settings.local_output_dir)
    if not reports:
        return
    tracker = SourceHealthTracker()
    tracker.update_from_reports(reports)
    tracker.save()
    tracker.render_html(Path("docs") / "source-health.html")
    info = tracker.summary()
    if info["auto_disabled"]:
        logger.warning(
            f"Source health: {len(info['auto_disabled'])} auto-disabled domains "
            f"(see docs/source-health.html): {', '.join(info['auto_disabled'][:10])}"
        )


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

    # Wall-clock deadline for crawl+analysis so export/publish always run
    # inside the CI step timeout. Leftover analysis resumes next run.
    deadline = None
    if settings.max_pipeline_minutes:
        deadline = start_time + timedelta(minutes=settings.max_pipeline_minutes)
        logger.info(
            f"Pipeline analysis deadline: {settings.max_pipeline_minutes} min "
            f"(until {deadline.strftime('%H:%M:%S')} UTC)"
        )

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

        # Phase 0: Hydrate Postgres from the durable Parquet store.
        # No-op when Postgres already has data (e.g. local persistent DB).
        # Critical for ephemeral environments like GitHub Actions, where the
        # Parquet file in docs/data/ is the only carrier of historical state.
        try:
            from crawler.storage import ParquetStore
            parquet_store = ParquetStore("docs/data")
            with db_manager.session_scope() as db:
                hydrated = parquet_store.hydrate_postgres(db)
                if hydrated:
                    logger.info(f"📦 Phase 0: Hydrated {hydrated} articles from Parquet store")
        except Exception as e:
            logger.warning(f"Phase 0 hydration failed (non-fatal): {e}", exc_info=True)

        # Phase 1+2: Crawl and analyze concurrently (skipped in ANALYZE_ONLY
        # mode, used by the backlog-processor workflow to drain stored
        # articles without re-crawling).
        analyzed_during_crawl = 0
        if settings.analyze_only:
            logger.info("\n🗄️ ANALYZE_ONLY mode: skipping crawl, draining the stored backlog")
        else:
            logger.info("\n📡 Phase 1: Crawling university news sites (parallel spiders + overlapping AI analysis)")
            crawl_success, analyzed_during_crawl = await run_crawl_with_analysis(deadline)

            if not crawl_success:
                logger.error("Crawling phase failed")
                return 1

            # Log spider health reports if available
            _log_spider_health()

            # Feed this run's results into the rolling source-health history
            # (auto-disables persistently dead sources, renders docs/source-health.html)
            try:
                _update_source_health()
            except Exception as e:
                logger.warning(f"Source health update failed (non-fatal): {e}")

        # Phase 3: Final analysis pass — pick up leftovers within this run's
        # allowance (per-run cap minus what the incremental loop already did).
        logger.info("\n📚 Phase 3: Final analysis pass for remaining articles")
        db_manager = get_db_manager()

        with db_manager.session_scope() as db:
            pending_before = _pending_query(db, include_old_scrapes=True).count()

        allowance = max(0, settings.max_articles_per_run - analyzed_during_crawl)
        final_analyzed = 0
        quota_exhausted = False

        if pending_before == 0:
            logger.info("No unanalyzed articles pending")
        elif not settings.enable_ai_analysis:
            logger.info(f"AI analysis disabled; {pending_before} articles left unanalyzed")
        elif allowance == 0:
            logger.info(
                f"Per-run cap ({settings.max_articles_per_run}) already used during "
                f"crawl; {pending_before} pending articles resume next run"
            )
        else:
            logger.info(f"{pending_before} unanalyzed articles pending (allowance {allowance})")
            final_analyzed, quota_exhausted, stopped_early = await drain_unanalyzed(deadline, allowance)
            logger.info(f"Completed {final_analyzed} final AI analyses")
            if (
                final_analyzed == 0
                and analyzed_during_crawl == 0
                and not quota_exhausted
                and not stopped_early
            ):
                # Nothing analyzed at all this run despite pending articles,
                # and not because of quota/deadline/cap (those are expected
                # and resumable) — fail instead of publishing an empty report.
                logger.error(
                    f"Analysis produced zero results for {pending_before} pending "
                    "articles — failing the run"
                )
                return 1

        # Write machine-readable run stats (the backlog-processor workflow
        # reads pending_after to decide whether to re-trigger itself).
        try:
            import json as _json
            with db_manager.session_scope() as db:
                pending_after = _pending_query(db, include_old_scrapes=True).count()
            stats_path = Path(settings.local_output_dir) / "pipeline_stats.json"
            stats_path.parent.mkdir(parents=True, exist_ok=True)
            stats_path.write_text(_json.dumps({
                "analyzed_during_crawl": analyzed_during_crawl,
                "analyzed_final_pass": final_analyzed,
                "analyzed_total": analyzed_during_crawl + final_analyzed,
                "pending_after": pending_after,
                "quota_exhausted": quota_exhausted,
            }, indent=2))
            logger.info(
                f"Run stats: {analyzed_during_crawl + final_analyzed} analyzed, "
                f"{pending_after} still pending"
            )
        except Exception as e:
            logger.warning(f"Could not write pipeline stats (non-fatal): {e}")

        with db_manager.session_scope() as db:
            lookback_time = datetime.now(timezone.utc) - timedelta(days=settings.lookback_days)
            age_limit_date = (datetime.now(timezone.utc) - timedelta(days=settings.max_article_age_days)).date()

            # Re-query all recently analyzed articles for reporting
            all_recent = db.query(Article).filter(
                and_(
                    Article.first_scraped >= lookback_time,
                    Article.last_analyzed != None,
                    (Article.published_date == None) | (Article.published_date >= age_limit_date)
                )
            ).limit(settings.max_articles_per_run).all()

            if not all_recent:
                logger.info("No new articles found in lookback window. "
                           "Falling through to editorial curation against the past 7 days "
                           "so the Top News tab still renders.")
            else:
                logger.info(f"Total articles for reporting: {len(all_recent)}")

            # Phase 3.5: Editorial Curation for Top News (last 7 days)
            editorial_picks = []
            if settings.enable_ai_analysis:
                try:
                    from crawler.ai.editor import EditorialCurator
                    curator = EditorialCurator()

                    # Query last 7 days of AI-related articles for editorial pool
                    editorial_lookback = datetime.now(timezone.utc) - timedelta(days=7)
                    editorial_articles = db.query(Article).filter(
                        and_(
                            Article.is_ai_related == True,
                            Article.last_analyzed != None,
                            Article.published_date >= editorial_lookback,
                        )
                    ).all()

                    candidates = []
                    for art in editorial_articles:
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

                    logger.info(f"\n⭐ Phase 3.5: Editorial curation for Top News ({len(candidates)} articles from last 7 days)")
                    editorial_picks = await curator.curate_top_news(candidates)
                    if editorial_picks:
                        logger.info(f"Editorial curation selected {len(editorial_picks)} top stories")
                        # Persist picks so the Top News tab survives empty
                        # crawls, API failures, and ephemeral-DB runs.
                        try:
                            articles_by_id = {
                                c['article_id']: {
                                    'title': c.get('title', ''),
                                    'url': c.get('url', ''),
                                    'university': c.get('university_name', ''),
                                    'published_date': c.get('published_date', ''),
                                }
                                for c in candidates
                            }
                            snapshot_gen = HTMLReportGenerator(
                                output_dir=settings.local_output_dir,
                                github_pages_dir="docs",
                            )
                            snap_path = snapshot_gen.save_top_news_snapshot(
                                editorial_picks, articles_by_id
                            )
                            if snap_path:
                                logger.info(f"Saved Top News snapshot: {snap_path}")
                        except Exception as e:
                            logger.warning(f"Failed to save Top News snapshot (non-fatal): {e}")
                    else:
                        logger.info("Editorial curation: no top stories selected")
                except Exception as e:
                    logger.warning(f"Editorial curation failed (non-fatal): {e}")

            # Phase 4: Snapshot Postgres → durable Parquet store.
            # Must run after editorial curation so the picks get stamped onto
            # the same snapshot. The website branch carries this file forward
            # across runs (including ephemeral GH Actions DBs).
            try:
                from crawler.storage import ParquetStore
                parquet_store = ParquetStore("docs/data")
                exported = parquet_store.export_from_postgres(db)
                if exported:
                    logger.info(f"📦 Phase 4a: Exported {exported} articles to {parquet_store.articles_path}")
                if editorial_picks:
                    stamped = parquet_store.save_editorial_picks(editorial_picks)
                    logger.info(f"📦 Phase 4a: Stamped {stamped} editorial picks onto Parquet snapshot")
                # Pre-aggregate themes for fast dashboard rendering
                theme_rows = parquet_store.export_themes_daily()
                if theme_rows:
                    logger.info(f"📦 Phase 4a: Pre-aggregated {theme_rows} (date, theme) rows for the dashboard")
            except Exception as e:
                logger.warning(f"Parquet export failed (non-fatal): {e}", exc_info=True)

            # Phase 4b: Generate and send reports
            logger.info("\n📬 Phase 4b: Generating and sending notifications/exports")
            # Analyses are committed to the DB per batch; the export layer
            # reads them from the articles/ai_analyses tables via all_recent.
            exported_files = await send_notifications(all_recent, [], db, editorial_picks=editorial_picks)

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
    """Return the Python script run inside each Scrapy subprocess.

    Scrapy settings come from crawler/config/scrapy_defaults.py — the same
    module the spider's custom_settings uses — so subprocess and in-process
    crawls behave identically.
    """
    return """
import sys
from scrapy.crawler import CrawlerProcess
from crawler.spiders.university_spider import UniversityNewsSpider
from crawler.config.settings import settings
from crawler.config.scrapy_defaults import build_scrapy_settings
from crawler.db.session import init_db, get_db_manager

if __name__ == '__main__':
    init_db(
        settings.database_url,
        pool_size=settings.database_pool_size,
        echo=settings.database_echo
    )
    get_db_manager().create_tables()

    process = CrawlerProcess(build_scrapy_settings())
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
    env["CRAWLER_GROUP_NAME"] = group_name

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

        required = max(1, len(CRAWL_GROUPS) - 1)
        logger.info(
            f"Crawling finished: {successes}/{len(CRAWL_GROUPS)} groups succeeded "
            f"(need >= {required})"
        )
        return successes >= required

    except Exception as e:
        logger.error(f"Crawling failed with exception: {e}", exc_info=True)
        return False


def _pending_query(db, include_old_scrapes: bool = False):
    """Unanalyzed, analyzable articles (shared by every analysis pass).

    `include_old_scrapes=True` drops the lookback filter — used when draining
    the cross-run backlog, whose articles were scraped by earlier runs.
    Articles without content (hydrated from pre-backlog parquet snapshots)
    are excluded: there is nothing to analyze.
    """
    age_limit_date = (datetime.now(timezone.utc) - timedelta(days=settings.max_article_age_days)).date()
    filters = [
        Article.last_analyzed == None,
        Article.content != None,
        (Article.published_date == None) | (Article.published_date >= age_limit_date),
    ]
    if not include_old_scrapes:
        lookback_time = datetime.now(timezone.utc) - timedelta(days=settings.lookback_days)
        filters.append(Article.first_scraped >= lookback_time)
    return db.query(Article).filter(and_(*filters))


def _store_batch(db, batch, analyses) -> int:
    """Persist one batch of analysis results; returns how many were stored.

    None entries (failed/skipped articles) are left untouched so their
    last_analyzed stays NULL and the next run resumes them.
    """
    stored = 0
    for i, analysis in enumerate(analyses):
        if analysis is None:
            continue
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

        # Store Claude-derived metadata (impact scores + themes) on
        # article_metadata so it flows into the Parquet store.
        claude_payload = analysis.get('claude') or {}
        meta_update = {}
        if claude_payload.get('impact_scores'):
            meta_update['impact_scores'] = claude_payload['impact_scores']
        if claude_payload.get('themes'):
            meta_update['themes'] = list(claude_payload['themes'])
        if meta_update:
            article.article_metadata = {
                **(article.article_metadata or {}),
                **meta_update,
            }
        stored += 1
    return stored


def _batch_payload(batch) -> list:
    return [
        {
            "article_id": art.article_id,
            "title": art.title or "Untitled",
            "content": art.content or "",
            "url": art.url.url if art.url else "",
        }
        for art in batch
    ]


async def drain_unanalyzed(deadline, max_articles: int) -> tuple:
    """Analyze up to max_articles pending articles in committed 100-row batches.

    Used for the post-crawl final pass and for ANALYZE_ONLY backlog runs.
    Stops cleanly on the wall-clock deadline, the subscription message
    budget, or quota exhaustion — every completed batch is already
    committed, so nothing is lost when a later run picks up the rest.

    Returns (analyzed_count, quota_exhausted, stopped_early).
    """
    if max_articles <= 0 or not settings.enable_ai_analysis:
        return 0, False, False

    analyzer = ClaudeCodeAnalyzer()
    db_manager = get_db_manager()
    analyzed = 0
    consecutive_failures = 0

    while analyzed < max_articles:
        if deadline and datetime.now(timezone.utc) >= deadline:
            logger.warning(
                f"Analysis deadline reached after {analyzed} articles; "
                "the rest resume next run"
            )
            return analyzed, False, True
        if analyzer.messages_used >= settings.ai_message_budget:
            logger.warning(
                f"Message budget ({settings.ai_message_budget}) reached after "
                f"{analyzed} articles; the rest resume next run"
            )
            return analyzed, False, True

        with db_manager.session_scope() as db:
            batch = _pending_query(db, include_old_scrapes=True).limit(
                min(100, max_articles - analyzed)
            ).all()
            if not batch:
                break

            analyses = await analyzer.batch_analyze(
                _batch_payload(batch),
                max_concurrent=settings.ai_analysis_batch_size,
            )
            stored = _store_batch(db, batch, analyses)
            db.commit()
            analyzed += stored
            logger.info(f"Backlog analysis: {analyzed}/{max_articles} articles this run")

            if getattr(analyzer, "_quota_exhausted", False):
                logger.warning(
                    f"Subscription quota exhausted after {analyzed} articles; "
                    "the rest resume next run"
                )
                return analyzed, True, True

            if stored == 0:
                consecutive_failures += 1
                if consecutive_failures >= 3:
                    logger.error("Backlog analysis giving up after repeated empty batches")
                    return analyzed, False, False
            else:
                consecutive_failures = 0

    return analyzed, False, False


async def run_crawl_with_analysis(deadline=None) -> tuple:
    """
    Run crawling and AI analysis concurrently.

    Launches all spider subprocesses, then starts analyzing articles as they
    arrive in the database — overlapping crawl I/O with AI API calls. The
    incremental analysis loop is bounded by max_articles_per_run, the
    subscription message budget, and the wall-clock deadline; leftovers are
    picked up by later runs.

    Returns:
        (crawl_success, articles_analyzed_during_crawl)
    """
    crawl_tasks = [
        _run_spider_subprocess(name, files)
        for name, files in CRAWL_GROUPS.items()
    ]

    # Wrap each crawl task so we can track completion
    crawl_done = asyncio.Event()
    crawl_results: list = []
    analysis_progress = {"count": 0}

    async def crawl_all():
        results = await asyncio.gather(*crawl_tasks, return_exceptions=True)
        crawl_results.extend(results)
        crawl_done.set()

    async def incremental_analysis():
        """Analyze articles as they appear in the DB while crawling continues.

        Bounded three ways so a huge discovery day can never starve the
        export/publish phases (run #289 analyzed 3,500 articles and was
        killed by the CI step timeout before anything was published):
        per-run article cap, subscription message budget, wall-clock
        deadline. Whatever is left resumes next run.
        """
        if not settings.enable_ai_analysis:
            return

        # Wait for initial articles to accumulate
        await asyncio.sleep(60)

        analyzer = ClaudeCodeAnalyzer()
        db_manager = get_db_manager()
        consecutive_errors = 0
        MAX_CONSECUTIVE_ERRORS = 5

        while True:
            if deadline and datetime.now(timezone.utc) >= deadline:
                logger.warning(
                    f"Incremental analysis stopping at pipeline deadline "
                    f"({analysis_progress['count']} analyzed; the rest resume next run)"
                )
                return
            remaining = settings.max_articles_per_run - analysis_progress["count"]
            if remaining <= 0:
                logger.info(
                    f"Incremental analysis reached the per-run cap of "
                    f"{settings.max_articles_per_run}; the rest resume next run"
                )
                return
            if analyzer.messages_used >= settings.ai_message_budget:
                logger.warning(
                    f"Incremental analysis stopping at the message budget "
                    f"({settings.ai_message_budget}); the rest resume next run"
                )
                return

            try:
                with db_manager.session_scope() as db:
                    batch = _pending_query(db).limit(min(100, remaining)).all()

                    if not batch:
                        if crawl_done.is_set():
                            logger.info(
                                f"Incremental analysis complete — "
                                f"{analysis_progress['count']} articles analyzed during crawl"
                            )
                            return
                        await asyncio.sleep(30)
                        continue

                    logger.info(f"Incremental analysis: processing {len(batch)} articles...")

                    analyses = await analyzer.batch_analyze(
                        _batch_payload(batch),
                        max_concurrent=settings.ai_analysis_batch_size,
                    )
                    stored = _store_batch(db, batch, analyses)
                    db.commit()
                    analysis_progress["count"] += stored
                    logger.info(
                        f"Incremental analysis: {analysis_progress['count']} total articles analyzed so far"
                    )

                    if getattr(analyzer, "_quota_exhausted", False):
                        logger.warning(
                            "Incremental analysis stopping: subscription quota exhausted "
                            f"({analysis_progress['count']} analyzed; the rest resume next run)"
                        )
                        return

                    if stored == 0:
                        # Nothing stored means the whole batch failed; back off
                        # instead of hammering the same articles.
                        consecutive_errors += 1
                        if consecutive_errors >= MAX_CONSECUTIVE_ERRORS:
                            logger.error("Incremental analysis giving up after repeated empty batches")
                            return
                        await asyncio.sleep(30)
                    else:
                        consecutive_errors = 0

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

    # Honest success criteria: a single surviving group out of three used to
    # count as a green run, hiding two-thirds of the crawl being broken.
    required = max(1, len(CRAWL_GROUPS) - 1)
    logger.info(
        f"Crawling finished: {successes}/{len(CRAWL_GROUPS)} groups succeeded "
        f"(need >= {required})"
    )
    return successes >= required, analysis_progress["count"]


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
            logger.info(f"✅ HTML report generated: {today_file}")
            exported_files['html'] = today_file

            # Generate Pagefind search index (non-fatal)
            popular_topics = []
            try:
                import subprocess as _sp
                import tempfile
                import shutil

                staging_dir = tempfile.mkdtemp(prefix='pagefind_stubs_')
                stub_count, popular_topics = html_gen.generate_search_stubs(staging_dir)
                logger.info(f"Generated {stub_count} search stubs")

                pagefind_output = str(Path("docs") / "pagefind")
                result = _sp.run(
                    ["pagefind", "--site", staging_dir, "--output-path", pagefind_output],
                    capture_output=True, text=True, timeout=120
                )
                if result.returncode == 0:
                    logger.info(f"✅ Pagefind index built at {pagefind_output}")
                else:
                    logger.warning(f"Pagefind failed: {result.stderr}")

                shutil.rmtree(staging_dir, ignore_errors=True)
            except FileNotFoundError:
                logger.warning("pagefind CLI not found, skipping search index")
            except Exception as e:
                logger.warning(f"Search index generation failed (non-fatal): {e}")

            archive_file = html_gen.generate_archive_index(popular_topics=popular_topics)
            how_it_works_file = html_gen.generate_how_it_works()
            logger.info(f"✅ Archive index generated: {archive_file}")
            logger.info(f"✅ How It Works page generated: {how_it_works_file}")
            logger.info(f"✅ GitHub Pages output: docs/")
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
        logger.info(f"✅ HTML report generated: {today_file}")
        exported_files['html'] = today_file

        # Generate Pagefind search index (non-fatal)
        popular_topics = []
        try:
            import subprocess as _sp
            import tempfile
            import shutil

            staging_dir = tempfile.mkdtemp(prefix='pagefind_stubs_')
            stub_count, popular_topics = html_gen.generate_search_stubs(staging_dir)
            logger.info(f"Generated {stub_count} search stubs")

            pagefind_output = str(Path("docs") / "pagefind")
            result = _sp.run(
                ["pagefind", "--site", staging_dir, "--output-path", pagefind_output],
                capture_output=True, text=True, timeout=120
            )
            if result.returncode == 0:
                logger.info(f"✅ Pagefind index built at {pagefind_output}")
            else:
                logger.warning(f"Pagefind failed: {result.stderr}")

            shutil.rmtree(staging_dir, ignore_errors=True)
        except FileNotFoundError:
            logger.warning("pagefind CLI not found, skipping search index")
        except Exception as e:
            logger.warning(f"Search index generation failed (non-fatal): {e}")

        archive_file = html_gen.generate_archive_index(popular_topics=popular_topics)
        how_it_works_file = html_gen.generate_how_it_works()
        logger.info(f"✅ Archive index generated: {archive_file}")
        logger.info(f"✅ How It Works page generated: {how_it_works_file}")
        logger.info(f"✅ GitHub Pages output: docs/")
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
