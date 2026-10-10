"""
ledger_report.py - what the Fact Ledger holds after a match.

Shows the claim mix, supersession, provenance depth, and a sample of what
a recap would actually read from - the claims still standing at full time,
rather than everything ever asserted.
"""

import sys

from chalkboard.contracts import ClaimType
from chalkboard.fixtures import build_match
from chalkboard.ledger import build
from chalkboard.sim import MatchSimulator


def main(seed: int = 7) -> None:
    meta = build_match(seed)
    sim = MatchSimulator(meta)
    result = build(meta, sim.run())
    ledger = result.ledger

    home, away = meta.teams
    print(f"--- seed {seed}: {home.short_name} {sim.score[home.team_id]}"
          f" - {sim.score[away.team_id]} {away.short_name} ---\n")

    s = ledger.summary()
    print(f"  {'claims':<22}{s['total']:>8,}")
    print(f"  {'superseded':<22}{s['superseded']:>8,}")
    print(f"  {'evidence refs/claim':<22}{s['mean_evidence_refs']:>8.1f}")
    print(f"  {'events detected':<22}{len(result.events):>8,}")
    print(f"  {'index snapshots':<22}{len(result.snapshots):>8,}")

    print("\n  by claim type")
    for kind, n in sorted(s["by_type"].items(), key=lambda kv: -kv[1]):
        print(f"  {kind:<22}{n:>8,}")

    print("\n  by method")
    methods: dict[str, int] = {}
    for e in ledger:
        methods[e.method] = methods.get(e.method, 0) + 1
    for method, n in sorted(methods.items(), key=lambda kv: -kv[1]):
        print(f"  {method:<22}{n:>8,}")

    # Provenance: a claim is only worth anything if it reaches the frames.
    print("\n  provenance")
    no_evidence = [e for e in ledger if not e.evidence]
    reaches = sum(1 for e in ledger
                  if ledger.trace(e.ledger_id)["frames"]
                  or ledger.trace(e.ledger_id)["events"])
    print(f"  {'claims with evidence':<22}{len(ledger) - len(no_evidence):>8,}"
          f" / {len(ledger):,}")
    print(f"  {'traceable to tracking':<22}{reaches:>8,} / {len(ledger):,}")

    # What a full-time recap would read.
    end = max(e.t_ms for e in ledger)
    standing = ledger.active_at(end, period=2)
    patterns = [e for e in standing if e.claim_type is ClaimType.PATTERN]
    print(f"\n  still standing at full time (period 2): {len(standing)}")
    print(f"    of which patterns: {len(patterns)}")

    print("\n  sample claims")
    goals = ledger.query(claim_type=ClaimType.METRIC)
    shown = 0
    for e in goals:
        if "scored" in e.claim and shown < 3:
            print(f"    [{e.ledger_id}] {e.period}H {e.t_ms // 60000:>2}'  "
                  f"{e.claim}")
            tr = ledger.trace(e.ledger_id)
            print(f"        method={e.method}  evidence: "
                  f"{len(tr['events'])} event(s), frames {sorted(tr['frames'])}")
            shown += 1

    for kind in (ClaimType.PATTERN, ClaimType.COMPARISON, ClaimType.MILESTONE):
        found = ledger.query(claim_type=kind)
        if found:
            e = found[len(found) // 2]
            print(f"\n    [{e.ledger_id}] {kind.value}  "
                  f"{e.period}H {e.t_ms // 60000:>2}'")
            print(f"        {e.claim}")
            print(f"        method={e.method}"
                  + (f"  supersedes={e.supersedes}" if e.supersedes else ""))


if __name__ == "__main__":
    main(int(sys.argv[1]) if len(sys.argv) > 1 else 7)
