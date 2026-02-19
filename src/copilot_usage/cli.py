"""CLI entry point for copilot-usage."""

from __future__ import annotations

import click
from rich.console import Console

from .config import config_exists, get_log_dir, load_config
from .dashboard import render_dashboard, render_status_line
from .log_parser import get_log_files, parse_log_file, parse_sessions
from .onboarding import run_onboarding
from .storage import UsageDB

console = Console()


@click.group(invoke_without_command=True)
@click.pass_context
def main(ctx):
    """Copilot Usage Tracker — visualize your GitHub Copilot premium request usage and spend."""
    if ctx.invoked_subcommand is None:
        from .interactive import run_interactive
        run_interactive()


@main.command()
def setup():
    """Run interactive setup to configure your plan and preferences."""
    run_onboarding()
    console.print("\n[dim]Run [bold]copilot-usage scan[/bold] to parse your logs, then [bold]copilot-usage[/bold] to see the dashboard.[/dim]")


@main.command()
@click.option("--force", is_flag=True, help="Re-parse all logs (clear cache first)")
def scan(force: bool):
    """Scan Copilot CLI logs and store usage data."""
    config = load_config()
    if not config:
        console.print("[red]No config found. Run 'copilot-usage setup' first.[/red]")
        return

    log_dir = get_log_dir(config)
    db = UsageDB()

    if force:
        db.clear()
        console.print("[yellow]Cleared cached data. Re-scanning all logs...[/yellow]")

    log_files = get_log_files(log_dir)
    if not log_files:
        console.print(f"[red]No log files found in {log_dir}[/red]")
        return

    new_files = 0
    total_records = 0
    total_sessions = 0

    with console.status("[cyan]Scanning log files...[/cyan]") as status:
        for log_file in log_files:
            if not force and db.is_file_parsed(log_file.name):
                continue

            status.update(f"[cyan]Parsing {log_file.name}...[/cyan]")
            records = parse_log_file(log_file)
            sessions = parse_sessions(log_file)
            if records:
                db.store_records(records, log_file.name)
                total_records += len(records)
            if sessions:
                db.store_sessions(sessions)
                total_sessions += len(sessions)
            new_files += 1

    console.print(f"[green]✓ Scanned {new_files} new log files, found {total_records} usage records, {total_sessions} sessions[/green]")
    console.print(f"  Total in database: {db.get_record_count()} records from {db.get_parsed_file_count()} files")
    db.close()


@main.command()
def dashboard():
    """Show the usage dashboard (default command)."""
    config = load_config()
    if not config:
        console.print("[red]No config found. Run 'copilot-usage setup' first.[/red]")
        return

    db = UsageDB()
    record_count = db.get_record_count()

    if record_count == 0:
        console.print("[yellow]No usage data found. Run 'copilot-usage scan' to parse your logs.[/yellow]")
        db.close()
        return

    records = db.get_records()
    sessions = db.get_sessions()
    db.close()

    render_dashboard(records, config, sessions)


@main.command()
def status():
    """Show a quick one-line usage status."""
    config = load_config()
    if not config:
        console.print("[red]No config found. Run 'copilot-usage setup' first.[/red]")
        return

    db = UsageDB()
    if db.get_record_count() == 0:
        console.print("[yellow]No data. Run 'copilot-usage scan' first.[/yellow]")
        db.close()
        return

    records = db.get_records()
    db.close()
    render_status_line(records, config)


if __name__ == "__main__":
    main()
