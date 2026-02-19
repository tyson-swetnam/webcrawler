#!/usr/bin/env python3
"""
Comprehensive audit of university news source coverage.

Checks every configured source against the database and probes URLs
to identify broken links, missing RSS feeds, and coverage gaps.

Usage:
    python scripts/audit_university_coverage.py --db-only --verbose
    python scripts/audit_university_coverage.py --batch 1 --total-batches 5
    python scripts/audit_university_coverage.py --merge-batches --total-batches 5
    python scripts/audit_university_coverage.py --source-filter "Stanford" --verbose
"""

import argparse
import asyncio
import json
import logging
import re
import sys
import time
from dataclasses import dataclass, field, asdict
from datetime import date, datetime
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse, urljoin

import httpx

# Add project root to path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

CONFIG_DIR = PROJECT_ROOT / "crawler" / "config"

logger = logging.getLogger(__name__)

# Common RSS feed paths to probe
RSS_CANDIDATE_PATHS = [
    "/rss", "/rss.xml", "/feed", "/feed.xml", "/atom.xml",
    "/news/rss", "/news/feed", "/news/rss.xml", "/news/feed.xml",
    "/newsroom/rss", "/newsroom/feed",
    "/?feed=rss2",
]

# Year patterns in URLs that suggest article links
ARTICLE_YEAR_RE = re.compile(r"/(20(?:2[4-6]))[/-]")
ARTICLE_PATH_RE = re.compile(r"/(news|stories|article|press|release|post)/", re.I)


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class CoverageRecord:
    total_articles_alltime: int = 0
    total_articles_2026: int = 0
    ai_articles_2026: int = 0
    most_recent_scraped: Optional[str] = None
    most_recent_published: Optional[str] = None
    ever_crawled: bool = False
    last_crawl_time: Optional[str] = None
    blocked_until: Optional[str] = None
    status: str = "never"  # good, stale, zero, never


@dataclass
class ProbeResult:
    http_status: Optional[int] = None
    content_type: str = ""
    article_link_count: int = 0
    rss_detected_in_html: Optional[str] = None
    redirect_url: Optional[str] = None
    error: Optional[str] = None


@dataclass
class RSSDiscoveryResult:
    discovered_url: Optional[str] = None
    entry_count: int = 0
    most_recent_entry: Optional[str] = None


@dataclass
class SourceAuditResult:
    name: str = ""
    abbreviation: str = ""
    source_type: str = ""
    source_file: str = ""
    news_url: str = ""
    configured_rss: Optional[str] = None
    coverage: CoverageRecord = field(default_factory=CoverageRecord)
    probe: Optional[ProbeResult] = None
    rss_discovery: Optional[RSSDiscoveryResult] = None
    recommended_action: str = "OK"
    priority: int = 4
    diagnosis: str = ""


# ---------------------------------------------------------------------------
# Phase 0 — Source loading
# ---------------------------------------------------------------------------

def determine_source_file(source: dict) -> str:
    """Determine which config file a source came from by matching its name."""
    # We tag this during loading; this is a fallback
    return source.get("_source_file", "unknown")


def load_all_sources() -> list[dict]:
    """Load all sources from JSON config files directly, tagging each with its origin file."""
    config_files = {
        "peer_institutions.json": ("universities", "peer"),
        "r1_universities.json": ("universities", "r1"),
        "major_facilities.json": ("facilities", "facility"),
        "national_laboratories.json": ("facilities", "national_lab"),
        "global_institutions.json": ("universities", "global"),
    }

    all_sources = []
    for fname, (key, source_type) in config_files.items():
        fpath = CONFIG_DIR / fname
        if not fpath.exists():
            logger.warning(f"Config file not found: {fpath}")
            continue

        with open(fpath, "r") as f:
            data = json.load(f)

        entries = data.get(key, [])
        for entry in entries:
            # Extract primary news source
            news_url = None
            rss_feed = None
            verified = False
            news_sources = entry.get("news_sources", [])
            if isinstance(news_sources, list) and news_sources:
                primary = None
                for ns in news_sources:
                    if ns.get("type") == "primary":
                        primary = ns
                        break
                if not primary:
                    primary = news_sources[0]
                news_url = primary.get("url", "")
                rss_feed = primary.get("rss_feed")
                verified = primary.get("verified", False)

            # Skip unverified or placeholder sources
            if not verified or not news_url:
                continue

            all_sources.append({
                "name": entry.get("name", "Unknown"),
                "abbreviation": entry.get("abbreviation", ""),
                "news_url": news_url,
                "rss_feed": rss_feed,
                "source_type": source_type,
                "_source_file": fname,
            })

    # Deduplicate by news_url
    seen_urls = set()
    deduped = []
    for s in all_sources:
        url = s["news_url"]
        if url not in seen_urls:
            seen_urls.add(url)
            deduped.append(s)
        else:
            logger.debug(f"Duplicate news_url skipped: {s['name']} -> {url}")
    return deduped


# ---------------------------------------------------------------------------
# Phase 1 — DB coverage (no network)
# ---------------------------------------------------------------------------

def check_db_coverage(sources: list[dict]) -> dict[str, CoverageRecord]:
    """Query the database for article coverage per source hostname."""
    try:
        from crawler.config.settings import settings
        from crawler.db.session import init_db, get_db_manager
        from crawler.db.models import URL, Article, HostCrawlState
        from sqlalchemy import func, case, text

        init_db(settings.database_url, pool_size=2, echo=False)
        session = get_db_manager().get_session()
    except Exception as e:
        logger.error(f"Database connection failed: {e}")
        return {}

    results = {}
    cutoff = "2026-01-01"

    for source in sources:
        parsed = urlparse(source["news_url"])
        hostname = parsed.hostname or ""
        rec = CoverageRecord()

        try:
            # Total articles all time for this hostname
            row = session.execute(
                text("""
                    SELECT
                        COUNT(*) AS total_all,
                        SUM(CASE WHEN a.first_scraped >= :cutoff THEN 1 ELSE 0 END) AS total_2026,
                        SUM(CASE WHEN a.is_ai_related AND a.first_scraped >= :cutoff THEN 1 ELSE 0 END) AS ai_2026,
                        MAX(a.first_scraped) AS max_scraped,
                        MAX(a.published_date) AS max_published
                    FROM articles a
                    JOIN urls u ON a.url_id = u.url_id
                    WHERE u.hostname = :hostname
                """),
                {"hostname": hostname, "cutoff": cutoff},
            ).fetchone()

            if row:
                rec.total_articles_alltime = row[0] or 0
                rec.total_articles_2026 = row[1] or 0
                rec.ai_articles_2026 = row[2] or 0
                rec.most_recent_scraped = str(row[3]) if row[3] else None
                rec.most_recent_published = str(row[4]) if row[4] else None
                rec.ever_crawled = rec.total_articles_alltime > 0

            # Check host_crawl_state
            hcs = session.query(HostCrawlState).filter(
                HostCrawlState.hostname == hostname
            ).first()
            if hcs:
                rec.last_crawl_time = str(hcs.last_crawl_time) if hcs.last_crawl_time else None
                rec.blocked_until = str(hcs.blocked_until) if hcs.blocked_until else None

            # Classify status
            if rec.ai_articles_2026 > 0:
                rec.status = "good"
            elif rec.total_articles_2026 > 0:
                rec.status = "stale"  # articles but no AI-flagged
            elif rec.ever_crawled:
                rec.status = "zero"  # crawled historically but nothing in 2026
            else:
                rec.status = "never"

        except Exception as e:
            logger.warning(f"DB query failed for {hostname}: {e}")
            rec.status = "never"

        results[source["news_url"]] = rec

    session.close()
    return results


# ---------------------------------------------------------------------------
# Phase 2 — URL probe (async network)
# ---------------------------------------------------------------------------

async def probe_url(url: str, client: httpx.AsyncClient, semaphore: asyncio.Semaphore) -> ProbeResult:
    """HTTP GET a news URL and analyze the response."""
    result = ProbeResult()
    async with semaphore:
        try:
            resp = await client.get(url, follow_redirects=True)
            result.http_status = resp.status_code
            result.content_type = resp.headers.get("content-type", "")
            if str(resp.url) != url:
                result.redirect_url = str(resp.url)

            if resp.status_code == 200 and "text/html" in result.content_type:
                html = resp.text
                # Count article-like links
                hrefs = re.findall(r'href=["\']([^"\']+)["\']', html)
                article_count = 0
                for href in hrefs:
                    if ARTICLE_YEAR_RE.search(href) or ARTICLE_PATH_RE.search(href):
                        article_count += 1
                result.article_link_count = article_count

                # Detect RSS <link> in HTML head
                rss_match = re.search(
                    r'<link[^>]+type=["\']application/rss\+xml["\'][^>]+href=["\']([^"\']+)["\']',
                    html, re.I
                )
                if not rss_match:
                    rss_match = re.search(
                        r'<link[^>]+href=["\']([^"\']+)["\'][^>]+type=["\']application/rss\+xml["\']',
                        html, re.I
                    )
                if not rss_match:
                    # Also check for atom feeds
                    rss_match = re.search(
                        r'<link[^>]+type=["\']application/atom\+xml["\'][^>]+href=["\']([^"\']+)["\']',
                        html, re.I
                    )
                if rss_match:
                    rss_href = rss_match.group(1)
                    # Resolve relative URLs
                    if rss_href.startswith("/"):
                        parsed = urlparse(url)
                        rss_href = f"{parsed.scheme}://{parsed.netloc}{rss_href}"
                    result.rss_detected_in_html = rss_href

        except httpx.TimeoutException:
            result.error = "timeout"
        except Exception as e:
            result.error = str(e)[:200]

    return result


async def probe_all_urls(
    sources: list[dict],
    coverage: dict[str, CoverageRecord],
    concurrency: int,
    timeout: int,
    probe_all: bool = False,
) -> dict[str, ProbeResult]:
    """Probe URLs for sources with zero/never DB coverage (or all if probe_all)."""
    to_probe = []
    for s in sources:
        cov = coverage.get(s["news_url"], CoverageRecord())
        if probe_all or cov.status in ("zero", "never"):
            to_probe.append(s)

    if not to_probe:
        return {}

    semaphore = asyncio.Semaphore(concurrency)
    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                       "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    }

    results = {}
    async with httpx.AsyncClient(
        headers=headers,
        timeout=httpx.Timeout(timeout),
        verify=False,
        limits=httpx.Limits(max_connections=concurrency, max_keepalive_connections=10),
    ) as client:
        tasks = {
            s["news_url"]: probe_url(s["news_url"], client, semaphore)
            for s in to_probe
        }
        done = await asyncio.gather(*tasks.values(), return_exceptions=True)
        for url, result in zip(tasks.keys(), done):
            if isinstance(result, Exception):
                results[url] = ProbeResult(error=str(result)[:200])
            else:
                results[url] = result

    return results


# ---------------------------------------------------------------------------
# Phase 3 — RSS discovery (async network)
# ---------------------------------------------------------------------------

async def discover_rss_for_url(
    base_url: str,
    client: httpx.AsyncClient,
    semaphore: asyncio.Semaphore,
) -> RSSDiscoveryResult:
    """Probe common RSS paths for a given base URL."""
    import feedparser

    parsed = urlparse(base_url)
    base = f"{parsed.scheme}://{parsed.netloc}"

    async with semaphore:
        for path in RSS_CANDIDATE_PATHS:
            candidate = urljoin(base, path)
            try:
                resp = await client.get(candidate, follow_redirects=True)
                ct = resp.headers.get("content-type", "")
                if resp.status_code == 200 and ("xml" in ct or "rss" in ct or "atom" in ct):
                    feed = feedparser.parse(resp.text)
                    if feed.entries:
                        most_recent = None
                        if hasattr(feed.entries[0], "published"):
                            most_recent = feed.entries[0].published
                        return RSSDiscoveryResult(
                            discovered_url=str(resp.url),
                            entry_count=len(feed.entries),
                            most_recent_entry=most_recent,
                        )
            except Exception:
                continue

    return RSSDiscoveryResult()


async def discover_all_rss(
    sources: list[dict],
    coverage: dict[str, CoverageRecord],
    probes: dict[str, ProbeResult],
    concurrency: int,
    timeout: int,
) -> dict[str, RSSDiscoveryResult]:
    """Discover RSS feeds for sources without one configured or detected."""
    to_discover = []
    for s in sources:
        # Skip if already has configured RSS
        if s.get("rss_feed"):
            continue
        # Skip if RSS was already detected in HTML probe
        probe = probes.get(s["news_url"])
        if probe and probe.rss_detected_in_html:
            continue
        to_discover.append(s)

    if not to_discover:
        return {}

    semaphore = asyncio.Semaphore(concurrency)
    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                       "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    }

    results = {}
    async with httpx.AsyncClient(
        headers=headers,
        timeout=httpx.Timeout(timeout),
        verify=False,
        limits=httpx.Limits(max_connections=concurrency, max_keepalive_connections=10),
    ) as client:
        tasks = {
            s["news_url"]: discover_rss_for_url(s["news_url"], client, semaphore)
            for s in to_discover
        }
        done = await asyncio.gather(*tasks.values(), return_exceptions=True)
        for url, result in zip(tasks.keys(), done):
            if isinstance(result, Exception):
                results[url] = RSSDiscoveryResult()
            else:
                results[url] = result

    return results


# ---------------------------------------------------------------------------
# Phase 4 — Report generation
# ---------------------------------------------------------------------------

def classify_source(
    source: dict,
    cov: CoverageRecord,
    probe: Optional[ProbeResult],
    rss_disc: Optional[RSSDiscoveryResult],
) -> tuple[str, int, str]:
    """Determine recommended action, priority, and diagnosis for a source."""

    has_rss_configured = bool(source.get("rss_feed"))
    rss_in_html = probe.rss_detected_in_html if probe else None
    rss_discovered = rss_disc.discovered_url if rss_disc else None
    url_reachable = probe and probe.http_status == 200 if probe else None
    url_errored = probe and probe.error if probe else None

    # Priority 1: URL unreachable + zero DB coverage
    if probe and (probe.error or (probe.http_status and probe.http_status >= 400)):
        if cov.status in ("zero", "never"):
            return "FIX_URL", 1, (
                f"URL returns {probe.http_status or probe.error}; "
                f"zero articles in DB since 2026"
            )

    # Priority 2: RSS discovered but not configured
    any_rss = rss_in_html or rss_discovered
    if any_rss and not has_rss_configured:
        rss_url = rss_in_html or rss_discovered
        entry_info = ""
        if rss_disc and rss_disc.entry_count:
            entry_info = f" ({rss_disc.entry_count} entries)"
        return "ADD_RSS", 2, f"RSS feed found at {rss_url}{entry_info} but not configured"

    # Priority 2: URL reachable with article links but zero DB coverage
    if url_reachable and probe and probe.article_link_count > 5 and cov.status in ("zero", "never"):
        return "INVESTIGATE", 2, (
            f"URL is live with {probe.article_link_count} article links "
            f"but {cov.total_articles_2026} articles in DB since 2026"
        )

    # Priority 3: URL reachable but few article links
    if url_reachable and probe and probe.article_link_count < 3 and cov.status in ("zero", "never"):
        return "REVIEW_NEWS_URL", 3, (
            f"URL is live but only {probe.article_link_count} article-like links found; "
            f"may not be the news page"
        )

    # Priority 3: Has articles but zero AI-flagged
    if cov.status == "stale":
        return "CHECK_AI_FILTER", 3, (
            f"{cov.total_articles_2026} articles since 2026 but 0 flagged as AI-related"
        )

    # Priority 4: All good
    if cov.status == "good":
        return "OK", 4, (
            f"{cov.ai_articles_2026} AI articles since 2026 "
            f"(of {cov.total_articles_2026} total)"
        )

    # Fallback for sources we couldn't probe (db-only mode)
    if probe is None:
        if cov.status == "never":
            return "INVESTIGATE", 2, "Never appeared in DB; needs URL probe"
        if cov.status == "zero":
            return "INVESTIGATE", 2, "Zero articles since 2026; needs URL probe"

    return "INVESTIGATE", 3, f"Status: {cov.status}; needs manual review"


def build_audit_results(
    sources: list[dict],
    coverage: dict[str, CoverageRecord],
    probes: dict[str, ProbeResult],
    rss_discoveries: dict[str, RSSDiscoveryResult],
) -> list[SourceAuditResult]:
    """Build the final list of audit results."""
    results = []
    for s in sources:
        url = s["news_url"]
        cov = coverage.get(url, CoverageRecord())
        probe = probes.get(url)
        rss_disc = rss_discoveries.get(url)

        # If RSS was detected in HTML probe, treat that as a discovery too
        if probe and probe.rss_detected_in_html and not rss_disc:
            rss_disc = RSSDiscoveryResult(discovered_url=probe.rss_detected_in_html)

        action, priority, diagnosis = classify_source(s, cov, probe, rss_disc)

        results.append(SourceAuditResult(
            name=s["name"],
            abbreviation=s.get("abbreviation", ""),
            source_type=s.get("source_type", ""),
            source_file=s.get("_source_file", ""),
            news_url=url,
            configured_rss=s.get("rss_feed"),
            coverage=cov,
            probe=probe,
            rss_discovery=rss_disc,
            recommended_action=action,
            priority=priority,
            diagnosis=diagnosis,
        ))

    # Sort by priority (critical first), then name
    results.sort(key=lambda r: (r.priority, r.name))
    return results


def print_console_summary(results: list[SourceAuditResult]):
    """Print a concise console summary of the audit."""
    print("\n" + "=" * 70)
    print("UNIVERSITY COVERAGE AUDIT REPORT")
    print("=" * 70)
    print(f"Total sources audited: {len(results)}")
    print(f"Generated: {time.strftime('%Y-%m-%d %H:%M:%S')}")

    # Summary by action
    by_action = {}
    for r in results:
        by_action.setdefault(r.recommended_action, []).append(r)

    print(f"\n{'Action':<20s} {'Count':>5s}  {'Priority':>8s}")
    print("-" * 40)
    for action in ["FIX_URL", "ADD_RSS", "INVESTIGATE", "REVIEW_NEWS_URL", "CHECK_AI_FILTER", "OK"]:
        items = by_action.get(action, [])
        if items:
            pri = items[0].priority
            print(f"  {action:<18s} {len(items):>5d}  P{pri}")

    # Summary by source file
    by_file = {}
    for r in results:
        by_file.setdefault(r.source_file, []).append(r)
    print(f"\n{'Source File':<35s} {'Total':>5s}  {'OK':>4s}  {'Issues':>6s}")
    print("-" * 55)
    for fname in sorted(by_file.keys()):
        items = by_file[fname]
        ok_count = sum(1 for r in items if r.recommended_action == "OK")
        issue_count = len(items) - ok_count
        print(f"  {fname:<33s} {len(items):>5d}  {ok_count:>4d}  {issue_count:>6d}")

    # DB coverage summary
    by_status = {}
    for r in results:
        by_status.setdefault(r.coverage.status, []).append(r)
    print(f"\n{'DB Status':<15s} {'Count':>5s}")
    print("-" * 25)
    for status in ["good", "stale", "zero", "never"]:
        items = by_status.get(status, [])
        print(f"  {status:<13s} {len(items):>5d}")

    # Detail: critical and high priority items
    critical = [r for r in results if r.priority <= 2]
    if critical:
        print(f"\n{'!' * 60}")
        print(f"CRITICAL & HIGH PRIORITY ITEMS ({len(critical)}):")
        print(f"{'!' * 60}")
        for r in critical:
            print(f"  P{r.priority} [{r.recommended_action}] {r.name}")
            print(f"       URL: {r.news_url}")
            print(f"       {r.diagnosis}")
            if r.rss_discovery and r.rss_discovery.discovered_url:
                print(f"       RSS: {r.rss_discovery.discovered_url} ({r.rss_discovery.entry_count} entries)")
            print()

    # RSS discovery summary
    rss_found = [r for r in results if r.rss_discovery and r.rss_discovery.discovered_url]
    if rss_found:
        print(f"\n{'~' * 60}")
        print(f"RSS FEEDS DISCOVERED ({len(rss_found)}):")
        print(f"{'~' * 60}")
        for r in rss_found:
            configured = " [ALREADY CONFIGURED]" if r.configured_rss else ""
            print(f"  {r.name}: {r.rss_discovery.discovered_url} "
                  f"({r.rss_discovery.entry_count} entries){configured}")


def save_report(results: list[SourceAuditResult], output_path: Path):
    """Save the full audit report as JSON."""
    output_path.parent.mkdir(parents=True, exist_ok=True)

    # Build summary
    by_action = {}
    by_status = {}
    for r in results:
        by_action[r.recommended_action] = by_action.get(r.recommended_action, 0) + 1
        by_status[r.coverage.status] = by_status.get(r.coverage.status, 0) + 1

    report = {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "total_sources": len(results),
        "summary": {
            "by_action": by_action,
            "by_db_status": by_status,
        },
        "results": [asdict(r) for r in results],
    }

    with open(output_path, "w") as f:
        json.dump(report, f, indent=2, default=str)
    print(f"\nReport saved to: {output_path}")


# ---------------------------------------------------------------------------
# Batch support
# ---------------------------------------------------------------------------

def slice_batch(sources: list[dict], batch: int, total_batches: int) -> list[dict]:
    """Return the subset of sources for the given batch number (1-indexed)."""
    n = len(sources)
    per_batch = n // total_batches
    remainder = n % total_batches
    start = (batch - 1) * per_batch + min(batch - 1, remainder)
    end = start + per_batch + (1 if batch <= remainder else 0)
    return sources[start:end]


def merge_batch_reports(total_batches: int, output_dir: Path) -> list[SourceAuditResult]:
    """Merge individual batch JSON files into a combined result list."""
    all_results = []
    for i in range(1, total_batches + 1):
        batch_path = output_dir / f"coverage_audit_batch_{i}_of_{total_batches}.json"
        if not batch_path.exists():
            print(f"WARNING: Missing batch file: {batch_path}")
            continue
        with open(batch_path, "r") as f:
            data = json.load(f)
        for entry in data.get("results", []):
            # Reconstruct dataclass from dict
            cov = CoverageRecord(**entry.pop("coverage"))
            probe_data = entry.pop("probe", None)
            probe = ProbeResult(**probe_data) if probe_data else None
            rss_data = entry.pop("rss_discovery", None)
            rss_disc = RSSDiscoveryResult(**rss_data) if rss_data else None
            r = SourceAuditResult(**entry, coverage=cov, probe=probe, rss_discovery=rss_disc)
            all_results.append(r)

    # Deduplicate by news_url (in case batches overlapped)
    seen = set()
    deduped = []
    for r in all_results:
        if r.news_url not in seen:
            seen.add(r.news_url)
            deduped.append(r)
    deduped.sort(key=lambda r: (r.priority, r.name))
    return deduped


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

async def run_audit(args):
    """Run the full audit pipeline."""
    # Phase 0: Load sources
    print("Phase 0: Loading sources...")
    sources = load_all_sources()
    print(f"  Loaded {len(sources)} verified sources")

    # Apply source filter
    if args.source_filter:
        sources = [s for s in sources if args.source_filter.lower() in s["name"].lower()]
        print(f"  Filtered to {len(sources)} sources matching '{args.source_filter}'")

    # Apply batch slicing
    if args.batch and args.total_batches:
        sources = slice_batch(sources, args.batch, args.total_batches)
        print(f"  Batch {args.batch}/{args.total_batches}: {len(sources)} sources")

    if not sources:
        print("No sources to audit!")
        return

    # Phase 1: DB coverage
    print("\nPhase 1: Checking database coverage...")
    coverage = check_db_coverage(sources)
    if coverage:
        statuses = {}
        for cov in coverage.values():
            statuses[cov.status] = statuses.get(cov.status, 0) + 1
        print(f"  DB results: {statuses}")
    else:
        print("  WARNING: No DB results (database may be unavailable)")
        # Fill in empty coverage records
        for s in sources:
            coverage[s["news_url"]] = CoverageRecord()

    probes = {}
    rss_discoveries = {}

    if not args.db_only:
        # Phase 2: URL probe
        print(f"\nPhase 2: Probing URLs (concurrency={args.concurrency}, timeout={args.timeout}s)...")
        probes = await probe_all_urls(
            sources, coverage, args.concurrency, args.timeout, probe_all=True
        )
        reachable = sum(1 for p in probes.values() if p.http_status == 200)
        errors = sum(1 for p in probes.values() if p.error)
        rss_in_html = sum(1 for p in probes.values() if p.rss_detected_in_html)
        print(f"  Probed {len(probes)} URLs: {reachable} reachable, {errors} errors, {rss_in_html} with RSS in HTML")

        # Phase 3: RSS discovery
        print(f"\nPhase 3: Discovering RSS feeds...")
        rss_discoveries = await discover_all_rss(
            sources, coverage, probes, args.concurrency, args.timeout
        )
        found = sum(1 for r in rss_discoveries.values() if r.discovered_url)
        print(f"  Probed {len(rss_discoveries)} sources, found {found} RSS feeds")

    # Phase 4: Report
    print("\nPhase 4: Building report...")
    results = build_audit_results(sources, coverage, probes, rss_discoveries)

    # Print and save
    if args.verbose or not args.batch:
        print_console_summary(results)

    # Determine output path
    output_dir = Path(args.output_dir)
    if args.batch and args.total_batches:
        output_path = output_dir / f"coverage_audit_batch_{args.batch}_of_{args.total_batches}.json"
    else:
        output_path = output_dir / "coverage_audit_report.json"

    save_report(results, output_path)
    return results


def main():
    parser = argparse.ArgumentParser(description="Audit university news source coverage")
    parser.add_argument("--db-only", action="store_true",
                        help="Skip network probes (fast offline analysis)")
    parser.add_argument("--batch", type=int, default=None,
                        help="Process only batch N (1-indexed)")
    parser.add_argument("--total-batches", type=int, default=None,
                        help="Total number of batches")
    parser.add_argument("--merge-batches", action="store_true",
                        help="Merge batch outputs into final report")
    parser.add_argument("--source-filter", type=str, default=None,
                        help="Filter to one institution name (substring match)")
    parser.add_argument("--concurrency", type=int, default=20,
                        help="Max concurrent HTTP requests (default: 20)")
    parser.add_argument("--timeout", type=int, default=15,
                        help="HTTP timeout in seconds (default: 15)")
    parser.add_argument("--output-dir", type=str,
                        default=str(PROJECT_ROOT / "output"),
                        help="Report output directory")
    parser.add_argument("--verbose", action="store_true",
                        help="Per-source detail during run")
    args = parser.parse_args()

    if args.verbose:
        logging.basicConfig(level=logging.DEBUG)
    else:
        logging.basicConfig(level=logging.WARNING)

    # Merge mode
    if args.merge_batches:
        if not args.total_batches:
            print("ERROR: --merge-batches requires --total-batches")
            sys.exit(1)
        output_dir = Path(args.output_dir)
        print(f"Merging {args.total_batches} batch files...")
        results = merge_batch_reports(args.total_batches, output_dir)
        print(f"Merged {len(results)} unique sources")
        print_console_summary(results)
        save_report(results, output_dir / "coverage_audit_report.json")
        return

    # Validate batch args
    if args.batch and not args.total_batches:
        print("ERROR: --batch requires --total-batches")
        sys.exit(1)
    if args.total_batches and not args.batch and not args.merge_batches:
        print("ERROR: --total-batches requires --batch or --merge-batches")
        sys.exit(1)

    asyncio.run(run_audit(args))


if __name__ == "__main__":
    main()
