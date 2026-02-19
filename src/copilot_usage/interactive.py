"""Interactive REPL mode with /commands and inline command picker."""

from __future__ import annotations

import msvcrt
import os
import sys

from rich.console import Console
from rich.table import Table
from rich.text import Text

from .config import config_exists, get_log_dir, get_multipliers_from_config, get_plan_from_config, load_config
from .dashboard import render_dashboard, render_sessions, render_status_line, render_tokens
from .log_parser import get_log_files, parse_log_file, parse_sessions
from .onboarding import run_onboarding
from .plans import DEFAULT_MULTIPLIERS, PLANS
from .storage import UsageDB

console = Console()

COMMANDS = {
    "/dashboard": "Show the full usage dashboard",
    "/status": "Quick one-line usage summary",
    "/tokens": "Show token usage and response latency",
    "/sessions": "Show session lifecycle overview",
    "/scan": "Re-parse Copilot CLI logs",
    "/setup": "Re-run plan & settings configuration",
    "/plan": "Show current plan details",
    "/models": "Show model multiplier table",
    "/help": "List available commands",
    "/quit": "Exit the app",
}

COMMAND_LIST = list(COMMANDS.keys())
SHORTCUT_MAP = {
    "/d": "/dashboard", "/s": "/status", "/p": "/plan",
    "/m": "/models", "/t": "/tokens", "/q": "/quit", "/?": "/help",
    "/exit": "/quit",
}


def _read_command() -> str:
    """Read user input with inline command picker when '/' is typed."""
    if sys.platform != "win32":
        # Fallback for non-Windows
        return input("\n> ").strip().lower()

    sys.stdout.write("\n> ")
    sys.stdout.flush()
    buf = ""

    while True:
        ch = msvcrt.getwch()

        if ch == "\r":  # Enter
            sys.stdout.write("\n")
            sys.stdout.flush()
            return buf.strip().lower()

        if ch == "\x03":  # Ctrl+C
            raise KeyboardInterrupt

        if ch == "\x04" or ch == "\x1a":  # Ctrl+D / Ctrl+Z
            raise EOFError

        if ch == "\b":  # Backspace
            if buf:
                buf = buf[:-1]
                sys.stdout.write("\b \b")
                sys.stdout.flush()
                # If we erased back past /, clear any leftover menu
                if "/" not in buf:
                    _clear_menu_lines(len(COMMAND_LIST))
            continue

        # Regular character
        buf += ch
        sys.stdout.write(ch)
        sys.stdout.flush()

        # Show command picker when buffer starts with /
        if buf == "/":
            selected = _show_command_picker(buf)
            if selected:
                # Erase the partial "/" from the displayed line and show full command
                sys.stdout.write("\b \b")  # erase /
                sys.stdout.write(selected)
                sys.stdout.write("\n")
                sys.stdout.flush()
                return selected
            else:
                # User pressed Escape, keep the "/" and continue typing
                continue

    return buf.strip().lower()


def _show_command_picker(prefix: str) -> str | None:
    """Show an interactive command picker below the prompt. Returns selected command or None."""
    matches = COMMAND_LIST
    selected_idx = 0
    menu_height = len(matches)

    # Print blank lines to reserve space, then move back up
    sys.stdout.write("\n" * menu_height)
    sys.stdout.write(f"\033[{menu_height}A")
    sys.stdout.flush()

    _render_menu(matches, selected_idx, menu_height)

    while True:
        ch = msvcrt.getwch()

        if ch == "\r":  # Enter — pick the selected item
            _clear_menu(menu_height)
            return matches[selected_idx]

        if ch == "\x1b":  # Escape — cancel
            _clear_menu(menu_height)
            return None

        if ch in ("\x00", "\xe0"):  # Arrow key prefix on Windows
            arrow = msvcrt.getwch()
            if arrow == "H":  # Up
                selected_idx = (selected_idx - 1) % len(matches)
            elif arrow == "P":  # Down
                selected_idx = (selected_idx + 1) % len(matches)
            _render_menu(matches, selected_idx, menu_height)
            continue

        # User is typing to filter
        prefix += ch
        new_matches = [c for c in COMMAND_LIST if c.startswith(prefix)]
        if not new_matches:
            _clear_menu(menu_height)
            # Return partial input for normal processing
            sys.stdout.write(ch)
            sys.stdout.flush()
            buf = prefix
            while True:
                c2 = msvcrt.getwch()
                if c2 == "\r":
                    sys.stdout.write("\n")
                    sys.stdout.flush()
                    return buf.strip().lower() if buf.strip() else None
                if c2 == "\b" and buf:
                    buf = buf[:-1]
                    sys.stdout.write("\b \b")
                    sys.stdout.flush()
                    continue
                buf += c2
                sys.stdout.write(c2)
                sys.stdout.flush()
        elif len(new_matches) == 1:
            _clear_menu(menu_height)
            return new_matches[0]
        else:
            matches = new_matches
            selected_idx = 0
            _render_menu(matches, selected_idx, menu_height)


def _render_menu(items: list[str], selected: int, total_height: int) -> None:
    """Render the command picker menu below current cursor position."""
    # Save cursor position
    sys.stdout.write("\033[s")
    # Move to line below prompt
    sys.stdout.write("\n")

    for i in range(total_height):
        sys.stdout.write("\033[2K")  # clear entire line
        if i < len(items):
            cmd = items[i]
            desc = COMMANDS.get(cmd, "")
            if i == selected:
                sys.stdout.write(f"  \033[96m❯ {cmd:<14}\033[0m \033[2m{desc}\033[0m")
            else:
                sys.stdout.write(f"    {cmd:<14} \033[2m{desc}\033[0m")
        if i < total_height - 1:
            sys.stdout.write("\n")

    # Restore cursor to prompt line
    sys.stdout.write("\033[u")
    sys.stdout.flush()


def _clear_menu(total_height: int) -> None:
    """Clear all menu lines below the prompt."""
    sys.stdout.write("\033[s")  # save cursor
    sys.stdout.write("\n")
    for i in range(total_height):
        sys.stdout.write("\033[2K")  # clear line
        if i < total_height - 1:
            sys.stdout.write("\n")
    sys.stdout.write("\033[u")  # restore cursor
    sys.stdout.flush()


def _enable_vt_mode() -> None:
    """Enable ANSI/VT escape sequences on Windows console."""
    if sys.platform != "win32":
        return
    try:
        import ctypes
        kernel32 = ctypes.windll.kernel32
        handle = kernel32.GetStdHandle(-11)  # STD_OUTPUT_HANDLE
        mode = ctypes.c_ulong()
        kernel32.GetConsoleMode(handle, ctypes.byref(mode))
        kernel32.SetConsoleMode(handle, mode.value | 0x0004)  # ENABLE_VIRTUAL_TERMINAL_PROCESSING
    except Exception:
        pass


def run_interactive() -> None:
    """Run the interactive REPL loop."""
    _enable_vt_mode()
    console.print("[bold cyan]📊 Copilot Usage Tracker[/bold cyan]")
    console.print("[dim]Type / to see commands · Arrow keys to select · Enter to run[/dim]\n")

    # Auto-setup on first run
    if not config_exists():
        console.print("[yellow]No config found. Running first-time setup...[/yellow]\n")
        run_onboarding()

    # Auto-scan if no data
    config = load_config()
    db = UsageDB()
    if db.get_record_count() == 0:
        console.print("[yellow]No usage data. Scanning logs...[/yellow]\n")
        db.close()
        _do_scan(config)
    else:
        db.close()

    while True:
        try:
            cmd = _read_command()
        except (EOFError, KeyboardInterrupt):
            console.print("\n[dim]Goodbye![/dim]")
            break

        if not cmd:
            continue

        # Resolve shortcuts
        cmd = SHORTCUT_MAP.get(cmd, cmd)

        if cmd == "/quit" or cmd == "/exit" or cmd == "/q":
            console.print("[dim]Goodbye![/dim]")
            break
        elif cmd == "/help" or cmd == "/?":
            _do_help()
        elif cmd == "/dashboard" or cmd == "/d":
            _clear()
            _do_dashboard()
        elif cmd == "/status" or cmd == "/s":
            _do_status()
        elif cmd == "/scan":
            _do_scan()
        elif cmd == "/setup":
            run_onboarding()
        elif cmd == "/plan" or cmd == "/p":
            _do_plan()
        elif cmd == "/models" or cmd == "/m":
            _do_models()
        elif cmd == "/tokens" or cmd == "/t":
            _do_tokens()
        elif cmd == "/sessions":
            _do_sessions()
        else:
            console.print(f"[red]Unknown command: {cmd}[/red] — type [bold]/help[/bold] for options")


def _clear() -> None:
    os.system("cls" if os.name == "nt" else "clear")


def _do_help() -> None:
    table = Table(title="Available Commands", show_lines=True)
    table.add_column("Command", style="cyan bold")
    table.add_column("Shortcut", style="dim")
    table.add_column("Description")

    shortcuts = {
        "/dashboard": "/d", "/status": "/s", "/plan": "/p",
        "/models": "/m", "/tokens": "/t", "/quit": "/q", "/help": "/?",
    }

    for cmd, desc in COMMANDS.items():
        table.add_row(cmd, shortcuts.get(cmd, ""), desc)

    console.print(table)


def _do_dashboard() -> None:
    config = load_config()
    if not config:
        console.print("[red]No config. Run /setup first.[/red]")
        return

    db = UsageDB()
    if db.get_record_count() == 0:
        console.print("[yellow]No data. Run /scan first.[/yellow]")
        db.close()
        return

    records = db.get_records()
    sessions = db.get_sessions()
    db.close()
    render_dashboard(records, config, sessions)


def _do_status() -> None:
    config = load_config()
    if not config:
        console.print("[red]No config. Run /setup first.[/red]")
        return

    db = UsageDB()
    if db.get_record_count() == 0:
        console.print("[yellow]No data. Run /scan first.[/yellow]")
        db.close()
        return

    records = db.get_records()
    db.close()
    render_status_line(records, config)


def _do_scan(config: dict | None = None) -> None:
    config = config or load_config()
    if not config:
        console.print("[red]No config. Run /setup first.[/red]")
        return

    log_dir = get_log_dir(config)
    db = UsageDB()

    log_files = get_log_files(log_dir)
    if not log_files:
        console.print(f"[red]No log files found in {log_dir}[/red]")
        return

    new_files = 0
    total_records = 0
    total_sessions = 0

    with console.status("[cyan]Scanning...[/cyan]") as status:
        for log_file in log_files:
            if db.is_file_parsed(log_file.name):
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

    console.print(f"[green]✓ Scanned {new_files} new files, {total_records} records, {total_sessions} sessions[/green]")
    console.print(f"  Total: {db.get_record_count()} records from {db.get_parsed_file_count()} files")
    db.close()


def _do_plan() -> None:
    config = load_config()
    if not config:
        console.print("[red]No config. Run /setup first.[/red]")
        return

    plan = get_plan_from_config(config)
    from .config import get_billing_cycle_day
    billing_day = get_billing_cycle_day(config)

    console.print(f"\n[bold]Current Plan:[/bold] [cyan]{plan.name}[/cyan]")
    console.print(f"  Price: ${plan.price_monthly:.0f}/mo")
    console.print(f"  Included premium requests: {plan.included_premium_reqs}")
    if plan.allows_overage:
        console.print(f"  Overage rate: ${plan.overage_rate}/req")
    else:
        console.print(f"  Overage: [red]Not allowed[/red]")
    console.print(f"  Billing cycle start day: {billing_day}")


def _do_models() -> None:
    config = load_config()
    multipliers = get_multipliers_from_config(config) if config else {}

    table = Table(title="Model Premium Request Multipliers", show_lines=True)
    table.add_column("Model", style="cyan")
    table.add_column("Default", justify="right")
    table.add_column("Active", justify="right", style="yellow bold")

    for m in DEFAULT_MULTIPLIERS:
        default_str = f"{m.multiplier}x" if m.multiplier > 0 else "0x (included)"
        active_val = multipliers.get(m.model_family, m.multiplier)
        active_str = f"{active_val}x" if active_val > 0 else "0x (included)"
        style = " [dim](overridden)[/dim]" if active_val != m.multiplier else ""
        table.add_row(m.display_name, default_str, f"{active_str}{style}")

    console.print(table)


def _do_tokens() -> None:
    db = UsageDB()
    if db.get_record_count() == 0:
        console.print("[yellow]No data. Run /scan first.[/yellow]")
        db.close()
        return
    records = db.get_records()
    db.close()
    render_tokens(records)


def _do_sessions() -> None:
    db = UsageDB()
    sessions = db.get_sessions()
    db.close()
    if not sessions:
        console.print("[yellow]No session data. Run /scan with --force to re-parse logs.[/yellow]")
        return
    render_sessions(sessions)
