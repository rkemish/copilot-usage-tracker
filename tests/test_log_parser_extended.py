"""Tests for log parser — token, latency, and session extraction."""

import tempfile
from datetime import datetime
from pathlib import Path

from copilot_usage.log_parser import parse_log_file, parse_sessions, parse_log_directory, get_log_files

SAMPLE_LOG_WITH_TELEMETRY = """\
2026-02-19T11:25:48.762Z [DEBUG] Using model: claude-opus-4.6
2026-02-19T11:25:49.000Z [DEBUG] PremiumRequestProcessor: Setting X-Initiator to 'user'
2026-02-19T11:25:49.313Z [DEBUG] Got model info: {
  "billing": {
    "is_premium": true,
    "multiplier": 6
  },
  "capabilities": {
    "family": "claude-opus-4.6",
    "limits": {
      "max_context_window_tokens": 200000,
      "max_output_tokens": 64000
    }
  }
}
2026-02-19T11:25:52.000Z [Telemetry] cli.model_call:
{
  "model": "claude-opus-4.6",
  "prompt_tokens_count": 85000,
  "completion_tokens_count": 1200,
  "cached_tokens_count": 70000,
  "duration_ms": 5400,
  "session_id": "sess-abc-123"
}
"""

SAMPLE_SESSION_LOG = """\
2026-02-19T10:00:00.000Z [DEBUG] {"kind": "session_start", "session_id": "sess-001"}
2026-02-19T10:00:01.000Z [DEBUG] "session_id": "sess-001"
2026-02-19T10:05:00.000Z [DEBUG] {"kind": "assistant_turn_end", "turn_id": "t1"}
2026-02-19T10:05:00.100Z [DEBUG] "session_id": "sess-001"
2026-02-19T10:10:00.000Z [DEBUG] {"kind": "assistant_turn_end", "turn_id": "t2"}
2026-02-19T10:10:00.100Z [DEBUG] "session_id": "sess-001"
2026-02-19T10:15:00.000Z [Telemetry] cli.model_call:
{
  "model": "claude-opus-4.6",
  "prompt_tokens_count": 5000,
  "completion_tokens_count": 300,
  "cached_tokens_count": 4000,
  "duration_ms": 2000,
  "session_id": "sess-001"
}
2026-02-19T10:30:00.000Z [DEBUG] End of log
"""


def _write_log(content):
    f = tempfile.NamedTemporaryFile(mode="w", suffix=".log", delete=False, prefix="process-")
    f.write(content)
    f.flush()
    f.close()
    return f.name


class TestTokenExtraction:
    def test_extracts_tokens_from_telemetry(self):
        path = _write_log(SAMPLE_LOG_WITH_TELEMETRY)
        records = parse_log_file(path)
        Path(path).unlink()

        assert len(records) == 1
        r = records[0]
        assert r.model == "claude-opus-4.6"
        assert r.prompt_tokens == 85000
        assert r.completion_tokens == 1200
        assert r.cached_tokens == 70000
        assert r.duration_ms == 5400
        assert r.session_id == "sess-abc-123"

    def test_records_without_telemetry_have_zero_tokens(self):
        log = """\
2026-02-19T11:25:49.313Z [DEBUG] Got model info: {
  "billing": {"is_premium": true, "multiplier": 1},
  "capabilities": {"family": "claude-sonnet-4.6"}
}
"""
        path = _write_log(log)
        records = parse_log_file(path)
        Path(path).unlink()

        assert len(records) == 1
        assert records[0].prompt_tokens == 0
        assert records[0].duration_ms == 0


class TestSessionParsing:
    def test_parses_session(self):
        path = _write_log(SAMPLE_SESSION_LOG)
        sessions = parse_sessions(path)
        Path(path).unlink()

        assert len(sessions) >= 1
        s = sessions[0]
        assert s.session_id == "sess-001"
        assert s.total_turns >= 2
        assert s.total_calls >= 1
        assert s.total_prompt_tokens == 5000
        assert s.total_completion_tokens == 300

    def test_no_sessions_in_empty_log(self):
        path = _write_log("2026-02-19T10:00:00.000Z [DEBUG] Nothing here\n")
        sessions = parse_sessions(path)
        Path(path).unlink()
        assert sessions == []

    def test_session_nonexistent_file(self):
        assert parse_sessions("/nonexistent/path.log") == []


class TestLogDirectory:
    def test_parse_directory(self, tmp_path):
        log1 = tmp_path / "process-001.log"
        log1.write_text("""\
2026-02-19T11:00:00.000Z [DEBUG] Got model info: {
  "billing": {"is_premium": true, "multiplier": 1},
  "capabilities": {"family": "model-a"}
}
""")
        log2 = tmp_path / "process-002.log"
        log2.write_text("""\
2026-02-19T12:00:00.000Z [DEBUG] Got model info: {
  "billing": {"is_premium": false, "multiplier": 0},
  "capabilities": {"family": "model-b"}
}
""")
        records = parse_log_directory(tmp_path)
        assert len(records) == 2
        assert records[0].timestamp < records[1].timestamp

    def test_parse_empty_directory(self, tmp_path):
        assert parse_log_directory(tmp_path) == []

    def test_parse_nonexistent_directory(self):
        assert parse_log_directory("/nonexistent/dir") == []


class TestGetLogFiles:
    def test_lists_process_logs(self, tmp_path):
        (tmp_path / "process-1.log").write_text("x")
        (tmp_path / "process-2.log").write_text("x")
        (tmp_path / "other.txt").write_text("x")
        files = get_log_files(tmp_path)
        assert len(files) == 2

    def test_nonexistent_dir(self):
        assert get_log_files("/nonexistent") == []
