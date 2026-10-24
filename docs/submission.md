# Submission pack

Everything needed to fill in the Innovation Studio project page, in one
place. Copy straight from here.

**Deadline: 27 October 2026.** All project page fields stay editable until
submissions close, so create the page first and refine it afterwards.

---

## Checklist

| Requirement | Rule | State |
|---|---|---|
| Newly built project, created after 29 Sep | 4.3 | done - repo created 19 Oct |
| Public GitHub repository | 4.4 | done - https://github.com/neelthomas/chalkboard |
| Project page created and linked to the Challenge | 4.4 | **outstanding** |
| Project pitch / description | 4.4 | ready, below |
| Demo video under 2:00, public URL | 4.4 | **outstanding** - see demo-script.md |
| Synthetic data only, no real footage | 4.7 | done - all fixtures invented |
| No third-party trademarks | 4.4 | done in code; **check the video before upload** |

### Brief coverage

| | | |
|---|---|---|
| (a) Ingest | done | tracking simulator at 25 Hz |
| (b) Interpret | done | 100% detection recall against ground truth |
| (c) Explain | part | Fact Ledger done, Analyst agent not built |
| (d) Render | done | overlay packets + viewer |
| (e) Personalize | done | player-focused mode, club and metric lenses |
| (ii) Metrics | done | speed, distance, pass difficulty, xG |
| (iii) Narrative | part | milestones and recaps from templates |
| (iv) Explainability | done | control vs chaos, pressure, rhythm |
| (v) Data innovation | done | the simulator, open-sourced |
| (vi) Multi-language | done | English, Spanish, French |

Eight of ten fully, two partial. Both partials are the same gap: no model
endpoint, so no Analyst. See below.

---

## Form fields

### Title

```
Chalkboard - Explainable Match Intelligence from Synthetic Football Data
```

### Short description (300 character limit, 296 used)

```
Every sentence, traceable to the frame it came from. Chalkboard turns synthetic football tracking into match narrative you can verify: a deterministic metrics engine computes what is true, a Fact Ledger records each claim with its evidence, and clicking any sentence lights up the tracking behind it.
```

### Keywords

```
agentic-ai
explainable-ai
synthetic-data
football-analytics
tracking-data
broadcast-graphics
expected-goals
real-time
azure
python
```

### Challenge

The Synthetic Match Insights Engine for Premier League Studio

*(the only challenge in this hackathon)*

### Writing Code

Yes

### Code Repository

```
https://github.com/neelthomas/chalkboard
```

### Skills Needed

Open to others: your call. Note the prize maths - the Grand Prize ARV range
of $5,050 to $20,200 is exactly 1x to 4x $5,050, so **per-member value is
constant**. Adding teammates multiplies the pot rather than splitting it.
Team cap is four.

If you open it, the gaps worth asking for are:

```
Azure AI Foundry
Agent orchestration
Front-end / data visualisation
Video production
```

Video production is the one to actually want - the demo is 20% of the score.

### Description

````markdown
## The problem

Football narrative today is one of two broken things. **Stats dumps** are
accurate, traceable and unreadable. **LLM prose** is fluent, engaging, and
quietly making things up. No broadcaster can ship a system that invents a
cross that never happened.

Chalkboard is the third thing: prose as traceable as a stats table.

## How it works

A **tracking simulator** emits 22 players and the ball at 25 Hz. A
**deterministic metrics engine** derives events from those frames alone and
computes what is true. A **Fact Ledger** records each claim as an atomic
assertion with pointers back to the exact frames and events behind it. A
**Director** turns surviving claims into timed, machine-readable overlay
packets a broadcast rendering partner can bind to its own graphics.

Click any claim in the viewer and the match seeks to that moment, the players
it is about are ringed, and the pass or shot behind it is drawn on the pitch.
The sentence is not a story about the match - it is a pointer into it.

## Why synthetic data is the point, not a constraint

Because the simulator knows what actually happened, detection accuracy is
measurable. On a real feed you can never grade your own event detection,
because nobody knows the right answer.

The detector reads tracking frames and nothing else. It never imports the
simulator - a test enforces that - so the same code would run unchanged over
a real tracking feed. Measured against ground truth over a full 90 minutes:

| | truth | detected | recall |
|---|---|---|---|
| Passes | 1,057 | 1,057 | 100% |
| Completed | 877 | 877 | 100% |
| Shots | 25 | 25 | 100% |
| On target | 11 | 11 | 100% |
| Goals | 2 | 2 | 100% |
| xG | 1.85 | 1.85 | 99.8% |

The same mechanism measures the narrative layer's hallucination rate - the
metric that currently keeps AI narrative out of broadcast.

## Explainability

Brief (iv) names its own primitives - control vs chaos, tactical pressure
changes, game rhythm - so those are the names used. None are published
metrics, which is exactly why each is defined in one place, versioned, and
**reports its components alongside its score**. A snapshot saying only
"control 0.71" would be useless: it could state the number but not say why.

Claims expire. "Rivermead Athletic are controlling the game" is true at 41'
and false at 75'. Each new claim supersedes the last, so a recap never
assembles a story out of stale facts. Across a match: 108 pattern claims
asserted, 3 still standing at full time.

## Verification

Claim text in the ledger is deliberately flat. Making it read well is the
narrative layer's job. Keeping voice out of the ledger lets one entry serve a
casual fan, an analyst and a broadcast caption without rewriting - and lets
the Verifier check claims against **evidence** rather than against prose.

The render path is already gated on it: `Director(require_verified=True)`
emits nothing the Verifier has not passed.

## Made for one fan, in their language

Pick a player and the whole system reframes around them: the claim feed
filters to claims about that player, they are highlighted on the pitch all
match, and a live strip tracks distance covered, top speed and current pace.
It is the same ledger read through one lens - every overlay packet already
carries a lens of player, club or metric, so a rendering partner can filter
the same feed the same way.

Claims are stored as a **template key and parameters**, not as finished
sentences, so one fact renders into any locale at the point it reaches a
screen:

| | |
|---|---|
| en-GB | Omar Hartnell scored for Rivermead Athletic from 20.8 m, a chance worth 0.09 expected goals. |
| es-ES | Omar Hartnell marco para Rivermead Athletic desde 20,8 m, una ocasion de 0,09 goles esperados. |
| fr-FR | Omar Hartnell a marque pour Rivermead Athletic a 20,8 m, une occasion valant 0,09 buts attendus. |

Including the decimal commas - a Spanish caption reading "20.8 m" looks
wrong to the audience it is for. Adding a language is adding one dictionary.

## Data

All data is synthetic and football-realistic. Every club, player and venue
name is invented. No real match data or footage is used anywhere.

## Engineering

163 tests. Deterministic and seeded - the same seed replays the same match
exactly, which is what makes the accuracy figures above reproducible rather
than anecdotal.
````

---

## Demo match

**Seed 2: Rivermead Athletic 4 - 1 Ashcombe Rovers.** Chosen by
`tools/pick_demo_seed.py`, which scores seeds on whether they are worth
filming.

| | |
|---|---|
| Goals | 14' RVM, 23' ASH, 41' RVM, 82' RVM, 83' RVM |
| Shots | 32, xG 2.60 |
| Claims | 290, of which 255 reach the screen |

Both sides score, goals land in both halves, and two go in within two minutes
late on - which gives the edit a closing beat.

Rebuild it with:

```bash
python -m chalkboard.viewer --seed 2 --full --hz 10
```

Writes `out/match_m_0002.html`, about 22 MB, loads in roughly 2 seconds.

Shot list and narration: `docs/demo-script.md`.

**Alternate, if you want a last-minute winner to end on:** seed 20, Ashcombe
Rovers 3 - 1 Calderwick City, goals at 26', 45', 48' and 89'. Tied with seed
2 on the scan at 9.5. Seed 2 has more goals and more shots; seed 20 has the
better closing beat. Either works - do not rebuild unless you want the 89th
minute specifically.

Full ranking: `python tools/pick_demo_seed.py 24` (takes about 8 minutes).

---

## Outstanding, in priority order

### 1. Create the project page

Nothing else can attach to the submission until this exists. The Code
Repository field only appears after the page is saved once.

### 2. Record the video

**This is the one that decides the entry now.** 20% of the score, and
nothing else outstanding is worth more. See `docs/demo-script.md` for the
shot list, timings and narration.

### The agent layer: dropped, deliberately

Criterion 2, Agentic Design, is 20% and will score low. There are no agents;
everything is deterministic Python.

That was a decision, not a drift. Building the Analyst and Verifier was
about three days of work **once a model endpoint existed**, and no endpoint
was ever provisioned. Azure AI Foundry requires a subscription, which
requires a credit card for identity verification even on the free tier,
unlike Fabric's trial. GitHub Models is free and card-less but rate-limited
to roughly 50 requests a day on the larger models, which supports a short
clip rather than a full match.

Chasing it in the last three days risked ending the 27th with a half-wired
agent and no video. The trade was to spend that time closing brief (e) and
(vi) instead - both now done, both deterministic, both scored under
criterion 5.

The work is not wasted if it is picked up later: the Fact Ledger stores
structured claims with evidence, and `Director(require_verified=True)`
already refuses to emit anything a Verifier has not passed. The sockets are
there.

---

## Pushing new commits

The remote is configured. Pushes have to run in an interactive terminal, as
Git Credential Manager needs to open a sign-in window:

```
git push
```

Windows PowerShell 5.1 does not support `&&` - use `;` to chain, or separate
lines.
