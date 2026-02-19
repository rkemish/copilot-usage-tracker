"""Data models for Copilot usage tracking."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional


@dataclass
class Plan:
    """A GitHub Copilot subscription plan."""

    name: str
    price_monthly: float
    included_premium_reqs: int
    overage_rate: float  # cost per overage premium request
    allows_overage: bool = True

    @property
    def label(self) -> str:
        if self.price_monthly == 0:
            return f"{self.name} (Free)"
        return f"{self.name} (${self.price_monthly:.0f}/mo)"


@dataclass
class ModelMultiplier:
    """Premium request multiplier for a specific model family."""

    model_family: str  # e.g. "claude-opus-4.6"
    multiplier: float  # e.g. 6.0
    display_name: str = ""  # human-friendly name

    def __post_init__(self):
        if not self.display_name:
            self.display_name = self.model_family


@dataclass
class UsageRecord:
    """A single Copilot model invocation parsed from logs."""

    timestamp: datetime
    model: str  # model family from logs
    multiplier: float  # multiplier from logs
    is_premium: bool
    initiator: str = "user"  # "user" or "agent"
    source_file: str = ""  # log file this was parsed from
    prompt_tokens: int = 0
    completion_tokens: int = 0
    cached_tokens: int = 0
    duration_ms: int = 0
    session_id: str = ""

    @property
    def total_tokens(self) -> int:
        return self.prompt_tokens + self.completion_tokens

    @property
    def cache_hit_rate(self) -> float:
        if self.prompt_tokens == 0:
            return 0.0
        return self.cached_tokens / self.prompt_tokens

    @property
    def premium_requests_consumed(self) -> float:
        """Premium requests consumed by this invocation using its log multiplier."""
        if not self.is_premium:
            return 0.0
        return self.multiplier


@dataclass
class SpendSummary:
    """Calculated spend for a date range."""

    plan: Plan
    total_calls: int = 0
    premium_calls: int = 0
    premium_requests_consumed: float = 0.0  # after multiplier
    included_used: float = 0.0
    overage_requests: float = 0.0
    overage_cost: float = 0.0
    plan_cost: float = 0.0
    total_estimated_spend: float = 0.0
    model_breakdown: dict = field(default_factory=dict)

    @property
    def included_remaining(self) -> float:
        return max(0, self.plan.included_premium_reqs - self.included_used)

    @property
    def usage_percent(self) -> float:
        if self.plan.included_premium_reqs == 0:
            return 100.0
        return min(100.0, (self.premium_requests_consumed / self.plan.included_premium_reqs) * 100)


@dataclass
class DailyUsage:
    """Aggregated usage for a single day."""

    date: datetime
    total_calls: int = 0
    premium_calls: int = 0
    premium_requests_consumed: float = 0.0
    estimated_cost: float = 0.0
    models_used: dict = field(default_factory=dict)


@dataclass
class SessionRecord:
    """A Copilot CLI session parsed from logs."""

    session_id: str
    start_time: datetime
    end_time: Optional[datetime] = None
    models_used: list = field(default_factory=list)
    total_turns: int = 0
    total_calls: int = 0
    total_prompt_tokens: int = 0
    total_completion_tokens: int = 0
    total_cached_tokens: int = 0
    total_duration_ms: int = 0
    source_file: str = ""

    @property
    def duration_seconds(self) -> float:
        if not self.end_time:
            return 0.0
        return (self.end_time - self.start_time).total_seconds()

    @property
    def avg_latency_ms(self) -> float:
        if self.total_calls == 0:
            return 0.0
        return self.total_duration_ms / self.total_calls
