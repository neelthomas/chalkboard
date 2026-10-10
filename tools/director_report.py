"""
director_report.py - what reaches the screen, and what gets dropped.

A real feed cannot have three lower-thirds fighting for the same strip.
Packets contend for a safe area and the higher priority wins; the loser is
dropped rather than queued, because a stat bug about the 41st minute is
worthless at the 44th. Dropping is a decision, so it is counted.
"""

import sys
from collections import Counter

from chalkboard.director import Director
from chalkboard.fixtures import build_match
from chalkboard.ledger import build
from chalkboard.sim import MatchSimulator


def main(seed: int = 7) -> None:
    meta = build_match(seed)
    sim = MatchSimulator(meta)
    result = build(meta, sim.run(), keep=False)
    director = Director(meta)
    packets = director.direct(result.ledger)

    home, away = meta.teams
    print(f"--- seed {seed}: {home.short_name} {sim.score[home.team_id]}"
          f" - {sim.score[away.team_id]} {away.short_name} ---\n")
    print(f"  {'ledger claims':<22}{len(result.ledger):>8,}")
    print(f"  {'packets on screen':<22}{len(packets):>8,}")
    print(f"  {'dropped (contention)':<22}{director.dropped:>8,}")

    total_ms = sum(p.duration_ms for p in packets)
    match_ms = sum(i.duration_ms for i in meta.periods)
    print(f"  {'screen time':<22}{total_ms / 60000:>8.1f} min"
          f"  of {match_ms // 60000} min")

    for label, counts in [
        ("by overlay type", Counter(p.overlay_type.value for p in packets)),
        ("by safe area", Counter(p.render_hints.safe_area for p in packets)),
        ("by lens", Counter(p.lens.type.value for p in packets)),
    ]:
        print(f"\n  {label}")
        for key, n in counts.most_common():
            print(f"  {key:<22}{n:>8,}")

    print("\n  every packet carries provenance")
    unbacked = [p for p in packets if not p.evidence]
    print(f"  {'with ledger evidence':<22}{len(packets) - len(unbacked):>8,}"
          f" / {len(packets):,}")

    print("\n  highest-priority packets")
    for p in sorted(packets, key=lambda p: (-p.priority, p.valid_from_ms))[:4]:
        mins = p.valid_from_ms // 60000
        print(f"    [{p.packet_id}] prio {p.priority}  {mins:>3}'  "
              f"{p.overlay_type.value} / {p.render_hints.safe_area}")
        print(f"        {p.headline}  |  {p.body}")
        print(f"        lens={p.lens.type.value}:{p.lens.target_id}"
              f"  evidence={p.evidence}")
        print(f"        data={p.data}")


if __name__ == "__main__":
    main(int(sys.argv[1]) if len(sys.argv) > 1 else 7)
