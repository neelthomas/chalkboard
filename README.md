# Chalkboard

**Explainable match intelligence from synthetic football data.**

Entry for *Inside the Game: Developer Hackathon* (Microsoft x Premier League).
Submissions close **27 October 2026**.

> This file is kept in plain ASCII on purpose. Editing it through tools that
> re-encode UTF-8 has already corrupted it once, and a README that renders as
> mojibake is a bad first impression for a judge. `tools/fix_encoding.py`
> enforces the same rule across the source tree.

---

## The idea

Football narrative today is one of two broken things. **Stats dumps** are
accurate, traceable and unreadable. **LLM prose** is fluent, engaging, and
quietly making things up.

Chalkboard is the third thing: prose as traceable as a stats table. A
deterministic metrics engine computes what is true; a **Fact Ledger** records
each claim with pointers to the exact tracking frames and events behind it;
an adversarial **Verifier** rejects any sentence the ledger does not support.

Click any claim and the evidence behind it lights up on the pitch.

Because the data is synthetic there is ground truth, so Chalkboard can measure
its own accuracy - and will measure its own hallucination rate, which is the
metric that currently keeps AI narrative out of broadcast.

---

## Status

| Component | State | |
|---|---|---|
| Four data contracts | **done** | tested |
| Match fixtures (fictional clubs) | **done** | tested |
| Tracking simulator | **done** | motion, possession, shooting, goals, restarts |
| Football maths (`football.py`) | **done** | xG, angles, progressive, pass difficulty |
| Metrics engine | **done** | `TrackingFrame` -> `MatchEvent`, 100% recall |
| Control / pressure / rhythm indices | **done** | brief (iv) |
| Fact Ledger + deterministic claims | **done** | ~290 claims/match, all traceable |
| Director + overlay packets | **done** | brief (d) |
| Viewer with clickable provenance | **done** | the demo's centrepiece |
| Player-focused mode | **done** | brief (e) |
| Multi-language storytelling | **done** | brief (vi) - English, Spanish, French |
| Analyst / Verifier / Storyteller agents | - | needs a model endpoint |
| Eval harness (hallucination rate) | - | needs the agents |
| Azure deployment (`azd up`) | - | |

163 tests.

---

## Quick start

```bash
pip install -e ".[dev]"
pytest
python -m chalkboard.fixtures     # print the two squads
```

A full 90-minute match generates in about 20 seconds, so the same seed can be
replayed instantly during development and streamed at 1x for the demo.

### Watch a match

```bash
python -m chalkboard.viewer                       # 10 min of seed 7
python -m chalkboard.viewer --seed 2 --full --hz 10   # the demo match
python -m chalkboard.viewer --minutes 30 --hz 8
```

**Seed 2 is the demo match**: Rivermead Athletic 4-1 Ashcombe Rovers, goals at
14', 23', 41', 82' and 83'. Picked by `tools/pick_demo_seed.py`, which scans
seeds and scores them on whether they are worth filming - both teams scoring,
goals in both halves, a late goal, enough shots for the overlays to have work
to do. A 0-0 makes the system look like it has nothing to say.

Writes a self-contained HTML file to `out/` and opens it. No server, no
dependencies - the data is embedded, so the file can be sent to someone.

The claim feed sits beside the pitch. **Click any claim and the match seeks to
the moment it describes, the players it is about are ringed, and the pass or
shot behind it is drawn on the pitch.** That is the whole argument of the
project made visible: the sentence is not a story about the match, it is a
pointer into it.

Space plays and pauses, arrow keys step frame by frame, hover for pace.

---

## Layout

```
src/chalkboard/
  contracts.py        the four data contracts - read this first
  football.py         pure football maths: xG, angles, pass difficulty
  language.py         claim templates per locale          brief (vi)
  fixtures.py         deterministic MatchMeta, fictional clubs and players
  sim/engine.py       tracking simulator                   brief (a)
  metrics/events.py   frames -> MatchEvents                brief (b)
  metrics/indices.py  control, pressure, rhythm            brief (iv)
  metrics/pipeline.py one streaming pass over a match
  ledger/store.py     the Fact Ledger                      brief (c)
  ledger/claims.py    deterministic claim builders
  ledger/build.py     frames -> populated ledger
  director.py         ledger -> OverlayPackets             brief (d)
  viewer.py           self-contained HTML match viewer
tools/
  sim_report.py       realism diagnostics
  metrics_report.py   detection accuracy vs ground truth
  ledger_report.py    claim mix, supersession, provenance
  director_report.py  what reaches the screen, and what is dropped
  pick_demo_seed.py   score seeds on whether they are worth filming
  fix_encoding.py     keep the tree pure ASCII
docs/
  submission.md       everything needed for the hackathon entry
  demo-script.md      shot list and narration for the demo video
```

`football.py` is deliberately separate and free of randomness and I/O. The
simulator and the metrics engine both import it, so a shot's xG is computed by
exactly one function - which is what makes a ledger claim citing
`shot_quality@0.1` reproducible years later.

### The four contracts

| Contract | Written by -> read by |
|---|---|
| `TrackingFrame` | simulator -> metrics engine |
| `MatchEvent` | metrics engine -> Analyst |
| `LedgerEntry` | Analyst -> Verifier, Storyteller |
| `OverlayPacket` | Director -> frontend / rendering partner |

Conventions (metres, origin at the centre spot, `seq` as the only sort key)
are documented at the top of `contracts.py`.

---

## Is the football plausible?

```bash
python tools/sim_report.py 7
```

Measured over a full 90 minutes, not extrapolated - shots and goals are too
rare for extrapolation to mean anything. Seed 7:

| | Chalkboard | Target |
|---|---|---|
| Outfield distance | 9,782 m | 9-12 km |
| Mean speed | 1.6 m/s | 1.3-1.8 |
| Top speed | 8.2 m/s | 8-10 |
| Passes, both teams | 1,018 | 800-1,100 |
| Completion | 85.0 % | 75-88 % |
| Mean pass | 19.3 m | 15-20 m |
| Shots, both teams | 35 | 20-30 |
| On target | 46 % | ~35 % |
| Goals | 4 | 2-3.5 |
| xG, both teams | 2.64 | 2-3.5 |

Caveat worth stating: those targets are *match-average* figures applied to
single matches, which is statistically the wrong comparison. Real matches vary
enormously - 0-0 and 5-0 are both ordinary results. Seed-to-seed spread is
expected, and a seed outside a band is not by itself a bug. Run several seeds
before concluding anything.

`tests/test_simulator.py` holds looser versions of these bands as regression
tests. One exists for a specific reason: positional noise was originally
resampled every tick, which at 25 Hz pinned all 22 players at a permanent
5.1 m/s sprint and produced 28 km per player per 90. It passed every
functional test. It took one look at the viewer to spot.

---

## The metrics engine

```bash
python tools/metrics_report.py 7
```

The detector reads `TrackingFrame`s and nothing else. It never imports the
simulator - a test enforces that - so the same code would run unchanged over a
real tracking feed.

### Does it actually work?

The simulator counted every pass, shot and goal as it produced them. The
detector has to work the same facts out from scratch. On a real feed you can
never grade your own event detection, because nobody knows the right answer.
Here we do:

| | truth | detected | recall |
|---|---|---|---|
| Passes | 1,057 | 1,057 | 100% |
| Completed | 877 | 877 | 100% |
| Shots | 25 | 25 | 100% |
| On target | 11 | 11 | 100% |
| Blocked | 7 | 7 | 100% |
| Goals | 2 | 2 | 100% |
| xG | 1.85 | 1.85 | 99.8% |

Holds across seeds. The occasional missing pass is one still in flight at the
final whistle.

**This is the argument for synthetic data, and it is the same mechanism that
will later measure the narrative layer's hallucination rate.**

### How a shot is detected

Not by aiming at the goal. A flight ends either with a new owner at the ball -
a pass - or with the ball jumping discontinuously, which means it went dead.
Where play then restarts says what happened: from the centre spot means a goal
was scored; from the edge of the goal area means saved, blocked or missed.
That is the inference a human analyst makes from a tracking feed, and it needs
no privileged knowledge.

### The three indices

Brief (iv) names its own primitives - "control vs. chaos, tactical pressure
changes, and game rhythm patterns" - so those are the names used.

None are published metrics. They are our own composites, which is exactly why
each is defined in one place, versioned as `indices@0.1`, and **reports its
components alongside its score**. A snapshot saying only "control 0.71" would
be useless to the Analyst: it could state the number but not say why.

Measured dynamic range over one match - an index that never moves cannot carry
a narrative, however well calibrated:

| Index | Range | sd |
|---|---|---|
| control | 0.07 - 0.93 | 0.15 |
| rhythm | 0.02 - 0.81 | 0.22 |
| chaos | 0.27 - 0.58 | 0.05 |
| tempo | 7.0 - 15.0 /min | 1.5 |
| pressure | 0.23 - 0.45 | 0.04 |

---

## The Fact Ledger

```bash
python tools/ledger_report.py 7
```

Append-only. Every entry is one atomic, evidence-backed claim. The Storyteller
may not write a sentence that is not backed by an entry here, and the Verifier
is the gate that enforces it.

| | |
|---|---|
| Claims per match | 290 |
| Superseded | 71 |
| Evidence refs per claim | 1.8 |
| With evidence | 290 / 290 |
| Traceable to tracking | 290 / 290 |

### Claims are populated deterministically first

No model call is involved. That ordering is deliberate: **the whole pipeline
works, and is verifiable, before an LLM is involved anywhere.** The Analyst
will later add causal claims on top - "because the press moved eight metres
higher" - and those are the ones that actually need reasoning. Everything here
is arithmetic, and arithmetic should never be delegated to a language model.

### Claim text is deliberately flat

> Hiro Lefevre scored for Calderwick City from 20.9 m, a chance worth 0.09
> expected goals.

That is a fact. Making it read well is the Storyteller's job. Keeping voice out
of the ledger is what lets one entry serve a casual fan, an analyst and a
broadcast caption without being rewritten - and what lets the Verifier check it
against *evidence* rather than against prose.

### Claims expire

"Calderwick City are controlling the game" is true at 41' and false at 75'.
Each new control claim supersedes the last, and `active_at(t)` answers what was
still standing at a given moment.

Across a match: **108 pattern claims asserted, 3 still standing at full time.**
Without that, a recap assembles a story out of stale facts and contradicts
itself - which you would discover the night before the video.

---

## The Director

```bash
python tools/director_report.py 7
```

Stage (d) asks for insight "timed and machine-readable enough to be rendered as
synchronized graphical overlays on a live match feed". So the Director does not
produce pictures. It produces instructions: which graphic, carrying which
numbers, on screen from when until when, at what priority. A rendering partner
binds those to its own templates.

That is why `OverlayPacket` keeps `data` separate from the text. Ship a
pre-formatted sentence and the packet is only renderable as a caption.

| | |
|---|---|
| Ledger claims | 290 |
| Packets on screen | 248 |
| Dropped to contention | 42 |
| Screen time | 22.3 min of 90 |
| Carrying provenance | 248 / 248 |

A real feed cannot have two lower-thirds fighting for the same strip, so
packets contend for a safe area and the higher priority keeps the slot. The
loser is dropped rather than queued, because a stat bug about the 41st minute
is worthless at the 44th. **Dropping is a decision, so it is counted.**

`Director(meta, require_verified=True)` refuses to emit anything the Verifier
has not passed. That switch is how the agent layer plugs in without the render
path changing.

---

## Personalisation and language

Brief (e) asks that the same intelligence reach "a data-hungry analyst and a
casual fan as two genuinely different experiences", and names **player
focused mode** specifically. Brief (vi) asks for multi-language output.

Both are in the viewer, and neither needs a model.

### Player-focused mode

Pick a player from the Focus menu. The claim feed filters to claims about
them, they are ringed on the pitch and everyone else dims, and a live strip
shows distance covered, top speed and current speed.

It is the same ledger read through one lens, not a separate system. Every
`OverlayPacket` already carries a `Lens` (player, club or metric), so a
rendering partner can filter the same feed the same way.

### Multi-language

A ledger entry stores a **template key and parameters**, not a finished
sentence, so one fact renders into any locale at the point it reaches a
screen:

| | |
|---|---|
| en-GB | Omar Hartnell scored for Rivermead Athletic from 20.8 m, a chance worth 0.09 expected goals. |
| es-ES | Omar Hartnell marco para Rivermead Athletic desde 20,8 m, una ocasion de 0,09 goles esperados. |
| fr-FR | Omar Hartnell a marque pour Rivermead Athletic a 20,8 m, une occasion valant 0,09 buts attendus. |

Note the decimal commas - a Spanish caption reading "20.8 m" looks wrong to
the audience it is for.

Two design notes. Each **shape** of claim is a whole sentence per locale
rather than assembled fragments, because gluing "a 27 m pass" to "past 6
opponents" works in English and produces broken grammar in languages where
the clauses inflect. And the English text stored on the entry is **rendered
from the same template**, so the stored sentence and the localised one
cannot drift apart. Adding a locale is adding one dict.

---

## How this maps to the challenge brief

*Judging criterion 5 is "Adherence to Hackathon Category" at 20%. This table is
the answer to it - keep it current.*

| Brief | Requirement | State |
|---|---|---|
| (a) | **Ingest** synthetic match events as they happen | **done** - `sim/engine.py` |
| (b) | **Interpret** into statistics, patterns and context | **done** - `metrics/events.py` |
| (c) | **Explain** why a moment matters | *part* - Ledger done, Analyst pending |
| (d) | **Render** on screen alongside the match | **done** - `director.py` + viewer |
| (e) | **Personalize** - analyst vs casual fan | **done** - player-focused mode, club and metric lenses |
| (ii) | Player identification, pass quality, speed metrics | **done** - tracking-level sim |
| (iii) | Narrative generation, milestones, recaps | *part* - milestones done |
| (iv) | Explainability: control vs chaos, pressure, rhythm | **done** - `metrics/indices.py` |
| (v) | Data innovation: synthetic football-realistic datasets | **done** - `sim/`, open-sourced |
| (vi) | Multi-language storytelling | **done** - `language.py`, 3 locales |

---

## Two rules that constrain the code

1. **No third-party trademarks** (rules 4.4). Every club, player, venue and
   competition name is invented and lives in `fixtures.py`. `test_fixtures.py`
   has a tripwire, but the real check is a human read before the video is cut.
2. **No real match footage** (rules 4.7). Any computer-vision work runs over
   our own rendered match view, which we own outright.

---

## Development notes

**Model response cache.** The simulator is seeded and deterministic, so every
LLM call will be cached on `(match_seed, event_id, agent, prompt_hash)` under
`.cache/`. After one full run, iterating on the frontend or the demo script
costs nothing. Do not skip this - without it you will re-run the same match
fifty times while tuning the UI and pay for every one.

**Local first, deploy late.** Everything runs locally; the only remote
dependency will be the model endpoint. Infrastructure is written as code from
the start but deployed near the end.

**Keep the tree ASCII.** `python tools/fix_encoding.py --check` fails if any
source file carries a BOM or a non-ASCII byte. Non-ASCII output belongs in
escapes the language understands.
