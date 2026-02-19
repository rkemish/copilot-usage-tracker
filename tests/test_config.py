"""Tests for config module."""

import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

from copilot_usage.config import (
    build_default_config,
    config_exists,
    get_billing_cycle_day,
    get_log_dir,
    get_multipliers_from_config,
    get_plan_from_config,
    load_config,
    save_config,
)


class TestConfigExists:
    def test_exists_false(self, tmp_path):
        with patch("copilot_usage.config.CONFIG_FILE", tmp_path / "nope.yaml"):
            assert config_exists() is False

    def test_exists_true(self, tmp_path):
        cfg = tmp_path / "config.yaml"
        cfg.write_text("plan: pro\n")
        with patch("copilot_usage.config.CONFIG_FILE", cfg):
            assert config_exists() is True


class TestLoadSaveConfig:
    def test_load_missing(self, tmp_path):
        with patch("copilot_usage.config.CONFIG_FILE", tmp_path / "missing.yaml"):
            assert load_config() == {}

    def test_save_and_load(self, tmp_path):
        cfg_file = tmp_path / "config.yaml"
        with patch("copilot_usage.config.CONFIG_FILE", cfg_file):
            save_config({"plan": "enterprise", "billing_cycle_day": 15})
            loaded = load_config()
            assert loaded["plan"] == "enterprise"
            assert loaded["billing_cycle_day"] == 15

    def test_save_creates_directory(self, tmp_path):
        cfg_file = tmp_path / "subdir" / "config.yaml"
        with patch("copilot_usage.config.CONFIG_FILE", cfg_file), \
             patch("copilot_usage.config.CONFIG_DIR", tmp_path / "subdir"):
            save_config({"plan": "pro"})
            assert cfg_file.exists()


class TestGetPlanFromConfig:
    def test_default_plan(self):
        plan = get_plan_from_config({})
        assert plan.name == "Pro"

    def test_enterprise_plan(self):
        plan = get_plan_from_config({"plan": "enterprise"})
        assert plan.name == "Enterprise"

    def test_free_plan(self):
        plan = get_plan_from_config({"plan": "free"})
        assert plan.price_monthly == 0


class TestGetMultipliers:
    def test_default_multipliers(self):
        m = get_multipliers_from_config({})
        assert "claude-opus-4.6" in m
        assert m["claude-opus-4.6"] == 6

    def test_overridden_multipliers(self):
        config = {"multiplier_overrides": {"claude-opus-4.6": 3}}
        m = get_multipliers_from_config(config)
        assert m["claude-opus-4.6"] == 3

    def test_override_preserves_others(self):
        config = {"multiplier_overrides": {"claude-opus-4.6": 3}}
        m = get_multipliers_from_config(config)
        assert m["gpt-5-mini"] == 0  # unchanged


class TestGetLogDir:
    def test_default(self):
        d = get_log_dir({})
        assert "logs" in str(d)

    def test_custom(self):
        d = get_log_dir({"log_dir": "/custom/path"})
        assert str(d) == "/custom/path"


class TestGetBillingCycleDay:
    def test_default(self):
        assert get_billing_cycle_day({}) == 1

    def test_custom(self):
        assert get_billing_cycle_day({"billing_cycle_day": 15}) == 15


class TestBuildDefaultConfig:
    def test_builds_config(self):
        c = build_default_config("enterprise", 15, "/some/path")
        assert c["plan"] == "enterprise"
        assert c["billing_cycle_day"] == 15
        assert c["log_dir"] == "/some/path"
        assert c["multiplier_overrides"] == {}
