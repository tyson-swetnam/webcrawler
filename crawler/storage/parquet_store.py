"""Parquet store — durable, queryable source of truth for article data.

The crawler hydrates Postgres from this file at start of run (Phase 0) and
dumps it back at the end (Phase 4). The file is committed to git alongside
the rendered HTML, so the website branch carries the full history. The
DuckDB-WASM analytics page reads the same file directly from the browser.

The schema is intentionally denormalized (one row per article) so the
analytics page does not need joins.
"""

from __future__ import annotations

import hashlib
import json
import logging
from datetime import date, datetime, timezone
from pathlib import Path
from typing import List, Optional

import duckdb
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from crawler.db.models import URL, Article, AIAnalysis

logger = logging.getLogger(__name__)


# Column order is canonical — keep it stable so existing Parquet files keep
# loading after additive schema changes. Add new columns at the end.
ARTICLE_COLUMNS = [
    "article_id",
    "url",
    "url_hash",
    "hostname",
    "title",
    "author",
    "university_name",
    "published_date",
    "first_scraped",
    "last_analyzed",
    "is_ai_related",
    "ai_confidence_score",
    "word_count",
    "language",
    "consensus_summary",
    "claude_summary",
    "claude_key_points",
    "openai_category",
    "relevance_score",
    "themes",
    "impact_scientific",
    "impact_financial",
    "impact_partnership",
    "editorial_pick_rank",
    "editorial_note",
    "editorial_impact_category",
    "editorial_picked_at",
    # Full text carried ONLY while an article awaits analysis, so the backlog
    # survives ephemeral CI databases between runs. Cleared once analyzed to
    # keep the snapshot small.
    "pending_content",
]


def _stable_article_id(url: str) -> int:
    """Derive a stable 63-bit article_id from a URL.

    Using a hash of the URL means article_ids are preserved across runs
    (and across machines) without coordinating an autoincrement sequence
    through Parquet, which would otherwise require a setval() dance.
    """
    digest = hashlib.sha256(url.encode("utf-8")).digest()
    # 63 bits keeps it positive in BIGINT
    return int.from_bytes(digest[:8], "big") & 0x7FFFFFFFFFFFFFFF


def _stable_url_id(url: str) -> int:
    """Same idea for url_id."""
    digest = hashlib.sha256(("url:" + url).encode("utf-8")).digest()
    return int.from_bytes(digest[:8], "big") & 0x7FFFFFFFFFFFFFFF


class ParquetStore:
    """Durable Parquet store for articles, with bi-directional Postgres sync."""

    def __init__(self, data_dir: str | Path):
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.articles_path = self.data_dir / "articles.parquet"
        self.themes_daily_path = self.data_dir / "themes_daily.parquet"

    # ────────────────────────────── EXPORT ────────────────────────────────

    def export_from_postgres(self, session: Session) -> int:
        """Snapshot all rows from Postgres into articles.parquet.

        We use a join against ai_analyses to fold the latest analysis into
        the wide row. The previous file is replaced atomically via a temp
        file rename.
        """
        # Pull every article + its most recent analysis. A subquery picks the
        # latest analysis per article so the row stays one-per-article even
        # when ai_analyses has multiple entries.
        stmt = (
            select(Article, URL, AIAnalysis)
            .join(URL, Article.url_id == URL.url_id)
            .outerjoin(
                AIAnalysis,
                AIAnalysis.analysis_id.in_(
                    select(AIAnalysis.analysis_id)
                    .where(AIAnalysis.article_id == Article.article_id)
                    .order_by(AIAnalysis.analyzed_at.desc())
                    .limit(1)
                    .correlate(Article)
                    .scalar_subquery()
                ),
            )
        )

        rows: List[dict] = []
        for article, url_row, analysis in session.execute(stmt).all():
            metadata = article.article_metadata or {}
            impact = (metadata.get("impact_scores") or {}) if isinstance(metadata, dict) else {}
            themes = metadata.get("themes") if isinstance(metadata, dict) else None

            rows.append(
                {
                    "article_id": int(article.article_id),
                    "url": url_row.url,
                    "url_hash": url_row.url_hash,
                    "hostname": url_row.hostname,
                    "title": article.title or "",
                    "author": article.author or "",
                    "university_name": article.university_name or "",
                    "published_date": article.published_date,
                    "first_scraped": article.first_scraped,
                    "last_analyzed": article.last_analyzed,
                    "is_ai_related": bool(article.is_ai_related),
                    "ai_confidence_score": _float_or_none(article.ai_confidence_score),
                    "word_count": int(article.word_count) if article.word_count else None,
                    "language": article.language or "en",
                    "consensus_summary": (analysis.consensus_summary if analysis else None) or "",
                    "claude_summary": (analysis.claude_summary if analysis else None) or "",
                    "claude_key_points": list(analysis.claude_key_points) if analysis and analysis.claude_key_points else [],
                    "openai_category": (analysis.openai_category if analysis else None) or "",
                    "relevance_score": _float_or_none(analysis.relevance_score) if analysis else None,
                    "themes": list(themes) if isinstance(themes, list) else [],
                    "impact_scientific": _float_or_none(impact.get("scientific")),
                    "impact_financial": _float_or_none(impact.get("financial")),
                    "impact_partnership": _float_or_none(impact.get("partnership")),
                    # Editorial-pick fields are written by save_editorial_picks(); leave null here.
                    "editorial_pick_rank": None,
                    "editorial_note": None,
                    "editorial_impact_category": None,
                    "editorial_picked_at": None,
                    "pending_content": (article.content or "") if article.last_analyzed is None else "",
                }
            )

        if not rows:
            logger.info("ParquetStore.export_from_postgres: no rows to export")
            return 0

        # Carry editorial-pick columns forward from any existing file so this
        # snapshot keeps the prior run's pick metadata until the editor
        # explicitly overwrites it via save_editorial_picks().
        prior_picks = self._read_editorial_columns()
        if prior_picks:
            for row in rows:
                pick = prior_picks.get(row["article_id"])
                if pick:
                    row["editorial_pick_rank"] = pick["rank"]
                    row["editorial_note"] = pick["note"]
                    row["editorial_impact_category"] = pick["category"]
                    row["editorial_picked_at"] = pick["picked_at"]

        self._write_rows(rows)
        logger.info(
            "ParquetStore.export_from_postgres: wrote %d rows to %s",
            len(rows),
            self.articles_path,
        )
        return len(rows)

    def export_themes_daily(self) -> int:
        """Pre-aggregate themes per published day into themes_daily.parquet.

        The dashboard's themes-over-time chart prefers this file because the
        scan is ~22 themes × N days instead of UNNEST-ing the full articles
        table. Built directly from articles.parquet (already on disk after
        export_from_postgres()), so no Postgres roundtrip needed.

        Returns the number of (date, theme) pairs written.
        """
        if not self.articles_path.exists():
            logger.info("export_themes_daily: no articles.parquet yet, skipping")
            return 0

        tmp = self.themes_daily_path.with_suffix(".parquet.tmp")
        con = duckdb.connect()
        try:
            con.execute(
                f"""
                COPY (
                    SELECT
                        CAST(published_date AS DATE) AS date,
                        theme,
                        COUNT(*)::INT AS n
                    FROM (
                        SELECT published_date, UNNEST(themes) AS theme
                        FROM read_parquet('{self.articles_path}')
                        WHERE is_ai_related
                          AND published_date IS NOT NULL
                          AND themes IS NOT NULL
                          AND len(themes) > 0
                    )
                    GROUP BY 1, 2
                    ORDER BY 1, 2
                ) TO '{tmp}' (FORMAT 'parquet', COMPRESSION 'zstd')
                """
            )
            (rowcount,) = con.execute(f"SELECT COUNT(*) FROM read_parquet('{tmp}')").fetchone()
        finally:
            con.close()

        tmp.replace(self.themes_daily_path)
        logger.info(
            "export_themes_daily: wrote %d (date, theme) pairs to %s",
            rowcount,
            self.themes_daily_path,
        )
        return int(rowcount)

    def save_editorial_picks(self, picks: List[dict]) -> int:
        """Stamp editorial-pick columns onto the existing Parquet snapshot.

        Picks are matched to rows by article_id. Articles previously picked
        but missing from `picks` have their pick columns cleared so the
        snapshot reflects the latest curation.
        """
        if not self.articles_path.exists():
            logger.warning("save_editorial_picks: no articles.parquet to update")
            return 0

        picked_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
        pick_map = {
            int(p["article_id"]): {
                "rank": int(p.get("rank") or 0),
                "note": str(p.get("editorial_note") or ""),
                "category": str(p.get("impact_category") or "Scientific Breakthrough"),
                "picked_at": picked_at,
            }
            for p in picks
            if p.get("article_id") is not None
        }

        # DuckDB read → in-memory update → DuckDB write. Single rolling file,
        # so a full rewrite is fine at our scale.
        con = duckdb.connect()
        try:
            con.execute(
                f"CREATE TEMP TABLE current AS SELECT * FROM read_parquet('{self.articles_path}')"
            )
            current_ids = [r[0] for r in con.execute("SELECT article_id FROM current").fetchall()]

            updates = 0
            for aid in current_ids:
                pick = pick_map.get(int(aid))
                if pick:
                    con.execute(
                        "UPDATE current SET "
                        "  editorial_pick_rank = ?, "
                        "  editorial_note = ?, "
                        "  editorial_impact_category = ?, "
                        "  editorial_picked_at = ? "
                        "WHERE article_id = ?",
                        [pick["rank"], pick["note"], pick["category"], pick["picked_at"], int(aid)],
                    )
                    updates += 1
                else:
                    # Clear stale pick metadata
                    con.execute(
                        "UPDATE current SET "
                        "  editorial_pick_rank = NULL, "
                        "  editorial_note = NULL, "
                        "  editorial_impact_category = NULL, "
                        "  editorial_picked_at = NULL "
                        "WHERE article_id = ? AND editorial_pick_rank IS NOT NULL",
                        [int(aid)],
                    )

            self._atomic_write_from_duckdb(con, "current")
            logger.info("save_editorial_picks: stamped %d picks", updates)
            return updates
        finally:
            con.close()

    # ────────────────────────────── IMPORT ────────────────────────────────

    def hydrate_postgres(self, session: Session) -> int:
        """Load articles.parquet into Postgres URL/Article/AIAnalysis tables.

        No-op if Postgres already has articles (assume an authoritative DB
        is in play, e.g. Tyson's local persistent Postgres). Otherwise
        bulk-insert with explicit IDs, then advance the autoincrement
        sequences so subsequent INSERTs don't collide.
        """
        if not self.articles_path.exists():
            logger.info("hydrate_postgres: no parquet file at %s, skipping", self.articles_path)
            return 0

        existing = session.query(Article).limit(1).first()
        if existing is not None:
            logger.info("hydrate_postgres: Postgres already has articles, skipping hydration")
            return 0

        con = duckdb.connect()
        try:
            con.execute(
                f"CREATE TEMP VIEW parquet_articles AS SELECT * FROM read_parquet('{self.articles_path}')"
            )
            # Older snapshots predate the pending_content column — substitute
            # an empty string so hydration keeps working on them.
            available = {
                c[0] for c in con.execute("SELECT * FROM parquet_articles LIMIT 0").description
            }
            content_expr = "pending_content" if "pending_content" in available else "'' AS pending_content"
            rows = con.execute(
                "SELECT article_id, url, url_hash, hostname, title, author, "
                "university_name, published_date, first_scraped, last_analyzed, "
                "is_ai_related, ai_confidence_score, word_count, language, "
                "consensus_summary, claude_summary, claude_key_points, openai_category, "
                "relevance_score, themes, impact_scientific, impact_financial, impact_partnership, "
                f"{content_expr} "
                "FROM parquet_articles"
            ).fetchall()
        finally:
            con.close()

        if not rows:
            logger.info("hydrate_postgres: parquet file is empty, nothing to hydrate")
            return 0

        url_objs: dict[int, URL] = {}
        # Key articles by (url_id, content_hash) — the table's unique
        # constraint. The parquet file can carry duplicate rows for the same
        # URL+title (e.g. re-scrapes under slightly different university
        # names), and a multi-row INSERT containing two such rows crashes
        # hydration with an IntegrityError. Keep the freshest row per key.
        articles_by_key: dict = {}
        analyses_by_article: dict = {}
        seen_article_ids: set = set()

        for r in rows:
            (
                article_id,
                url,
                url_hash,
                hostname,
                title,
                author,
                university_name,
                published_date,
                first_scraped,
                last_analyzed,
                is_ai_related,
                ai_confidence_score,
                word_count,
                language,
                consensus_summary,
                claude_summary,
                claude_key_points,
                openai_category,
                relevance_score,
                themes,
                impact_scientific,
                impact_financial,
                impact_partnership,
                pending_content,
            ) = r

            url_id = _stable_url_id(url)
            if url_id not in url_objs:
                url_objs[url_id] = URL(
                    url_id=url_id,
                    url=url,
                    url_hash=url_hash or hashlib.sha256(url.encode("utf-8")).hexdigest(),
                    normalized_url=url,
                    hostname=hostname or "",
                    status="crawled",
                )

            metadata = {
                "themes": list(themes) if themes else [],
                "impact_scores": {
                    "scientific": impact_scientific,
                    "financial": impact_financial,
                    "partnership": impact_partnership,
                },
            }

            article_id = int(article_id)
            if article_id in seen_article_ids:
                continue
            seen_article_ids.add(article_id)

            content_hash = hashlib.sha256((title or url).encode("utf-8")).hexdigest()
            key = (url_id, content_hash)
            existing_row = articles_by_key.get(key)
            if existing_row is not None:
                # Duplicate URL+content — keep the freshest row.
                def _freshness(analyzed, scraped):
                    fallback = datetime.min
                    return (analyzed or scraped or fallback, scraped or fallback)
                candidate_fresh = _freshness(last_analyzed, first_scraped)
                existing_fresh = _freshness(existing_row.last_analyzed, existing_row.first_scraped)
                if candidate_fresh <= existing_fresh:
                    continue
                analyses_by_article.pop(existing_row.article_id, None)

            articles_by_key[key] = Article(
                article_id=article_id,
                url_id=url_id,
                title=title,
                author=author,
                university_name=university_name,
                published_date=published_date,
                first_scraped=first_scraped,
                last_analyzed=last_analyzed,
                is_ai_related=bool(is_ai_related),
                ai_confidence_score=ai_confidence_score,
                word_count=word_count,
                language=language or "en",
                content_hash=content_hash,
                # Restore full text for the unanalyzed backlog so analysis
                # can resume in a fresh (ephemeral) database.
                content=pending_content or None,
                article_metadata=metadata,
            )

            if consensus_summary or claude_summary:
                analyses_by_article[article_id] = AIAnalysis(
                    article_id=article_id,
                    consensus_summary=consensus_summary or None,
                    claude_summary=claude_summary or None,
                    claude_key_points=list(claude_key_points) if claude_key_points else None,
                    openai_category=openai_category or None,
                    relevance_score=relevance_score,
                )

        article_objs = list(articles_by_key.values())
        analysis_objs = list(analyses_by_article.values())
        dropped = len(rows) - len(article_objs)
        if dropped:
            logger.info("hydrate_postgres: dropped %d duplicate parquet rows", dropped)

        session.bulk_save_objects(list(url_objs.values()))
        session.bulk_save_objects(article_objs)
        session.bulk_save_objects(analysis_objs)
        session.flush()

        # We INSERTed with explicit primary keys, so the autoincrement
        # sequences still point at 1. Bump them past MAX(id) to avoid
        # collisions on subsequent INSERTs.
        for table, col in [
            ("urls", "url_id"),
            ("articles", "article_id"),
            ("ai_analyses", "analysis_id"),
        ]:
            session.execute(
                text(
                    f"SELECT setval(pg_get_serial_sequence(:tbl, :col), "
                    f"COALESCE((SELECT MAX({col}) FROM {table}), 1), true)"
                ),
                {"tbl": table, "col": col},
            )

        session.commit()
        logger.info(
            "hydrate_postgres: loaded %d articles, %d analyses from %s",
            len(article_objs),
            len(analysis_objs),
            self.articles_path,
        )
        return len(article_objs)

    # ────────────────────────────── INTERNALS ─────────────────────────────

    def _write_rows(self, rows: List[dict]) -> None:
        """Write a list of dicts to articles.parquet via DuckDB."""
        con = duckdb.connect()
        try:
            # Register the Python list as a DuckDB relation.
            con.register("py_rows", _RowAdapter(rows))
            select_cols = ", ".join(ARTICLE_COLUMNS)
            self._atomic_write_from_duckdb(con, f"(SELECT {select_cols} FROM py_rows)")
        finally:
            con.close()

    def _atomic_write_from_duckdb(self, con, source_sql: str) -> None:
        """COPY ... TO a temp file then rename, so readers never see torn writes."""
        tmp = self.articles_path.with_suffix(".parquet.tmp")
        con.execute(
            f"COPY {source_sql} TO '{tmp}' (FORMAT 'parquet', COMPRESSION 'zstd')"
        )
        tmp.replace(self.articles_path)

    def _read_editorial_columns(self) -> dict[int, dict]:
        """Read just the editorial-pick columns from the prior snapshot.

        Used during export to carry pick metadata forward when re-snapshotting
        from a fresh Postgres (e.g. an ephemeral GH Actions run that hydrated
        from this same file).
        """
        if not self.articles_path.exists():
            return {}
        con = duckdb.connect()
        try:
            rows = con.execute(
                f"SELECT article_id, editorial_pick_rank, editorial_note, "
                f"  editorial_impact_category, editorial_picked_at "
                f"FROM read_parquet('{self.articles_path}') "
                f"WHERE editorial_pick_rank IS NOT NULL"
            ).fetchall()
        except duckdb.Error:
            return {}
        finally:
            con.close()
        return {
            int(r[0]): {"rank": r[1], "note": r[2], "category": r[3], "picked_at": r[4]}
            for r in rows
        }


def _float_or_none(value) -> Optional[float]:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


class _RowAdapter:
    """Make a list of dicts look like a DuckDB-friendly object via __arrow_c_stream__.

    DuckDB's register() accepts pandas DataFrames, pyarrow Tables, and a
    handful of other shapes. We avoid forcing pandas as a dep by converting
    on the fly with pyarrow (which duckdb pulls in transitively).
    """

    def __init__(self, rows: List[dict]):
        import pyarrow as pa  # noqa: WPS433 — lazy import keeps cold start cheap
        self._table = pa.Table.from_pylist(rows, schema=_arrow_schema())

    def __arrow_c_stream__(self, requested_schema=None):  # noqa: D401
        return self._table.__arrow_c_stream__(requested_schema)


def _arrow_schema():
    """Pin the Arrow schema so DuckDB doesn't infer narrower types from sparse data."""
    import pyarrow as pa  # noqa: WPS433

    return pa.schema(
        [
            ("article_id", pa.int64()),
            ("url", pa.string()),
            ("url_hash", pa.string()),
            ("hostname", pa.string()),
            ("title", pa.string()),
            ("author", pa.string()),
            ("university_name", pa.string()),
            ("published_date", pa.date32()),
            ("first_scraped", pa.timestamp("us")),
            ("last_analyzed", pa.timestamp("us")),
            ("is_ai_related", pa.bool_()),
            ("ai_confidence_score", pa.float64()),
            ("word_count", pa.int32()),
            ("language", pa.string()),
            ("consensus_summary", pa.string()),
            ("claude_summary", pa.string()),
            ("claude_key_points", pa.list_(pa.string())),
            ("openai_category", pa.string()),
            ("relevance_score", pa.float64()),
            ("themes", pa.list_(pa.string())),
            ("impact_scientific", pa.float64()),
            ("impact_financial", pa.float64()),
            ("impact_partnership", pa.float64()),
            ("editorial_pick_rank", pa.int32()),
            ("editorial_note", pa.string()),
            ("editorial_impact_category", pa.string()),
            ("editorial_picked_at", pa.string()),
            ("pending_content", pa.string()),
        ]
    )
