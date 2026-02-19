"""Tests for the spend calculator."""

from datetime import datetime

from copilot_usage.calculator import calculate_spend, calculate_daily_usage, get_billing_period
from copilot_usage.models import Plan, UsageRecord


def _make_plan():
    return Plan(name="Pro", price_monthly=10, included_premium_reqs=300, overage_rate=0.04)


def _make_records():
    base = datetime(2026, 2, 10, 12, 0, 0)
    return [
        UsageRecord(timestamp=base, model="claude-opus-4.6", multiplier=6, is_premium=True),
        UsageRecord(timestamp=base, model="claude-opus-4.6", multiplier=6, is_premium=True),
        UsageRecord(timestamp=base, model="gpt-5-mini", multiplier=0, is_premium=False),
        UsageRecord(timestamp=base, model="claude-haiku-4.5", multiplier=0.33, is_premium=True),
        UsageRecord(timestamp=base, model="claude-sonnet-4.6", multiplier=1, is_premium=True),
    ]


def test_calculate_spend_basic():
    plan = _make_plan()
    records = _make_records()
    multipliers = {
        "claude-opus-4.6": 6,
        "gpt-5-mini": 0,
        "claude-haiku-4.5": 0.33,
        "claude-sonnet-4.6": 1,
    }
    summary = calculate_spend(records, plan, multipliers)

    assert summary.total_calls == 5
    assert summary.premium_calls == 4
    # 6 + 6 + 0.33 + 1 = 13.33
    assert abs(summary.premium_requests_consumed - 13.33) < 0.01
    assert summary.included_used == 13.33
    assert summary.overage_requests == 0
    assert summary.overage_cost == 0
    assert summary.total_estimated_spend == 10  # just plan cost


def test_calculate_spend_with_overage():
    plan = Plan(name="Free", price_monthly=0, included_premium_reqs=5, overage_rate=0.04)
    records = _make_records()
    multipliers = {"claude-opus-4.6": 6, "claude-haiku-4.5": 0.33, "claude-sonnet-4.6": 1}
    summary = calculate_spend(records, plan, multipliers)

    assert summary.premium_requests_consumed > 5
    assert summary.overage_requests > 0
    expected_overage = summary.premium_requests_consumed - 5
    assert abs(summary.overage_requests - expected_overage) < 0.01
    assert abs(summary.overage_cost - expected_overage * 0.04) < 0.01


def test_billing_period():
    ref = datetime(2026, 2, 15)
    start, end = get_billing_period(1, ref)
    assert start.day == 1
    assert start.month == 2
    assert end.month == 3

    # Mid-month cycle
    start2, end2 = get_billing_period(15, ref)
    assert start2.day == 15
    assert start2.month == 2


def test_daily_usage():
    records = _make_records()
    multipliers = {"claude-opus-4.6": 6, "claude-haiku-4.5": 0.33, "claude-sonnet-4.6": 1}
    daily = calculate_daily_usage(records, multipliers)

    assert len(daily) == 1  # all same day
    assert daily[0].total_calls == 5
    assert daily[0].premium_calls == 4


def test_usage_percent():
    plan = _make_plan()
    records = _make_records()
    multipliers = {"claude-opus-4.6": 6, "claude-haiku-4.5": 0.33, "claude-sonnet-4.6": 1}
    summary = calculate_spend(records, plan, multipliers)
    assert summary.usage_percent < 10  # 13.33 / 300 = ~4.4%


if __name__ == "__main__":
    test_calculate_spend_basic()
    test_calculate_spend_with_overage()
    test_billing_period()
    test_daily_usage()
    test_usage_percent()
    print("All calculator tests passed!")
