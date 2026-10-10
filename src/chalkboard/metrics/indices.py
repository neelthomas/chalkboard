"""
indices.py - the three explainability primitives the brief names.

    (iv) "explain why moments matter, such as control vs. chaos,
          tactical pressure changes, and game rhythm patterns"

Those are the brief's own words, so they are the names used here.

None of these are published metrics. They are our own composites, which is
precisely why each one is defined in exactly one place, versioned, and
reports its components alongside its score. A snapshot that said only
"control 0.71" would be unusable by the Analyst - it could state the number
but not say why. Every composite here carries the parts it was built from,
so a ledger claim can cite `control_index@0.1` and show its working.

Normalisation constants are judgement calls. They are named, not inlined,
so they can be argued with.
"""

from __future__ import annotations

import math
import statistics
from collections import deque
from typing import Iterable, Optional

from chalkboard import football as fb
from chalkboard.contracts import Contract, EventType, MatchEvent, MatchMeta, TrackingFrame
from chalkboard.fixtures import attack_direction

VERSION = "0.1"

WINDOW_S = 120              # rolling window the indices describe
SAMPLE_EVERY = 5            # sample frames at hz/5 to keep this cheap

# Normalisation anchors - the value at which a component reads 1.0.
TURNOVERS_PER_MIN_MAX = 8.0
PASSES_PER_MIN_MAX = 18.0
PRESS_BODIES_MAX = 1.5      # opponents within the press radius of the carrier
BALL_SPEED_SD_MAX = 9.0     # m/s standard deviation within the window
PRESS_RADIUS_M = 6.0
DEEPEST_N = 4               # defenders averaged for line height


def _clamp01(v: float) -> float:
    return 0.0 if v < 0.0 else 1.0 if v > 1.0 else v


class TeamIndices(Contract):
    """Per-team scores, each with the components it was built from."""
    team_id: str

    control: float                      # 0-1, how settled their hold is
    possession_share: float
    pass_completion: float
    territory: float                    # 0 = own goal line, 1 = opponent's

    pressure: float                     # 0-1, how hard they press
    press_intensity: float              # bodies around the carrier
    line_height: float                  # 0-1, how high the back line sits


class IndexSnapshot(Contract):
    """
    Everything the Analyst needs to explain a moment, at one instant.

    Deliberately carries components as well as composites: a claim that
    cites only the headline number cannot be verified against the ledger.
    """
    method: str = f"indices@{VERSION}"
    match_id: str
    period: int
    t_ms: int
    window_ms: int
    frame_seq_range: tuple[int, int]

    teams: list[TeamIndices]

    chaos: float                        # 0-1, match-level
    turnovers_per_min: float
    loose_ball_share: float
    ball_speed_sd: float

    tempo: float                        # passes per minute, both teams
    rhythm: float                       # 0-1, 1 = metronomic, 0 = broken

    def team(self, team_id: str) -> TeamIndices:
        return next(t for t in self.teams if t.team_id == team_id)


class IndexEngine:
    """
        eng = IndexEngine(meta)
        for frame in frames:
            eng.observe(frame, events_at_this_frame)
            if frame.seq % (25 * 15) == 0:
                snap = eng.snapshot(frame)
    """

    def __init__(self, meta: MatchMeta, window_s: int = WINDOW_S):
        self.meta = meta
        self.hz = meta.tracking_hz
        self.window_ticks = window_s * self.hz
        self.team_ids = [t.team_id for t in meta.teams]
        self.team_of = {p.player_id: t.team_id
                        for t in meta.teams for p in t.players}
        self.keepers = {
            t.team_id: next(p.player_id for p in t.players if p.position == "GK")
            for t in meta.teams
        }

        maxlen = window_s * self.hz // SAMPLE_EVERY + 2
        self._owner: deque[Optional[str]] = deque(maxlen=maxlen)
        self._ball_speed: deque[float] = deque(maxlen=maxlen)
        self._ball_x: deque[float] = deque(maxlen=maxlen)
        self._press: dict[str, deque[float]] = {
            t: deque(maxlen=maxlen) for t in self.team_ids}
        self._line: dict[str, deque[float]] = {
            t: deque(maxlen=maxlen) for t in self.team_ids}

        # events are sparse, so keep (seq, ...) and prune by window
        self._passes: deque[tuple[int, str, bool]] = deque()
        self._turnovers: deque[int] = deque()
        self._first_seq = 0

    # -- ingest ---------------------------------------------------------

    def observe(self, frame: TrackingFrame,
                events: Iterable[MatchEvent] = ()) -> None:
        for e in events:
            if e.type is EventType.PASS:
                self._passes.append((e.seq, e.team_id or "", e.detail.completed))
            elif e.type is EventType.POSSESSION_CHANGE:
                self._turnovers.append(e.seq)

        cutoff = frame.seq - self.window_ticks
        while self._passes and self._passes[0][0] < cutoff:
            self._passes.popleft()
        while self._turnovers and self._turnovers[0] < cutoff:
            self._turnovers.popleft()
        self._first_seq = max(0, cutoff)

        if frame.seq % SAMPLE_EVERY:
            return

        owner = frame.ball.owner
        self._owner.append(self.team_of[owner] if owner else None)
        self._ball_speed.append(frame.ball.speed)
        self._ball_x.append(frame.ball.pos.x)

        adir = {t: attack_direction(self.meta, t, frame.period)
                for t in self.team_ids}
        bx, by = frame.ball.pos.x, frame.ball.pos.y
        owner_team = self.team_of[owner] if owner else None

        for team_id in self.team_ids:
            mine = [p for p in frame.players
                    if self.team_of[p.player_id] == team_id
                    and p.player_id != self.keepers[team_id]]

            # Press intensity only counts while this team is NOT in possession.
            if owner_team is not None and owner_team != team_id:
                bodies = sum(
                    1 for p in mine
                    if math.hypot(p.pos.x - bx, p.pos.y - by) <= PRESS_RADIUS_M
                )
                self._press[team_id].append(float(bodies))

            # Line height: the deepest few outfielders, 0 = own goal line.
            d = adir[team_id]
            forward = sorted(p.pos.x * d for p in mine)[:DEEPEST_N]
            if forward:
                mean_back = sum(forward) / len(forward)
                self._line[team_id].append(_clamp01(
                    (mean_back + fb.PITCH_X) / (2 * fb.PITCH_X)))

    # -- output ---------------------------------------------------------

    def snapshot(self, frame: TrackingFrame) -> IndexSnapshot:
        n = max(len(self._owner), 1)
        window_ms = int(len(self._owner) * SAMPLE_EVERY / self.hz * 1000)
        minutes = max(window_ms / 60000, 1e-6)

        loose = sum(1 for o in self._owner if o is None) / n
        speeds = list(self._ball_speed) or [0.0]
        speed_sd = statistics.pstdev(speeds) if len(speeds) > 1 else 0.0
        turnovers_pm = len(self._turnovers) / minutes
        passes_pm = len(self._passes) / minutes

        chaos = _clamp01(
            0.50 * _clamp01(turnovers_pm / TURNOVERS_PER_MIN_MAX)
            + 0.25 * _clamp01(loose)
            + 0.25 * _clamp01(speed_sd / BALL_SPEED_SD_MAX)
        )

        # Rhythm: how evenly spaced the passes are. A metronomic build-up
        # scores high; a scrappy spell of long balls and turnovers scores low.
        gaps = [b[0] - a[0] for a, b in zip(self._passes, list(self._passes)[1:])]
        if len(gaps) >= 3:
            mean_gap = statistics.mean(gaps)
            cv = statistics.pstdev(gaps) / mean_gap if mean_gap else 1.0
            rhythm = _clamp01(1.0 - cv)
        else:
            rhythm = 0.0

        adir = {t: attack_direction(self.meta, t, frame.period)
                for t in self.team_ids}
        teams: list[TeamIndices] = []
        for team_id in self.team_ids:
            held = sum(1 for o in self._owner if o == team_id)
            owned = sum(1 for o in self._owner if o is not None)
            share = held / owned if owned else 0.0

            mine = [p for p in self._passes if p[1] == team_id]
            completion = (sum(1 for p in mine if p[2]) / len(mine)) if mine else 0.0

            d = adir[team_id]
            xs = self._ball_x or [0.0]
            territory = _clamp01(
                statistics.mean(x * d for x in xs) / fb.PITCH_X * 0.5 + 0.5)

            press_samples = self._press[team_id] or [0.0]
            press_intensity = _clamp01(
                statistics.mean(press_samples) / PRESS_BODIES_MAX)
            line_height = statistics.mean(self._line[team_id] or [0.5])

            teams.append(TeamIndices(
                team_id=team_id,
                control=round(_clamp01(0.40 * share + 0.30 * completion
                                       + 0.30 * territory), 3),
                possession_share=round(share, 3),
                pass_completion=round(completion, 3),
                territory=round(territory, 3),
                pressure=round(_clamp01(0.55 * press_intensity
                                        + 0.45 * line_height), 3),
                press_intensity=round(press_intensity, 3),
                line_height=round(line_height, 3),
            ))

        return IndexSnapshot(
            match_id=frame.match_id,
            period=frame.period,
            t_ms=frame.t_ms,
            window_ms=window_ms,
            frame_seq_range=(self._first_seq, frame.seq),
            teams=teams,
            chaos=round(chaos, 3),
            turnovers_per_min=round(turnovers_pm, 2),
            loose_ball_share=round(loose, 3),
            ball_speed_sd=round(speed_sd, 2),
            tempo=round(passes_pm, 2),
            rhythm=round(rhythm, 3),
        )

