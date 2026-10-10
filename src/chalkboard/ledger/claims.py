"""
claims.py - deterministic claim builders.

These turn events and index snapshots into LedgerEntries without any model
call. That ordering is deliberate: the whole pipeline works, and is
verifiable, before an LLM is involved anywhere. The Analyst agent will
later add causal claims on top - "because the press moved eight metres
higher" - and those are the ones that actually need reasoning. Everything
here is arithmetic, and arithmetic should never be delegated to a language
model.

Claim text is deliberately flat. "Calderwick City completed 85% of their
passes in the last two minutes" is a fact; making it read well is the
Storyteller's job. Keeping voice out of the ledger is what lets the same
entry serve a casual fan, an analyst and a broadcast caption without being
rewritten, and what lets the Verifier check it against evidence rather than
against prose.

Every builder names its `method`, so any number here can be recomputed from
the frames years later.
"""

from __future__ import annotations

import math
from typing import Optional

from chalkboard.contracts import (
    ClaimType,
    EvidenceKind,
    EvidenceRef,
    EventType,
    LedgerEntry,
    MatchEvent,
    MatchMeta,
    TrackingFrame,
)
from chalkboard.ledger.store import FactLedger
from chalkboard.metrics.indices import IndexSnapshot

VERSION = "0.1"

# Thresholds for "worth recording". Named rather than inlined so they can
# be argued with - they are editorial judgements, not facts.
PASS_DIFFICULTY = 0.68
PASS_BYPASSED = 5
CARRY_NOTABLE_M = 18.0
PRESSURE_NOTABLE_MS = 1500
CONTROL_SWING = 0.22
PRESSURE_SWING = 0.08
TEMPO_SWING = 2.5
SPRINT_MS = 7.6                 # m/s - a genuine sprint
DISTANCE_MILESTONES_M = (5_000, 8_000, 10_000)


class ClaimBuilder:
    """
        builder = ClaimBuilder(meta, ledger)
        builder.on_event(event)
        builder.on_snapshot(snapshot)
        builder.on_frame(frame)
    """

    def __init__(self, meta: MatchMeta, ledger: FactLedger):
        self.meta = meta
        self.ledger = ledger
        self.name_of = {p.player_id: p.name
                        for t in meta.teams for p in t.players}
        self.team_name = {t.team_id: t.name for t in meta.teams}
        self.team_short = {t.team_id: t.short_name for t in meta.teams}
        self.team_of = {p.player_id: t.team_id
                        for t in meta.teams for p in t.players}

        self._goals: dict[str, int] = {t.team_id: 0 for t in meta.teams}
        self._player_goals: dict[str, int] = {}
        self._top_speed: dict[str, float] = {}
        self._distance: dict[str, float] = {}
        self._last_pos: dict[str, tuple[float, float]] = {}
        self._milestones_hit: set[str] = set()
        self._last_control: Optional[float] = None
        self._last_pressure: dict[str, float] = {}
        self._last_tempo: Optional[float] = None

    # -- helper ---------------------------------------------------------

    def _add(self, *, period: int, t_ms: int, claim: str,
             claim_type: ClaimType, subject_ids: list[str], method: str,
             evidence: list[EvidenceRef], confidence: float = 0.98,
             value: Optional[float] = None, unit: Optional[str] = None,
             window_ms: Optional[tuple[int, int]] = None,
             supersedes: Optional[str] = None) -> LedgerEntry:
        return self.ledger.append(LedgerEntry(
            ledger_id=self.ledger.next_id(),
            match_id=self.meta.match_id,
            period=period,
            t_ms=t_ms,
            claim=claim,
            claim_type=claim_type,
            subject_ids=subject_ids,
            value=value,
            unit=unit,
            window_ms=window_ms,
            evidence=evidence,
            method=f"{method}@{VERSION}",
            confidence=confidence,
            supersedes=supersedes,
        ))

    @staticmethod
    def _from_event(event: MatchEvent) -> list[EvidenceRef]:
        lo, hi = event.frame_seq_range
        return [
            EvidenceRef(kind=EvidenceKind.EVENT, ids=[event.event_id]),
            EvidenceRef(kind=EvidenceKind.FRAME, ids=[str(lo), str(hi)],
                        note="tracking span"),
        ]

    # -- events ---------------------------------------------------------

    def on_event(self, event: MatchEvent) -> list[LedgerEntry]:
        if event.type is EventType.SHOT:
            return self._shot(event)
        if event.type is EventType.PASS:
            return self._pass(event)
        if event.type is EventType.PRESSURE:
            return self._pressure_event(event)
        return []

    def _shot(self, e: MatchEvent) -> list[LedgerEntry]:
        d = e.detail
        who = self.name_of[e.player_id]
        team = self.team_name[e.team_id]
        out: list[LedgerEntry] = []

        if d.goal:
            self._goals[e.team_id] += 1
            self._player_goals[e.player_id] = \
                self._player_goals.get(e.player_id, 0) + 1
            out.append(self._add(
                period=e.period, t_ms=e.t_ms,
                claim=(f"{who} scored for {team} from {d.distance_m:.1f} m, "
                       f"a chance worth {d.xg:.2f} expected goals."),
                claim_type=ClaimType.METRIC,
                subject_ids=[e.player_id, e.team_id],
                method="goal_claim", evidence=self._from_event(e),
                value=d.xg, unit="xG", confidence=1.0,
            ))
            tally = self._player_goals[e.player_id]
            if tally >= 2:
                word = {2: "a brace", 3: "a hat-trick"}.get(tally, f"{tally} goals")
                out.append(self._add(
                    period=e.period, t_ms=e.t_ms,
                    claim=f"{who} has scored {word} in this match.",
                    claim_type=ClaimType.MILESTONE,
                    subject_ids=[e.player_id, e.team_id],
                    method="scoring_milestone", evidence=self._from_event(e),
                    value=float(tally), unit="goals", confidence=1.0,
                ))
        else:
            verdict = ("was blocked" if d.blocked
                       else "was on target" if d.on_target
                       else "went off target")
            out.append(self._add(
                period=e.period, t_ms=e.t_ms,
                claim=(f"{who} shot from {d.distance_m:.1f} m and it {verdict}; "
                       f"the chance was worth {d.xg:.2f} expected goals."),
                claim_type=ClaimType.METRIC,
                subject_ids=[e.player_id, e.team_id],
                method="shot_claim", evidence=self._from_event(e),
                value=d.xg, unit="xG",
            ))
        return out

    def _pass(self, e: MatchEvent) -> list[LedgerEntry]:
        d = e.detail
        notable = (d.difficulty >= PASS_DIFFICULTY
                   or d.opponents_bypassed >= PASS_BYPASSED
                   or (d.progressive and d.distance_m >= 30.0))
        if not notable or not d.completed:
            return []

        who = self.name_of[e.player_id]
        bits = [f"{d.distance_m:.0f} m"]
        if d.opponents_bypassed:
            bits.append(f"past {d.opponents_bypassed} opponents")
        if d.into_final_third:
            bits.append("into the final third")
        elif d.progressive:
            bits.append("advancing the ball")

        return [self._add(
            period=e.period, t_ms=e.t_ms,
            claim=(f"{who} completed a pass of {', '.join(bits)}, "
                   f"rated {d.difficulty:.2f} for difficulty."),
            claim_type=ClaimType.METRIC,
            subject_ids=[e.player_id, e.team_id],
            method="pass_claim", evidence=self._from_event(e),
            value=d.difficulty, unit="difficulty",
            confidence=0.95,
        )]

    # Carries are detected but produce no claim yet - CARRY has no typed
    # detail on the contract, so there is nothing to assert beyond "it
    # happened". It gets a claim when it gets a detail model.

    def _pressure_event(self, e: MatchEvent) -> list[LedgerEntry]:
        d = e.detail
        if d.duration_ms < PRESSURE_NOTABLE_MS or len(d.pressing_player_ids) < 2:
            return []
        who = self.name_of[e.player_id]
        return [self._add(
            period=e.period, t_ms=e.t_ms,
            claim=(f"{who} was closed down by {len(d.pressing_player_ids)} "
                   f"opponents for {d.duration_ms / 1000:.1f} s, the nearest "
                   f"within {d.min_distance_m:.1f} m."),
            claim_type=ClaimType.PATTERN,
            subject_ids=[e.player_id, e.team_id],
            method="pressure_event", evidence=self._from_event(e),
            value=d.duration_ms / 1000, unit="s",
        )]

    # -- snapshots ------------------------------------------------------

    def on_snapshot(self, snap: IndexSnapshot) -> list[LedgerEntry]:
        ev = [
            EvidenceRef(kind=EvidenceKind.METRIC, ids=[snap.snapshot_id],
                        note=snap.method),
            EvidenceRef(kind=EvidenceKind.FRAME,
                        ids=[str(snap.frame_seq_range[0]),
                             str(snap.frame_seq_range[1])],
                        note="window"),
        ]
        window = (max(snap.t_ms - snap.window_ms, 0), snap.t_ms)
        out: list[LedgerEntry] = []
        out += self._control(snap, ev, window)
        out += self._pressure_state(snap, ev, window)
        out += self._tempo(snap, ev, window)
        return out

    def _control(self, snap, ev, window) -> list[LedgerEntry]:
        lead = max(snap.teams, key=lambda t: t.control)
        other = min(snap.teams, key=lambda t: t.control)
        margin = lead.control - other.control

        if self._last_control is not None and abs(
                margin - self._last_control) < CONTROL_SWING:
            return []
        self._last_control = margin

        previous = self.ledger.latest(claim_type=ClaimType.PATTERN,
                                      method=f"control_state@{VERSION}")
        if margin < 0.08:
            text = (f"Neither side is controlling the game: "
                    f"possession is {snap.teams[0].possession_share:.0%} to "
                    f"{snap.teams[1].possession_share:.0%} with chaos at "
                    f"{snap.chaos:.2f}.")
            subjects = [t.team_id for t in snap.teams]
        else:
            text = (f"{self.team_name[lead.team_id]} are controlling the game: "
                    f"{lead.possession_share:.0%} of the ball, "
                    f"{lead.pass_completion:.0%} pass completion, territory "
                    f"{lead.territory:.2f}.")
            subjects = [lead.team_id]

        return [self._add(
            period=snap.period, t_ms=snap.t_ms, claim=text,
            claim_type=ClaimType.PATTERN, subject_ids=subjects,
            method="control_state", evidence=ev,
            value=round(margin, 3), unit="index", window_ms=window,
            confidence=0.9,
            supersedes=previous.ledger_id if previous else None,
        )]

    def _pressure_state(self, snap, ev, window) -> list[LedgerEntry]:
        out = []
        for team in snap.teams:
            before = self._last_pressure.get(team.team_id)
            if before is not None and abs(team.pressure - before) < PRESSURE_SWING:
                continue
            self._last_pressure[team.team_id] = team.pressure
            if before is None:
                continue

            direction = "stepped up" if team.pressure > before else "dropped off"
            previous = self.ledger.latest(
                claim_type=ClaimType.PATTERN, subject=team.team_id,
                method=f"pressure_state@{VERSION}")
            out.append(self._add(
                period=snap.period, t_ms=snap.t_ms,
                claim=(f"{self.team_name[team.team_id]} have {direction} their "
                       f"press: pressure index {before:.2f} to "
                       f"{team.pressure:.2f}, line height "
                       f"{team.line_height:.2f}."),
                claim_type=ClaimType.PATTERN, subject_ids=[team.team_id],
                method="pressure_state", evidence=ev,
                value=team.pressure, unit="index", window_ms=window,
                confidence=0.9,
                supersedes=previous.ledger_id if previous else None,
            ))
        return out

    def _tempo(self, snap, ev, window) -> list[LedgerEntry]:
        if self._last_tempo is None:
            self._last_tempo = snap.tempo
            return []
        if abs(snap.tempo - self._last_tempo) < TEMPO_SWING:
            return []
        before, self._last_tempo = self._last_tempo, snap.tempo
        direction = "quickened" if snap.tempo > before else "slowed"
        return [self._add(
            period=snap.period, t_ms=snap.t_ms,
            claim=(f"The game has {direction}: {before:.1f} to "
                   f"{snap.tempo:.1f} passes per minute, rhythm "
                   f"{snap.rhythm:.2f}."),
            claim_type=ClaimType.COMPARISON,
            subject_ids=[t.team_id for t in snap.teams],
            method="tempo_compare", evidence=ev,
            value=round(snap.tempo - before, 2), unit="passes/min",
            window_ms=window, confidence=0.9,
        )]

    # -- frames ---------------------------------------------------------

    def on_frame(self, frame: TrackingFrame) -> list[LedgerEntry]:
        """Physical milestones. Cheap per frame, so kept arithmetic only."""
        out: list[LedgerEntry] = []
        for p in frame.players:
            pid = p.player_id
            last = self._last_pos.get(pid)
            if last is not None:
                self._distance[pid] = self._distance.get(pid, 0.0) + math.hypot(
                    p.pos.x - last[0], p.pos.y - last[1])
            self._last_pos[pid] = (p.pos.x, p.pos.y)

            if p.speed > self._top_speed.get(pid, 0.0):
                self._top_speed[pid] = p.speed
                key = f"sprint:{pid}"
                if p.speed >= SPRINT_MS and key not in self._milestones_hit:
                    self._milestones_hit.add(key)
                    out.append(self._add(
                        period=frame.period, t_ms=frame.t_ms,
                        claim=(f"{self.name_of[pid]} hit {p.speed:.1f} m/s, "
                               f"his quickest of the match so far."),
                        claim_type=ClaimType.MILESTONE,
                        subject_ids=[pid, self.team_of[pid]],
                        method="speed_milestone",
                        evidence=[EvidenceRef(kind=EvidenceKind.FRAME,
                                              ids=[str(frame.seq)])],
                        value=round(p.speed, 2), unit="m/s", confidence=1.0,
                    ))

            run = self._distance.get(pid, 0.0)
            for mark in DISTANCE_MILESTONES_M:
                key = f"dist:{pid}:{mark}"
                if run >= mark and key not in self._milestones_hit:
                    self._milestones_hit.add(key)
                    out.append(self._add(
                        period=frame.period, t_ms=frame.t_ms,
                        claim=(f"{self.name_of[pid]} has covered "
                               f"{mark / 1000:.0f} km."),
                        claim_type=ClaimType.MILESTONE,
                        subject_ids=[pid, self.team_of[pid]],
                        method="distance_milestone",
                        evidence=[EvidenceRef(kind=EvidenceKind.FRAME,
                                              ids=[str(frame.seq)])],
                        value=float(mark), unit="m", confidence=1.0,
                    ))
        return out

