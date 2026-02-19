"""Extended calculator tests for edge cases and week ranges."""

from datetime import datetime

from copilot_usage.calculator import (
    calculate_spend,
    calculate_daily_usage,
    get_billing_period,
    get_week_ranges,
)
from copilot_usage.models import Plan, UsageRecord


def _plan(**overrides):
    defaults = dict(name="Pro", price_monthly=10, included_premium_reqs=300, overage_rate=0.04)
    defaults.update(overrides)
    return Plan(**defaults)


def _record(ts=None, model="opus", mult=6, premium=True):
    return UsageRecord(
        timestamp=ts or datetime(2026, 2, 10, 12, 0),
        model=model, multiplier=mult, is_premium=premium,
    )


class TestBillingPeriod:
    def test_start_of_month(self):
        s, e = get_billing_period(1, datetime(2026, 3, 15))
        assert s == datetime(2026, 3, 1)
        assert e == datetime(2026, 4, 1)

    def test_mid_month_before_day(self):
        s, e = get_billing_period(20, datetime(2026, 2, 10))
        assert s == datetime(2026, 1, 20)
        assert e == datetime(2026, 2, 20)

    def test_mid_month_after_day(self):
        s, e = get_billing_period(5, datetime(2026, 2, 10))
        assert s == datetime(2026, 2, 5)
        assert e == datetime(2026, 3, 5)

    def test_january_rollback(self):
        s, e = get_billing_period(15, datetime(2026, 1, 5))
        assert s.month == 12
        assert s.year == 2025

    def test_december_forward(self):
        s, e = get_billing_period(1, datetime(2026, 12, 15))
        assert s == datetime(2026, 12, 1)
        assert e == datetime(2027, 1, 1)


class TestWeekRanges:
    def test_full_month(self):
        start = datetime(2026, 2, 1)
        end = datetime(2026, 3, 1)
        weeks = get_week_ranges(start, end)
        assert len(weeks) == 4
        assert weeks[0][0] == start
        assert weeks[-1][1] == end

    def test_partial_week(self):
        start = datetime(2026, 2, 1)
        end = datetime(2026, 2, 10)
        weeks = get_week_ranges(start, end)
        assert len(weeks) == 2
        assert weeks[-1][1] == end


class TestChronologicalOverage:
    def test_no_overage_within_quota(self):
        plan = _plan(included_premium_reqs=100)
        records = [_record(mult=6)] * 10  # 60 reqs total
        m = {"opus": 6}
        summary = calculate_spend(records, plan, m)
        assert summary.overage_requests == 0
        assert summary.overage_cost == 0

    def test_overage_attributed_to_later_calls(self):
        plan = _plan(included_premium_reqs=10)
        ts1 = datetime(2026, 2, 10, 10, 0)
        ts2 = datetime(2026, 2, 10, 11, 0)
        ts3 = datetime(2026, 2, 10, 12, 0)
        records = [
            _record(ts=ts1, mult=6),   # 6 reqs, 4 remaining
            _record(ts=ts2, mult=6),   # 6 reqs, overage 2
            _record(ts=ts3, mult=6),   # 6 reqs, overage 6
        ]
        m = {"opus": 6}
        summary = calculate_spend(records, plan, m)
        assert summary.premium_requests_consumed == 18
        assert summary.included_used == 10
        assert summary.overage_requests == 8
        assert abs(summary.overage_cost - 8 * 0.04) < 0.01

    def test_no_overage_for_free_models(self):
        plan = _plan(included_premium_reqs=5)
        records = [
            _record(model="free", mult=0, premium=False),
            _record(model="free", mult=0, premium=False),
        ]
        m = {"free": 0}
        summary = calculate_spend(records, plan, m)
        assert summary.overage_requests == 0

    def test_model_breakdown_populated(self):
        plan = _plan(included_premium_reqs=100)
        records = [
            _record(model="a", mult=6),
            _record(model="b", mult=1),
        ]
        m = {"a": 6, "b": 1}
        summary = calculate_spend(records, plan, m)
        assert "a" in summary.model_breakdown
        assert "b" in summary.model_breakdown
        assert summary.model_breakdown["a"]["calls"] == 1
        assert summary.model_breakdown["a"]["premium_reqs"] == 6

    def test_empty_records(self):
        plan = _plan()
        summary = calculate_spend([], plan, {})
        assert summary.total_calls == 0
        assert summary.total_estimated_spend == 10  # just plan cost


class TestDailyUsage:
    def test_multiple_days(self):
        records = [
            _record(ts=datetime(2026, 2, 10, 10, 0)),
            _record(ts=datetime(2026, 2, 10, 11, 0)),
            _record(ts=datetime(2026, 2, 11, 10, 0), model="haiku", mult=0.33),
        ]
        m = {"opus": 6, "haiku": 0.33}
        daily = calculate_daily_usage(records, m)
        assert len(daily) == 2
        assert daily[0].total_calls == 2
        assert daily[1].total_calls == 1

    def test_empty_records(self):
        daily = calculate_daily_usage([], {})
        assert daily == []
