"""Tests for data models."""

from datetime import datetime, timezone
from copilot_usage.models import Plan, UsageRecord, SpendSummary, DailyUsage, SessionRecord


class TestPlan:
    def test_label_free(self):
        p = Plan(name="Free", price_monthly=0, included_premium_reqs=50, overage_rate=0)
        assert p.label == "Free (Free)"

    def test_label_paid(self):
        p = Plan(name="Pro", price_monthly=10, included_premium_reqs=300, overage_rate=0.04)
        assert p.label == "Pro ($10/mo)"

    def test_label_enterprise(self):
        p = Plan(name="Enterprise", price_monthly=39, included_premium_reqs=1000, overage_rate=0.04)
        assert p.label == "Enterprise ($39/mo)"


class TestUsageRecord:
    def test_total_tokens(self):
        r = UsageRecord(timestamp=datetime.now(), model="m", multiplier=1, is_premium=True,
                        prompt_tokens=100, completion_tokens=50)
        assert r.total_tokens == 150

    def test_total_tokens_zero(self):
        r = UsageRecord(timestamp=datetime.now(), model="m", multiplier=1, is_premium=True)
        assert r.total_tokens == 0

    def test_cache_hit_rate(self):
        r = UsageRecord(timestamp=datetime.now(), model="m", multiplier=1, is_premium=True,
                        prompt_tokens=1000, cached_tokens=800)
        assert r.cache_hit_rate == 0.8

    def test_cache_hit_rate_no_prompts(self):
        r = UsageRecord(timestamp=datetime.now(), model="m", multiplier=1, is_premium=True,
                        prompt_tokens=0, cached_tokens=0)
        assert r.cache_hit_rate == 0.0

    def test_premium_requests_consumed_premium(self):
        r = UsageRecord(timestamp=datetime.now(), model="m", multiplier=6, is_premium=True)
        assert r.premium_requests_consumed == 6

    def test_premium_requests_consumed_not_premium(self):
        r = UsageRecord(timestamp=datetime.now(), model="m", multiplier=0, is_premium=False)
        assert r.premium_requests_consumed == 0.0


class TestSpendSummary:
    def _plan(self):
        return Plan(name="Pro", price_monthly=10, included_premium_reqs=300, overage_rate=0.04)

    def test_included_remaining(self):
        s = SpendSummary(plan=self._plan(), included_used=100)
        assert s.included_remaining == 200

    def test_included_remaining_over(self):
        s = SpendSummary(plan=self._plan(), included_used=500)
        assert s.included_remaining == 0

    def test_usage_percent(self):
        s = SpendSummary(plan=self._plan(), premium_requests_consumed=150)
        assert s.usage_percent == 50.0

    def test_usage_percent_capped(self):
        s = SpendSummary(plan=self._plan(), premium_requests_consumed=600)
        assert s.usage_percent == 100.0

    def test_usage_percent_zero_plan(self):
        p = Plan(name="X", price_monthly=0, included_premium_reqs=0, overage_rate=0)
        s = SpendSummary(plan=p, premium_requests_consumed=10)
        assert s.usage_percent == 100.0


class TestSessionRecord:
    def test_duration_seconds(self):
        s = SessionRecord(
            session_id="s1",
            start_time=datetime(2026, 2, 10, 10, 0, 0),
            end_time=datetime(2026, 2, 10, 10, 30, 0),
        )
        assert s.duration_seconds == 1800

    def test_duration_no_end(self):
        s = SessionRecord(session_id="s1", start_time=datetime(2026, 2, 10, 10, 0))
        assert s.duration_seconds == 0.0

    def test_avg_latency(self):
        s = SessionRecord(session_id="s1", start_time=datetime.now(),
                          total_calls=10, total_duration_ms=50000)
        assert s.avg_latency_ms == 5000.0

    def test_avg_latency_no_calls(self):
        s = SessionRecord(session_id="s1", start_time=datetime.now())
        assert s.avg_latency_ms == 0.0
