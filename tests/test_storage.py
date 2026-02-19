"""Tests for SQLite storage layer."""

import tempfile
from datetime import datetime
from pathlib import Path

import pytest

from copilot_usage.models import SessionRecord, UsageRecord
from copilot_usage.storage import UsageDB


@pytest.fixture
def db(tmp_path):
    db = UsageDB(db_path=tmp_path / "test.db")
    yield db
    db.close()


def _make_record(**kwargs):
    defaults = dict(
        timestamp=datetime(2026, 2, 10, 12, 0, 0),
        model="claude-opus-4.6",
        multiplier=6,
        is_premium=True,
        initiator="user",
        source_file="test.log",
    )
    defaults.update(kwargs)
    return UsageRecord(**defaults)


def _make_session(**kwargs):
    defaults = dict(
        session_id="sess-1",
        start_time=datetime(2026, 2, 10, 10, 0),
        end_time=datetime(2026, 2, 10, 11, 0),
        models_used=["claude-opus-4.6"],
        total_turns=10,
        total_calls=5,
        total_prompt_tokens=1000,
        total_completion_tokens=200,
        total_cached_tokens=800,
        total_duration_ms=30000,
        source_file="test.log",
    )
    defaults.update(kwargs)
    return SessionRecord(**defaults)


class TestStoreAndRetrieve:
    def test_store_records(self, db):
        records = [_make_record(), _make_record(model="gpt-5-mini", multiplier=0, is_premium=False)]
        stored = db.store_records(records, "test.log")
        assert stored == 2
        assert db.get_record_count() == 2

    def test_deduplication(self, db):
        r = _make_record()
        db.store_records([r], "test.log")
        db.store_records([r], "test.log")  # same record again
        assert db.get_record_count() == 1

    def test_get_records(self, db):
        records = [
            _make_record(timestamp=datetime(2026, 2, 10, 12, 0)),
            _make_record(timestamp=datetime(2026, 2, 11, 12, 0), model="haiku"),
        ]
        db.store_records(records, "test.log")
        result = db.get_records()
        assert len(result) == 2
        assert result[0].model == "claude-opus-4.6"
        assert result[1].model == "haiku"

    def test_get_records_date_filter(self, db):
        records = [
            _make_record(timestamp=datetime(2026, 2, 5, 12, 0)),
            _make_record(timestamp=datetime(2026, 2, 15, 12, 0), model="late"),
        ]
        db.store_records(records, "test.log")
        result = db.get_records(start=datetime(2026, 2, 10))
        assert len(result) == 1
        assert result[0].model == "late"

    def test_get_records_premium_only(self, db):
        records = [
            _make_record(is_premium=True),
            _make_record(model="free", multiplier=0, is_premium=False,
                         timestamp=datetime(2026, 2, 10, 13, 0)),
        ]
        db.store_records(records, "test.log")
        result = db.get_records(premium_only=True)
        assert len(result) == 1
        assert result[0].is_premium is True

    def test_token_fields_stored(self, db):
        r = _make_record(prompt_tokens=5000, completion_tokens=500,
                         cached_tokens=4000, duration_ms=3000, session_id="s1")
        db.store_records([r], "test.log")
        result = db.get_records()
        assert result[0].prompt_tokens == 5000
        assert result[0].completion_tokens == 500
        assert result[0].cached_tokens == 4000
        assert result[0].duration_ms == 3000
        assert result[0].session_id == "s1"


class TestParsedFiles:
    def test_is_file_parsed(self, db):
        assert db.is_file_parsed("test.log") is False
        db.store_records([_make_record()], "test.log")
        assert db.is_file_parsed("test.log") is True

    def test_parsed_file_count(self, db):
        assert db.get_parsed_file_count() == 0
        db.store_records([_make_record()], "file1.log")
        db.store_records([_make_record(model="m2", timestamp=datetime(2026, 2, 11))], "file2.log")
        assert db.get_parsed_file_count() == 2


class TestSessions:
    def test_store_sessions(self, db):
        sessions = [_make_session(), _make_session(session_id="sess-2")]
        stored = db.store_sessions(sessions)
        assert stored == 2

    def test_get_sessions(self, db):
        db.store_sessions([_make_session()])
        result = db.get_sessions()
        assert len(result) == 1
        s = result[0]
        assert s.session_id == "sess-1"
        assert s.total_turns == 10
        assert s.total_calls == 5
        assert "claude-opus-4.6" in s.models_used

    def test_get_sessions_date_filter(self, db):
        db.store_sessions([
            _make_session(session_id="early", start_time=datetime(2026, 2, 1)),
            _make_session(session_id="late", start_time=datetime(2026, 2, 20)),
        ])
        result = db.get_sessions(start=datetime(2026, 2, 15))
        assert len(result) == 1
        assert result[0].session_id == "late"

    def test_session_upsert(self, db):
        db.store_sessions([_make_session(total_turns=5)])
        db.store_sessions([_make_session(total_turns=15)])
        result = db.get_sessions()
        assert len(result) == 1
        assert result[0].total_turns == 15  # updated


class TestClear:
    def test_clear(self, db):
        db.store_records([_make_record()], "test.log")
        db.store_sessions([_make_session()])
        assert db.get_record_count() > 0
        db.clear()
        assert db.get_record_count() == 0
        assert db.get_parsed_file_count() == 0
        assert len(db.get_sessions()) == 0


class TestMigration:
    def test_opens_existing_db(self, tmp_path):
        """Verify schema migration works on a fresh DB opened twice."""
        db1 = UsageDB(db_path=tmp_path / "migrate.db")
        db1.store_records([_make_record(prompt_tokens=100)], "f.log")
        db1.close()

        db2 = UsageDB(db_path=tmp_path / "migrate.db")
        records = db2.get_records()
        assert records[0].prompt_tokens == 100
        db2.close()
