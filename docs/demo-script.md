# Demo video - shot list

Under two minutes, hard. Rules 4.4: *"Judges are not required to watch beyond
two (2) minutes."* Assume they stop dead at 1:59.

The video is **20% of the total score** - the same weight as the entire
technical implementation. It is also the part most entries waste, usually by
spending forty seconds on a title card and a problem statement nobody needed.

## Rules that constrain the edit

| Rule | What it means here |
|---|---|
| 4.4 | Under 2:00. Public URL on YouTube, Vimeo, Facebook Video or Youku |
| 4.4 | **No third-party trademarks.** No real club names, badges or players anywhere on screen - our fixtures are all invented, so just do not open a browser tab showing a real one |
| 4.4 | **No copyrighted music.** Silence or a licence you hold. Silence is safer and this film does not need a soundtrack |
| 4.3 | *"must function as depicted in the video"* - no mockups, no sped-up fakery, no screens that do not exist |

## The spine

Lead with the thing nobody else has. Every entry will show a pitch and some
generated text. Only this one can click a sentence and land on the frame that
produced it, and only this one can show a measured accuracy number.

---

## 0:00 - 0:12   The problem, fast

**Show:** two panels side by side. Left, a wall of raw numbers. Right, a
fluent paragraph of generated commentary with one clause circled in red.

**Say:**
> Football narrative is either accurate and unreadable, or readable and
> quietly wrong. No broadcaster can ship a system that invents a cross that
> never happened.

Twelve seconds. Do not explain the hackathon, do not introduce yourself, do
not show a logo.

---

## 0:12 - 0:40   The money shot

**Show:** the viewer, match running. Pause. Click a claim in the feed.

The scorer rings purple, the shot trajectory draws on the pitch, the
lower-third renders, the feed entry highlights. Let it breathe - this is the
single most important shot in the film. Hold for three seconds after the
click before moving.

Then click a second, different claim - a line-breaking pass - so it reads as
a property of the system and not one hard-coded trick.

**Say:**
> Every sentence is a pointer into the match. Click it and the system shows
> you the exact tracking that produced it - the players involved, the pass,
> the moment.

**Cursor matters here.** Move deliberately. A jittery cursor makes a precise
system look improvised.

---

## 0:40 - 1:00   It is measured, not asserted

**Show:** terminal, `python tools/metrics_report.py 7`, cut to the recall
table on screen. Let the 100% column sit still for two seconds.

**Say:**
> The event detector reads tracking frames and nothing else - it never sees
> the simulator. Because the data is synthetic we know the right answer, so
> detection accuracy is measurable: a hundred percent of passes, shots and
> goals, recovered from frames alone.
>
> On a real feed nobody can grade their own event detection, because nobody
> knows the truth. That is what synthetic data buys.

This is the twenty seconds that separates the entry from the field. Do not
rush it and do not talk over the number.

---

## 1:00 - 1:15   Made for one fan, in their language

**Show:** pick a player from the Focus menu. The feed collapses from 255
claims to that player's, he rings green, everyone else dims, the stat strip
fills in. Then change Language to Espanol and let the whole feed re-render.

**Say:**
> The same match, read through one player - his claims, his distance, his
> top speed. And the same intelligence in another language, because a claim
> is stored as a fact and a template, not as an English sentence.

Two switches, fifteen seconds, and it answers two of the brief's named
requirements on screen. Do the language switch slowly enough that the text
visibly changes - it is easy to miss at speed.

---

## 1:15 - 1:30   Explainability and expiry

**Show:** the claim feed scrolling - control, pressure, tempo claims going
past. Then the ledger report showing supersession.

**Say:**
> Control versus chaos, tactical pressure, game rhythm - each one reports the
> components it was built from, so a claim can show its working rather than
> just state a number.
>
> And claims expire. A side controlling the game at forty minutes is not at
> seventy-five. A hundred and eight pattern claims get asserted across a
> match; three are still standing at full time. Without that, a recap
> contradicts itself.

---

## 1:30 - 1:45   Render, for broadcast

**Show:** overlay packets appearing in sync with the clock. Then cut briefly
to a packet's JSON - timecodes, priority, `data` separate from text,
`evidence` naming the ledger entry.

**Say:**
> Insight only matters if it reaches a screen. The Director emits timed,
> machine-readable overlay packets a rendering partner binds to its own
> graphics - data kept separate from text, every packet carrying the ledger
> entry it came from. Nothing reaches air without provenance.

---

## 1:45 - 1:58   Close

**Show:** architecture diagram, three seconds. Then back to the viewer with a
claim selected, held to the end.

**Say:**
> Chalkboard turns synthetic football into match intelligence you can verify.
> Every sentence, traceable to the frame it came from.

End on the pitch, not on a slide.

---

## Recording notes

- **1920x1080, 30fps.** Record the browser at a fixed window size; do not
  resize mid-take.
- **Hide browser chrome** - F11 full screen. Tabs and bookmarks look amateur
  and risk showing something you do not want on camera.
- **Clean desktop.** No notifications. Turn on Focus Assist before recording.
- **Record in segments**, not one take. Each section above is a separate clip.
- **Record the audio separately** and lay it under the picture. Live
  narration while clicking produces hesitation and mouse noise.
- **Write the voiceover out and read it.** Improvised narration runs long,
  every time.
- **Check the runtime after the first assembly.** If it is over 2:00, cut the explainability section first and the opening second. Never cut the money shot or the
  recall table.

## Before uploading

- [ ] Under 2:00
- [ ] No real club, player or competition names visible in any frame
- [ ] No copyrighted music
- [ ] Everything shown actually runs
- [ ] Uploaded public on YouTube (not unlisted - rules say public URL)
- [ ] URL pasted into the project page
