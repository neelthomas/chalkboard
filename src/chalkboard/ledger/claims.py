"""
claims.py - deterministic claim builders.

These turn events and index snapshots into LedgerEntries without any model
call. That ordering is deliberate: the whole pipeline works, and is
verifiable, before an LLM is involved anywhere. The Analyst agent will
later add causal claims on top - "because the press moved eight metres
higher" - and those are the ones that actually need reasoning. Everything
here is arithmetic, and arithmetic should never be delegated to a language
model.

Each builder emits a **template key and parameters** rather than a
hand-written sentence, and the canonical English `claim` is rendered from
that same pair. One source of truth, so the stored sentence and the
localised one can never drift apart, and brief (vi) comes free - see
language.py.

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

from chalkboard import language
from chalkboard.contracts import (
    ClaimType,
    EventType,
    EvidenceKind,
    EvidenceRef,
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
PASS_PROGRESSIVE_M = 30.0
CARRY_NOTABLE_M = 18.0
PRESSURE_NOTABLE_MS = 1500
CONTROL_SWING = 0.22
CONTROL_BALANCED = 0.08
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
        self.team_of = {p.player_id: t.team_id
                        for t in meta.teams for p in t.players}

        self._player_goals: dict[str, int] = {}
        self._top_speed: dict[str, float] = {}
        self._distance: dict[str, float] = {}
        self._last_pos: dict[str, tuple[float, float]] = {}
        self._milestones_hit: set[str] = set()
        self._last_control: Optional[float] = None
        self._last_pressure: dict[str, float] = {}
        self._last_tempo: Optional[float] = None

    # -- helper ---------------------------------------------------------

    def _add(self, *, period: int, t_ms: int, template: str, params: dict,
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
            claim=language.render(template, params, language.DEFAULT_LOCALE),
            claim_type=claim_type,
            subject_ids=subject_ids,
            template=template,
            params=params,
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
        out: list[LedgerEntry] = []

        if d.goal:
            self._player_goals[e.player_id] = \
                self._player_goals.get(e.player_id, 0) + 1
            out.append(self._add(
                period=e.period, t_ms=e.t_ms,
                template="goal",
                params={"player": who, "team": self.team_name[e.team_id],
                        "distance": d.distance_m, "xg": d.xg},
                claim_type=ClaimType.METRIC,
                subject_ids=[e.player_id, e.team_id],
                method="goal_claim", evidence=self._from_event(e),
                value=d.xg, unit="xG", confidence=1.0,
            ))
            tally = self._player_goals[e.player_id]
            if tally >= 2:
                key = {2: "milestone.brace",
                       3: "milestone.hattrick"}.get(tally, "milestone.many")
                out.append(self._add(
                    period=e.period, t_ms=e.t_ms,
                    template=key, params={"player": who, "goals": tally},
                    claim_type=ClaimType.MILESTONE,
                    subject_ids=[e.player_id, e.team_id],
                    method="scoring_milestone", evidence=self._from_event(e),
                    value=float(tally), unit="goals", confidence=1.0,
                ))
        else:
            key = ("shot.blocked" if d.blocked
                   else "shot.on_target" if d.on_target
                   else "shot.off_target")
            out.append(self._add(
                period=e.period, t_ms=e.t_ms,
                template=key,
                params={"player": who, "distance": d.distance_m, "xg": d.xg},
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
                   or (d.progressive and d.distance_m >= PASS_PROGRESSIVE_M))
        if not notable or not d.completed:
            return []

        bypassed = d.opponents_bypassed > 0
        if bypassed and d.into_final_third:
            key = "pass.bypassed_final_third"
        elif bypassed:
            key = "pass.bypassed"
        elif d.into_final_third:
            key = "pass.final_third"
        else:
            key = "pass.plain"

        return [self._add(
            period=e.period, t_ms=e.t_ms,
            template=key,
            params={"player": self.name_of[e.player_id],
                    "distance": d.distance_m,
                    "bypassed": d.opponents_bypassed,
                    "difficulty": d.difficulty},
            claim_type=ClaimType.METRIC,
            subject_ids=[e.player_id, e.team_id],
            method="pass_claim", evidence=self._from_event(e),
            value=d.difficulty, unit="difficulty", confidence=0.95,
        )]

    # Carries are detected but produce no claim yet - CARRY has no typed
    # detail on the contract, so there is nothing to assert beyond "it
    # happened". It gets a claim when it gets a detail model.

    def _pressure_event(self, e: MatchEvent) -> list[LedgerEntry]:
        d = e.detail
        if d.duration_ms < PRESSURE_NOTABLE_MS or len(d.pressing_player_ids) < 2:
            return []
        return [self._add(
            period=e.period, t_ms=e.t_ms,
            template="pressure",
            params={"player": self.name_of[e.player_id],
                    "opponents": len(d.pressing_player_ids),
                    "seconds": d.duration_ms / 1000,
                    "distance": d.min_distance_m},
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
        if margin < CONTROL_BALANCED:
            template = "control.balanced"
            params = {
                "possession": round(snap.teams[0].possession_share * 100),
                "possession_other": round(snap.teams[1].possession_share * 100),
                "chaos": snap.chaos,
            }
            subjects = [t.team_id for t in snap.teams]
        else:
            template = "control.leader"
            params = {
                "team": self.team_name[lead.team_id],
                "possession": round(lead.possession_share * 100),
                "completion": round(lead.pass_completion * 100),
                "territory": lead.territory,
            }
            subjects = [lead.team_id]

        return [self._add(
            period=snap.period, t_ms=snap.t_ms,
            template=template, params=params,
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

            previous = self.ledger.latest(
                claim_type=ClaimType.PATTERN, subject=team.team_id,
                method=f"pressure_state@{VERSION}")
            out.append(self._add(
                period=snap.period, t_ms=snap.t_ms,
                template="press.up" if team.pressure > before else "press.down",
                params={"team": self.team_name[team.team_id],
                        "before": before, "after": team.pressure,
                        "line_height": team.line_height},
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
        return [self._add(
            period=snap.period, t_ms=snap.t_ms,
            template="tempo.up" if snap.tempo > before else "tempo.down",
            params={"before": before, "after": snap.tempo,
                    "rhythm": snap.rhythm},
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
                        template="speed",
                        params={"player": self.name_of[pid], "speed": p.speed},
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
                        template="distance",
                        params={"player": self.name_of[pid],
                                "km": float(mark) / 1000},
                        claim_type=ClaimType.MILESTONE,
                        subject_ids=[pid, self.team_of[pid]],
                        method="distance_milestone",
                        evidence=[EvidenceRef(kind=EvidenceKind.FRAME,
                                              ids=[str(frame.seq)])],
                        value=float(mark), unit="m", confidence=1.0,
                    ))
        return out
