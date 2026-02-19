"""Published GitHub Copilot plans and model multiplier pricing."""

from __future__ import annotations

from .models import ModelMultiplier, Plan

# ── Published Copilot Plans ──────────────────────────────────────────────────

PLANS: dict[str, Plan] = {
    "free": Plan(
        name="Free",
        price_monthly=0,
        included_premium_reqs=50,
        overage_rate=0,
        allows_overage=False,
    ),
    "pro": Plan(
        name="Pro",
        price_monthly=10,
        included_premium_reqs=300,
        overage_rate=0.04,
    ),
    "pro_plus": Plan(
        name="Pro+",
        price_monthly=39,
        included_premium_reqs=1500,
        overage_rate=0.04,
    ),
    "business": Plan(
        name="Business",
        price_monthly=19,
        included_premium_reqs=300,
        overage_rate=0.04,
    ),
    "enterprise": Plan(
        name="Enterprise",
        price_monthly=39,
        included_premium_reqs=1000,
        overage_rate=0.04,
    ),
}

# ── Published Model Multipliers ─────────────────────────────────────────────
# Maps model family strings (as they appear in logs) to their premium request
# multiplier. Models not listed here default to 1x if premium, 0x if not.

DEFAULT_MULTIPLIERS: list[ModelMultiplier] = [
    # Non-premium (0x) — included in all paid plans
    ModelMultiplier("gpt-4o", 0, "GPT-4o"),
    ModelMultiplier("gpt-4.1", 0, "GPT-4.1"),
    ModelMultiplier("gpt-5-mini", 0, "GPT-5-mini"),
    # Low multiplier
    ModelMultiplier("gemini-2.0-flash", 0.25, "Gemini 2.0 Flash"),
    ModelMultiplier("o3-mini", 0.33, "o3-mini"),
    ModelMultiplier("o4-mini", 0.33, "o4-mini"),
    # Standard (1x)
    ModelMultiplier("claude-3.5-sonnet", 1, "Claude 3.5 Sonnet"),
    ModelMultiplier("claude-3.7-sonnet", 1, "Claude 3.7 Sonnet"),
    ModelMultiplier("claude-sonnet-4", 1, "Claude Sonnet 4"),
    ModelMultiplier("claude-sonnet-4.5", 1, "Claude Sonnet 4.5"),
    ModelMultiplier("claude-sonnet-4.6", 1, "Claude Sonnet 4.6"),
    ModelMultiplier("gemini-2.0-pro", 1, "Gemini 2.0 Pro"),
    ModelMultiplier("gemini-2.5-pro", 1, "Gemini 2.5 Pro"),
    ModelMultiplier("gemini-3-pro-preview", 1, "Gemini 3 Pro (Preview)"),
    ModelMultiplier("gpt-5.1", 1, "GPT-5.1"),
    ModelMultiplier("gpt-5.1-codex", 1, "GPT-5.1 Codex"),
    ModelMultiplier("gpt-5.1-codex-mini", 1, "GPT-5.1 Codex Mini"),
    ModelMultiplier("gpt-5.2", 1, "GPT-5.2"),
    ModelMultiplier("gpt-5.2-codex", 1, "GPT-5.2 Codex"),
    ModelMultiplier("gpt-5.3-codex", 1, "GPT-5.3 Codex"),
    # Above standard
    ModelMultiplier("claude-3.7-sonnet-thinking", 1.25, "Claude 3.7 Thinking"),
    # High multiplier
    ModelMultiplier("spark", 4, "Spark"),
    ModelMultiplier("claude-opus-4", 10, "Claude Opus 4"),
    ModelMultiplier("claude-opus-4.5", 10, "Claude Opus 4.5"),
    ModelMultiplier("claude-opus-4.6", 6, "Claude Opus 4.6"),
    ModelMultiplier("claude-opus-4.6-fast", 6, "Claude Opus 4.6 (fast)"),
    ModelMultiplier("claude-opus-4.6-1m", 6, "Claude Opus 4.6 (1M)"),
    ModelMultiplier("gpt-5.1-codex-max", 5, "GPT-5.1 Codex Max"),
    ModelMultiplier("claude-haiku-4.5", 0.33, "Claude Haiku 4.5"),
    # Very high
    ModelMultiplier("gpt-4.5", 50, "GPT-4.5"),
]


def get_multiplier_map() -> dict[str, ModelMultiplier]:
    """Return a dict mapping model family → ModelMultiplier."""
    return {m.model_family: m for m in DEFAULT_MULTIPLIERS}


def get_plan(plan_key: str) -> Plan:
    """Get a plan by key, raising KeyError if not found."""
    return PLANS[plan_key]
