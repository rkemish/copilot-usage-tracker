"""Spend calculation engine — compute premium request usage and costs."""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timedelta
from typing import Optional

from .config import get_billing_cycle_day, get_multipliers_from_config, get_plan_from_config
from .models import DailyUsage, Plan, SpendSummary, UsageRecord


def calculate_spend(records: list[UsageRecord], plan: Plan,
                    multipliers: dict[str, float]) -> SpendSummary:
    """Calculate spend summary for a list of usage records.

    Records are processed in chronological order. The first requests consume
    the included allowance; once exhausted, subsequent requests are overage
    and billed at the plan's overage rate. Per-model cost reflects only the
    overage portion each model actually incurred.
    """
    # Sort chronologically so included quota is consumed by earliest requests
    sorted_records = sorted(records, key=lambda r: r.timestamp)

    summary = SpendSummary(plan=plan)
    summary.plan_cost = plan.price_monthly
    model_breakdown: dict[str, dict] = defaultdict(
        lambda: {"calls": 0, "premium_reqs": 0.0, "overage_reqs": 0.0,
                 "overage_cost": 0.0, "display_name": ""}
    )

    remaining_included = float(plan.included_premium_reqs)

    for record in sorted_records:
        summary.total_calls += 1

        if not record.is_premium:
            continue

        summary.premium_calls += 1

        # Use config multiplier if available, else fall back to log multiplier
        mult = multipliers.get(record.model, record.multiplier)

        summary.premium_requests_consumed += mult

        entry = model_breakdown[record.model]
        entry["calls"] += 1
        entry["premium_reqs"] += mult
        entry["display_name"] = record.model

        # Determine how much of this request is covered vs overage
        if remaining_included >= mult:
            # Fully covered by included allowance
            remaining_included -= mult
        elif remaining_included > 0:
            # Partially covered — the remainder is overage
            overage_portion = mult - remaining_included
            remaining_included = 0
            if plan.allows_overage:
                entry["overage_reqs"] += overage_portion
                entry["overage_cost"] += overage_portion * plan.overage_rate
        else:
            # Entirely overage
            if plan.allows_overage:
                entry["overage_reqs"] += mult
                entry["overage_cost"] += mult * plan.overage_rate

    summary.included_used = min(summary.premium_requests_consumed,
                                plan.included_premium_reqs)
    summary.overage_requests = max(0,
        summary.premium_requests_consumed - plan.included_premium_reqs)
    if plan.allows_overage:
        summary.overage_cost = summary.overage_requests * plan.overage_rate
    summary.total_estimated_spend = plan.price_monthly + summary.overage_cost
    summary.model_breakdown = dict(model_breakdown)

    return summary


def calculate_daily_usage(records: list[UsageRecord],
                          multipliers: dict[str, float]) -> list[DailyUsage]:
    """Group usage records by day and calculate daily aggregates."""
    daily: dict[str, DailyUsage] = {}

    for record in records:
        day_key = record.timestamp.strftime("%Y-%m-%d")
        if day_key not in daily:
            daily[day_key] = DailyUsage(
                date=record.timestamp.replace(hour=0, minute=0, second=0, microsecond=0)
            )

        d = daily[day_key]
        d.total_calls += 1

        if record.is_premium:
            d.premium_calls += 1
            mult = multipliers.get(record.model, record.multiplier)
            d.premium_requests_consumed += mult

            models = d.models_used
            if record.model not in models:
                models[record.model] = {"calls": 0, "premium_reqs": 0.0}
            models[record.model]["calls"] += 1
            models[record.model]["premium_reqs"] += mult

    return sorted(daily.values(), key=lambda d: d.date)


def get_billing_period(billing_cycle_day: int,
                       reference_date: datetime | None = None) -> tuple[datetime, datetime]:
    """Calculate the current billing period start and end dates."""
    ref = reference_date or datetime.now()
    year, month = ref.year, ref.month

    start_day = min(billing_cycle_day, 28)
    if ref.day >= start_day:
        start = ref.replace(day=start_day, hour=0, minute=0, second=0, microsecond=0)
    else:
        # Go to previous month
        if month == 1:
            start = ref.replace(year=year - 1, month=12, day=start_day,
                                hour=0, minute=0, second=0, microsecond=0)
        else:
            start = ref.replace(month=month - 1, day=start_day,
                                hour=0, minute=0, second=0, microsecond=0)

    # End is start + ~1 month
    if start.month == 12:
        end = start.replace(year=start.year + 1, month=1)
    else:
        end = start.replace(month=start.month + 1)

    return start, end


def get_week_ranges(start: datetime, end: datetime) -> list[tuple[datetime, datetime]]:
    """Split a date range into week-sized chunks."""
    weeks = []
    current = start
    while current < end:
        week_end = min(current + timedelta(days=7), end)
        weeks.append((current, week_end))
        current = week_end
    return weeks
