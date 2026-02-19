"""Tests for the dashboard rendering (smoke tests — verify no crashes)."""

from datetime import datetime
from io import StringIO
from unittest.mock import patch

from rich.console import Console

from copilot_usage.dashboard import (
    render_dashboard,
    render_sessions,
    render_status_line,
    render_tokens,
)
from copilot_usage.models import Plan, SessionRecord, UsageRecord


def _plan():
    return Plan(name="Pro", price_monthly=10, included_premium_reqs=300, overage_rate=0.04)


def _config():
    return {"plan": "pro", "billing_cycle_day": 1}


def _records():
    base = datetime(2026, 2, 10, 12, 0)
    return [
        UsageRecord(timestamp=base, model="claude-opus-4.6", multiplier=6, is_premium=True,
                    prompt_tokens=50000, completion_tokens=1000, cached_tokens=40000,
                    duration_ms=5000, session_id="s1"),
        UsageRecord(timestamp=base, model="gpt-5-mini", multiplier=0, is_premium=False,
                    prompt_tokens=10000, completion_tokens=500, duration_ms=2000),
        UsageRecord(timestamp=base, model="claude-haiku-4.5", multiplier=0.33, is_premium=True,
                    prompt_tokens=20000, completion_tokens=800, cached_tokens=15000,
                    duration_ms=3000, session_id="s1"),
    ]


def _sessions():
    return [
        SessionRecord(
            session_id="s1",
            start_time=datetime(2026, 2, 10, 10, 0),
            end_time=datetime(2026, 2, 10, 11, 30),
            models_used=["claude-opus-4.6", "claude-haiku-4.5"],
            total_turns=20,
            total_calls=15,
            total_prompt_tokens=70000,
            total_completion_tokens=1800,
            total_cached_tokens=55000,
            total_duration_ms=45000,
            source_file="test.log",
        ),
    ]


def _capture(fn, *args, **kwargs):
    """Run a dashboard function and capture its output."""
    import copilot_usage.dashboard as d
    c = Console(file=StringIO(), width=120, force_terminal=True)
    old = d.console
    d.console = c
    try:
        fn(*args, **kwargs)
    finally:
        d.console = old
    return c.file.getvalue()


class TestDashboardRenders:
    def test_render_dashboard(self):
        output = _capture(render_dashboard, _records(), _config(), _sessions())
        assert "Copilot Usage Summary" in output
        assert "Usage by Model" in output

    def test_render_dashboard_no_sessions(self):
        output = _capture(render_dashboard, _records(), _config())
        assert "Copilot Usage Summary" in output

    def test_render_dashboard_empty_records(self):
        output = _capture(render_dashboard, [], _config())
        assert "Copilot Usage Summary" in output

    def test_render_status_line(self):
        output = _capture(render_status_line, _records(), _config())
        assert "Pro" in output

    def test_render_tokens(self):
        output = _capture(render_tokens, _records())
        assert "Token Usage" in output
        assert "Latency" in output

    def test_render_tokens_no_data(self):
        empty = [UsageRecord(timestamp=datetime.now(), model="m", multiplier=1, is_premium=True)]
        output = _capture(render_tokens, empty)
        # No crash, may be empty since no token data
        assert isinstance(output, str)

    def test_render_sessions(self):
        output = _capture(render_sessions, _sessions())
        assert "Session Overview" in output

    def test_render_sessions_empty(self):
        output = _capture(render_sessions, [])
        assert isinstance(output, str)
