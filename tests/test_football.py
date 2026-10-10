"""Football maths: geometry and xG calibration.

These are the functions the metrics engine and the Fact Ledger will cite by
name and version, so they get pinned here rather than left to drift.
"""

import math

import pytest

from chalkboard import football as fb

ATTACK_POS_X = 1.0
GOAL_X = fb.PITCH_X


def at(distance_from_goal: float, y: float = 0.0) -> tuple[float, float]:
    """A point `distance_from_goal` out from the +x goal, on the centre line."""
    return GOAL_X - distance_from_goal, y


class TestGeometry:
    def test_distance_to_goal(self):
        x, y = at(18.0)
        assert fb.distance_to_goal(x, y, ATTACK_POS_X) == pytest.approx(18.0)

    def test_attacking_the_other_way(self):
        # Same spot, opposite attacking direction -> nearly the full pitch.
        x, y = at(18.0)
        assert fb.distance_to_goal(x, y, -1.0) == pytest.approx(105.0 - 18.0)

    def test_angle_is_widest_close_and_central(self):
        close = fb.goal_mouth_angle(*at(6.0), ATTACK_POS_X)
        far = fb.goal_mouth_angle(*at(30.0), ATTACK_POS_X)
        wide = fb.goal_mouth_angle(*at(6.0, 25.0), ATTACK_POS_X)
        assert close > far > 0
        assert close > wide

    def test_angle_never_negative(self):
        for d in (1.0, 5.0, 20.0, 50.0):
            for y in (-30.0, -10.0, 0.0, 10.0, 30.0):
                assert fb.goal_mouth_angle(*at(d, y), ATTACK_POS_X) >= 0

    def test_penalty_area(self):
        assert fb.in_penalty_area(*at(10.0), ATTACK_POS_X)
        assert not fb.in_penalty_area(*at(20.0), ATTACK_POS_X)
        assert not fb.in_penalty_area(*at(10.0, 25.0), ATTACK_POS_X)

    def test_thirds(self):
        assert fb.thirds(40.0, ATTACK_POS_X) == "final"
        assert fb.thirds(0.0, ATTACK_POS_X) == "middle"
        assert fb.thirds(-40.0, ATTACK_POS_X) == "defensive"
        # Flip the direction and the same spot flips meaning.
        assert fb.thirds(40.0, -1.0) == "defensive"


class TestExpectedGoals:
    @pytest.mark.parametrize("distance,low,high", [
        (6.0, 0.50, 0.75),
        (11.0, 0.20, 0.35),
        (18.0, 0.08, 0.16),
        (25.0, 0.03, 0.09),
        (35.0, 0.01, 0.05),
    ])
    def test_central_calibration(self, distance, low, high):
        _d, _a, xg = fb.shot_quality(*at(distance), ATTACK_POS_X)
        assert low <= xg <= high, f"{distance} m central gave xG {xg:.3f}"

    def test_monotonic_in_distance(self):
        xgs = [fb.shot_quality(*at(d), ATTACK_POS_X)[2]
               for d in range(5, 40, 2)]
        assert xgs == sorted(xgs, reverse=True)

    def test_tight_angle_is_worth_less_than_central(self):
        _d, _a, central = fb.shot_quality(*at(12.0, 0.0), ATTACK_POS_X)
        _d, _a, wide = fb.shot_quality(*at(12.0, 22.0), ATTACK_POS_X)
        assert wide < central

    def test_always_a_probability(self):
        for d in (0.5, 10.0, 60.0, 110.0):
            for y in (0.0, 15.0, 33.0):
                xg = fb.shot_quality(*at(d, y), ATTACK_POS_X)[2]
                assert 0.0 <= xg <= 1.0

    def test_halfway_line_is_near_hopeless(self):
        assert fb.shot_quality(0.0, 0.0, ATTACK_POS_X)[2] < 0.02


class TestPassMetrics:
    def test_progressive_requires_forward_gain(self):
        assert not fb.is_progressive(0, 0, -10, 0, ATTACK_POS_X)
        assert fb.is_progressive(-40, 0, -5, 0, ATTACK_POS_X)

    def test_ten_metre_gain_in_the_attacking_half(self):
        assert fb.is_progressive(10, 0, 22, 0, ATTACK_POS_X)
        # Same 12 m gain deep in our own half is not 25% of the distance.
        assert not fb.is_progressive(-50, 0, -38, 0, ATTACK_POS_X)

    def test_opponents_bypassed_counts_only_forward(self):
        opponents = [-10.0, 0.0, 10.0, 20.0]
        assert fb.opponents_bypassed(-20, 15, ATTACK_POS_X, opponents) == 3
        assert fb.opponents_bypassed(15, -20, ATTACK_POS_X, opponents) == 0

    def test_difficulty_bounds_and_ordering(self):
        easy = fb.pass_difficulty(5.0, 0, 20.0, 2.0)
        hard = fb.pass_difficulty(40.0, 5, 1.0, 30.0)
        assert 0.0 <= easy < hard <= 1.0

    def test_difficulty_rises_with_pressure(self):
        loose = fb.pass_difficulty(20.0, 2, 15.0, 5.0)
        pressed = fb.pass_difficulty(20.0, 2, 0.5, 5.0)
        assert pressed > loose
