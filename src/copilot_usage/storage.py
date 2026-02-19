"""SQLite storage for parsed usage records."""

from __future__ import annotations

import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Optional

from .config import DB_FILE
from .models import SessionRecord, UsageRecord

SCHEMA = """
CREATE TABLE IF NOT EXISTS usage_records (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT NOT NULL,
    model TEXT NOT NULL,
    multiplier REAL NOT NULL,
    is_premium INTEGER NOT NULL,
    initiator TEXT NOT NULL DEFAULT 'user',
    source_file TEXT NOT NULL,
    prompt_tokens INTEGER NOT NULL DEFAULT 0,
    completion_tokens INTEGER NOT NULL DEFAULT 0,
    cached_tokens INTEGER NOT NULL DEFAULT 0,
    duration_ms INTEGER NOT NULL DEFAULT 0,
    session_id TEXT NOT NULL DEFAULT '',
    UNIQUE(timestamp, model, source_file)
);

CREATE TABLE IF NOT EXISTS sessions (
    session_id TEXT PRIMARY KEY,
    start_time TEXT NOT NULL,
    end_time TEXT,
    models_used TEXT NOT NULL DEFAULT '',
    total_turns INTEGER NOT NULL DEFAULT 0,
    total_calls INTEGER NOT NULL DEFAULT 0,
    total_prompt_tokens INTEGER NOT NULL DEFAULT 0,
    total_completion_tokens INTEGER NOT NULL DEFAULT 0,
    total_cached_tokens INTEGER NOT NULL DEFAULT 0,
    total_duration_ms INTEGER NOT NULL DEFAULT 0,
    source_file TEXT NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS parsed_files (
    filename TEXT PRIMARY KEY,
    parsed_at TEXT NOT NULL,
    record_count INTEGER NOT NULL DEFAULT 0
);

CREATE INDEX IF NOT EXISTS idx_usage_timestamp ON usage_records(timestamp);
CREATE INDEX IF NOT EXISTS idx_usage_model ON usage_records(model);
CREATE INDEX IF NOT EXISTS idx_usage_premium ON usage_records(is_premium);
CREATE INDEX IF NOT EXISTS idx_sessions_start ON sessions(start_time);
"""


class UsageDB:
    """SQLite database for caching parsed usage data."""

    def __init__(self, db_path: str | Path | None = None):
        self.db_path = Path(db_path) if db_path else DB_FILE
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(str(self.db_path))
        self.conn.row_factory = sqlite3.Row
        self._init_schema()

    def _init_schema(self):
        self.conn.executescript(SCHEMA)
        self._migrate()
        self.conn.commit()

    def _migrate(self):
        """Add new columns to existing tables if missing."""
        cols = {row[1] for row in self.conn.execute("PRAGMA table_info(usage_records)")}
        new_cols = [
            ("prompt_tokens", "INTEGER NOT NULL DEFAULT 0"),
            ("completion_tokens", "INTEGER NOT NULL DEFAULT 0"),
            ("cached_tokens", "INTEGER NOT NULL DEFAULT 0"),
            ("duration_ms", "INTEGER NOT NULL DEFAULT 0"),
            ("session_id", "TEXT NOT NULL DEFAULT ''"),
        ]
        for col_name, col_def in new_cols:
            if col_name not in cols:
                self.conn.execute(f"ALTER TABLE usage_records ADD COLUMN {col_name} {col_def}")

    def is_file_parsed(self, filename: str) -> bool:
        row = self.conn.execute(
            "SELECT 1 FROM parsed_files WHERE filename = ?", (filename,)
        ).fetchone()
        return row is not None

    def store_records(self, records: list[UsageRecord], filename: str) -> int:
        """Store usage records and mark the file as parsed. Returns count stored."""
        stored = 0
        for r in records:
            try:
                self.conn.execute(
                    """INSERT OR IGNORE INTO usage_records
                       (timestamp, model, multiplier, is_premium, initiator, source_file,
                        prompt_tokens, completion_tokens, cached_tokens, duration_ms, session_id)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (r.timestamp.isoformat(), r.model, r.multiplier,
                     int(r.is_premium), r.initiator, r.source_file,
                     r.prompt_tokens, r.completion_tokens, r.cached_tokens,
                     r.duration_ms, r.session_id),
                )
                stored += 1
            except sqlite3.IntegrityError:
                pass

        self.conn.execute(
            """INSERT OR REPLACE INTO parsed_files (filename, parsed_at, record_count)
               VALUES (?, ?, ?)""",
            (filename, datetime.now().isoformat(), len(records)),
        )
        self.conn.commit()
        return stored

    def store_sessions(self, sessions: list[SessionRecord]) -> int:
        """Store session records."""
        stored = 0
        for s in sessions:
            try:
                self.conn.execute(
                    """INSERT OR REPLACE INTO sessions
                       (session_id, start_time, end_time, models_used, total_turns,
                        total_calls, total_prompt_tokens, total_completion_tokens,
                        total_cached_tokens, total_duration_ms, source_file)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (s.session_id, s.start_time.isoformat(),
                     s.end_time.isoformat() if s.end_time else None,
                     ",".join(s.models_used), s.total_turns, s.total_calls,
                     s.total_prompt_tokens, s.total_completion_tokens,
                     s.total_cached_tokens, s.total_duration_ms, s.source_file),
                )
                stored += 1
            except sqlite3.IntegrityError:
                pass
        self.conn.commit()
        return stored

    def get_records(self, start: datetime | None = None,
                    end: datetime | None = None,
                    premium_only: bool = False) -> list[UsageRecord]:
        """Query usage records by date range."""
        query = "SELECT * FROM usage_records WHERE 1=1"
        params: list = []

        if start:
            query += " AND timestamp >= ?"
            params.append(start.isoformat())
        if end:
            query += " AND timestamp <= ?"
            params.append(end.isoformat())
        if premium_only:
            query += " AND is_premium = 1"

        query += " ORDER BY timestamp"
        rows = self.conn.execute(query, params).fetchall()

        return [
            UsageRecord(
                timestamp=datetime.fromisoformat(row["timestamp"]),
                model=row["model"],
                multiplier=row["multiplier"],
                is_premium=bool(row["is_premium"]),
                initiator=row["initiator"],
                source_file=row["source_file"],
                prompt_tokens=row["prompt_tokens"],
                completion_tokens=row["completion_tokens"],
                cached_tokens=row["cached_tokens"],
                duration_ms=row["duration_ms"],
                session_id=row["session_id"],
            )
            for row in rows
        ]

    def get_sessions(self, start: datetime | None = None,
                     end: datetime | None = None) -> list[SessionRecord]:
        """Query session records by date range."""
        query = "SELECT * FROM sessions WHERE 1=1"
        params: list = []
        if start:
            query += " AND start_time >= ?"
            params.append(start.isoformat())
        if end:
            query += " AND start_time <= ?"
            params.append(end.isoformat())
        query += " ORDER BY start_time"
        rows = self.conn.execute(query, params).fetchall()
        return [
            SessionRecord(
                session_id=row["session_id"],
                start_time=datetime.fromisoformat(row["start_time"]),
                end_time=datetime.fromisoformat(row["end_time"]) if row["end_time"] else None,
                models_used=row["models_used"].split(",") if row["models_used"] else [],
                total_turns=row["total_turns"],
                total_calls=row["total_calls"],
                total_prompt_tokens=row["total_prompt_tokens"],
                total_completion_tokens=row["total_completion_tokens"],
                total_cached_tokens=row["total_cached_tokens"],
                total_duration_ms=row["total_duration_ms"],
                source_file=row["source_file"],
            )
            for row in rows
        ]

    def get_record_count(self) -> int:
        row = self.conn.execute("SELECT COUNT(*) as cnt FROM usage_records").fetchone()
        return row["cnt"]

    def get_parsed_file_count(self) -> int:
        row = self.conn.execute("SELECT COUNT(*) as cnt FROM parsed_files").fetchone()
        return row["cnt"]

    def clear(self):
        """Clear all data — for re-scanning."""
        self.conn.execute("DELETE FROM usage_records")
        self.conn.execute("DELETE FROM parsed_files")
        self.conn.execute("DELETE FROM sessions")
        self.conn.commit()

    def close(self):
        self.conn.close()
