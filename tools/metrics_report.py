"""
metrics_report.py - does the metrics engine recover what actually happened?

The simulator knows the truth: it counted every pass, shot and goal as it
produced them. The detector sees only TrackingFrames and has to work the
same facts out from scratch.

Comparing the two is the whole argument for synthetic data. On a real feed
you can never grade your own event detection, because nobody knows the
right answer. Here we do, so detection accuracy is measurable - and the
same trick is what will later let us measure the hallucination rate of the
narrative layer.
"""

import statistics
import sys
from collections import Counter

from chalkboard.contracts import EventType
from chalkboard.fixtures import build_match
from chalkboard.metrics import analyse
from chalkboard.metrics.indices import IndexSnapshot
from chalkboard.sim import MatchSimulator


def pct(a: float, b: float) -> str:
    if not b:
        return "   -  "
    return f"{100 * a / b:5.1f}%"


def main(seed: int = 7) -> None:
    meta = build_match(seed)
    sim = MatchSimulator(meta)

    counts: Counter[str] = Counter()
    detected = {"passes": 0, "completed": 0, "shots": 0, "goals": 0,
                "on_target": 0, "blocked": 0, "xg": 0.0}
    snaps: list[IndexSnapshot] = []

    for item in analyse(meta, sim.run()):
        if isinstance(item, IndexSnapshot):
            snaps.append(item)
            continue
        counts[item.type.value] += 1
        if item.type is EventType.PASS:
            detected["passes"] += 1
            detected["completed"] += int(item.detail.completed)
        elif item.type is EventType.SHOT:
            detected["shots"] += 1
            detected["xg"] += item.detail.xg
            detected["goals"] += int(item.detail.goal)
            detected["on_target"] += int(item.detail.on_target)
            detected["blocked"] += int(item.detail.blocked)

    home, away = meta.teams
    print(f"--- seed {seed}: {home.short_name} {sim.score[home.team_id]}"
          f" - {sim.score[away.team_id]} {away.short_name} ---\n")

    print("  detection vs ground truth")
    print(f"  {'':<14}{'truth':>8}{'detected':>10}{'recall':>9}")
    for label, key in [("passes", "passes"), ("completed", "completed"),
                       ("shots", "shots"), ("on target", "on_target"),
                       ("blocked", "blocked"), ("goals", "goals")]:
        truth = sim.stats[key]
        got = detected[key]
        print(f"  {label:<14}{truth:>8,.0f}{got:>10,.0f}{pct(got, truth):>9}")
    print(f"  {'xG':<14}{sim.stats['xg']:>8.2f}{detected['xg']:>10.2f}"
          f"{pct(detected['xg'], sim.stats['xg']):>9}")

    print("\n  events emitted")
    for kind, n in counts.most_common():
        print(f"  {kind:<22}{n:>8,}")

    print(f"\n  index snapshots: {len(snaps)}")
    if snaps:
        mid = snaps[len(snaps) // 2]
        h = mid.team(home.team_id)
        a = mid.team(away.team_id)
        mins = mid.t_ms // 60000 + (0 if mid.period == 1 else 45)
        print(f"\n  sample at {mins}' (window {mid.window_ms // 1000}s)"
              f"   method={mid.method}")
        print(f"    {'':<18}{home.short_name:>9}{away.short_name:>9}")
        for label, attr in [("control", "control"),
                            ("  possession", "possession_share"),
                            ("  completion", "pass_completion"),
                            ("  territory", "territory"),
                            ("pressure", "pressure"),
                            ("  press bodies", "press_intensity"),
                            ("  line height", "line_height")]:
            print(f"    {label:<18}{getattr(h, attr):>9.3f}{getattr(a, attr):>9.3f}")
        print(f"\n    {'chaos':<18}{mid.chaos:>9.3f}")
        print(f"    {'  turnovers/min':<18}{mid.turnovers_per_min:>9.2f}")
        print(f"    {'  loose ball':<18}{mid.loose_ball_share:>9.3f}")
        print(f"    {'tempo (passes/m)':<18}{mid.tempo:>9.2f}")
        print(f"    {'rhythm':<18}{mid.rhythm:>9.3f}")

        # An index that never moves cannot carry a narrative, however well
        # calibrated it is. This is the check that matters for stage (c).
        print("\n  dynamics over the match (settled window only)")
        print(f"  {'':<22}{'min':>8}{'max':>8}{'range':>8}{'sd':>8}")
        warm = snaps[8:]
        series = {
            "control (home)": [s.team(home.team_id).control for s in warm],
            "control (away)": [s.team(away.team_id).control for s in warm],
            "pressure (home)": [s.team(home.team_id).pressure for s in warm],
            "pressure (away)": [s.team(away.team_id).pressure for s in warm],
            "chaos": [s.chaos for s in warm],
            "tempo": [s.tempo for s in warm],
            "rhythm": [s.rhythm for s in warm],
        }
        for label, values in series.items():
            lo, hi = min(values), max(values)
            sd = statistics.pstdev(values)
            flag = "" if hi - lo > 0.10 else "   <- flat"
            print(f"  {label:<22}{lo:>8.3f}{hi:>8.3f}{hi - lo:>8.3f}{sd:>8.3f}{flag}")


if __name__ == "__main__":
    main(int(sys.argv[1]) if len(sys.argv) > 1 else 7)

