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

## Data

All data is synthetic and football-realistic. Every club, player and venue
name is invented. No real match data or footage is used anywhere.

## Engineering

144 tests. Deterministic and seeded - the same seed replays the same match
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

### 2. Decide the agent layer

Criterion 2, Agentic Design, is 20% of the score and currently reads zero -
there are no agents, everything is deterministic Python.

**Azure AI Foundry needs a subscription, which normally needs a credit card
for identity verification** even on the free tier, unlike Fabric's trial.

**GitHub Models is the free path**: https://github.com/marketplace/models -
rate-limited, authenticates with a GitHub token, no card. It will not win
*Best Use of Microsoft Foundry*, but it would unblock the Analyst and
Verifier, which is the 20% criterion rather than a 1,500-dollar category.

The Fact Ledger and the `require_verified` gate were built to receive these,
so it is additive work, not a rewrite.

### 3. Record the video

Start no later than 24 October. See `docs/demo-script.md`.

---

## Pushing new commits

The remote is configured. Pushes have to run in an interactive terminal, as
Git Credential Manager needs to open a sign-in window:

```
git push
```

Windows PowerShell 5.1 does not support `&&` - use `;` to chain, or separate
lines.
