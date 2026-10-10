"""
sim_report.py - realism diagnostics for the simulator.

Runs a full 90 minutes and streams it, so the numbers are measured rather
than extrapolated from a few minutes. Shots and goals are too rare for
extrapolation to mean anything.

Run after any change to the motion, possession or shooting model.

Reference ranges for professional football, rough targets rather than hard
truth - they vary by competition, season and provider:

    outfield distance      9-12 km per player
    mean in-play speed     1.3-1.8 m/s
    top speed              8-10 m/s
    passes                 800-1,100 per match, both teams
    pass completion        75-88%
    mean pass distance     15-20 m
    shots                  20-30 per match, both teams
    shots on target        ~35% of shots
    goals                  2-3.5 per match
"""

import math
import sys

from chalkboard.fixtures import build_match
from chalkboard.sim import MatchSimulator


def band(value: float, lo: float, hi: float) -> str:
    return "ok " if lo <= value <= hi else ("LOW" if value < lo else "HIGH")


def main(seed: int = 7) -> None:
    meta = build_match(seed)
    sim = MatchSimulator(meta)
    hz = meta.tracking_hz

    run: dict[str, float] = {}
    prev: dict[str, tuple[float, float]] = {}
    speed_sum = speed_n = at_rest = 0.0
    top_speed = 0.0
    ball_dist = 0.0
    prev_ball: tuple[float, float] | None = None
    bx_min, bx_max, bx_abs_sum, bx_n = 99.0, -99.0, 0.0, 0
    in_box_frames = 0
    frames = 0

    for f in sim.run():
        frames += 1
        for p in f.players:
            if p.player_id in prev:
                ox, oy = prev[p.player_id]
                run[p.player_id] = run.get(p.player_id, 0.0) + math.hypot(
                    p.pos.x - ox, p.pos.y - oy)
            prev[p.player_id] = (p.pos.x, p.pos.y)

        if f.seq % hz == 0:                      # sample speeds once a second
            for p in f.players:
                speed_sum += p.speed
                speed_n += 1
                if p.speed < 0.5:
                    at_rest += 1
                top_speed = max(top_speed, p.speed)

        bx, by = f.ball.pos.x, f.ball.pos.y
        if prev_ball is not None:
            ball_dist += math.hypot(bx - prev_ball[0], by - prev_ball[1])
        prev_ball = (bx, by)
        bx_min, bx_max = min(bx_min, bx), max(bx_max, bx)
        bx_abs_sum += abs(bx)
        bx_n += 1
        if abs(bx) >= 36.0 and abs(by) <= 20.16:
            in_box_frames += 1

    s = sim.stats
    outfield = [v for pid, v in run.items() if not pid.endswith("p01")]
    dist = sum(outfield) / len(outfield)
    mean_spd = speed_sum / speed_n
    completion = 100 * s["completed"] / max(s["passes"], 1)
    mean_pass = s["pass_distance_m"] / max(s["passes"], 1)
    on_target_pct = 100 * s["on_target"] / max(s["shots"], 1)

    home, away = meta.teams
    print(f"--- seed {meta.seed}: {home.short_name} {sim.score[home.team_id]}"
          f" - {sim.score[away.team_id]} {away.short_name}"
          f"  ({frames:,} frames) ---\n")

    rows = [
        ("outfield distance", f"{dist:8,.0f} m", band(dist, 9000, 12000), "9-12 km"),
        ("mean speed",        f"{mean_spd:8.1f} m/s", band(mean_spd, 1.3, 1.8), "1.3-1.8"),
        ("top speed",         f"{top_speed:8.1f} m/s", band(top_speed, 8.0, 10.0), "8-10"),
        ("passes (both)",     f"{s['passes']:8,.0f}", band(s["passes"], 800, 1100), "800-1,100"),
        ("completion",        f"{completion:7.1f} %", band(completion, 75, 88), "75-88%"),
        ("mean pass",         f"{mean_pass:8.1f} m", band(mean_pass, 15, 20), "15-20 m"),
        ("shots (both)",      f"{s['shots']:8,.0f}", band(s["shots"], 20, 30), "20-30"),
        ("on target",         f"{on_target_pct:7.0f} %", band(on_target_pct, 28, 45), "~35%"),
        ("goals",             f"{s['goals']:8,.0f}", band(s["goals"], 2, 4), "2-3.5"),
        ("xG (both)",         f"{s['xg']:8.2f}", band(s["xg"], 2.0, 3.5), "2-3.5"),
    ]
    for label, value, verdict, target in rows:
        print(f"  {label:<20} {value:>13}   {verdict}   (target {target})")

    print(f"\n  {'ball travelled':<20} {ball_dist:10,.0f} m")
    print(f"  {'ball x range':<20} {bx_min:10.1f} to {bx_max:.1f}")
    print(f"  {'ball mean |x|':<20} {bx_abs_sum / bx_n:10.1f} m from centre")
    print(f"  {'time in a box':<20} {100 * in_box_frames / frames:10.1f} %")
    print(f"  {'standing still':<20} {100 * at_rest / speed_n:10.1f} %")


if __name__ == "__main__":
    main(int(sys.argv[1]) if len(sys.argv) > 1 else 7)
