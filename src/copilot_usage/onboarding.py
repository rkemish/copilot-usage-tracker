"""Interactive onboarding flow for first-run setup."""

from __future__ import annotations

from rich.console import Console
from rich.prompt import IntPrompt, Prompt
from rich.table import Table

from .config import build_default_config, get_default_log_dir, save_config
from .plans import DEFAULT_MULTIPLIERS, PLANS

console = Console()


def run_onboarding() -> dict:
    """Run interactive setup and return the saved config dict."""
    console.print("\n[bold cyan]🚀 Copilot Usage Tracker — Setup[/bold cyan]\n")

    # Step 1: Select plan
    plan_key = _select_plan()

    # Step 2: Review multipliers
    _show_multipliers()
    overrides = _ask_multiplier_overrides()

    # Step 3: Billing cycle day
    billing_day = _ask_billing_cycle_day()

    # Step 4: Log directory
    log_dir = _ask_log_dir()

    # Build and save config
    config = build_default_config(plan_key, billing_day, log_dir)
    if overrides:
        config["multiplier_overrides"] = overrides
    save_config(config)

    plan = PLANS[plan_key]
    console.print(f"\n[bold green]✓ Config saved![/bold green]")
    console.print(f"  Plan: [cyan]{plan.name}[/cyan] (${plan.price_monthly}/mo, {plan.included_premium_reqs} premium reqs)")
    console.print(f"  Billing cycle day: [cyan]{billing_day}[/cyan]")
    console.print(f"  Log directory: [cyan]{log_dir}[/cyan]\n")

    return config


def _select_plan() -> str:
    """Prompt user to select a Copilot plan."""
    table = Table(title="Available Copilot Plans", show_lines=True)
    table.add_column("#", style="bold", width=3)
    table.add_column("Plan", style="cyan")
    table.add_column("Price/mo", justify="right")
    table.add_column("Premium Reqs", justify="right")
    table.add_column("Overage Rate", justify="right")

    plan_keys = list(PLANS.keys())
    for i, (key, plan) in enumerate(PLANS.items(), 1):
        price = "Free" if plan.price_monthly == 0 else f"${plan.price_monthly:.0f}"
        overage = "N/A" if not plan.allows_overage else f"${plan.overage_rate}/req"
        table.add_row(str(i), plan.name, price, str(plan.included_premium_reqs), overage)

    console.print(table)
    console.print()

    choice = IntPrompt.ask(
        "Select your plan number",
        choices=[str(i) for i in range(1, len(plan_keys) + 1)],
        default=2,  # Pro
    )
    return plan_keys[choice - 1]


def _show_multipliers() -> None:
    """Display the model multiplier table."""
    console.print()
    table = Table(title="Model Premium Request Multipliers", show_lines=True)
    table.add_column("Model", style="cyan")
    table.add_column("Multiplier", justify="right", style="yellow")

    for m in DEFAULT_MULTIPLIERS:
        mult_str = f"{m.multiplier}x" if m.multiplier > 0 else "0x (included)"
        table.add_row(m.display_name, mult_str)

    console.print(table)


def _ask_multiplier_overrides() -> dict:
    """Ask if user wants to override any multipliers."""
    console.print()
    override = Prompt.ask(
        "Override any multipliers? (enter model=value pairs, comma-separated, or 'no')",
        default="no",
    )
    if override.lower() in ("no", "n", ""):
        return {}

    overrides = {}
    for pair in override.split(","):
        pair = pair.strip()
        if "=" in pair:
            model, val = pair.split("=", 1)
            try:
                overrides[model.strip()] = float(val.strip())
            except ValueError:
                console.print(f"[yellow]Skipping invalid: {pair}[/yellow]")
    return overrides


def _ask_billing_cycle_day() -> int:
    """Ask for billing cycle start day."""
    console.print()
    return IntPrompt.ask("Billing cycle start day (1-28)", default=1)


def _ask_log_dir() -> str:
    """Ask for Copilot CLI log directory."""
    default = get_default_log_dir()
    console.print()
    return Prompt.ask("Copilot CLI log directory", default=default)
