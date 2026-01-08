"""Unit tests for military calculations logic.

These tests verify that military calculations (specifically win chance calculations)
match the Uniform Distribution model documented in PWPedia.

Reference: PWPedia "War-Mechanics" article
"""

import pytest
import sys
import os

# Add parent directory to path so we can import logic
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from logic.military import calculate_win_chance_raw, score_range


class TestCalculateWinChance:
    """Test suite for calculate_win_chance_raw function.
    
    The win chance calculation is based on a uniform distribution model where:
    - Both attacker and defender roll between 40% (MIN_EFFICIENCY) and 100% (MAX_EFFICIENCY) of their score
    - Win probability is the fraction of the rectangle where attacker_roll > defender_roll
    """

    def test_edge_case_zero_defender(self):
        """Attacker always wins if defender has 0 score."""
        assert calculate_win_chance_raw(100, 0) == 1.0
        assert calculate_win_chance_raw(1, 0) == 1.0
        assert calculate_win_chance_raw(10000, 0) == 1.0

    def test_edge_case_zero_attacker(self):
        """Attacker always loses if attacker has 0 score."""
        assert calculate_win_chance_raw(0, 100) == 0.0
        assert calculate_win_chance_raw(0, 1) == 0.0
        assert calculate_win_chance_raw(0, 10000) == 0.0

    def test_edge_case_both_zero(self):
        """Special case: both zero means defender wins (returns 0.0)."""
        assert calculate_win_chance_raw(0, 0) == 0.0

    def test_guaranteed_win(self):
        """Attacker wins if score ratio > 2.5.
        
        When attacker_value > 2.5 * defender_value:
        min_a (40% of attacker) >= max_d (100% of defender)
        So attacker wins even with worst roll vs best opponent roll.
        """
        # Exactly 2.5x should be guaranteed win
        assert calculate_win_chance_raw(2.6, 1.0) == 1.0
        assert calculate_win_chance_raw(100, 39) == 1.0
        assert calculate_win_chance_raw(1000, 399) == 1.0

    def test_guaranteed_loss(self):
        """Attacker loses if score ratio < 0.4.
        
        When attacker_value < 0.4 * defender_value:
        max_a (100% of attacker) <= min_d (40% of defender)
        So attacker loses even with best roll vs worst opponent roll.
        """
        # Less than 0.4x should be guaranteed loss
        assert calculate_win_chance_raw(0.39, 1.0) == 0.0
        assert calculate_win_chance_raw(39, 100) == 0.0
        assert calculate_win_chance_raw(399, 1000) == 0.0

    def test_equal_scores(self):
        """Equal scores should result in 50% win chance.
        
        When attacker = defender:
        - min_a = 0.4 * A
        - max_a = 1.0 * A
        - min_d = 0.4 * A
        - max_d = 1.0 * A
        
        The rectangle is [0.4A to 1.0A] × [0.4A to 1.0A]
        Win area is above the diagonal y=x, which is exactly half.
        """
        result = calculate_win_chance_raw(100, 100)
        assert abs(result - 0.5) < 0.01, f"Expected ~0.5 for equal scores, got {result}"
        
        result = calculate_win_chance_raw(500, 500)
        assert abs(result - 0.5) < 0.01, f"Expected ~0.5 for equal scores, got {result}"

    def test_slightly_higher_score(self):
        """Attacker with slightly higher score should have > 50% win chance."""
        result = calculate_win_chance_raw(110, 100)
        assert result > 0.5, f"Expected > 0.5 for 110 vs 100, got {result}"
        assert result < 1.0, f"Expected < 1.0 for 110 vs 100, got {result}"

    def test_slightly_lower_score(self):
        """Attacker with slightly lower score should have < 50% win chance."""
        result = calculate_win_chance_raw(90, 100)
        assert result < 0.5, f"Expected < 0.5 for 90 vs 100, got {result}"
        assert result > 0.0, f"Expected > 0.0 for 90 vs 100, got {result}"

    def test_ratio_2_to_1(self):
        """2:1 score advantage (not quite guaranteed win at 2.5x)."""
        result = calculate_win_chance_raw(200, 100)
        # At exactly 2:1, this should be very favorable but not guaranteed
        assert result > 0.7, f"Expected > 0.7 for 200 vs 100, got {result}"
        assert result < 1.0, f"Expected < 1.0 for 200 vs 100, got {result}"

    def test_ratio_1_to_2(self):
        """1:2 score disadvantage (not quite guaranteed loss at 0.4x)."""
        result = calculate_win_chance_raw(50, 100)
        # At exactly 1:2, this should be very unfavorable but not hopeless
        assert result > 0.0, f"Expected > 0.0 for 50 vs 100, got {result}"
        assert result < 0.3, f"Expected < 0.3 for 50 vs 100, got {result}"

    def test_symmetry_property(self):
        """If A beats B with p%, then B beats A with 1-p%."""
        a_score, b_score = 150, 100
        a_win_chance = calculate_win_chance_raw(a_score, b_score)
        b_win_chance = calculate_win_chance_raw(b_score, a_score)
        
        assert abs((a_win_chance + b_win_chance) - 1.0) < 0.001, \
            f"Symmetry failed: {a_win_chance} + {b_win_chance} != 1.0"

    def test_monotonicity(self):
        """Increasing attacker score should never decrease win chance."""
        defender = 100
        scores = [50, 75, 100, 125, 150, 200, 300]
        win_chances = [calculate_win_chance_raw(s, defender) for s in scores]
        
        for i in range(len(win_chances) - 1):
            assert win_chances[i] <= win_chances[i + 1], \
                f"Monotonicity violated: {scores[i]}/{defender} ({win_chances[i]}) > " \
                f"{scores[i+1]}/{defender} ({win_chances[i+1]})"

    def test_range_bounds(self):
        """Win chance should always be between 0 and 1."""
        test_cases = [
            (1, 1000),
            (1000, 1),
            (100, 100),
            (50, 150),
            (500, 200),
        ]
        for attacker, defender in test_cases:
            result = calculate_win_chance_raw(attacker, defender)
            assert 0.0 <= result <= 1.0, \
                f"Win chance out of range [{0},1]: {result} for {attacker} vs {defender}"

    def test_realistic_scenario_balanced(self):
        """Test with realistic balanced nation scores."""
        # Both nations ~1500 score, should be near 50/50
        result = calculate_win_chance_raw(1500, 1500)
        assert abs(result - 0.5) < 0.05

    def test_realistic_scenario_advantage(self):
        """Test with realistic advantage scenario."""
        # Attacker 2000 score vs defender 1000 score
        result = calculate_win_chance_raw(2000, 1000)
        # Exactly 2x, so in the overlap zone but with advantage
        assert result > 0.7 and result < 1.0


class TestScoreRange:
    """Test suite for score_range helper function."""

    def test_basic_range(self):
        """Test basic score range calculation."""
        min_score, max_score = score_range(100)
        assert min_score == 75
        assert max_score == 250

    def test_range_preserves_ratios(self):
        """Score range should maintain 0.75 to 2.5 ratio."""
        scores = [50, 100, 500, 1000, 5000]
        for score in scores:
            min_score, max_score = score_range(score)
            assert abs(min_score / score - 0.75) < 0.001
            assert abs(max_score / score - 2.5) < 0.001

    def test_ordering(self):
        """Min score should always be less than max score."""
        scores = [1, 10, 100, 1000, 10000]
        for score in scores:
            min_score, max_score = score_range(score)
            assert min_score < max_score


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
