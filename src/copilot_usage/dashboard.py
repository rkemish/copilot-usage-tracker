"""Rich terminal dashboard for visualizing Copilot usage and spend."""

from __future__ import annotations

from datetime import datetime

from rich.bar import Bar
from rich.console import Console, Group
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from .calculator import (
    calculate_daily_usage,
    calculate_spend,
    get_billing_period,
    get_week_ranges,
)
from .config import (
    get_billing_cycle_day,
    get_log_dir,
    get_multipliers_from_config,
    get_plan_from_config,
)
from .models import DailyUsage, Plan, SessionRecord, SpendSummary, UsageRecord

console = Console()


def render_dashboard(records: list[UsageRecord], config: dict,
                     sessions: list[SessionRecord] | None = None) -> None:
    """Render the full dashboard."""
    plan = get_plan_from_config(config)
    multipliers = get_multipliers_from_config(config)
    billing_day = get_billing_cycle_day(config)

    # Current billing period
    now = datetime.now()
    period_start, period_end = get_billing_period(billing_day, now)

    # Filter records to current billing period
    period_records = [
        r for r in records
        if period_start <= r.timestamp.replace(tzinfo=None) < period_end
    ]

    summary = calculate_spend(period_records, plan, multipliers)
    daily = calculate_daily_usage(period_records, multipliers)

    console.print()
    _render_summary_panel(summary, period_start, period_end, now)
    console.print()
    _render_model_breakdown(summary)
    console.print()
    _render_token_panel(period_records)
    console.print()
    _render_latency_panel(period_records)
    console.print()
    if sessions:
        period_sessions = [
            s for s in sessions
            if period_start <= s.start_time.replace(tzinfo=None) < period_end
        ]
        if period_sessions:
            _render_session_panel(period_sessions)
            console.print()
    _render_weekly_view(daily, summary, period_start, period_end)
    console.print()
    _render_daily_table(daily, plan, multipliers)
    console.print()


def render_status_line(records: list[UsageRecord], config: dict) -> None:
    """Render a single-line status summary."""
    plan = get_plan_from_config(config)
    multipliers = get_multipliers_from_config(config)
    billing_day = get_billing_cycle_day(config)

    now = datetime.now()
    period_start, period_end = get_billing_period(billing_day, now)
    period_records = [
        r for r in records
        if period_start <= r.timestamp.replace(tzinfo=None) < period_end
    ]
    summary = calculate_spend(period_records, plan, multipliers)

    used = summary.premium_requests_consumed
    total = plan.included_premium_reqs
    pct = summary.usage_percent

    status_color = "green" if pct < 70 else "yellow" if pct < 90 else "red"
    overage_str = ""
    if summary.overage_requests > 0:
        overage_str = f" | [red]Overage: {summary.overage_requests:.0f} reqs (${summary.overage_cost:.2f})[/red]"

    console.print(
        f"[bold]{plan.name}[/bold] │ "
        f"[{status_color}]{used:.0f}/{total} premium reqs ({pct:.0f}%)[/{status_color}]"
        f"{overage_str} │ "
        f"Est. spend: [bold]${summary.total_estimated_spend:.2f}[/bold] │ "
        f"Period: {period_start.strftime('%b %d')} – {period_end.strftime('%b %d')}"
    )


def _render_summary_panel(summary: SpendSummary, period_start: datetime,
                          period_end: datetime, now: datetime) -> None:
    """Render the main summary panel."""
    plan = summary.plan
    days_total = (period_end - period_start).days
    days_elapsed = (now - period_start).days
    days_remaining = max(0, days_total - days_elapsed)

    # Usage bar
    pct = summary.usage_percent
    bar_color = "green" if pct < 70 else "yellow" if pct < 90 else "red"

    lines = []
    lines.append(f"[bold]Plan:[/bold] {plan.name} (${plan.price_monthly:.0f}/mo)")
    lines.append(f"[bold]Period:[/bold] {period_start.strftime('%b %d')} – {period_end.strftime('%b %d')} ({days_elapsed}d elapsed, {days_remaining}d remaining)")
    lines.append("")
    lines.append(f"[bold]Premium Requests:[/bold] [{bar_color}]{summary.premium_requests_consumed:.0f}[/{bar_color}] / {plan.included_premium_reqs} ({pct:.0f}%)")

    # Simple ASCII progress bar
    bar_width = 40
    filled = int(bar_width * min(pct, 100) / 100)
    bar = f"[{bar_color}]{'█' * filled}{'░' * (bar_width - filled)}[/{bar_color}]"
    lines.append(f"  {bar}")

    lines.append("")
    lines.append(f"[bold]Total API Calls:[/bold] {summary.total_calls} ({summary.premium_calls} premium)")
    lines.append(f"[bold]Remaining:[/bold] {summary.included_remaining:.0f} premium requests")

    if summary.overage_requests > 0:
        lines.append(f"[bold red]Overage:[/bold red] {summary.overage_requests:.0f} requests × ${plan.overage_rate} = [red]${summary.overage_cost:.2f}[/red]")

    lines.append("")
    lines.append(f"[bold]Estimated Spend:[/bold] [{'red' if summary.overage_cost > 0 else 'green'}]${summary.total_estimated_spend:.2f}[/{'red' if summary.overage_cost > 0 else 'green'}]")

    panel = Panel(
        "\n".join(lines),
        title="[bold cyan]📊 Copilot Usage Summary[/bold cyan]",
        border_style="cyan",
    )
    console.print(panel)


def _render_model_breakdown(summary: SpendSummary) -> None:
    """Render per-model usage table."""
    if not summary.model_breakdown:
        return

    table = Table(title="📋 Usage by Model", show_lines=True)
    table.add_column("Model", style="cyan")
    table.add_column("Calls", justify="right")
    table.add_column("Premium Reqs", justify="right", style="yellow")
    table.add_column("% of Total", justify="right")
    table.add_column("Est. Cost", justify="right", style="green")

    total_premium = summary.premium_requests_consumed or 1

    sorted_models = sorted(
        summary.model_breakdown.items(),
        key=lambda x: x[1]["premium_reqs"],
        reverse=True,
    )

    for model, data in sorted_models:
        pct = (data["premium_reqs"] / total_premium) * 100
        cost = data.get("overage_cost", 0)
        table.add_row(
            data["display_name"] or model,
            str(data["calls"]),
            f"{data['premium_reqs']:.1f}",
            f"{pct:.1f}%",
            f"${cost:.2f}" if cost > 0 else "-",
        )

    # Totals row
    table.add_row(
        "[bold]Total[/bold]",
        f"[bold]{summary.premium_calls}[/bold]",
        f"[bold]{summary.premium_requests_consumed:.1f}[/bold]",
        "[bold]100%[/bold]",
        f"[bold]${summary.overage_cost:.2f}[/bold]" if summary.overage_cost > 0 else "[bold]-[/bold]",
    )

    console.print(table)


def _render_weekly_view(daily: list[DailyUsage], summary: SpendSummary,
                        period_start: datetime, period_end: datetime) -> None:
    """Render weekly usage bars."""
    if not daily:
        return

    weeks = get_week_ranges(period_start, period_end)
    table = Table(title="📅 Weekly Breakdown", show_lines=True)
    table.add_column("Week", style="cyan")
    table.add_column("Calls", justify="right")
    table.add_column("Premium Reqs", justify="right", style="yellow")
    table.add_column("Usage", min_width=25)

    max_reqs = max((d.premium_requests_consumed for d in daily), default=1)
    weekly_max = max_reqs * 7  # scale

    for i, (ws, we) in enumerate(weeks, 1):
        week_daily = [d for d in daily if ws <= d.date.replace(tzinfo=None) < we]
        calls = sum(d.total_calls for d in week_daily)
        premium = sum(d.premium_requests_consumed for d in week_daily)

        bar_width = 20
        filled = int(bar_width * premium / weekly_max) if weekly_max > 0 else 0
        bar = f"[yellow]{'█' * filled}{'░' * (bar_width - filled)}[/yellow] {premium:.0f}"

        table.add_row(
            f"Wk {i} ({ws.strftime('%b %d')})",
            str(calls),
            f"{premium:.0f}",
            bar,
        )

    console.print(table)


def _render_daily_table(daily: list[DailyUsage], plan: Plan,
                        multipliers: dict[str, float]) -> None:
    """Render daily usage table for the last 14 days."""
    if not daily:
        return

    recent = daily[-14:]  # last 14 days

    table = Table(title="📆 Recent Daily Usage (last 14 days)", show_lines=True)
    table.add_column("Date", style="cyan")
    table.add_column("Calls", justify="right")
    table.add_column("Premium", justify="right")
    table.add_column("Reqs Used", justify="right", style="yellow")
    table.add_column("Bar", min_width=20)

    max_reqs = max((d.premium_requests_consumed for d in recent), default=1) or 1

    for d in recent:
        bar_width = 15
        filled = int(bar_width * d.premium_requests_consumed / max_reqs)
        bar = f"[yellow]{'█' * filled}{'░' * (bar_width - filled)}[/yellow]"

        table.add_row(
            d.date.strftime("%b %d (%a)"),
            str(d.total_calls),
            str(d.premium_calls),
            f"{d.premium_requests_consumed:.1f}",
            bar,
        )

    console.print(table)


def _format_tokens(n: int) -> str:
    """Format token counts with K/M suffixes."""
    if n >= 1_000_000:
        return f"{n / 1_000_000:.1f}M"
    if n >= 1_000:
        return f"{n / 1_000:.1f}K"
    return str(n)


def _render_token_panel(records: list[UsageRecord]) -> None:
    """Render token usage summary and per-model breakdown."""
    records_with_tokens = [r for r in records if r.prompt_tokens > 0 or r.completion_tokens > 0]
    if not records_with_tokens:
        return

    total_prompt = sum(r.prompt_tokens for r in records_with_tokens)
    total_completion = sum(r.completion_tokens for r in records_with_tokens)
    total_cached = sum(r.cached_tokens for r in records_with_tokens)
    total_all = total_prompt + total_completion
    cache_rate = (total_cached / total_prompt * 100) if total_prompt > 0 else 0

    lines = []
    lines.append(f"[bold]Prompt Tokens:[/bold]     {_format_tokens(total_prompt)}")
    lines.append(f"[bold]Completion Tokens:[/bold] {_format_tokens(total_completion)}")
    lines.append(f"[bold]Cached Tokens:[/bold]     {_format_tokens(total_cached)} ({cache_rate:.0f}% cache hit rate)")
    lines.append(f"[bold]Total Tokens:[/bold]      {_format_tokens(total_all)}")
    lines.append(f"[bold]Calls w/ Data:[/bold]     {len(records_with_tokens)}/{len(records)}")

    panel = Panel(
        "\n".join(lines),
        title="[bold magenta]🔤 Token Usage[/bold magenta]",
        border_style="magenta",
    )
    console.print(panel)

    model_tokens: dict[str, dict] = {}
    for r in records_with_tokens:
        if r.model not in model_tokens:
            model_tokens[r.model] = {"prompt": 0, "completion": 0, "cached": 0, "calls": 0}
        model_tokens[r.model]["prompt"] += r.prompt_tokens
        model_tokens[r.model]["completion"] += r.completion_tokens
        model_tokens[r.model]["cached"] += r.cached_tokens
        model_tokens[r.model]["calls"] += 1

    table = Table(title="Token Usage by Model", show_lines=True)
    table.add_column("Model", style="cyan")
    table.add_column("Calls", justify="right")
    table.add_column("Prompt", justify="right")
    table.add_column("Completion", justify="right")
    table.add_column("Cached", justify="right", style="dim")
    table.add_column("Avg/Call", justify="right", style="yellow")

    for model, data in sorted(model_tokens.items(), key=lambda x: x[1]["prompt"], reverse=True):
        avg = (data["prompt"] + data["completion"]) / data["calls"]
        table.add_row(
            model, str(data["calls"]),
            _format_tokens(data["prompt"]),
            _format_tokens(data["completion"]),
            _format_tokens(data["cached"]),
            _format_tokens(int(avg)),
        )

    console.print(table)


def _render_latency_panel(records: list[UsageRecord]) -> None:
    """Render response latency statistics per model."""
    records_with_latency = [r for r in records if r.duration_ms > 0]
    if not records_with_latency:
        return

    model_latency: dict[str, list[int]] = {}
    for r in records_with_latency:
        model_latency.setdefault(r.model, []).append(r.duration_ms)

    table = Table(title="⚡ Response Latency by Model", show_lines=True)
    table.add_column("Model", style="cyan")
    table.add_column("Calls", justify="right")
    table.add_column("Avg", justify="right", style="yellow")
    table.add_column("Min", justify="right", style="green")
    table.add_column("Max", justify="right", style="red")
    table.add_column("P50", justify="right")
    table.add_column("P95", justify="right")

    def _fmt_ms(ms: float) -> str:
        if ms >= 60_000:
            return f"{ms / 60_000:.1f}m"
        if ms >= 1_000:
            return f"{ms / 1_000:.1f}s"
        return f"{ms:.0f}ms"

    def _percentile(data: list[int], p: float) -> int:
        s = sorted(data)
        k = (len(s) - 1) * p / 100
        f = int(k)
        c = f + 1 if f + 1 < len(s) else f
        return int(s[f] + (k - f) * (s[c] - s[f]))

    for model, latencies in sorted(model_latency.items(),
                                     key=lambda x: sum(x[1]) / len(x[1]),
                                     reverse=True):
        avg = sum(latencies) / len(latencies)
        table.add_row(
            model, str(len(latencies)),
            _fmt_ms(avg),
            _fmt_ms(min(latencies)),
            _fmt_ms(max(latencies)),
            _fmt_ms(_percentile(latencies, 50)),
            _fmt_ms(_percentile(latencies, 95)),
        )

    all_latencies = [r.duration_ms for r in records_with_latency]
    avg_all = sum(all_latencies) / len(all_latencies)
    table.add_row(
        "[bold]Overall[/bold]", f"[bold]{len(all_latencies)}[/bold]",
        f"[bold]{_fmt_ms(avg_all)}[/bold]",
        f"[bold]{_fmt_ms(min(all_latencies))}[/bold]",
        f"[bold]{_fmt_ms(max(all_latencies))}[/bold]",
        f"[bold]{_fmt_ms(_percentile(all_latencies, 50))}[/bold]",
        f"[bold]{_fmt_ms(_percentile(all_latencies, 95))}[/bold]",
    )

    console.print(table)


def _render_session_panel(sessions: list[SessionRecord]) -> None:
    """Render session lifecycle summary."""
    if not sessions:
        return

    total = len(sessions)
    total_turns = sum(s.total_turns for s in sessions)
    total_calls = sum(s.total_calls for s in sessions)
    durations = []
    for s in sessions:
        if s.end_time:
            dur = (s.end_time - s.start_time).total_seconds()
            if dur > 0:
                durations.append(dur)

    avg_dur = sum(durations) / len(durations) if durations else 0
    avg_turns = total_turns / total if total else 0
    all_models = set()
    for s in sessions:
        all_models.update(s.models_used)

    def _fmt_dur(secs: float) -> str:
        if secs >= 3600:
            return f"{secs / 3600:.1f}h"
        if secs >= 60:
            return f"{secs / 60:.0f}m"
        return f"{secs:.0f}s"

    lines = []
    lines.append(f"[bold]Sessions:[/bold]          {total}")
    lines.append(f"[bold]Total Turns:[/bold]       {total_turns}")
    lines.append(f"[bold]Total Model Calls:[/bold] {total_calls}")
    lines.append(f"[bold]Avg Duration:[/bold]      {_fmt_dur(avg_dur)}")
    lines.append(f"[bold]Avg Turns/Session:[/bold] {avg_turns:.1f}")
    lines.append(f"[bold]Models Used:[/bold]       {', '.join(sorted(all_models)) if all_models else 'N/A'}")

    panel = Panel(
        "\n".join(lines),
        title="[bold blue]🔄 Session Overview[/bold blue]",
        border_style="blue",
    )
    console.print(panel)

    recent = sorted(sessions, key=lambda s: s.start_time, reverse=True)[:10]
    table = Table(title="Recent Sessions (last 10)", show_lines=True)
    table.add_column("Start", style="cyan")
    table.add_column("Duration", justify="right")
    table.add_column("Turns", justify="right")
    table.add_column("Calls", justify="right")
    table.add_column("Models", style="dim")
    table.add_column("Tokens", justify="right", style="yellow")

    for s in recent:
        dur = ""
        if s.end_time:
            dur = _fmt_dur((s.end_time - s.start_time).total_seconds())
        tokens = s.total_prompt_tokens + s.total_completion_tokens
        table.add_row(
            s.start_time.strftime("%b %d %H:%M"),
            dur,
            str(s.total_turns),
            str(s.total_calls),
            ", ".join(s.models_used[:2]) + ("..." if len(s.models_used) > 2 else ""),
            _format_tokens(tokens),
        )

    console.print(table)


def render_tokens(records: list[UsageRecord]) -> None:
    """Standalone token/latency view."""
    _render_token_panel(records)
    console.print()
    _render_latency_panel(records)


def render_sessions(sessions: list[SessionRecord]) -> None:
    """Standalone session view."""
    _render_session_panel(sessions)
