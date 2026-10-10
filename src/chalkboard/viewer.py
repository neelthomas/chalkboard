"""
viewer.py - watch a match.

Writes a single self-contained HTML file (data embedded, no server, no
dependencies) that plays back a simulated match on a scale pitch.

    python -m chalkboard.viewer                    # 10 min of seed 7
    python -m chalkboard.viewer --seed 12 --minutes 5 --hz 10
    python -m chalkboard.viewer --full             # whole match, bigger file

This exists for debugging as much as for the demo. The football model is
placeholder right now; the only way to tell whether 22 players are holding a
shape or collapsing onto the ball is to look at them.
"""

from __future__ import annotations

import argparse
import itertools
import json
import webbrowser
from pathlib import Path

from chalkboard.fixtures import build_match
from chalkboard.sim import MatchSimulator

HOME_COLOUR = "#38bdf8"
AWAY_COLOUR = "#fb923c"


def export(seed: int, minutes: float | None, hz: int, open_browser: bool) -> Path:
    meta = build_match(seed)
    stride = max(1, meta.tracking_hz // hz)
    effective_hz = meta.tracking_hz / stride

    roster = [p for t in meta.teams for p in t.players]
    index = {p.player_id: i for i, p in enumerate(roster)}

    total_ticks = sum(
        int(p.duration_ms / 1000 * meta.tracking_hz) for p in meta.periods
    )
    limit = total_ticks if minutes is None else int(minutes * 60 * meta.tracking_hz)

    sim = MatchSimulator(meta)
    prev_score = dict(sim.score)
    goal_events: list[dict] = []

    frames: list[list[float]] = []
    for f in itertools.islice(sim.run(), limit):
        if sim.score != prev_score:
            scorer = next(t for t in sim.score if sim.score[t] > prev_score[t])
            prev_score = dict(sim.score)
            goal_events.append({
                "frame": len(frames),            # next row to be written
                "team": scorer,
                "period": f.period,
                "t_ms": f.t_ms,
            })
        if f.seq % stride:
            continue
        by_id = {p.player_id: p for p in f.players}
        row: list[float] = [
            f.period,
            f.t_ms // 100,                       # tenths of a second, keeps it small
            round(f.ball.pos.x, 1),
            round(f.ball.pos.y, 1),
            index.get(f.ball.owner, -1) if f.ball.owner else -1,
        ]
        for p in roster:
            s = by_id[p.player_id]
            row += [round(s.pos.x, 1), round(s.pos.y, 1), round(s.speed, 1)]
        frames.append(row)

    home, away = meta.teams
    payload = {
        "match_id": meta.match_id,
        "seed": meta.seed,
        "competition": meta.competition,
        "venue": meta.venue,
        "home": {"name": home.name, "short": home.short_name,
                 "formation": home.formation, "id": home.team_id},
        "away": {"name": away.name, "short": away.short_name,
                 "formation": away.formation, "id": away.team_id},
        "goals": goal_events,
        "players": [
            {"name": p.name, "shirt": p.shirt, "pos": p.position,
             "home": p.team_id == home.team_id}
            for p in roster
        ],
        "fps": effective_hz,
        "frames": frames,
    }

    out_dir = Path(__file__).resolve().parents[2] / "out"
    out_dir.mkdir(exist_ok=True)
    out = out_dir / f"match_{meta.match_id}.html"
    out.write_text(
        _TEMPLATE.replace("__DATA__", json.dumps(payload, separators=(",", ":")))
                 .replace("__HOME_COLOUR__", HOME_COLOUR)
                 .replace("__AWAY_COLOUR__", AWAY_COLOUR),
        encoding="utf-8",
    )

    size_mb = out.stat().st_size / 1_000_000
    mins = len(frames) / effective_hz / 60 if frames else 0
    print(f"{home.short_name} {sim.score[home.team_id]} - "
          f"{sim.score[away.team_id]} {away.short_name}"
          f"   ({int(sim.stats['shots'])} shots, xG {sim.stats['xg']:.2f})")
    print(f"{len(frames):,} frames  ({effective_hz:g} Hz, {mins:.1f} min of play)")
    print(f"{out}  [{size_mb:.1f} MB]")

    if open_browser:
        webbrowser.open(out.as_uri())
    return out


_TEMPLATE = r"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Chalkboard - match viewer</title>
<style>
  :root {
    --bg: #0f1115; --panel: #171a21; --line: #2a2f3a;
    --text: #e6e8ec; --muted: #8b93a3;
    --home: __HOME_COLOUR__; --away: __AWAY_COLOUR__;
  }
  * { box-sizing: border-box; }
  body {
    margin: 0; background: var(--bg); color: var(--text);
    font: 14px/1.5 ui-sans-serif, system-ui, -apple-system, "Segoe UI", sans-serif;
    display: flex; flex-direction: column; align-items: center;
    padding: 16px; gap: 12px;
  }
  header { display: flex; align-items: baseline; gap: 12px; flex-wrap: wrap; }
  h1 { font-size: 15px; font-weight: 600; margin: 0; letter-spacing: .01em; }
  .sub { color: var(--muted); font-size: 12px; }
  .teams { display: flex; gap: 16px; align-items: center; font-size: 13px; }
  .score { font-size: 18px; font-weight: 600; font-variant-numeric: tabular-nums;
           padding: 0 4px; }
  #goalLog { min-height: 18px; }
  .dot { display: inline-block; width: 9px; height: 9px; border-radius: 50%;
         margin-right: 6px; vertical-align: baseline; }
  canvas { width: 100%; max-width: 1060px; height: auto; border-radius: 8px;
           box-shadow: 0 2px 24px rgba(0,0,0,.5); }
  .controls {
    width: 100%; max-width: 1060px; background: var(--panel);
    border: 1px solid var(--line); border-radius: 8px; padding: 10px 14px;
    display: flex; align-items: center; gap: 14px; flex-wrap: wrap;
  }
  button {
    background: #222733; color: var(--text); border: 1px solid var(--line);
    border-radius: 6px; padding: 6px 14px; font: inherit; cursor: pointer;
  }
  button:hover { background: #2b3140; }
  input[type=range] { flex: 1; min-width: 200px; accent-color: var(--home); }
  select { background: #222733; color: var(--text); border: 1px solid var(--line);
           border-radius: 6px; padding: 5px 8px; font: inherit; }
  .clock { font-variant-numeric: tabular-nums; font-size: 15px; min-width: 76px; }
  .hint { color: var(--muted); font-size: 12px; max-width: 1060px; }
  @media (prefers-color-scheme: light) {
    :root:not([data-theme="dark"]) {
      --bg: #f6f7f9; --panel: #fff; --line: #dfe3ea;
      --text: #12151b; --muted: #5b6474;
    }
    :root:not([data-theme="dark"]) button,
    :root:not([data-theme="dark"]) select { background: #eef1f5; }
  }
</style>
</head>
<body>

<header>
  <h1>Chalkboard</h1>
  <span class="sub" id="fixture"></span>
</header>

<div class="teams">
  <span><span class="dot" style="background:var(--home)"></span><span id="homeName"></span></span>
  <span class="score" id="score">0 &ndash; 0</span>
  <span><span class="dot" style="background:var(--away)"></span><span id="awayName"></span></span>
</div>
<div class="sub" id="goalLog"></div>

<canvas id="pitch" width="1060" height="700"></canvas>

<div class="controls">
  <button id="play">Pause</button>
  <span class="clock" id="clock">0:00</span>
  <input type="range" id="scrub" min="0" value="0">
  <select id="speed">
    <option value="0.25">0.25x</option>
    <option value="0.5">0.5x</option>
    <option value="1" selected>1x</option>
    <option value="2">2x</option>
    <option value="4">4x</option>
    <option value="8">8x</option>
  </select>
</div>

<p class="hint">
  Ball carrier is ringed. Player brightness tracks speed. Hover a player for name
  and pace. The football model is still placeholder &mdash; watch for the shape
  collapsing onto the ball, which is the next thing to fix.
</p>

<script>
const D = __DATA__;

const PITCH_L = 105, PITCH_W = 68, MARGIN = 26;
const cv = document.getElementById('pitch'), ctx = cv.getContext('2d');
const SCALE = (cv.width - MARGIN * 2) / PITCH_L;
const toX = x => MARGIN + (x + PITCH_L / 2) * SCALE;
const toY = y => MARGIN + (y + PITCH_W / 2) * SCALE;
const STRIDE = 3;               // floats per player per frame
const N = D.players.length;

document.getElementById('fixture').textContent =
  `${D.competition} · ${D.venue} · seed ${D.seed}`;
document.getElementById('homeName').textContent = `${D.home.name} (${D.home.formation})`;
document.getElementById('awayName').textContent = `${D.away.name} (${D.away.formation})`;

const scrub = document.getElementById('scrub');
scrub.max = D.frames.length - 1;

let i = 0, playing = true, rate = 1, acc = 0, last = performance.now();
let hover = -1;

function drawPitch() {
  const g = ctx;
  g.fillStyle = '#16301f';
  g.fillRect(0, 0, cv.width, cv.height);

  // mown stripes
  g.fillStyle = 'rgba(255,255,255,.022)';
  for (let s = 0; s < 10; s += 2) {
    g.fillRect(toX(-PITCH_L / 2) + s * PITCH_L * SCALE / 10, toY(-PITCH_W / 2),
               PITCH_L * SCALE / 10, PITCH_W * SCALE);
  }

  g.strokeStyle = 'rgba(255,255,255,.34)';
  g.lineWidth = 1.5;
  const L = toX(-PITCH_L / 2), R = toX(PITCH_L / 2);
  const T = toY(-PITCH_W / 2), B = toY(PITCH_W / 2);

  g.strokeRect(L, T, R - L, B - T);
  g.beginPath(); g.moveTo(toX(0), T); g.lineTo(toX(0), B); g.stroke();
  g.beginPath(); g.arc(toX(0), toY(0), 9.15 * SCALE, 0, Math.PI * 2); g.stroke();
  g.beginPath(); g.arc(toX(0), toY(0), 2.5, 0, Math.PI * 2);
  g.fillStyle = 'rgba(255,255,255,.34)'; g.fill();

  for (const sign of [-1, 1]) {
    const edge = sign * PITCH_L / 2;
    // penalty area 16.5 x 40.32
    g.strokeRect(toX(Math.min(edge, edge - sign * 16.5)), toY(-20.16),
                 16.5 * SCALE, 40.32 * SCALE);
    // six-yard box 5.5 x 18.32
    g.strokeRect(toX(Math.min(edge, edge - sign * 5.5)), toY(-9.16),
                 5.5 * SCALE, 18.32 * SCALE);
    // penalty spot
    g.beginPath(); g.arc(toX(edge - sign * 11), toY(0), 2.2, 0, Math.PI * 2); g.fill();
    // goal
    g.lineWidth = 3;
    g.beginPath(); g.moveTo(toX(edge), toY(-3.66)); g.lineTo(toX(edge), toY(3.66));
    g.stroke();
    g.lineWidth = 1.5;
  }
}

function frameAt(k) { return D.frames[Math.max(0, Math.min(k, D.frames.length - 1))]; }

function render() {
  const f = frameAt(i);
  drawPitch();

  const owner = f[4];
  for (let p = 0; p < N; p++) {
    const x = f[5 + p * STRIDE], y = f[6 + p * STRIDE], spd = f[7 + p * STRIDE];
    const meta = D.players[p];
    const cx = toX(x), cy = toY(y);
    const lift = Math.min(spd / 7.5, 1);

    if (p === owner) {
      ctx.beginPath(); ctx.arc(cx, cy, 13, 0, Math.PI * 2);
      ctx.strokeStyle = '#fff'; ctx.lineWidth = 2; ctx.stroke();
    }
    ctx.beginPath(); ctx.arc(cx, cy, p === hover ? 11 : 8.5, 0, Math.PI * 2);
    ctx.fillStyle = meta.home
      ? `rgba(56,189,248,${0.55 + lift * 0.45})`
      : `rgba(251,146,60,${0.55 + lift * 0.45})`;
    ctx.fill();

    ctx.fillStyle = '#0b0d11';
    ctx.font = '600 9px ui-sans-serif, system-ui, sans-serif';
    ctx.textAlign = 'center'; ctx.textBaseline = 'middle';
    ctx.fillText(meta.shirt, cx, cy + 0.5);

    if (p === hover) {
      const label = `${meta.name}  ${meta.pos}  ${spd.toFixed(1)} m/s`;
      ctx.font = '12px ui-sans-serif, system-ui, sans-serif';
      const w = ctx.measureText(label).width + 12;
      ctx.fillStyle = 'rgba(10,12,16,.92)';
      ctx.fillRect(cx - w / 2, cy - 34, w, 20);
      ctx.fillStyle = '#e6e8ec';
      ctx.fillText(label, cx, cy - 24);
    }
  }

  // ball
  ctx.beginPath(); ctx.arc(toX(f[2]), toY(f[3]), 4.5, 0, Math.PI * 2);
  ctx.fillStyle = '#fff'; ctx.fill();
  ctx.strokeStyle = 'rgba(0,0,0,.6)'; ctx.lineWidth = 1; ctx.stroke();

  const tenths = f[1], mins = Math.floor(tenths / 600), secs = Math.floor(tenths / 10) % 60;
  const base = f[0] === 1 ? 0 : 45;
  document.getElementById('clock').textContent =
    `${base + mins}:${String(secs).padStart(2, '0')}`;

  let hg = 0, ag = 0;
  const scored = [];
  for (const g of D.goals) {
    if (g.frame > i) break;
    const home = g.team === D.home.id;
    home ? hg++ : ag++;
    const m = Math.floor(g.t_ms / 60000) + (g.period === 1 ? 0 : 45) + 1;
    scored.push(`${m}' ${home ? D.home.short : D.away.short}`);
  }
  document.getElementById('score').innerHTML = `${hg} &ndash; ${ag}`;
  document.getElementById('goalLog').textContent = scored.join('  ·  ');

  scrub.value = i;
}

function tick(now) {
  const dt = (now - last) / 1000; last = now;
  if (playing) {
    acc += dt * D.fps * rate;
    while (acc >= 1) { i++; acc--; }
    if (i >= D.frames.length) { i = D.frames.length - 1; playing = false; btn.textContent = 'Replay'; }
  }
  render();
  requestAnimationFrame(tick);
}

const btn = document.getElementById('play');
btn.onclick = () => {
  if (i >= D.frames.length - 1) i = 0;
  playing = !playing;
  btn.textContent = playing ? 'Pause' : 'Play';
};
scrub.oninput = e => { i = +e.target.value; render(); };
document.getElementById('speed').onchange = e => { rate = +e.target.value; };

cv.addEventListener('mousemove', e => {
  const r = cv.getBoundingClientRect();
  const mx = (e.clientX - r.left) * cv.width / r.width;
  const my = (e.clientY - r.top) * cv.height / r.height;
  const f = frameAt(i);
  hover = -1;
  let best = 16;
  for (let p = 0; p < N; p++) {
    const d = Math.hypot(toX(f[5 + p * STRIDE]) - mx, toY(f[6 + p * STRIDE]) - my);
    if (d < best) { best = d; hover = p; }
  }
});
cv.addEventListener('mouseleave', () => { hover = -1; });

document.addEventListener('keydown', e => {
  if (e.code === 'Space') { e.preventDefault(); btn.click(); }
  if (e.code === 'ArrowRight') { playing = false; btn.textContent = 'Play'; i++; render(); }
  if (e.code === 'ArrowLeft') { playing = false; btn.textContent = 'Play'; i--; render(); }
});

render();
requestAnimationFrame(tick);
</script>
</body>
</html>
"""


def main() -> None:
    ap = argparse.ArgumentParser(description="Render a simulated match to HTML.")
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--minutes", type=float, default=10.0,
                    help="minutes of play to export (default 10)")
    ap.add_argument("--full", action="store_true", help="export the whole match")
    ap.add_argument("--hz", type=int, default=8,
                    help="playback sample rate (default 8)")
    ap.add_argument("--no-open", action="store_true")
    a = ap.parse_args()
    export(a.seed, None if a.full else a.minutes, a.hz, not a.no_open)


if __name__ == "__main__":
    main()
