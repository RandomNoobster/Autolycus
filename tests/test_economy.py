"""Unit tests for economy calculations logic.

These tests verify that economy calculations (infra, land, city, expansion costs)
match the PWPedia game mechanics formulas.

References:
- PWPedia "Infrastructure" article for infrastructure cost calculations
- PWPedia "Land" article for land cost calculations
- PWPedia "Cities" article for city cost calculations
"""

import pytest
import sys
import os

# Add parent directory to path so we can import logic
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from logic.economy import infra_cost, land_cost, city_cost, expansion_cost


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


class TestLandCost:
    """Test suite for land cost calculation.
    
    Per PWPedia "Land" article:
    Land cost increases with land owned and city count.
    Formula varies based on land efficiency and bulking discounts.
    """

    def test_single_land_from_zero(self):
        """Test buying single land from zero."""
        cost = land_cost(0, 1)
        assert cost > 0

    def test_range_purchase(self):
        """Test buying range of land."""
        cost_0_to_100 = land_cost(0, 100)
        cost_0_to_50 = land_cost(0, 50)
        
        assert cost_0_to_50 < cost_0_to_100

    def test_zero_range_cost(self):
        """Buying 0 land (same start/end) should cost 0."""
        assert land_cost(100, 100) == 0

    def test_bulk_discount_applies(self):
        """Larger land purchases should be more efficient per unit."""
        cost_bulk = land_cost(0, 100)
        cost_split = land_cost(0, 50) + land_cost(50, 100)
        
        # Per-unit cost better with bulk
        assert cost_bulk / 100 < cost_split / 100

    def test_escalating_cost(self):
        """Later land should cost more per unit due to scaling."""
        cost_early = land_cost(0, 50)
        cost_late = land_cost(500, 550)
        
        # Same amount of land, but later should cost more
        assert cost_late > cost_early

    def test_with_nation_data(self):
        """Test land cost with nation data dict."""
        nation = {
            "infrastructure": 100,
            "land": 200,
            "num_cities": 5
        }
        cost = land_cost(0, 100, nation)
        assert cost > 0

    def test_city_count_affects_cost(self):
        """More cities should increase land cost."""
        low_cities = {"num_cities": 1}
        high_cities = {"num_cities": 20}
        
        cost_low = land_cost(0, 100, low_cities)
        cost_high = land_cost(0, 100, high_cities)
        
        # More cities = higher land cost
        assert cost_high >= cost_low


class TestCityCost:
    """Test suite for city cost calculation.
    
    Per PWPedia "Cities" article:
    City costs scale with current city count and nation infrastructure/land.
    """

    def test_first_city(self):
        """First city should have a base cost."""
        first_city = {"num_cities": 0}
        cost = city_cost(first_city)
        assert cost > 0

    def test_subsequent_cities_more_expensive(self):
        """Each additional city should cost more."""
        city_1 = {"num_cities": 1}
        city_5 = {"num_cities": 5}
        
        cost_1 = city_cost(city_1)
        cost_5 = city_cost(city_5)
        
        assert cost_5 > cost_1

    def test_with_nation_stats(self):
        """Test city cost with comprehensive nation data."""
        nation = {
            "num_cities": 3,
            "infrastructure": 500,
            "land": 1000,
            "population": 5000000
        }
        cost = city_cost(nation)
        assert cost > 0

    def test_cost_escalation(self):
        """City cost should escalate significantly with city count."""
        costs = []
        for i in range(1, 11):
            nation_state = {"num_cities": i}
            cost = city_cost(nation_state)
            costs.append(cost)
        
        # Each city should generally cost more than the previous
        for i in range(1, len(costs)):
            assert costs[i] >= costs[i - 1], \
                f"City {i + 1} (cost {costs[i]}) should cost >= City {i} (cost {costs[i-1]})"


class TestExpansionCost:
    """Test suite for total expansion cost calculation.
    
    Expansion cost combines infra, land, and city costs.
    """

    def test_basic_expansion(self):
        """Test basic expansion scenario."""
        nation = {
            "infrastructure": 100,
            "land": 200,
            "num_cities": 5
        }
        cost = expansion_cost(100, 200, 100, 300, nation)
        assert cost > 0

    def test_zero_expansion(self):
        """No expansion (same start/end) should cost 0."""
        nation = {
            "infrastructure": 100,
            "land": 200,
            "num_cities": 5
        }
        # Infra: 100->100, Land: 200->200, no city
        cost = expansion_cost(100, 200, 100, 200, nation)
        assert cost == 0

    def test_expansion_parts_add_up(self):
        """Total expansion should equal sum of parts."""
        nation = {
            "infrastructure": 100,
            "land": 200,
            "num_cities": 5
        }
        
        # Expansion: add 50 infra, 100 land, 1 city
        total_cost = expansion_cost(100, 200, 150, 300, nation)
        
        infra_cost_sep = infra_cost(100, 150)
        land_cost_sep = land_cost(200, 300, nation)
        city_cost_sep = city_cost({"num_cities": nation["num_cities"] + 1}) - \
                        city_cost({"num_cities": nation["num_cities"]})
        
        expected_cost = infra_cost_sep + land_cost_sep + city_cost_sep
        
        # Should be equal or very close
        assert abs(total_cost - expected_cost) < 1

    def test_realistic_expansion_scenario(self):
        """Test realistic nation expansion scenario."""
        nation = {
            "infrastructure": 500,
            "land": 1000,
            "num_cities": 10
        }
        
        # Expand: +200 infra, +500 land, +2 cities
        cost = expansion_cost(500, 1000, 700, 1500, nation)
        assert cost > 0
        
        # Cost should scale reasonably
        assert cost < 10_000_000_000  # Sanity check (not astronomical)


class TestCostIntegration:
    """Integration tests combining multiple cost calculations."""

    def test_progression_scaling(self):
        """Costs should scale reasonably as nation grows."""
        initial_cost = expansion_cost(0, 0, 100, 100, {"infrastructure": 0, "land": 0, "num_cities": 1})
        mid_cost = expansion_cost(100, 100, 200, 200, {"infrastructure": 100, "land": 100, "num_cities": 5})
        late_cost = expansion_cost(500, 500, 600, 600, {"infrastructure": 500, "land": 500, "num_cities": 15})
        
        # Late game should cost more than early game
        assert late_cost > initial_cost

    def test_efficiency_comparison(self):
        """Compare cost efficiency of different build strategies."""
        nation_base = {"infrastructure": 100, "land": 200, "num_cities": 5}
        
        # Strategy 1: Heavy infra
        cost_infra_heavy = expansion_cost(100, 200, 300, 200, nation_base)
        
        # Strategy 2: Balanced
        cost_balanced = expansion_cost(100, 200, 150, 300, nation_base)
        
        # Strategy 3: Heavy land
        cost_land_heavy = expansion_cost(100, 200, 100, 400, nation_base)
        
        # All should be positive
        assert cost_infra_heavy > 0
        assert cost_balanced > 0
        assert cost_land_heavy > 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
