"""The simulator is deterministic, stays on the pitch, and obeys physics."""

import itertools
import math
import statistics

import pytest

from chalkboard.contracts import PITCH_LENGTH_M, PITCH_WIDTH_M
from chalkboard.fixtures import build_match
from chalkboard.sim import MatchSimulator

MAX_PLAUSIBLE_SPEED = 13.0   # m/s - faster than any human has run


def _first(n: int, seed: int = 7):
    return list(itertools.islice(MatchSimulator(build_match(seed)).run(), n))


def test_same_seed_same_match():
    assert _first(500, seed=7) == _first(500, seed=7)


def test_different_seed_different_match():
    assert _first(500, seed=7) != _first(500, seed=8)


def test_everyone_stays_on_the_pitch():
    for frame in _first(2000):
        assert abs(frame.ball.pos.x) <= PITCH_LENGTH_M / 2
        assert abs(frame.ball.pos.y) <= PITCH_WIDTH_M / 2
        for p in frame.players:
            assert abs(p.pos.x) <= PITCH_LENGTH_M / 2
            assert abs(p.pos.y) <= PITCH_WIDTH_M / 2


def test_nobody_runs_faster_than_a_human():
    for frame in _first(2000):
        for p in frame.players:
            assert p.speed <= MAX_PLAUSIBLE_SPEED, f"{p.player_id} hit {p.speed} m/s"


def test_twenty_two_players_every_frame():
    for frame in _first(1000):
        assert len(frame.players) == 22
        assert len({p.player_id for p in frame.players}) == 22


def test_seq_is_monotonic():
    frames = _first(1000)
    assert [f.seq for f in frames] == list(range(len(frames)))


# --- realism regression -------------------------------------------------
# Bands are deliberately wider than the targets in tools/sim_report.py.
# These exist to catch a change that breaks the motion model, not to pin
# the tuning. Run sim_report.py for the tight numbers.

MINUTES = 4


@pytest.fixture(scope="module")
def run_stats():
    meta = build_match(7)
    sim = MatchSimulator(meta)
    frames = list(itertools.islice(sim.run(), meta.tracking_hz * 60 * MINUTES))
    return meta, sim, frames


def test_players_cover_a_plausible_distance(run_stats):
    meta, _sim, frames = run_stats
    run = {p.player_id: 0.0 for p in frames[0].players}
    for i in range(1, len(frames)):
        prev = {p.player_id: p for p in frames[i - 1].players}
        for p in frames[i].players:
            q = prev[p.player_id]
            run[p.player_id] += math.hypot(p.pos.x - q.pos.x, p.pos.y - q.pos.y)
    outfield = [v for pid, v in run.items() if not pid.endswith("p01")]
    per_90 = statistics.mean(outfield) * (90 / MINUTES)
    assert 7_000 <= per_90 <= 15_000, f"{per_90:,.0f} m per 90"


def test_mean_speed_is_not_a_permanent_sprint(run_stats):
    """The bug this guards: per-tick noise pinned everyone at 5.1 m/s."""
    _meta, _sim, frames = run_stats
    speeds = [p.speed for f in frames[::25] for p in f.players]
    assert 1.0 <= statistics.mean(speeds) <= 2.5


def test_players_sometimes_stand_still(run_stats):
    _meta, _sim, frames = run_stats
    speeds = [p.speed for f in frames[::25] for p in f.players]
    at_rest = sum(1 for s in speeds if s < 0.5) / len(speeds)
    assert at_rest > 0.05, "nobody ever stops moving"


def test_pass_volume_and_completion(run_stats):
    _meta, sim, _frames = run_stats
    per_90 = sim.stats["passes"] * (90 / MINUTES)
    completion = sim.stats["completed"] / max(sim.stats["passes"], 1)
    assert 600 <= per_90 <= 1_400, f"{per_90:,.0f} passes per 90"
    assert 0.65 <= completion <= 0.92, f"{completion:.0%} completion"


def test_nobody_teleports(run_stats):
    """
    A tracking feed with teleports is physically invalid - it registers as
    infinite speed and poisons every distance and speed metric downstream.
    Resetting the shape after a goal used to do exactly that.
    """
    _meta, _sim, frames = run_stats
    limit = 9.0 / 25 + 0.05          # vmax per tick, plus slack
    for i in range(1, len(frames)):
        prev = {p.player_id: p for p in frames[i - 1].players}
        for p in frames[i].players:
            q = prev[p.player_id]
            jump = math.hypot(p.pos.x - q.pos.x, p.pos.y - q.pos.y)
            assert jump <= limit, f"{p.player_id} jumped {jump:.2f} m in one tick"


def test_play_reaches_both_halves(run_stats):
    """A symmetric block shift used to trap the ball in the middle third."""
    _meta, _sim, frames = run_stats
    bx = [f.ball.pos.x for f in frames]
    assert min(bx) < -25 and max(bx) > 25, f"ball x range {min(bx):.1f}..{max(bx):.1f}"
    assert statistics.mean(abs(x) for x in bx) > 12
