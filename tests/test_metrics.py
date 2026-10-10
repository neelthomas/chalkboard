"""
Metrics engine: event detection and the three index primitives.

The headline test is detection recall. The simulator knows what actually
happened; the detector sees only TrackingFrames and has to work it out.
Comparing the two is only possible because the data is synthetic, and it is
the same mechanism that will later measure the narrative layer's
hallucination rate.
"""

import pytest

from chalkboard.contracts import EventType, MatchEvent
from chalkboard.fixtures import build_match
from chalkboard.metrics import collect
from chalkboard.metrics.indices import IndexSnapshot
from chalkboard.sim import MatchSimulator

SEED = 7


@pytest.fixture(scope="module")
def run():
    meta = build_match(SEED)
    sim = MatchSimulator(meta)
    events, snaps = collect(meta, sim.run())
    return meta, sim, events, snaps


def by_type(events, kind):
    return [e for e in events if e.type is kind]


# --- detection accuracy -------------------------------------------------

class TestRecall:
    def test_passes(self, run):
        _m, sim, events, _s = run
        found = len(by_type(events, EventType.PASS))
        # One pass may still be in flight at the final whistle.
        assert sim.stats["passes"] - 1 <= found <= sim.stats["passes"]

    def test_completions(self, run):
        _m, sim, events, _s = run
        found = sum(1 for e in by_type(events, EventType.PASS)
                    if e.detail.completed)
        assert found == pytest.approx(sim.stats["completed"], abs=1)

    def test_shots(self, run):
        _m, sim, events, _s = run
        assert len(by_type(events, EventType.SHOT)) == sim.stats["shots"]

    def test_goals(self, run):
        _m, sim, events, _s = run
        found = sum(1 for e in by_type(events, EventType.SHOT) if e.detail.goal)
        assert found == sim.stats["goals"] == sum(sim.score.values())

    def test_on_target(self, run):
        _m, sim, events, _s = run
        found = sum(1 for e in by_type(events, EventType.SHOT)
                    if e.detail.on_target)
        assert found == sim.stats["on_target"]

    def test_xg_is_recomputed_identically(self, run):
        """Both sides call football.shot_quality, so they must agree."""
        _m, sim, events, _s = run
        found = sum(e.detail.xg for e in by_type(events, EventType.SHOT))
        assert found == pytest.approx(sim.stats["xg"], rel=0.01)


# --- provenance ---------------------------------------------------------

class TestProvenance:
    def test_every_event_traces_to_frames(self, run):
        _m, _sim, events, _s = run
        for e in events:
            lo, hi = e.frame_seq_range
            assert 0 <= lo <= hi, f"{e.event_id} has range {lo}..{hi}"

    def test_passes_span_their_flight(self, run):
        _m, _sim, events, _s = run
        for e in by_type(events, EventType.PASS):
            lo, hi = e.frame_seq_range
            assert hi > lo, "a pass that takes no time did not happen"

    def test_events_are_ordered(self, run):
        _m, _sim, events, _s = run
        seqs = [e.seq for e in events]
        assert seqs == sorted(seqs)

    def test_event_ids_unique(self, run):
        _m, _sim, events, _s = run
        ids = [e.event_id for e in events]
        assert len(set(ids)) == len(ids)


# --- pass detail --------------------------------------------------------

class TestPassDetail:
    def test_interception_follows_every_failed_pass(self, run):
        _m, _sim, events, _s = run
        failed = sum(1 for e in by_type(events, EventType.PASS)
                     if not e.detail.completed)
        assert len(by_type(events, EventType.INTERCEPTION)) == failed

    def test_release_speed_is_plausible(self, run):
        _m, _sim, events, _s = run
        for e in by_type(events, EventType.PASS):
            assert 1.0 <= e.detail.release_speed <= 40.0

    def test_some_passes_are_progressive(self, run):
        _m, _sim, events, _s = run
        passes = by_type(events, EventType.PASS)
        share = sum(1 for e in passes if e.detail.progressive) / len(passes)
        assert 0.05 < share < 0.80

    def test_difficulty_is_bounded(self, run):
        _m, _sim, events, _s = run
        for e in by_type(events, EventType.PASS):
            assert 0.0 <= e.detail.difficulty <= 1.0


# --- indices ------------------------------------------------------------

class TestIndices:
    def test_snapshots_are_emitted(self, run):
        _m, _sim, _e, snaps = run
        assert len(snaps) > 50

    def test_everything_is_a_unit_interval(self, run):
        _m, _sim, _e, snaps = run
        for s in snaps:
            assert 0.0 <= s.chaos <= 1.0
            assert 0.0 <= s.rhythm <= 1.0
            for t in s.teams:
                for field in ("control", "possession_share", "pass_completion",
                              "territory", "pressure", "press_intensity",
                              "line_height"):
                    v = getattr(t, field)
                    assert 0.0 <= v <= 1.0, f"{field} = {v}"

    def test_possession_shares_sum_to_one(self, run):
        _m, _sim, _e, snaps = run
        for s in snaps[5:]:
            total = sum(t.possession_share for t in s.teams)
            assert total == pytest.approx(1.0, abs=0.02)

    def test_territory_is_a_mirror(self, run):
        """One team's territory is the other's, inverted - same ball."""
        _m, _sim, _e, snaps = run
        for s in snaps[5:]:
            a, b = s.teams
            assert a.territory + b.territory == pytest.approx(1.0, abs=0.02)

    def test_snapshot_carries_its_method_and_window(self, run):
        _m, _sim, _e, snaps = run
        for s in snaps[5:]:
            assert s.method.startswith("indices@")
            assert s.window_ms > 0
            lo, hi = s.frame_seq_range
            assert lo <= hi

    def test_components_are_reported_not_just_composites(self, run):
        """
        A claim citing only the headline number cannot be verified. Every
        composite has to show its working.
        """
        _m, _sim, _e, snaps = run
        t = snaps[-1].teams[0]
        assert {"possession_share", "pass_completion", "territory"} <= set(
            t.model_dump())
        assert {"press_intensity", "line_height"} <= set(t.model_dump())

    def test_tempo_is_plausible(self, run):
        _m, _sim, _e, snaps = run
        tempos = [s.tempo for s in snaps[5:]]
        assert 2.0 < sum(tempos) / len(tempos) < 25.0


# --- the detector must not peek ----------------------------------------

def test_detector_does_not_import_the_simulator():
    """
    Stage (b) has to work from frames alone or it is not interpretation.
    If this fails, the detector has started cheating.
    """
    import pathlib

    src = pathlib.Path(__file__).resolve().parents[1] / "src"
    text = (src / "chalkboard" / "metrics" / "events.py").read_text()
    assert "chalkboard.sim" not in text
    assert "MatchSimulator" not in text


def test_events_are_contract_instances(run):
    _m, _sim, events, _s = run
    assert all(isinstance(e, MatchEvent) for e in events)


def test_snapshots_are_contract_instances(run):
    _m, _sim, _e, snaps = run
    assert all(isinstance(s, IndexSnapshot) for s in snaps)
