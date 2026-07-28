"""Tests for archive page healing (crawler.__main__._heal_archive_pages).

The archive index is built by scanning docs/archive/*.html, so any date with
stored articles but no page is invisible on the site. These tests pin the
selection logic: only missing dates are rendered, and the per-run cap holds.
"""

from datetime import date, datetime
from pathlib import Path

import pytest

from crawler.__main__ import _heal_archive_pages


class _StubQuery:
    """Mimics the SQLAlchemy chain used by _heal_archive_pages."""

    def __init__(self, rows):
        self._rows = rows

    def filter(self, *args, **kwargs):
        return self

    def distinct(self):
        return self

    def all(self):
        return self._rows


class _StubDB:
    def __init__(self, dates):
        # SQLAlchemy returns row tuples for a single-column query
        self._rows = [(d,) for d in dates]

    def query(self, *args):
        return _StubQuery(self._rows)


class _StubGenerator:
    """Records which dates would be rendered."""

    def __init__(self, docs_dir, output_dir=None):
        self.github_pages_dir = Path(docs_dir)
        self.output_dir = Path(output_dir or docs_dir)
        self.rendered = []

    def generate_daily_report(self, dt):
        self.rendered.append(dt.date())
        page = self.github_pages_dir / "archive" / f"{dt.strftime('%Y-%m-%d')}.html"
        page.parent.mkdir(parents=True, exist_ok=True)
        page.write_text("<html></html>", encoding="utf-8")
        return str(page)


@pytest.fixture
def docs(tmp_path):
    (tmp_path / "archive").mkdir()
    return tmp_path


def _existing(docs, day: date):
    (docs / "archive" / f"{day.strftime('%Y-%m-%d')}.html").write_text("x", encoding="utf-8")


def test_renders_only_missing_dates(docs):
    have, missing_a, missing_b = date(2026, 5, 1), date(2026, 5, 2), date(2026, 6, 3)
    _existing(docs, have)

    gen = _StubGenerator(docs)
    count = _heal_archive_pages(gen, _StubDB([have, missing_a, missing_b]))

    assert count == 2
    assert set(gen.rendered) == {missing_a, missing_b}


def test_no_op_when_every_page_exists(docs):
    days = [date(2026, 5, 1), date(2026, 5, 2)]
    for d in days:
        _existing(docs, d)

    gen = _StubGenerator(docs)
    assert _heal_archive_pages(gen, _StubDB(days)) == 0
    assert gen.rendered == []


def test_respects_per_run_limit(docs):
    days = [date(2026, 5, day) for day in range(1, 11)]

    gen = _StubGenerator(docs)
    count = _heal_archive_pages(gen, _StubDB(days), limit=4)

    assert count == 4
    assert len(gen.rendered) == 4
    # Newest first, so a capped run fills in the most recent gaps
    assert gen.rendered == sorted(days, reverse=True)[:4]


def test_render_failure_is_non_fatal(docs):
    days = [date(2026, 5, 1), date(2026, 5, 2)]

    class _Boom(_StubGenerator):
        def generate_daily_report(self, dt):
            if dt.date() == days[0]:
                raise RuntimeError("render exploded")
            return super().generate_daily_report(dt)

    gen = _Boom(docs)
    count = _heal_archive_pages(gen, _StubDB(days))

    assert count == 1
    assert gen.rendered == [days[1]]


def test_uses_published_dir_when_pages_only_exist_locally(tmp_path):
    """A page in output/ but not docs/ still needs rendering — docs/ is what
    ships, and generate_daily_report writes both."""
    docs = tmp_path / "docs"
    output = tmp_path / "output"
    (docs / "archive").mkdir(parents=True)
    (output / "archive").mkdir(parents=True)
    day = date(2026, 5, 1)
    (output / "archive" / f"{day.strftime('%Y-%m-%d')}.html").write_text("x", encoding="utf-8")

    gen = _StubGenerator(docs, output_dir=output)
    assert _heal_archive_pages(gen, _StubDB([day])) == 1
    assert gen.rendered == [day]
