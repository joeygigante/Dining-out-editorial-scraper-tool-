"""SQLite storage for trend items and report history.

Retains 90 days of data for week-over-week and month-over-month comparisons.
"""

from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path

from src.collectors.base import City, Source, TrendItem

DEFAULT_DB_PATH = Path("data/trends.db")
RETENTION_DAYS = 90


class Storage:
    def __init__(self, db_path: str | Path = DEFAULT_DB_PATH):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()

    @contextmanager
    def _conn(self):
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    def _init_schema(self):
        with self._conn() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS trend_items (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    title TEXT NOT NULL,
                    source TEXT NOT NULL,
                    city TEXT NOT NULL,
                    url TEXT,
                    summary TEXT,
                    category TEXT,
                    published TEXT,
                    collected_at TEXT NOT NULL,
                    raw_score REAL DEFAULT 0,
                    final_score REAL DEFAULT 0,
                    metadata_json TEXT,
                    run_id TEXT
                );

                CREATE INDEX IF NOT EXISTS idx_items_collected
                    ON trend_items(collected_at);
                CREATE INDEX IF NOT EXISTS idx_items_city
                    ON trend_items(city);
                CREATE INDEX IF NOT EXISTS idx_items_source
                    ON trend_items(source);
                CREATE INDEX IF NOT EXISTS idx_items_run
                    ON trend_items(run_id);

                CREATE TABLE IF NOT EXISTS reports (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    run_id TEXT NOT NULL,
                    report_type TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    html TEXT,
                    metadata_json TEXT
                );

                CREATE INDEX IF NOT EXISTS idx_reports_run
                    ON reports(run_id);
                """
            )

    def save_items(self, items: list[TrendItem], run_id: str) -> int:
        """Persist collected trend items. Returns count saved."""
        with self._conn() as conn:
            for item in items:
                conn.execute(
                    """
                    INSERT INTO trend_items
                        (title, source, city, url, summary, category,
                         published, collected_at, raw_score, metadata_json, run_id)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        item.title,
                        item.source.value,
                        item.city.value,
                        item.url,
                        item.summary,
                        item.category,
                        item.published.isoformat() if item.published else None,
                        item.collected_at.isoformat(),
                        item.raw_score,
                        json.dumps(item.metadata),
                        run_id,
                    ),
                )
        return len(items)

    def update_scores(self, run_id: str, scores: dict[int, float]):
        """Update final_score for items by their database ID."""
        with self._conn() as conn:
            for item_id, score in scores.items():
                conn.execute(
                    "UPDATE trend_items SET final_score = ? WHERE id = ?",
                    (score, item_id),
                )

    def get_items_for_run(self, run_id: str) -> list[dict]:
        """Get all items from a specific run."""
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT * FROM trend_items WHERE run_id = ? ORDER BY final_score DESC",
                (run_id,),
            ).fetchall()
            return [dict(r) for r in rows]

    def get_items_by_period(self, days: int = 7) -> list[dict]:
        """Get items from the last N days."""
        cutoff = (datetime.now(tz=timezone.utc) - timedelta(days=days)).isoformat()
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT * FROM trend_items WHERE collected_at >= ? ORDER BY final_score DESC",
                (cutoff,),
            ).fetchall()
            return [dict(r) for r in rows]

    def get_previous_run_items(self, current_run_id: str, days_back: int = 7) -> list[dict]:
        """Get items from previous runs for comparison."""
        cutoff = (datetime.now(tz=timezone.utc) - timedelta(days=days_back)).isoformat()
        with self._conn() as conn:
            rows = conn.execute(
                """
                SELECT * FROM trend_items
                WHERE run_id != ? AND collected_at >= ?
                ORDER BY final_score DESC
                """,
                (current_run_id, cutoff),
            ).fetchall()
            return [dict(r) for r in rows]

    def save_report(self, run_id: str, report_type: str, html: str, metadata: dict | None = None):
        """Save a generated report."""
        with self._conn() as conn:
            conn.execute(
                """
                INSERT INTO reports (run_id, report_type, created_at, html, metadata_json)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    run_id,
                    report_type,
                    datetime.now(tz=timezone.utc).isoformat(),
                    html,
                    json.dumps(metadata or {}),
                ),
            )

    def cleanup_old_data(self, retention_days: int = RETENTION_DAYS):
        """Delete data older than retention period."""
        cutoff = (datetime.now(tz=timezone.utc) - timedelta(days=retention_days)).isoformat()
        with self._conn() as conn:
            deleted_items = conn.execute(
                "DELETE FROM trend_items WHERE collected_at < ?", (cutoff,)
            ).rowcount
            deleted_reports = conn.execute(
                "DELETE FROM reports WHERE created_at < ?", (cutoff,)
            ).rowcount
            return {"items_deleted": deleted_items, "reports_deleted": deleted_reports}

    def get_stats(self) -> dict:
        """Get database statistics."""
        with self._conn() as conn:
            item_count = conn.execute("SELECT COUNT(*) FROM trend_items").fetchone()[0]
            report_count = conn.execute("SELECT COUNT(*) FROM reports").fetchone()[0]
            latest_run = conn.execute(
                "SELECT run_id, MAX(collected_at) as ts FROM trend_items"
            ).fetchone()
            return {
                "total_items": item_count,
                "total_reports": report_count,
                "latest_run_id": latest_run["run_id"] if latest_run else None,
                "latest_run_time": latest_run["ts"] if latest_run else None,
            }
