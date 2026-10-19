"""
pick_demo_seed.py - find a match worth filming.

The demo video is 20% of the score and runs for under two minutes, so the
match behind it is not a neutral choice. A 0-0 with four tame shots makes
the system look like it has nothing to say. What the video needs is a
scoreline with something happening, goals spread across both halves rather
than bunched, and enough shots that the overlays have work to do.

This scores seeds on those properties and ranks them. It runs the simulator
only - no ledger, no director - because that is the cheap pass and it is
enough to shortlist.

    python tools/pick_demo_seed.py            scan seeds 1-24
    python tools/pick_demo_seed.py 40         scan seeds 1-40
"""

import sys
import time

from chalkboard.fixtures import build_match
from chalkboard.sim import MatchSimulator


def minutes_of_goals(meta, sim_score_history):
    return sim_score_history


def score_match(goals_home, goals_away, goal_mins, shots, xg) -> tuple[float, str]:
    """Higher is better for a demo. Returns (score, one-line reason)."""
    total = goals_home + goals_away
    notes = []
    s = 0.0

    # A scoreline with something in it, but not a farce.
    if 3 <= total <= 6:
        s += 3.0
        notes.append(f"{total} goals")
    elif total == 2:
        s += 1.5
        notes.append("2 goals")
    elif total > 6:
        s += 0.5
        notes.append(f"{total} goals (chaotic)")
    else:
        notes.append(f"only {total}")

    # Both teams scoring gives the narrative two sides.
    if goals_home and goals_away:
        s += 2.0
        notes.append("both scored")

    # Goals in both halves - the viewer should not peak in the first ten
    # minutes and then coast.
    first = [m for m in goal_mins if m <= 45]
    second = [m for m in goal_mins if m > 45]
    if first and second:
        s += 2.0
        notes.append("goals in both halves")

    # A late goal is the single best thing a two-minute edit can end on.
    if any(m >= 70 for m in goal_mins):
        s += 1.5
        notes.append("late goal")

    # Enough shots that the overlay layer has traffic.
    if 22 <= shots <= 40:
        s += 1.0
        notes.append(f"{shots} shots")
    elif shots < 15:
        s -= 1.0
        notes.append(f"only {shots} shots")

    # A close game beats a procession.
    if abs(goals_home - goals_away) <= 1 and total >= 3:
        s += 1.0
        notes.append("close")

    return s, ", ".join(notes)


def main(limit: int = 24) -> None:
    rows = []
    started = time.time()

    for seed in range(1, limit + 1):
        meta = build_match(seed)
        sim = MatchSimulator(meta)
        home, away = meta.teams
        prev = dict(sim.score)
        goal_mins: list[int] = []

        for f in sim.run():
            if sim.score != prev:
                prev = dict(sim.score)
                goal_mins.append(f.t_ms // 60000 + (0 if f.period == 1 else 45))

        gh, ga = sim.score[home.team_id], sim.score[away.team_id]
        s, why = score_match(gh, ga, goal_mins, int(sim.stats["shots"]),
                             sim.stats["xg"])
        rows.append((s, seed, home.short_name, gh, ga, away.short_name,
                     goal_mins, int(sim.stats["shots"]), sim.stats["xg"], why))
        print(f"  seed {seed:>3}  {home.short_name} {gh}-{ga} {away.short_name}"
              f"   score {s:4.1f}   {why}", flush=True)

    rows.sort(reverse=True)
    print(f"\n  scanned {limit} seeds in {time.time() - started:.0f}s\n")
    print("  === best candidates for the demo ===")
    for s, seed, hs, gh, ga, as_, mins, shots, xg, why in rows[:5]:
        goals = ", ".join(f"{m}'" for m in mins) or "none"
        print(f"\n  seed {seed}:  {hs} {gh} - {ga} {as_}    (score {s:.1f})")
        print(f"     goals at {goals}")
        print(f"     {shots} shots, xG {xg:.2f}")
        print(f"     {why}")


if __name__ == "__main__":
    main(int(sys.argv[1]) if len(sys.argv) > 1 else 24)
