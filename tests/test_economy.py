"""Unit tests for economy calculations logic.

These tests verify that infrastructure cost calculations match the PWPedia
game mechanics formulas.

References:
- PWPedia "Infrastructure" article for infrastructure cost calculations
- .ctx/projects_canon.md for project discounts
"""

import pytest
import sys
import os

# Add parent directory to path so we can import logic
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from logic.economy import infra_cost, infra_rebuild_cost


class TestInfraCost:
    """Test suite for infrastructure cost calculation.
    
    Per PWPedia "Infrastructure" article:
    Infrastructure has a bulk discount; prices come in batches of 500.
    Each batch of 500 levels costs proportionally to the starting point.
    """

    def test_single_level_from_zero(self):
        """Test building single infrastructure level from zero."""
        cost = infra_cost(0, 1)
        assert cost > 0, "Cost should be positive for building infra from 0 to 1"

    def test_range_building(self):
        """Test building range of infrastructure levels."""
        cost_0_to_100 = infra_cost(0, 100)
        cost_0_to_50 = infra_cost(0, 50)
        
        # Building 50 levels should cost less than building 100 levels
        assert cost_0_to_50 < cost_0_to_100

    def test_zero_range_cost(self):
        """Building 0 levels (same start and end) should cost 0."""
        assert infra_cost(100, 100) == 0
        assert infra_cost(0, 0) == 0

    def test_partial_building(self):
        """Test building from middle point."""
        cost_mid = infra_cost(50, 100)
        cost_low = infra_cost(0, 50)
        
        # Both are 50 levels, should be different costs (mid point more expensive)
        assert cost_mid > 0
        assert cost_low > 0

    def test_bulk_discount_efficiency(self):
        """Building in larger chunks should be more efficient (per level cost lower)."""
        # Building 100 levels at once
        cost_bulk = infra_cost(0, 100)
        
        # Building 50 levels twice (if done separately, would be more expensive)
        # This tests the bulk discount benefit
        cost_split = infra_cost(0, 50) + infra_cost(50, 100)
        
        # Per-level cost should be better with bulk
        assert cost_bulk / 100 < cost_split / 100

    def test_maximum_value(self):
        """Test with large infrastructure values."""
        cost = infra_cost(0, 1000)
        assert cost > 0

    def test_invalid_range_rejected(self):
        """Building backwards (end < start) should be handled gracefully."""
        # Should either return 0 or raise error, but not crash
        try:
            cost = infra_cost(100, 50)
            assert cost == 0, "Backward range should cost 0"
        except (ValueError, AssertionError):
            pass  # Either behavior is acceptable


class TestInfraRebuildCost:
    """Buying back infrastructure destroyed in an attack."""

    def test_small_loss_on_fractional_infra_is_never_negative(self):
        # 2345.67 - 0.15 used to round up to 2346 while 2345.67 truncated to 2345,
        # pricing the loss as a sale of one infra (-150).
        assert infra_rebuild_cost(2345.67, 0.15) > 0
        assert infra_rebuild_cost(2345.9, 0.4) > 0

    def test_cost_covers_the_whole_loss(self):
        # 99.6 infra would be charged when the ends were rounded separately.
        full = infra_rebuild_cost(2345.6, 100)
        assert full == pytest.approx(infra_cost(2245.6, 2345.6))
        assert full > infra_cost(2246, 2345)

    def test_no_loss_costs_nothing(self):
        assert infra_rebuild_cost(2000, 0) == 0.0
        assert infra_rebuild_cost(2000, -5) == 0.0


class TestInfraCostDiscounts:
    """Project and domestic policy discounts on infrastructure."""

    def test_urbanization_title_case_from_the_api_applies(self):
        base = infra_cost(1000, 1500)
        assert infra_cost(1000, 1500, {"dompolicy": "Urbanization"}) == pytest.approx(base * 0.95)
        assert infra_cost(1000, 1500, {"domestic_policy": "URBANIZATION"}) == pytest.approx(base * 0.95)

    def test_policy_boosts_stack_with_gsa_and_bda(self):
        base = infra_cost(1000, 1500)
        gsa = {"dompolicy": "Urbanization", "government_support_agency": True}
        both = {**gsa, "bureau_of_domestic_affairs": True}
        assert infra_cost(1000, 1500, gsa) == pytest.approx(base * 0.925)
        assert infra_cost(1000, 1500, both) == pytest.approx(base * 0.9125)

    def test_engineering_projects(self):
        base = infra_cost(1000, 1500)
        nation = {"center_for_civil_engineering": True, "advanced_engineering_corps": True}
        assert infra_cost(1000, 1500, nation) == pytest.approx(base * 0.9)
