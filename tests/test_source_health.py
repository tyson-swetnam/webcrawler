"""Tests for the source health feedback loop."""

from pathlib import Path

from crawler.utils.source_health import DISABLE_AFTER, PROBE_EVERY, SourceHealthTracker


def _report(hostname, articles=0, errors=1):
    return {"domain_stats": {hostname: {"articles": articles, "errors": errors}}}


def test_auto_disable_after_consecutive_failures(tmp_path):
    tracker = SourceHealthTracker(tmp_path / "health.json")
    for _ in range(DISABLE_AFTER):
        tracker.update_from_reports([_report("dead.example.edu")])
    assert tracker.domains["dead.example.edu"]["status"] == "auto_disabled"
    assert tracker.should_skip("dead.example.edu") is True


def test_success_resets_counter(tmp_path):
    tracker = SourceHealthTracker(tmp_path / "health.json")
    for _ in range(DISABLE_AFTER - 1):
        tracker.update_from_reports([_report("flaky.example.edu")])
    tracker.update_from_reports([_report("flaky.example.edu", articles=3, errors=0)])
    record = tracker.domains["flaky.example.edu"]
    assert record["status"] == "active"
    assert record["consecutive_failures"] == 0
    assert tracker.should_skip("flaky.example.edu") is False


def test_probe_every_nth_run(tmp_path):
    tracker = SourceHealthTracker(tmp_path / "health.json")
    for _ in range(DISABLE_AFTER):
        tracker.update_from_reports([_report("dead.example.edu")])
    # Tick runs_since_disabled up to a probe multiple
    while tracker.domains["dead.example.edu"]["runs_since_disabled"] % PROBE_EVERY != 0:
        tracker.update_from_reports([])
    assert tracker.should_skip("dead.example.edu") is False  # probe run


def test_ignore_health_env(tmp_path, monkeypatch):
    tracker = SourceHealthTracker(tmp_path / "health.json")
    for _ in range(DISABLE_AFTER):
        tracker.update_from_reports([_report("dead.example.edu")])
    monkeypatch.setenv("CRAWLER_IGNORE_HEALTH", "true")
    assert tracker.should_skip("dead.example.edu") is False


def test_save_and_reload_roundtrip(tmp_path):
    path = tmp_path / "health.json"
    tracker = SourceHealthTracker(path)
    for _ in range(DISABLE_AFTER):
        tracker.update_from_reports([_report("dead.example.edu")])
    tracker.save()

    reloaded = SourceHealthTracker(path)
    assert reloaded.domains["dead.example.edu"]["status"] == "auto_disabled"
    assert reloaded.should_skip("dead.example.edu") is True


def test_render_html(tmp_path):
    tracker = SourceHealthTracker(tmp_path / "health.json")
    tracker.update_from_reports([_report("ok.example.edu", articles=2, errors=0)])
    out = tmp_path / "source-health.html"
    tracker.render_html(out)
    html = out.read_text()
    assert "ok.example.edu" in html
    assert "SOURCE HEALTH" in html
