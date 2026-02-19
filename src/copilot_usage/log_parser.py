"""Parse Copilot CLI process log files for model usage data."""

from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path
from typing import Generator

from .models import SessionRecord, UsageRecord

# Regex patterns for log parsing
RE_TIMESTAMP = re.compile(r"^(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d+Z)")
RE_USING_MODEL = re.compile(r"Using model:\s*(\S+)")
RE_MODEL_INFO_START = re.compile(r"Got model info:\s*\{")
RE_INITIATOR = re.compile(r"PremiumRequestProcessor: Setting X-Initiator to '(\w+)'")
RE_MODEL_CALL = re.compile(r'\[Telemetry\] cli\.model_call:')
RE_SESSION_START = re.compile(r'"kind":\s*"session_start"')
RE_TURN_END = re.compile(r'"kind":\s*"assistant_turn_end"')
RE_SESSION_ID = re.compile(r'"session_id":\s*"([^"]+)"')


def parse_log_file(filepath: str | Path) -> list[UsageRecord]:
    """Parse a single Copilot CLI log file and extract usage records."""
    filepath = Path(filepath)
    if not filepath.exists():
        return []

    lines = filepath.read_text(encoding="utf-8", errors="replace").splitlines()
    records: list[UsageRecord] = []
    # Collect model_call telemetry for token/latency data, keyed by approximate timestamp
    model_calls: list[dict] = []

    # First pass: extract cli.model_call telemetry blocks
    i = 0
    while i < len(lines):
        if RE_MODEL_CALL.search(lines[i]):
            timestamp = _extract_timestamp(lines[i])
            block = _extract_json_block(lines, i + 1)  # JSON starts on next line
            if block and timestamp:
                block["_timestamp"] = timestamp
                model_calls.append(block)
        i += 1

    # Build lookup: map (timestamp_second, model) -> model_call data
    call_lookup: dict[str, dict] = {}
    for mc in model_calls:
        ts = mc["_timestamp"]
        model = mc.get("model", "")
        # Key by second-level timestamp + model for matching
        key = f"{ts.strftime('%Y-%m-%dT%H:%M')}-{model}"
        call_lookup[key] = mc

    # Second pass: extract Got model info blocks (existing logic) and enrich with tokens
    i = 0
    while i < len(lines):
        line = lines[i]

        if "Got model info:" in line:
            timestamp = _extract_timestamp(line)
            model_info = _extract_json_block(lines, i)
            if model_info and timestamp:
                model_name = _find_recent_model_name(lines, i)
                initiator = _find_recent_initiator(lines, i)
                session_id = _find_recent_session_id(lines, i)

                billing = model_info.get("billing", {})
                capabilities = model_info.get("capabilities", {})
                family = capabilities.get("family", model_name or "unknown")

                # Try to find matching model_call for token/latency data
                lookup_key = f"{timestamp.strftime('%Y-%m-%dT%H:%M')}-{family}"
                mc = call_lookup.get(lookup_key, {})

                record = UsageRecord(
                    timestamp=timestamp,
                    model=family,
                    multiplier=billing.get("multiplier", 0),
                    is_premium=billing.get("is_premium", False),
                    initiator=initiator or "user",
                    source_file=filepath.name,
                    prompt_tokens=mc.get("prompt_tokens_count", 0),
                    completion_tokens=mc.get("completion_tokens_count", 0),
                    cached_tokens=mc.get("cached_tokens_count", 0),
                    duration_ms=mc.get("duration_ms", 0),
                    session_id=session_id or mc.get("session_id", ""),
                )
                records.append(record)
        i += 1

    # For records that didn't match via minute-level key, try sequential matching
    _enrich_unmatched_records(records, model_calls)

    return records


def parse_sessions(filepath: str | Path) -> list[SessionRecord]:
    """Parse session lifecycle events from a log file."""
    filepath = Path(filepath)
    if not filepath.exists():
        return []

    lines = filepath.read_text(encoding="utf-8", errors="replace").splitlines()
    sessions: dict[str, SessionRecord] = {}
    last_timestamp: datetime | None = None

    for i, line in enumerate(lines):
        ts = _extract_timestamp(line)
        if ts:
            last_timestamp = ts

        # Session start
        if RE_SESSION_START.search(line):
            sid_match = _find_nearby_field(lines, i, "session_id", 20)
            if sid_match and last_timestamp:
                sessions[sid_match] = SessionRecord(
                    session_id=sid_match,
                    start_time=last_timestamp,
                    source_file=filepath.name,
                )

        # Turn end — count turns
        if RE_TURN_END.search(line):
            sid_match = _find_nearby_field(lines, i, "session_id", 20)
            if sid_match and sid_match in sessions:
                sessions[sid_match].total_turns += 1

        # Model call — aggregate tokens
        if RE_MODEL_CALL.search(line):
            block = _extract_json_block(lines, i + 1)
            if block:
                sid = block.get("session_id", "")
                if sid in sessions:
                    s = sessions[sid]
                    s.total_calls += 1
                    s.total_prompt_tokens += block.get("prompt_tokens_count", 0)
                    s.total_completion_tokens += block.get("completion_tokens_count", 0)
                    s.total_cached_tokens += block.get("cached_tokens_count", 0)
                    s.total_duration_ms += block.get("duration_ms", 0)
                    model = block.get("model", "unknown")
                    if model not in s.models_used:
                        s.models_used.append(model)
                    if ts:
                        s.end_time = ts  # keep updating to last seen

    # Set end_time to last timestamp for sessions that didn't get one
    for s in sessions.values():
        if not s.end_time and last_timestamp:
            s.end_time = last_timestamp

    return list(sessions.values())


def _enrich_unmatched_records(records: list[UsageRecord],
                              model_calls: list[dict]) -> None:
    """Try to match remaining model_calls to records that have no token data."""
    used_indices: set[int] = set()
    for record in records:
        if record.prompt_tokens > 0:
            continue  # already matched
        # Find closest model_call by timestamp and model
        best_idx = -1
        best_delta = float("inf")
        for idx, mc in enumerate(model_calls):
            if idx in used_indices:
                continue
            if mc.get("model", "") != record.model:
                continue
            delta = abs((mc["_timestamp"] - record.timestamp).total_seconds())
            if delta < best_delta and delta < 5:  # within 5 seconds
                best_delta = delta
                best_idx = idx
        if best_idx >= 0:
            mc = model_calls[best_idx]
            record.prompt_tokens = mc.get("prompt_tokens_count", 0)
            record.completion_tokens = mc.get("completion_tokens_count", 0)
            record.cached_tokens = mc.get("cached_tokens_count", 0)
            record.duration_ms = mc.get("duration_ms", 0)
            if not record.session_id:
                record.session_id = mc.get("session_id", "")
            used_indices.add(best_idx)


def parse_log_directory(log_dir: str | Path) -> list[UsageRecord]:
    """Parse all process log files in a directory."""
    log_dir = Path(log_dir)
    if not log_dir.exists():
        return []

    all_records: list[UsageRecord] = []
    for log_file in sorted(log_dir.glob("process-*.log")):
        records = parse_log_file(log_file)
        all_records.extend(records)

    return sorted(all_records, key=lambda r: r.timestamp)


def get_log_files(log_dir: str | Path) -> list[Path]:
    """List all process log files in a directory."""
    log_dir = Path(log_dir)
    if not log_dir.exists():
        return []
    return sorted(log_dir.glob("process-*.log"))


def _extract_timestamp(line: str) -> datetime | None:
    """Extract ISO timestamp from a log line."""
    match = RE_TIMESTAMP.match(line)
    if match:
        ts_str = match.group(1)
        try:
            return datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
        except ValueError:
            return None
    return None


def _extract_json_block(lines: list[str], start_idx: int) -> dict | None:
    """Extract a multi-line JSON block starting from a line containing '{'."""
    if start_idx >= len(lines):
        return None
    first_line = lines[start_idx]
    json_start = first_line.find("{")
    if json_start == -1:
        return None

    json_lines = [first_line[json_start:]]
    brace_count = json_lines[0].count("{") - json_lines[0].count("}")

    i = start_idx + 1
    while i < len(lines) and brace_count > 0:
        line = lines[i]
        if RE_TIMESTAMP.match(line) and "{" not in line:
            break
        json_lines.append(line)
        brace_count += line.count("{") - line.count("}")
        i += 1

    json_str = "\n".join(json_lines)
    try:
        return json.loads(json_str)
    except json.JSONDecodeError:
        return None


def _find_recent_model_name(lines: list[str], before_idx: int) -> str | None:
    """Look backwards from before_idx for the most recent 'Using model:' line."""
    search_start = max(0, before_idx - 10)
    for i in range(before_idx - 1, search_start - 1, -1):
        match = RE_USING_MODEL.search(lines[i])
        if match:
            return match.group(1)
    return None


def _find_recent_initiator(lines: list[str], before_idx: int) -> str | None:
    """Look backwards for the most recent PremiumRequestProcessor initiator."""
    search_start = max(0, before_idx - 20)
    for i in range(before_idx - 1, search_start - 1, -1):
        match = RE_INITIATOR.search(lines[i])
        if match:
            return match.group(1)
    return None


def _find_recent_session_id(lines: list[str], around_idx: int) -> str | None:
    """Look nearby for a session_id field."""
    search_start = max(0, around_idx - 30)
    search_end = min(len(lines), around_idx + 30)
    for i in range(around_idx, search_start - 1, -1):
        match = RE_SESSION_ID.search(lines[i])
        if match:
            return match.group(1)
    return None


def _find_nearby_field(lines: list[str], around_idx: int,
                       field_name: str, window: int = 20) -> str | None:
    """Find a JSON field value near a given line index."""
    pattern = re.compile(rf'"{field_name}":\s*"([^"]+)"')
    for i in range(around_idx, min(len(lines), around_idx + window)):
        match = pattern.search(lines[i])
        if match:
            return match.group(1)
    return None
