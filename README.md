# Chalkboard

**Explainable match intelligence from synthetic football data.**

Entry for *Inside the Game: Developer Hackathon* (Microsoft × Premier League).
Submissions close **27 October 2026**.

---

## The idea

Football narrative today is one of two broken things. **Stats dumps** are
accurate, traceable and unreadable. **LLM prose** is fluent, engaging, and
quietly making things up.

Chalkboard is the third thing: prose as traceable as a stats table. A
deterministic metrics engine computes what is true; a **Fact Ledger** records
each claim with pointers to the exact tracking frames and events behind it;
an adversarial **Verifier** rejects any sentence the ledger does not support.

Click any sentence in the narrative and the events behind it light up on the
pitch.

Because the data is synthetic, there is ground truth — so Chalkboard measures
and reports its own hallucination rate, which is the metric that currently
keeps AI narrative out of broadcast.

---

## Status

| Component | State |
|---|---|
| Four data contracts | ✅ done, tested |
| Match fixtures (fictional clubs) | ✅ done, tested |
| Tracking simulator | ✅ motion, possession, shooting, goals, restarts |
| Football maths (`football.py`) | ✅ xG, angles, progressive, pass difficulty |
| Match viewer | ✅ `python -m chalkboard.viewer` |
| Metrics engine | ⬜ **next** — `TrackingFrame` → `MatchEvent` |
| Control / pressure / rhythm metrics | ⬜ brief (iv) |
| Fact Ledger | ⬜ |
| Agents (Scout / Analyst / Verifier / Storyteller / Director / Producer) | ⬜ |
| Overlay renderer + frontend | ⬜ |
| Eval harness | ⬜ |
| Azure deployment (`azd up`) | ⬜ |

---

## Quick start

```bash
pip install -e ".[dev]"
pytest
python -m chalkboard.fixtures     # print the two squads
```

A full 90-minute match generates in about 20 seconds, so the same seed can be
replayed instantly during development and streamed at 1× for the demo.

### Watch a match

```bash
python -m chalkboard.viewer                   # 10 min of seed 7
python -m chalkboard.viewer --seed 12 --full  # whole match
```

Writes a self-contained HTML file to `out/` and opens it. No server, no
dependencies — the data is embedded, so the file can be sent to someone.
Space plays and pauses, arrow keys step frame by frame, hover for pace.

### Is the football plausible?

```bash
python tools/sim_report.py
```

Measured over a full 90 minutes, not extrapolated — shots and goals are too
rare for extrapolation to mean anything. Seed 7:

| | Chalkboard | Target |
|---|---|---|
| Outfield distance | 9,782 m | 9–12 km |
| Mean speed | 1.6 m/s | 1.3–1.8 |
| Top speed | 8.2 m/s | 8–10 |
| Passes, both teams | 1,018 | 800–1,100 |
| Completion | 85.0 % | 75–88 % |
| Mean pass | 19.3 m | 15–20 m |
| Shots, both teams | 35 | 20–30 |
| On target | 46 % | ~35 % |
| Goals | 4 | 2–3.5 |
| xG, both teams | 2.64 | 2–3.5 |

Caveat worth stating: those targets are *match-average* figures being applied
to single matches, which is statistically the wrong comparison. Real matches
vary enormously — 0–0 and 5–0 are both ordinary results. Seed-to-seed spread
of goals and xG is expected, and a seed landing outside a band is not by
itself a bug. Run several seeds (`python tools/sim_report.py 21`) before
concluding anything.

`tests/test_simulator.py` holds looser versions of these bands as regression
tests. One of them exists for a specific reason: positional noise was
originally resampled every tick, which at 25 Hz pinned all 22 players at a
permanent 5.1 m/s sprint and produced 28 km per player per 90. It passed every
functional test. It took one look at the viewer to spot.

---

## Layout

```
src/chalkboard/
  contracts.py      the four data contracts - read this first
  football.py       pure football maths: xG, angles, pass difficulty
  fixtures.py       deterministic MatchMeta, fictional clubs and players
  sim/engine.py     tracking simulator
  viewer.py         self-contained HTML match viewer
tools/sim_report.py realism diagnostics
tests/              52 tests
```

`football.py` is deliberately separate and free of randomness and I/O. The
simulator and the metrics engine both import it, so a shot's xG is computed
by exactly one function — which is what makes a ledger claim citing
`shot_quality@0.1` reproducible years later.

### The four contracts

| Contract | Written by → read by |
|---|---|
| `TrackingFrame` | simulator → metrics engine |
| `MatchEvent` | metrics engine → Scout, Analyst |
| `LedgerEntry` | Analyst → Verifier, Storyteller |
| `OverlayPacket` | Director → frontend / rendering partner |

Conventions (metres, origin at the centre spot, `seq` as the only sort key)
are documented at the top of `contracts.py`.

---

## How this maps to the challenge brief

*Judging criterion 5 is "Adherence to Hackathon Category" at 20%. This table
is the answer to it — keep it current.*

| Brief | Requirement | Where |
|---|---|---|
| (a) | **Ingest** synthetic match events as they happen | `sim/engine.py` → Event Hubs |
| (b) | **Interpret** into statistics, patterns and context | metrics engine |
| (c) | **Explain** why a moment matters | Analyst + Fact Ledger |
| (d) | **Render** on screen alongside the match | `OverlayPacket` + frontend |
| (e) | **Personalize** — analyst vs casual fan | `Lens` (player / club / metric × depth) |
| (ii) | Player identification, pass quality, speed metrics | tracking-level simulation |
| (iii) | Narrative generation, milestones, recaps | Storyteller |
| (iv) | Explainability: control vs chaos, pressure, rhythm | named metrics in the engine |
| (v) | Data innovation: synthetic football-realistic datasets | `sim/` — open-sourced |
| (vi) | Multi-language storytelling | `OverlayPacket.locale` |

---

## Two rules that constrain the code

1. **No third-party trademarks** (rules §4.4). Every club, player, venue and
   competition name is invented and lives in `fixtures.py`. `test_fixtures.py`
   has a tripwire, but the real check is a human read before the video is cut.
2. **No real match footage** (rules §4.7). Any computer-vision work runs over
   our own rendered match view, which we own outright.

---

## Development notes

**Model response cache.** The simulator is seeded and deterministic, so every
LLM call is cached on `(match_seed, event_id, agent, prompt_hash)` under
`.cache/`. After one full run, iterating on the frontend or the demo script
costs nothing. Do not skip this — without it you will re-run the same match
fifty times while tuning the UI and pay for every one.

**Local first, deploy late.** Everything runs locally; the only remote
dependency is the model endpoint. Infrastructure is written as code from the
start but deployed near the end.
