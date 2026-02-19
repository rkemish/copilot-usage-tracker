"""Tests for the log parser."""

import tempfile
from datetime import datetime
from pathlib import Path

from copilot_usage.log_parser import parse_log_file

SAMPLE_LOG = """\
2026-02-19T11:25:48.762Z [DEBUG] Using model: claude-opus-4.6-1m
2026-02-19T11:25:49.313Z [DEBUG] Successfully listed 39 models
2026-02-19T11:25:49.313Z [DEBUG] Got model info: {
  "billing": {
    "is_premium": true,
    "multiplier": 6,
    "restricted_to": [
      "pro",
      "edu",
      "pro_plus",
      "business",
      "enterprise"
    ]
  },
  "capabilities": {
    "family": "claude-opus-4.6-1m",
    "limits": {
      "max_context_window_tokens": 1000000,
      "max_output_tokens": 64000
    }
  }
}
2026-02-19T11:25:50.095Z [DEBUG] PremiumRequestProcessor: Setting X-Initiator to 'user'
2026-02-19T11:25:50.111Z [DEBUG] Using model: gpt-5-mini
2026-02-19T11:25:50.111Z [DEBUG] Got model info: {
  "billing": {
    "is_premium": false,
    "multiplier": 0
  },
  "capabilities": {
    "family": "gpt-5-mini",
    "limits": {
      "max_context_window_tokens": 264000,
      "max_output_tokens": 64000
    }
  }
}
2026-02-19T11:26:16.082Z [DEBUG] Using model: claude-haiku-4.5
2026-02-19T11:26:16.234Z [DEBUG] Got model info: {
  "billing": {
    "is_premium": true,
    "multiplier": 0.33
  },
  "capabilities": {
    "family": "claude-haiku-4.5",
    "limits": {
      "max_context_window_tokens": 200000,
      "max_output_tokens": 8192
    }
  }
}
"""


def test_parse_log_file_extracts_records():
    with tempfile.NamedTemporaryFile(mode="w", suffix=".log", delete=False) as f:
        f.write(SAMPLE_LOG)
        f.flush()

        records = parse_log_file(f.name)

    assert len(records) == 3

    # First: claude-opus-4.6-1m, premium, multiplier 6
    r0 = records[0]
    assert r0.model == "claude-opus-4.6-1m"
    assert r0.is_premium is True
    assert r0.multiplier == 6
    assert r0.timestamp.year == 2026

    # Second: gpt-5-mini, not premium
    r1 = records[1]
    assert r1.model == "gpt-5-mini"
    assert r1.is_premium is False
    assert r1.multiplier == 0

    # Third: claude-haiku-4.5, premium, multiplier 0.33
    r2 = records[2]
    assert r2.model == "claude-haiku-4.5"
    assert r2.is_premium is True
    assert r2.multiplier == 0.33

    Path(f.name).unlink()


def test_parse_nonexistent_file():
    records = parse_log_file("/nonexistent/path.log")
    assert records == []


def test_premium_requests_consumed():
    with tempfile.NamedTemporaryFile(mode="w", suffix=".log", delete=False) as f:
        f.write(SAMPLE_LOG)
        f.flush()
        records = parse_log_file(f.name)

    premium = [r for r in records if r.is_premium]
    assert len(premium) == 2
    total = sum(r.premium_requests_consumed for r in records)
    assert abs(total - 6.33) < 0.01  # 6 + 0.33

    Path(f.name).unlink()


if __name__ == "__main__":
    test_parse_log_file_extracts_records()
    test_parse_nonexistent_file()
    test_premium_requests_consumed()
    print("All log parser tests passed!")
