#!/usr/bin/env python3
"""
URL Health Test Script for University News Crawler

Loads all 3 JSON config files directly (bypassing settings.py) and tests every URL.
Reports on placeholder domains, broken URLs, working unverified entries, etc.

Usage:
    python scripts/test_all_urls.py
    python scripts/test_all_urls.py --verified-only
    python scripts/test_all_urls.py --concurrency 10 --timeout 20
"""

import argparse
import asyncio
import json
import os
import re
import socket
import sys
import time
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse

import httpx

# Add project root to path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

CONFIG_DIR = PROJECT_ROOT / "crawler" / "config"

# Placeholder domain patterns
PLACEHOLDER_PATTERNS = [
    r"universityof\.edu",
    r"universityat\.edu",
    r"theuniversity\.edu",
    r"stateuniversity\.edu",
    r"university-main\.edu",
    r"universityof[a-z]+\.edu",  # e.g., universityofarkansas.edu (AI-generated)
]

# Suspicious domain patterns (AI-generated full-name domains)
SUSPICIOUS_PATTERNS = [
    r"news\.[a-z]+university(-main)?\.edu",  # news.purdueuniversity-main.edu
    r"&",  # URLs with ampersands in domain
    r"\u2014|\u2013",  # em-dash or en-dash in URL
]


@dataclass
class URLResult:
    """Result of testing a single URL."""
    source_file: str
    institution_name: str
    abbreviation: str
    url: str
    verified: bool
    category: str = "unknown"  # working, redirect_ok, blocked_403, not_found_404, server_error_5xx, dns_failure, placeholder, timeout, connection_error
    status_code: Optional[int] = None
    final_url: Optional[str] = None
    response_time_ms: Optional[float] = None
    server_header: Optional[str] = None
    error_message: Optional[str] = None
    is_placeholder: bool = False
    has_news_url_field: bool = False
    news_url_field_value: Optional[str] = None


def load_config_file(filepath: Path) -> tuple[list[dict], str]:
    """Load a JSON config file and return entries + key name."""
    with open(filepath, "r") as f:
        data = json.load(f)

    if "universities" in data:
        return data["universities"], "universities"
    elif "facilities" in data:
        return data["facilities"], "facilities"
    return [], "unknown"


def extract_url_info(entry: dict, source_file: str) -> dict:
    """Extract URL and metadata from a config entry."""
    name = entry.get("name", "Unknown")
    abbreviation = entry.get("abbreviation", "")

    # Get primary news source URL
    news_url = None
    verified = False
    news_sources = entry.get("news_sources", [])
    if isinstance(news_sources, list) and news_sources:
        for ns in news_sources:
            if ns.get("type") == "primary":
                news_url = ns.get("url")
                verified = ns.get("verified", False)
                break
        if not news_url:
            news_url = news_sources[0].get("url")
            verified = news_sources[0].get("verified", False)

    # Check for legacy news_url field
    legacy_news_url = entry.get("news_url")

    return {
        "name": name,
        "abbreviation": abbreviation,
        "url": news_url,
        "verified": verified,
        "legacy_news_url": legacy_news_url,
    }


def is_placeholder_domain(url: str) -> bool:
    """Check if a URL uses a known placeholder domain."""
    if not url:
        return True
    url_lower = url.lower()
    for pattern in PLACEHOLDER_PATTERNS:
        if re.search(pattern, url_lower):
            return True
    for pattern in SUSPICIOUS_PATTERNS:
        if re.search(pattern, url_lower):
            return True
    return False


def check_dns(hostname: str) -> bool:
    """Check if a hostname resolves via DNS."""
    try:
        socket.getaddrinfo(hostname, None, socket.AF_UNSPEC, socket.SOCK_STREAM)
        return True
    except (socket.gaierror, OSError):
        return False


async def test_url(url: str, timeout: int, client: "httpx.AsyncClient") -> dict:
    """Test a single URL and return results."""
    start = time.monotonic()
    result = {
        "status_code": None,
        "final_url": None,
        "response_time_ms": None,
        "server_header": None,
        "error_message": None,
        "category": "unknown",
    }

    parsed = urlparse(url)
    hostname = parsed.hostname

    # DNS check first
    if not check_dns(hostname):
        result["category"] = "dns_failure"
        result["error_message"] = f"DNS resolution failed for {hostname}"
        result["response_time_ms"] = (time.monotonic() - start) * 1000
        return result

    try:
        resp = await client.get(url, follow_redirects=True)
        elapsed_ms = (time.monotonic() - start) * 1000
        result["status_code"] = resp.status_code
        result["final_url"] = str(resp.url)
        result["response_time_ms"] = round(elapsed_ms, 1)
        result["server_header"] = resp.headers.get("Server", "")

        if resp.status_code == 200:
            result["category"] = "working"
        elif resp.status_code in (301, 302, 303, 307, 308):
            result["category"] = "redirect_ok"
        elif resp.status_code == 403:
            server = resp.headers.get("Server", "").lower()
            if "cloudflare" in server:
                result["category"] = "blocked_403"
                result["error_message"] = "Cloudflare 403 block"
            else:
                result["category"] = "blocked_403"
                result["error_message"] = f"403 Forbidden (Server: {resp.headers.get('Server', 'unknown')})"
        elif resp.status_code == 404:
            result["category"] = "not_found_404"
        elif 500 <= resp.status_code < 600:
            result["category"] = "server_error_5xx"
            result["error_message"] = f"Server error: {resp.status_code}"
        else:
            result["category"] = f"http_{resp.status_code}"

        if elapsed_ms > 10000:
            result["category"] = "slow"

    except httpx.TimeoutException:
        result["category"] = "timeout"
        result["error_message"] = f"Timeout after {timeout}s"
        result["response_time_ms"] = timeout * 1000
    except Exception as e:
        result["category"] = "connection_error"
        result["error_message"] = str(e)[:200]
        result["response_time_ms"] = (time.monotonic() - start) * 1000

    return result


async def run_tests(entries: list[dict], concurrency: int, timeout: int) -> list[URLResult]:
    """Run all URL tests with concurrency control."""
    semaphore = asyncio.Semaphore(concurrency)

    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.5",
    }

    async with httpx.AsyncClient(
        headers=headers,
        timeout=httpx.Timeout(timeout),
        verify=False,
        limits=httpx.Limits(max_connections=concurrency, max_keepalive_connections=10),
    ) as client:

        async def test_one(entry_info, source_file):
            url = entry_info["url"]
            r = URLResult(
                source_file=source_file,
                institution_name=entry_info["name"],
                abbreviation=entry_info["abbreviation"],
                url=url or "",
                verified=entry_info["verified"],
                has_news_url_field=entry_info["legacy_news_url"] is not None,
                news_url_field_value=entry_info["legacy_news_url"],
            )

            if not url:
                r.category = "no_url"
                r.is_placeholder = True
                return r

            if is_placeholder_domain(url):
                r.category = "placeholder"
                r.is_placeholder = True
                return r

            async with semaphore:
                test_result = await test_url(url, timeout, client)
                r.category = test_result["category"]
                r.status_code = test_result["status_code"]
                r.final_url = test_result["final_url"]
                r.response_time_ms = test_result["response_time_ms"]
                r.server_header = test_result["server_header"]
                r.error_message = test_result["error_message"]
                return r

        tasks = []
        for entry_info, source_file in entries:
            tasks.append(test_one(entry_info, source_file))

        results = await asyncio.gather(*tasks)

    return list(results)


def print_summary(results: list[URLResult]):
    """Print a summary of test results to console."""
    # Group by source file
    by_file = {}
    for r in results:
        by_file.setdefault(r.source_file, []).append(r)

    # Group by category
    by_category = {}
    for r in results:
        by_category.setdefault(r.category, []).append(r)

    print("\n" + "=" * 70)
    print("URL HEALTH TEST REPORT")
    print("=" * 70)

    print(f"\nTotal entries tested: {len(results)}")
    print(f"\nResults by category:")
    for cat in sorted(by_category.keys()):
        items = by_category[cat]
        print(f"  {cat:25s}: {len(items):4d}")

    print(f"\nResults by source file:")
    for fname in sorted(by_file.keys()):
        items = by_file[fname]
        print(f"\n  {fname}:")
        file_cats = {}
        for r in items:
            file_cats.setdefault(r.category, []).append(r)
        for cat in sorted(file_cats.keys()):
            print(f"    {cat:25s}: {len(file_cats[cat]):4d}")

    # Flag mismatches: verified=true but broken, verified=false but working
    verified_broken = [r for r in results if r.verified and r.category not in ("working", "redirect_ok", "slow")]
    unverified_working = [r for r in results if not r.verified and r.category in ("working", "redirect_ok")]

    if verified_broken:
        print(f"\n{'!' * 60}")
        print(f"VERIFIED BUT BROKEN ({len(verified_broken)} entries):")
        for r in verified_broken:
            print(f"  [{r.category}] {r.institution_name}: {r.url}")
            if r.error_message:
                print(f"    Error: {r.error_message}")

    if unverified_working:
        print(f"\n{'*' * 60}")
        print(f"UNVERIFIED BUT WORKING ({len(unverified_working)} entries):")
        for r in unverified_working:
            print(f"  [{r.category}] {r.institution_name}: {r.url}")

    # Entries with legacy news_url that differs from primary
    has_alt = [r for r in results if r.has_news_url_field and r.news_url_field_value and r.news_url_field_value != r.url and r.category not in ("working", "redirect_ok")]
    if has_alt:
        print(f"\n{'~' * 60}")
        print(f"BROKEN BUT HAVE LEGACY news_url FIELD ({len(has_alt)} entries):")
        for r in has_alt:
            print(f"  {r.institution_name}: primary={r.url} -> news_url={r.news_url_field_value}")


def save_report(results: list[URLResult], output_dir: Path):
    """Save full report as JSON."""
    output_dir.mkdir(parents=True, exist_ok=True)
    report_path = output_dir / "url_health_report.json"

    report = {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "total_entries": len(results),
        "summary": {},
        "results": [],
    }

    # Build summary
    by_category = {}
    for r in results:
        by_category.setdefault(r.category, 0)
        by_category[r.category] += 1
    report["summary"] = by_category

    # Serialize results
    for r in results:
        report["results"].append(asdict(r))

    with open(report_path, "w") as f:
        json.dump(report, f, indent=2, default=str)
    print(f"\nFull report saved to: {report_path}")


def main():
    parser = argparse.ArgumentParser(description="Test all university news URLs")
    parser.add_argument("--verified-only", action="store_true", help="Only test verified URLs")
    parser.add_argument("--concurrency", type=int, default=20, help="Max concurrent requests (default: 20)")
    parser.add_argument("--timeout", type=int, default=15, help="Request timeout in seconds (default: 15)")
    parser.add_argument("--output-dir", type=str, default=str(PROJECT_ROOT / "output"), help="Output directory")
    args = parser.parse_args()

    # Load all config files
    config_files = {
        "peer_institutions.json": CONFIG_DIR / "peer_institutions.json",
        "r1_universities.json": CONFIG_DIR / "r1_universities.json",
        "major_facilities.json": CONFIG_DIR / "major_facilities.json",
    }

    all_entries = []
    for fname, fpath in config_files.items():
        if not fpath.exists():
            print(f"Warning: {fpath} not found, skipping")
            continue
        entries, key = load_config_file(fpath)
        print(f"Loaded {len(entries)} entries from {fname}")
        for entry in entries:
            info = extract_url_info(entry, fname)
            if args.verified_only and not info["verified"]:
                continue
            all_entries.append((info, fname))

    print(f"\nTotal entries to test: {len(all_entries)}")
    print(f"Concurrency: {args.concurrency}, Timeout: {args.timeout}s")

    # Run tests
    results = asyncio.run(run_tests(all_entries, args.concurrency, args.timeout))

    # Print summary
    print_summary(results)

    # Save report
    save_report(results, Path(args.output_dir))

    # Exit code: 1 if any verified URLs are broken
    verified_broken = [r for r in results if r.verified and r.category not in ("working", "redirect_ok", "slow")]
    if verified_broken:
        print(f"\nEXIT 1: {len(verified_broken)} verified URLs are broken")
        sys.exit(1)
    else:
        print(f"\nEXIT 0: All verified URLs are working")
        sys.exit(0)


if __name__ == "__main__":
    main()
