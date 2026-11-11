"""A tiny SQLite store used for persistent de-duplication.

The same file is opened by the spiders (to skip jobs that were already scraped,
which saves detail-page requests) and by the item pipeline (to persist new jobs).
``UNIQUE(source, source_id)`` makes inserts idempotent, so re-running a crawl
never creates duplicates.
"""
from __future__ import annotations

import os
import sqlite3
from typing import Mapping

_SCHEMA = """
CREATE TABLE IF NOT EXISTS jobs (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    source          TEXT NOT NULL,
    source_id       TEXT NOT NULL,
    title           TEXT,
    company         TEXT,
    location        TEXT,
    employment_type TEXT,
    salary          TEXT,
    summary         TEXT,
    description     TEXT,
    url             TEXT,
    keyword         TEXT,
    search_location TEXT,
    scraped_at      TEXT,
    UNIQUE (source, source_id)
);
"""

_COLUMNS = (
    "source", "source_id", "title", "company", "location", "employment_type",
    "salary", "summary", "description", "url", "keyword", "search_location", "scraped_at",
)


class JobStore:
    def __init__(self, path: str):
        if path != ":memory:":
            directory = os.path.dirname(os.path.abspath(path))
            os.makedirs(directory, exist_ok=True)
        self.conn = sqlite3.connect(path, timeout=30)
        self.conn.execute("PRAGMA journal_mode=WAL")
        self.conn.executescript(_SCHEMA)

    def exists(self, source: str, source_id: str) -> bool:
        row = self.conn.execute(
            "SELECT 1 FROM jobs WHERE source = ? AND source_id = ? LIMIT 1",
            (source, source_id),
        ).fetchone()
        return row is not None

    def add(self, item: Mapping) -> bool:
        """Insert a job. Returns ``True`` if it was new, ``False`` if a duplicate."""
        values = [item.get(column, "") for column in _COLUMNS]
        cursor = self.conn.execute(
            f"INSERT OR IGNORE INTO jobs ({', '.join(_COLUMNS)}) "
            f"VALUES ({', '.join('?' for _ in _COLUMNS)})",
            values,
        )
        self.conn.commit()
        return cursor.rowcount == 1

    def count(self) -> int:
        return self.conn.execute("SELECT COUNT(*) FROM jobs").fetchone()[0]

    def close(self) -> None:
        self.conn.close()
