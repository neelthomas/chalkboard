"""
football.py - pure football maths.

Deterministic, dependency-free, unit-testable. No randomness, no model
calls, no I/O. Both the simulator and the metrics engine import from here,
so a shot's xG is computed by exactly one function and a claim about it can
be recomputed years later.

Geometry matches contracts.py: metres, origin at the centre spot,
x in [-52.5, 52.5], y in [-34, 34]. A team's `attack_dir` is +1 if they
shoot toward +x, -1 otherwise.
"""

from __future__ import annotations

import math

PITCH_X = 52.5
PITCH_Y = 34.0
GOAL_WIDTH = 7.32
GOAL_HALF = GOAL_WIDTH / 2
PENALTY_AREA_DEPTH = 16.5
PENALTY_AREA_HALF_WIDTH = 20.16
SIX_YARD_DEPTH = 5.5


def goal_centre(attack_dir: float) -> tuple[float, float]:
    """The goal this team is attacking."""
    return (math.copysign(PITCH_X, attack_dir), 0.0)


def distance_to_goal(x: float, y: float, attack_dir: float) -> float:
    gx, gy = goal_centre(attack_dir)
    return math.hypot(gx - x, gy - y)


def goal_mouth_angle(x: float, y: float, attack_dir: float) -> float:
    """
    Radians of goal visible from (x, y) - the standard shooting-angle term.

    Zero when the shooter is on the goal line outside the posts; widest
    when they are close and central.
    """
    dx = abs(math.copysign(PITCH_X, attack_dir) - x)
    denom = dx * dx + y * y - GOAL_HALF * GOAL_HALF
    angle = math.atan2(GOAL_WIDTH * dx, denom)
    return angle if angle >= 0 else angle + math.pi


def expected_goals(distance_m: float, angle_rad: float) -> float:
    """
    Logistic xG on distance and visible goal angle.

    Calibrated to land near commonly published open-play values:
        6 m central   ~0.60      11 m central  ~0.28
        18 m central  ~0.12      25 m central  ~0.06
        11 m, 20 m wide ~0.05

    Open play only - penalties and set pieces are not modelled.
    """
    z = -1.9 + 2.6 * angle_rad - 0.065 * distance_m
    return 1.0 / (1.0 + math.exp(-z))


def shot_quality(x: float, y: float, attack_dir: float) -> tuple[float, float, float]:
    """Convenience: (distance, angle, xG) for a shot from this spot."""
    d = distance_to_goal(x, y, attack_dir)
    a = goal_mouth_angle(x, y, attack_dir)
    return d, a, expected_goals(d, a)


def in_penalty_area(x: float, y: float, attack_dir: float) -> bool:
    """Inside the box this team is attacking."""
    gx = math.copysign(PITCH_X, attack_dir)
    return abs(gx - x) <= PENALTY_AREA_DEPTH and abs(y) <= PENALTY_AREA_HALF_WIDTH


def in_final_third(x: float, attack_dir: float) -> bool:
    return x * attack_dir > PITCH_X / 3


def thirds(x: float, attack_dir: float) -> str:
    """Which third of the pitch, from this team's point of view."""
    forward = x * attack_dir
    if forward > PITCH_X / 3:
        return "final"
    if forward < -PITCH_X / 3:
        return "defensive"
    return "middle"


def is_progressive(start_x: float, start_y: float,
                   end_x: float, end_y: float, attack_dir: float) -> bool:
    """
    A pass that meaningfully advances the ball toward goal.

    Uses the common definition: it reduces the distance to the opposition
    goal by at least 25%, or by at least 10 m in the attacking half.
    """
    before = distance_to_goal(start_x, start_y, attack_dir)
    after = distance_to_goal(end_x, end_y, attack_dir)
    gain = before - after
    if gain <= 0:
        return False
    if start_x * attack_dir > 0 and gain >= 10.0:
        return True
    return gain >= before * 0.25


def pass_difficulty(distance_m: float, opponents_bypassed: int,
                    pressure_m: float, lateral_m: float) -> float:
    """
    A 0-1 difficulty rating for a pass. Not a published metric - this is
    our own composite, which is exactly why it is written down in one place
    and versioned in the ledger as `pass_metrics@<version>`.

        distance            longer is harder
        opponents_bypassed  threading more bodies is harder
        pressure_m          how close the nearest opponent was to the passer
        lateral_m           sideways distance; square balls are harder to time
    """
    d = min(distance_m / 45.0, 1.0) * 0.40
    b = min(opponents_bypassed / 6.0, 1.0) * 0.30
    p = max(0.0, 1.0 - pressure_m / 8.0) * 0.20
    s = min(abs(lateral_m) / 40.0, 1.0) * 0.10
    return round(min(d + b + p + s, 1.0), 3)


def opponents_bypassed(start_x: float, end_x: float, attack_dir: float,
                       opponent_xs: list[float]) -> int:
    """How many opponents the ball travelled past, measured along the pitch."""
    a, b = start_x * attack_dir, end_x * attack_dir
    if b <= a:
        return 0
    return sum(1 for ox in opponent_xs if a < ox * attack_dir <= b)
