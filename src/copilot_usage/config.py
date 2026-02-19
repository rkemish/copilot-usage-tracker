"""Load, save, and validate user configuration."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

import yaml

from .models import Plan
from .plans import DEFAULT_MULTIPLIERS, PLANS, get_multiplier_map

CONFIG_DIR = Path.home() / ".copilot-usage"
CONFIG_FILE = CONFIG_DIR / "config.yaml"
DB_FILE = CONFIG_DIR / "usage.db"


def get_default_log_dir() -> str:
    """Return the default Copilot CLI log directory."""
    return str(Path.home() / ".copilot" / "logs")


def config_exists() -> bool:
    return CONFIG_FILE.exists()


def load_config() -> dict:
    """Load config from YAML file. Returns empty dict if not found."""
    if not CONFIG_FILE.exists():
        return {}
    with open(CONFIG_FILE, "r") as f:
        return yaml.safe_load(f) or {}


def save_config(config: dict) -> None:
    """Save config to YAML file, creating directory if needed."""
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    with open(CONFIG_FILE, "w") as f:
        yaml.dump(config, f, default_flow_style=False, sort_keys=False)


def get_plan_from_config(config: dict) -> Plan:
    """Get the Plan object for the configured plan key."""
    plan_key = config.get("plan", "pro")
    return PLANS.get(plan_key, PLANS["pro"])


def get_multipliers_from_config(config: dict) -> dict[str, float]:
    """Get model multiplier map from config, falling back to defaults.

    Returns dict of model_family -> multiplier value.
    """
    base = {m.model_family: m.multiplier for m in DEFAULT_MULTIPLIERS}
    overrides = config.get("multiplier_overrides", {})
    base.update(overrides)
    return base


def get_log_dir(config: dict) -> str:
    """Get log directory from config, falling back to default."""
    return config.get("log_dir", get_default_log_dir())


def get_billing_cycle_day(config: dict) -> int:
    """Get billing cycle start day (1-28). Defaults to 1."""
    return config.get("billing_cycle_day", 1)


def build_default_config(plan_key: str = "pro", billing_cycle_day: int = 1,
                         log_dir: str | None = None) -> dict:
    """Build a default config dict."""
    return {
        "plan": plan_key,
        "billing_cycle_day": billing_cycle_day,
        "log_dir": log_dir or get_default_log_dir(),
        "multiplier_overrides": {},
    }
