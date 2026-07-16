"""
Source health feedback loop.

The spiders write per-group spider_health_<group>.json reports every run,
but historically nobody consumed them — dead sources accumulated silently
for months. This module keeps a rolling per-domain history in
docs/data/source_health.json (which travels via the website branch, like
articles.parquet), auto-disables domains that fail repeatedly, and renders
a human-readable report page so the config can be repaired.

Policy:
- A domain with >= DISABLE_AFTER consecutive zero-article/error runs is
  marked auto_disabled and skipped by the spider.
- Every PROBE_EVERY runs a disabled domain gets one probe crawl; a
  successful article resets it to active.
- CRAWLER_IGNORE_HEALTH=true bypasses skipping entirely.
"""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Iterable, Optional

logger = logging.getLogger(__name__)

DISABLE_AFTER = 7   # consecutive failing runs before auto-disable
PROBE_EVERY = 7     # probe a disabled domain every Nth run

DEFAULT_HEALTH_PATH = Path("docs/data/source_health.json")


class SourceHealthTracker:
    """Rolling per-domain crawl health with auto-disable."""

    def __init__(self, path: Optional[Path] = None):
        self.path = Path(path or DEFAULT_HEALTH_PATH)
        self.domains: Dict[str, dict] = {}
        self.updated_at: Optional[str] = None
        self._load()

    def _load(self) -> None:
        if not self.path.exists():
            return
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            self.domains = data.get("domains", {})
            self.updated_at = data.get("updated_at")
        except (OSError, ValueError) as e:
            logger.warning(f"Could not load source health file {self.path}: {e}")
            self.domains = {}

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "updated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "policy": {"disable_after": DISABLE_AFTER, "probe_every": PROBE_EVERY},
            "domains": self.domains,
        }
        self.path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
        logger.info(f"Source health saved to {self.path} ({len(self.domains)} domains)")

    # ── run-time queries (spider side) ────────────────────────────────────

    def should_skip(self, hostname: str) -> bool:
        """True if this domain is auto-disabled and this run isn't a probe."""
        if os.environ.get("CRAWLER_IGNORE_HEALTH", "").lower() == "true":
            return False
        record = self.domains.get(hostname)
        if not record or record.get("status") != "auto_disabled":
            return False
        # Give the domain one probe crawl every PROBE_EVERY runs.
        runs_disabled = record.get("runs_since_disabled", 0)
        if runs_disabled and runs_disabled % PROBE_EVERY == 0:
            logger.info(f"Source health: probing auto-disabled domain {hostname}")
            return False
        return True

    # ── post-run merge (pipeline side) ────────────────────────────────────

    def update_from_reports(self, reports: Iterable[dict]) -> None:
        """Merge one run's spider health reports into the rolling history."""
        now = datetime.now(timezone.utc).isoformat(timespec="seconds")
        seen_this_run = set()

        for report in reports:
            for hostname, stats in (report.get("domain_stats") or {}).items():
                seen_this_run.add(hostname)
                record = self.domains.setdefault(hostname, {
                    "status": "active",
                    "consecutive_failures": 0,
                    "runs_since_disabled": 0,
                    "last_success": None,
                    "last_seen": None,
                })
                record["last_seen"] = now
                articles = stats.get("articles", 0)
                errors = stats.get("errors", 0)

                if articles > 0:
                    record["consecutive_failures"] = 0
                    record["runs_since_disabled"] = 0
                    record["last_success"] = now
                    record["status"] = "active"
                elif errors > 0:
                    record["consecutive_failures"] = record.get("consecutive_failures", 0) + 1
                    if record["consecutive_failures"] >= DISABLE_AFTER:
                        if record["status"] != "auto_disabled":
                            logger.warning(
                                f"Source health: auto-disabling {hostname} after "
                                f"{record['consecutive_failures']} consecutive failing runs"
                            )
                        record["status"] = "auto_disabled"

        # Tick the probe counter for disabled domains (whether or not the
        # spider touched them this run).
        for hostname, record in self.domains.items():
            if record.get("status") == "auto_disabled":
                record["runs_since_disabled"] = record.get("runs_since_disabled", 0) + 1

    # ── reporting ─────────────────────────────────────────────────────────

    def summary(self) -> dict:
        disabled = [h for h, r in self.domains.items() if r.get("status") == "auto_disabled"]
        dying = [
            h for h, r in self.domains.items()
            if r.get("status") == "active" and r.get("consecutive_failures", 0) >= 3
        ]
        return {
            "total": len(self.domains),
            "auto_disabled": sorted(disabled),
            "dying": sorted(dying),
        }

    def render_html(self, path: Path) -> None:
        """Write a simple monochrome report page listing dead/dying sources."""
        info = self.summary()
        rows = []
        for hostname in sorted(self.domains):
            record = self.domains[hostname]
            rows.append(
                f"<tr><td>{hostname}</td>"
                f"<td>{record.get('status', 'active')}</td>"
                f"<td>{record.get('consecutive_failures', 0)}</td>"
                f"<td>{record.get('last_success') or '—'}</td></tr>"
            )
        html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Source Health — AI University News</title>
<style>
body {{ font-family: 'Courier New', monospace; background: #fff; color: #000; margin: 2em; }}
h1 {{ border-bottom: 3px solid #000; }}
.summary {{ margin: 1em 0; }}
.bad {{ color: #cc0000; font-weight: bold; }}
table {{ border-collapse: collapse; width: 100%; }}
th, td {{ border: 1px solid #000; padding: 4px 8px; text-align: left; font-size: 13px; }}
th {{ background: #000; color: #fff; }}
</style>
</head>
<body>
<h1>SOURCE HEALTH</h1>
<p class="summary">
{info['total']} tracked domains ·
<span class="bad">{len(info['auto_disabled'])} auto-disabled</span> ·
{len(info['dying'])} failing (not yet disabled) ·
updated {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}
</p>
<p><a href="index.html">&larr; back to the news</a></p>
<table>
<tr><th>Domain</th><th>Status</th><th>Consecutive failures</th><th>Last success</th></tr>
{''.join(rows)}
</table>
</body>
</html>"""
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(html, encoding="utf-8")
        logger.info(f"Source health report written to {path}")


def collect_spider_reports(output_dir: str = "output") -> list:
    """Load every spider_health*.json written by this run's spider groups."""
    reports = []
    for report_path in sorted(Path(output_dir).glob("spider_health*.json")):
        try:
            reports.append(json.loads(report_path.read_text(encoding="utf-8")))
        except (OSError, ValueError) as e:
            logger.warning(f"Could not read {report_path}: {e}")
    return reports
