"""Shooting, goals and restarts.

A full match is slow, so these share one module-scoped run.
"""

import pytest

from chalkboard.fixtures import build_match
from chalkboard.sim import MatchSimulator


@pytest.fixture(scope="module")
def match():
    meta = build_match(7)
    sim = MatchSimulator(meta)
    frames = 0
    for _ in sim.run():
        frames += 1
    return meta, sim, frames


def test_match_runs_to_completion(match):
    meta, _sim, frames = match
    expected = sum(int(p.duration_ms / 1000 * meta.tracking_hz)
                   for p in meta.periods)
    assert frames == expected


def test_shots_are_taken(match):
    _meta, sim, _ = match
    assert 15 <= sim.stats["shots"] <= 45


def test_goals_are_scored_and_match_the_score(match):
    _meta, sim, _ = match
    assert sim.stats["goals"] == sum(sim.score.values())
    assert sim.stats["goals"] >= 1


def test_shot_outcomes_are_consistent(match):
    _meta, sim, _ = match
    s = sim.stats
    assert s["goals"] <= s["on_target"] <= s["shots"]
    assert s["blocked"] <= s["shots"]


def test_goals_are_a_plausible_fraction_of_xg(match):
    """Goals are drawn against xG, so they should land near it."""
    _meta, sim, _ = match
    assert 0.3 <= sim.stats["goals"] / sim.stats["xg"] <= 3.0


def test_passes_still_dominate_shots(match):
    _meta, sim, _ = match
    assert sim.stats["passes"] > sim.stats["shots"] * 10


def test_scoreline_is_football_shaped(match):
    _meta, sim, _ = match
    for goals in sim.score.values():
        assert 0 <= goals <= 8
