"""
viewer.py - watch a match, with the claim feed beside it.

Writes a single self-contained HTML file (data embedded, no server, no
dependencies) that plays back a simulated match on a scale pitch, renders
the Director's overlay packets in sync with the clock, and lists every
claim the Fact Ledger holds.

    python -m chalkboard.viewer                    # 10 min of seed 7
    python -m chalkboard.viewer --seed 12 --full
    python -m chalkboard.viewer --minutes 25 --hz 8

Click any claim and the match seeks to the moment it describes, the players
it is about are ringed, and the pass or shot behind it is drawn on the
pitch. That is the whole argument of the project made visible: the sentence
is not a story about the match, it is a pointer into it.
"""

from __future__ import annotations

import argparse
import itertools
import json
import webbrowser
from pathlib import Path

from chalkboard.contracts import EventType
from chalkboard.director import Director
from chalkboard.fixtures import build_match
from chalkboard.ledger import build
from chalkboard.sim import MatchSimulator

HOME_COLOUR = "#38bdf8"
AWAY_COLOUR = "#fb923c"


def export(seed: int, minutes: float | None, hz: int, open_browser: bool) -> Path:
    meta = build_match(seed)
    stride = max(1, meta.tracking_hz // hz)
    effective_hz = meta.tracking_hz / stride

    roster = [p for t in meta.teams for p in t.players]
    index = {p.player_id: i for i, p in enumerate(roster)}

    total_ticks = sum(int(p.duration_ms / 1000 * meta.tracking_hz)
                      for p in meta.periods)
    limit = total_ticks if minutes is None else int(minutes * 60 * meta.tracking_hz)

    sim = MatchSimulator(meta)
    frames: list[list[float]] = []
    goal_events: list[dict] = []
    prev_score = dict(sim.score)

    def tee(stream):
        """Feed the pipeline every frame; keep only every `stride`th to render."""
        nonlocal prev_score
        for f in itertools.islice(stream, limit):
            if sim.score != prev_score:
                scorer = next(t for t in sim.score
                              if sim.score[t] > prev_score[t])
                prev_score = dict(sim.score)
                goal_events.append({"frame": len(frames), "team": scorer,
                                    "period": f.period, "t_ms": f.t_ms})
            if f.seq % stride == 0:
                by_id = {p.player_id: p for p in f.players}
                row: list[float] = [
                    f.period, f.t_ms // 100,
                    round(f.ball.pos.x, 1), round(f.ball.pos.y, 1),
                    index.get(f.ball.owner, -1) if f.ball.owner else -1,
                ]
                for p in roster:
                    s = by_id[p.player_id]
                    row += [round(s.pos.x, 1), round(s.pos.y, 1),
                            round(s.speed, 1)]
                frames.append(row)
            yield f

    result = build(meta, tee(sim.run()), keep=True)
    packets = Director(meta).direct(result.ledger)

    # Geometry per event, so a claim can draw what it is about.
    geometry: dict[str, dict] = {}
    for e in result.events:
        if e.type in (EventType.PASS, EventType.SHOT) and e.start is not None:
            geometry[e.event_id] = {
                "line": [e.start.x, e.start.y, e.detail.end.x, e.detail.end.y],
                "kind": e.type.value,
            }

    def to_row(seq: int) -> int:
        return min(max(seq // stride, 0), max(len(frames) - 1, 0))

    period_offset = {}
    running = 0
    for info in meta.periods:
        period_offset[info.period] = running
        running += info.duration_ms

    claims = []
    for packet in packets:
        entry = result.ledger.get(packet.evidence[0])
        trace = result.ledger.trace(entry.ledger_id)
        line = next((geometry[eid]["line"] for eid in trace["events"]
                     if eid in geometry), None)
        seqs = sorted(int(s) for s in trace["frames"] if s.isdigit())
        claims.append({
            "id": entry.ledger_id,
            "row": to_row(seqs[0]) if seqs else to_row(
                int((packet.valid_from_ms - period_offset[entry.period])
                    / 1000 * meta.tracking_hz)),
            "to": to_row(seqs[-1]) if seqs else None,
            "dur": packet.duration_ms,
            "prio": packet.priority,
            "type": packet.overlay_type.value,
            "area": packet.render_hints.safe_area if packet.render_hints else "full",
            "head": packet.headline,
            "body": packet.body,
            "method": entry.method,
            "players": [index[s] for s in entry.subject_ids if s in index],
            "line": line,
            "ev": len(trace["events"]),
            "fr": len(trace["frames"]),
        })
    claims.sort(key=lambda c: c["row"])

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
        "claims": claims,
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

    mins = len(frames) / effective_hz / 60 if frames else 0
    print(f"{home.short_name} {sim.score[home.team_id]} - "
          f"{sim.score[away.team_id]} {away.short_name}"
          f"   ({int(sim.stats['shots'])} shots, xG {sim.stats['xg']:.2f})")
    print(f"{len(frames):,} frames ({effective_hz:g} Hz, {mins:.1f} min)   "
          f"{len(result.ledger):,} claims -> {len(claims):,} on screen")
    print(f"{out}  [{out.stat().st_size / 1_000_000:.1f} MB]")

    if open_browser:
        webbrowser.open(out.as_uri())
    return out


_TEMPLATE = r"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Chalkboard</title>
<style>
  :root {
    --bg:#0f1115; --panel:#171a21; --line:#2a2f3a; --text:#e6e8ec;
    --muted:#8b93a3; --home:__HOME_COLOUR__; --away:__AWAY_COLOUR__;
    --accent:#a78bfa;
  }
  * { box-sizing:border-box; }
  body {
    margin:0; background:var(--bg); color:var(--text);
    font:14px/1.55 ui-sans-serif,system-ui,-apple-system,"Segoe UI",sans-serif;
    padding:16px;
  }
  .wrap { max-width:1480px; margin:0 auto; }
  header { display:flex; align-items:baseline; gap:12px; flex-wrap:wrap;
           margin-bottom:6px; }
  h1 { font-size:15px; font-weight:600; margin:0; }
  .sub { color:var(--muted); font-size:12px; }
  .teams { display:flex; gap:14px; align-items:center; font-size:13px;
           margin-bottom:10px; }
  .score { font-size:18px; font-weight:600; font-variant-numeric:tabular-nums; }
  .dot { display:inline-block; width:9px; height:9px; border-radius:50%;
         margin-right:6px; }
  .stage { display:grid; grid-template-columns:minmax(0,1fr) 340px; gap:14px; }
  canvas { width:100%; height:auto; border-radius:8px; display:block;
           box-shadow:0 2px 24px rgba(0,0,0,.5); }
  .feed { background:var(--panel); border:1px solid var(--line);
          border-radius:8px; display:flex; flex-direction:column;
          max-height:74vh; }
  .feed h2 { font-size:12px; text-transform:uppercase; letter-spacing:.07em;
             color:var(--muted); margin:0; padding:11px 13px;
             border-bottom:1px solid var(--line); }
  .feed .list { overflow-y:auto; flex:1; }
  .claim { padding:9px 13px; border-bottom:1px solid var(--line);
           cursor:pointer; font-size:12.5px; }
  .claim:hover { background:#1e222c; }
  .claim.sel { background:#232838; border-left:3px solid var(--accent);
               padding-left:10px; }
  .claim .m { color:var(--muted); font-size:11px; font-variant-numeric:tabular-nums;
              display:flex; gap:8px; }
  .claim .h { font-weight:600; }
  .claim .b { color:#c5cbd6; }
  .claim .p { color:var(--muted); font-size:10.5px; margin-top:3px; }
  .controls { margin-top:12px; background:var(--panel);
              border:1px solid var(--line); border-radius:8px;
              padding:10px 14px; display:flex; align-items:center;
              gap:14px; flex-wrap:wrap; }
  button { background:#222733; color:var(--text); border:1px solid var(--line);
           border-radius:6px; padding:6px 14px; font:inherit; cursor:pointer; }
  button:hover { background:#2b3140; }
  input[type=range] { flex:1; min-width:180px; accent-color:var(--accent); }
  select { background:#222733; color:var(--text); border:1px solid var(--line);
           border-radius:6px; padding:5px 8px; font:inherit; }
  .clock { font-variant-numeric:tabular-nums; font-size:15px; min-width:72px; }
  .hint { color:var(--muted); font-size:12px; margin-top:10px; }
  @media (max-width:1100px) { .stage { grid-template-columns:1fr; } }
  @media (prefers-color-scheme:light) {
    :root:not([data-theme="dark"]) {
      --bg:#f6f7f9; --panel:#fff; --line:#dfe3ea; --text:#12151b;
      --muted:#5b6474; --accent:#7c3aed;
    }
    :root:not([data-theme="dark"]) button,
    :root:not([data-theme="dark"]) select { background:#eef1f5; }
    :root:not([data-theme="dark"]) .claim:hover { background:#f2f4f8; }
    :root:not([data-theme="dark"]) .claim.sel { background:#f0ecfd; }
    :root:not([data-theme="dark"]) .claim .b { color:#333a46; }
  }
</style>
</head>
<body>
<div class="wrap">

<header>
  <h1>Chalkboard</h1>
  <span class="sub" id="fixture"></span>
</header>

<div class="teams">
  <span><span class="dot" style="background:var(--home)"></span><span id="homeName"></span></span>
  <span class="score" id="score">0 &ndash; 0</span>
  <span><span class="dot" style="background:var(--away)"></span><span id="awayName"></span></span>
  <span class="sub" id="goalLog"></span>
</div>

<div class="stage">
  <div>
    <canvas id="pitch" width="1060" height="700"></canvas>
    <div class="controls">
      <button id="play">Pause</button>
      <span class="clock" id="clock">0:00</span>
      <input type="range" id="scrub" min="0" value="0">
      <select id="speed">
        <option value="0.5">0.5x</option><option value="1" selected>1x</option>
        <option value="2">2x</option><option value="4">4x</option>
        <option value="8">8x</option>
      </select>
    </div>
    <p class="hint" id="hint">
      Click a claim to jump to it. The players it is about are ringed and the
      pass or shot behind it is drawn on the pitch.
    </p>
  </div>

  <div class="feed">
    <h2><span id="claimCount"></span> ledger claims</h2>
    <div class="list" id="list"></div>
  </div>
</div>

</div>
<script>
const D = __DATA__;

const PITCH_L=105, PITCH_W=68, MARGIN=26;
const cv=document.getElementById('pitch'), ctx=cv.getContext('2d');
const SCALE=(cv.width-MARGIN*2)/PITCH_L;
const toX=x=>MARGIN+(x+PITCH_L/2)*SCALE, toY=y=>MARGIN+(y+PITCH_W/2)*SCALE;
const STRIDE=3, N=D.players.length;

document.getElementById('fixture').textContent =
  `${D.competition} \u00b7 ${D.venue} \u00b7 seed ${D.seed}`;
document.getElementById('homeName').textContent = `${D.home.name} (${D.home.formation})`;
document.getElementById('awayName').textContent = `${D.away.name} (${D.away.formation})`;
document.getElementById('claimCount').textContent = D.claims.length;

const scrub=document.getElementById('scrub');
scrub.max=D.frames.length-1;
let i=0, playing=true, rate=1, acc=0, last=performance.now();
/* A selected claim stays highlighted until another is picked or play
   resumes. A timeout here looked tidy and was wrong: the point of the
   highlight is to be studied, and six seconds is not long enough to read a
   claim and find its evidence on the pitch. */
let hover=-1, picked=null;

/* ---------- claim feed ---------- */
const list=document.getElementById('list');
const nodes=D.claims.map((c,k)=>{
  const row=D.frames[Math.min(c.row,D.frames.length-1)];
  const mins=row?Math.floor(row[1]/600)+(row[0]===1?0:45):0;
  const el=document.createElement('div');
  el.className='claim';
  el.innerHTML=`<div class="m"><span>${mins}'</span><span class="h">${c.head}</span></div>`+
    `<div class="b">${c.body}</div>`+
    `<div class="p">${c.method} \u00b7 ${c.ev} event(s), ${c.fr} frame ref(s)</div>`;
  el.onclick=()=>pick(k);
  list.appendChild(el);
  return el;
});

function pick(k){
  const c=D.claims[k];
  picked=c;
  nodes.forEach(n=>n.classList.remove('sel'));
  nodes[k].classList.add('sel');
  nodes[k].scrollIntoView({block:'nearest'});
  i=Math.max(0,c.row-8);
  playing=false; btn.textContent='Play';
  render();
}

/* ---------- pitch ---------- */
function drawPitch(){
  const g=ctx;
  g.fillStyle='#16301f'; g.fillRect(0,0,cv.width,cv.height);
  g.fillStyle='rgba(255,255,255,.022)';
  for(let s=0;s<10;s+=2)
    g.fillRect(toX(-PITCH_L/2)+s*PITCH_L*SCALE/10,toY(-PITCH_W/2),
               PITCH_L*SCALE/10,PITCH_W*SCALE);
  g.strokeStyle='rgba(255,255,255,.34)'; g.lineWidth=1.5;
  const L=toX(-PITCH_L/2),R=toX(PITCH_L/2),T=toY(-PITCH_W/2),B=toY(PITCH_W/2);
  g.strokeRect(L,T,R-L,B-T);
  g.beginPath(); g.moveTo(toX(0),T); g.lineTo(toX(0),B); g.stroke();
  g.beginPath(); g.arc(toX(0),toY(0),9.15*SCALE,0,Math.PI*2); g.stroke();
  g.fillStyle='rgba(255,255,255,.34)';
  g.beginPath(); g.arc(toX(0),toY(0),2.5,0,Math.PI*2); g.fill();
  for(const sign of [-1,1]){
    const edge=sign*PITCH_L/2;
    g.strokeRect(toX(Math.min(edge,edge-sign*16.5)),toY(-20.16),16.5*SCALE,40.32*SCALE);
    g.strokeRect(toX(Math.min(edge,edge-sign*5.5)),toY(-9.16),5.5*SCALE,18.32*SCALE);
    g.beginPath(); g.arc(toX(edge-sign*11),toY(0),2.2,0,Math.PI*2); g.fill();
    g.lineWidth=3; g.beginPath();
    g.moveTo(toX(edge),toY(-3.66)); g.lineTo(toX(edge),toY(3.66)); g.stroke();
    g.lineWidth=1.5;
  }
}

function frameAt(k){ return D.frames[Math.max(0,Math.min(k,D.frames.length-1))]; }

function drawOverlay(c){
  /* The lower third a rendering partner would bind the packet to. */
  const pad=14, h=62, w=cv.width-MARGIN*2-120;
  const x=MARGIN+10, y=cv.height-h-MARGIN-6;
  ctx.fillStyle='rgba(12,14,19,.88)';
  ctx.fillRect(x,y,w,h);
  ctx.fillStyle='#a78bfa';
  ctx.fillRect(x,y,4,h);
  ctx.fillStyle='#fff';
  ctx.font='600 15px ui-sans-serif,system-ui,sans-serif';
  ctx.textAlign='left'; ctx.textBaseline='top';
  ctx.fillText(c.head,x+pad,y+11);
  ctx.fillStyle='#c5cbd6';
  ctx.font='13px ui-sans-serif,system-ui,sans-serif';
  const words=c.body.split(' '); let lineStr='', yy=y+32;
  for(const word of words){
    if(ctx.measureText(lineStr+word).width>w-pad*2){ ctx.fillText(lineStr,x+pad,yy); lineStr=''; yy+=16; if(yy>y+h-14) break; }
    lineStr+=word+' ';
  }
  if(yy<=y+h-14) ctx.fillText(lineStr,x+pad,yy);
}

function render(){
  const f=frameAt(i);
  drawPitch();

  const live = picked;
  const ringed = live ? new Set(live.players) : null;

  if(live && live.line){
    const [x1,y1,x2,y2]=live.line;
    ctx.strokeStyle='#a78bfa'; ctx.lineWidth=2.5; ctx.setLineDash([7,5]);
    ctx.beginPath(); ctx.moveTo(toX(x1),toY(y1)); ctx.lineTo(toX(x2),toY(y2));
    ctx.stroke(); ctx.setLineDash([]);
    ctx.fillStyle='#a78bfa';
    ctx.beginPath(); ctx.arc(toX(x2),toY(y2),4,0,Math.PI*2); ctx.fill();
  }

  const owner=f[4];
  for(let p=0;p<N;p++){
    const x=f[5+p*STRIDE],y=f[6+p*STRIDE],spd=f[7+p*STRIDE];
    const meta=D.players[p], cx=toX(x), cy=toY(y);
    const lift=Math.min(spd/7.5,1);

    if(ringed && ringed.has(p)){
      ctx.beginPath(); ctx.arc(cx,cy,17,0,Math.PI*2);
      ctx.strokeStyle='#a78bfa'; ctx.lineWidth=3; ctx.stroke();
    }
    if(p===owner){
      ctx.beginPath(); ctx.arc(cx,cy,13,0,Math.PI*2);
      ctx.strokeStyle='#fff'; ctx.lineWidth=2; ctx.stroke();
    }
    ctx.beginPath(); ctx.arc(cx,cy,p===hover?11:8.5,0,Math.PI*2);
    ctx.fillStyle=meta.home?`rgba(56,189,248,${0.55+lift*0.45})`
                           :`rgba(251,146,60,${0.55+lift*0.45})`;
    ctx.fill();
    ctx.fillStyle='#0b0d11';
    ctx.font='600 9px ui-sans-serif,system-ui,sans-serif';
    ctx.textAlign='center'; ctx.textBaseline='middle';
    ctx.fillText(meta.shirt,cx,cy+0.5);

    if(p===hover){
      const label=`${meta.name}  ${meta.pos}  ${spd.toFixed(1)} m/s`;
      ctx.font='12px ui-sans-serif,system-ui,sans-serif';
      const w=ctx.measureText(label).width+12;
      ctx.fillStyle='rgba(10,12,16,.92)'; ctx.fillRect(cx-w/2,cy-34,w,20);
      ctx.fillStyle='#e6e8ec'; ctx.fillText(label,cx,cy-24);
    }
  }

  ctx.beginPath(); ctx.arc(toX(f[2]),toY(f[3]),4.5,0,Math.PI*2);
  ctx.fillStyle='#fff'; ctx.fill();
  ctx.strokeStyle='rgba(0,0,0,.6)'; ctx.lineWidth=1; ctx.stroke();

  /* Overlay packets due on the clock, highest priority wins the strip. */
  let due=null;
  for(const c of D.claims){
    const span=Math.max(1,Math.round(c.dur/1000*D.fps));
    if(i>=c.row && i<c.row+span && (!due || c.prio>due.prio)) due=c;
  }
  if(live) drawOverlay(live);
  else if(due) drawOverlay(due);

  const tenths=f[1], mins=Math.floor(tenths/600), secs=Math.floor(tenths/10)%60;
  document.getElementById('clock').textContent=
    `${(f[0]===1?0:45)+mins}:${String(secs).padStart(2,'0')}`;

  let hg=0,ag=0; const scored=[];
  for(const g of D.goals){
    if(g.frame>i) break;
    const home=g.team===D.home.id; home?hg++:ag++;
    scored.push(`${Math.floor(g.t_ms/60000)+(g.period===1?0:45)+1}' ${home?D.home.short:D.away.short}`);
  }
  document.getElementById('score').innerHTML=`${hg} &ndash; ${ag}`;
  document.getElementById('goalLog').textContent=scored.join('  \u00b7  ');
  scrub.value=i;
}

function tick(now){
  const dt=(now-last)/1000; last=now;
  if(playing){
    acc+=dt*D.fps*rate;
    while(acc>=1){ i++; acc--; }
    if(i>=D.frames.length){ i=D.frames.length-1; playing=false; btn.textContent='Replay'; }
  }
  render(); requestAnimationFrame(tick);
}

const btn=document.getElementById('play');
btn.onclick=()=>{ if(i>=D.frames.length-1) i=0; playing=!playing;
                  if(playing){ picked=null; nodes.forEach(n=>n.classList.remove('sel')); }
                  btn.textContent=playing?'Pause':'Play'; };
scrub.oninput=e=>{ i=+e.target.value; render(); };
document.getElementById('speed').onchange=e=>{ rate=+e.target.value; };

cv.addEventListener('mousemove',e=>{
  const r=cv.getBoundingClientRect();
  const mx=(e.clientX-r.left)*cv.width/r.width, my=(e.clientY-r.top)*cv.height/r.height;
  const f=frameAt(i); hover=-1; let best=16;
  for(let p=0;p<N;p++){
    const d=Math.hypot(toX(f[5+p*STRIDE])-mx,toY(f[6+p*STRIDE])-my);
    if(d<best){ best=d; hover=p; }
  }
});
cv.addEventListener('mouseleave',()=>{hover=-1;});
document.addEventListener('keydown',e=>{
  if(e.code==='Space'){ e.preventDefault(); btn.click(); }
  if(e.code==='ArrowRight'){ playing=false; btn.textContent='Play'; i++; render(); }
  if(e.code==='ArrowLeft'){ playing=false; btn.textContent='Play'; i--; render(); }
});

render(); requestAnimationFrame(tick);
</script>
</body>
</html>
"""


def main() -> None:
    ap = argparse.ArgumentParser(description="Render a simulated match to HTML.")
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--minutes", type=float, default=10.0)
    ap.add_argument("--full", action="store_true")
    ap.add_argument("--hz", type=int, default=8)
    ap.add_argument("--no-open", action="store_true")
    a = ap.parse_args()
    export(a.seed, None if a.full else a.minutes, a.hz, not a.no_open)


if __name__ == "__main__":
    main()

