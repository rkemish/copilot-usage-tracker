"""Tests for plans registry."""

from copilot_usage.plans import PLANS, DEFAULT_MULTIPLIERS, get_plan, get_multiplier_map
from copilot_usage.models import Plan, ModelMultiplier
import pytest


class TestPlans:
    def test_all_plans_exist(self):
        assert "free" in PLANS
        assert "pro" in PLANS
        assert "pro_plus" in PLANS
        assert "business" in PLANS
        assert "enterprise" in PLANS

    def test_plan_types(self):
        for key, plan in PLANS.items():
            assert isinstance(plan, Plan)
            assert plan.price_monthly >= 0
            assert plan.included_premium_reqs >= 0

    def test_free_no_overage(self):
        p = PLANS["free"]
        assert p.allows_overage is False

    def test_pro_pricing(self):
        p = PLANS["pro"]
        assert p.price_monthly == 10
        assert p.included_premium_reqs == 300
        assert p.overage_rate == 0.04

    def test_enterprise_pricing(self):
        p = PLANS["enterprise"]
        assert p.price_monthly == 39
        assert p.included_premium_reqs == 1000

    def test_get_plan_valid(self):
        p = get_plan("pro")
        assert p.name == "Pro"

    def test_get_plan_invalid(self):
        with pytest.raises(KeyError):
            get_plan("nonexistent")


class TestMultipliers:
    def test_multipliers_not_empty(self):
        assert len(DEFAULT_MULTIPLIERS) > 0

    def test_multiplier_types(self):
        for m in DEFAULT_MULTIPLIERS:
            assert isinstance(m, ModelMultiplier)
            assert isinstance(m.multiplier, (int, float))
            assert m.model_family

    def test_get_multiplier_map(self):
        mm = get_multiplier_map()
        assert isinstance(mm, dict)
        assert "claude-opus-4.6" in mm
        assert "gpt-5-mini" in mm

    def test_known_multipliers(self):
        mm = get_multiplier_map()
        assert mm["gpt-5-mini"].multiplier == 0
        assert mm["claude-opus-4.6"].multiplier == 3

    def test_display_name_default(self):
        m = ModelMultiplier(model_family="test-model", multiplier=1.0)
        assert m.display_name == "test-model"

    def test_display_name_custom(self):
        m = ModelMultiplier(model_family="test", multiplier=1.0, display_name="Test Model")
        assert m.display_name == "Test Model"
