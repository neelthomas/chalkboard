"""
director.py - LedgerEntry -> OverlayPacket.

Stage (d) of the brief: render insight into something that can sit on
screen alongside the match, "timed and machine-readable enough to be
rendered as synchronized graphical overlays on a live match feed".

So this does not produce pictures. It produces instructions: what kind of
graphic, carrying which numbers, on screen from when until when, at what
priority. A rendering partner binds those to its own templates. That is why
OverlayPacket keeps `data` separate from the text - ship a pre-formatted
sentence and the packet is only renderable as a caption.

The scheduler is the Producer's job showing through: a real feed cannot
have three lower-thirds fighting for the same strip, so packets contend for
a safe area and the higher priority wins. Dropping an overlay is a decision,
not a failure, and the count of what was dropped is reported.

Every packet carries the ledger ids it came from. Nothing reaches the screen
without provenance, which is what makes a claim on screen clickable back to
the tracking.
"""

from __future__ import annotations

from typing import Iterable, Optional

from chalkboard import language
from chalkboard.contracts import (
    ClaimType,
    LedgerEntry,
    Lens,
    LensType,
    MatchMeta,
    OverlayPacket,
    OverlayType,
    RenderHints,
    VerificationStatus,
)

VERSION = "0.1"

# method prefix -> (overlay, safe area, priority, seconds on screen)
STYLE: dict[str, tuple[OverlayType, str, int, float]] = {
    "goal_claim":         (OverlayType.LOWER_THIRD,    "lower_third", 9, 7.0),
    "scoring_milestone":  (OverlayType.LOWER_THIRD,    "lower_third", 8, 6.0),
    "shot_claim":         (OverlayType.STAT_BUG,       "upper_right", 6, 4.5),
    "pass_claim":         (OverlayType.PLAYER_CARD,    "lower_third", 3, 4.0),
    "speed_milestone":    (OverlayType.PLAYER_CARD,    "upper_right", 4, 4.0),
    "distance_milestone": (OverlayType.STAT_BUG,       "upper_right", 2, 3.5),
    "control_state":      (OverlayType.MOMENTUM_STRIP, "sidebar",     5, 9.0),
    "pressure_state":     (OverlayType.PRESSURE_METER, "sidebar",     5, 8.0),
    "tempo_compare":      (OverlayType.STAT_BUG,       "upper_right", 4, 5.0),
    "pressure_event":     (OverlayType.STAT_BUG,       "upper_right", 3, 4.0),
}

DEFAULT_STYLE = (OverlayType.STAT_BUG, "upper_right", 2, 4.0)


def _body(entry: LedgerEntry, locale: str) -> str:
    """
    The claim, in this packet's language. Brief (vi).

    The entry stores a template key and its parameters, so the sentence is
    rendered here rather than translated - see language.py. An entry
    without a template (anything written before that existed, or by hand)
    falls back to its canonical English.
    """
    if entry.template:
        return language.render(entry.template, entry.params, locale)
    return entry.claim


class Director:
    """
        director = Director(meta)
        packets = director.direct(ledger)
    """

    def __init__(self, meta: MatchMeta, locale: str = "en-GB",
                 require_verified: bool = False):
        self.meta = meta
        self.locale = locale
        self.require_verified = require_verified
        self.player_names = {p.player_id: p.name
                             for t in meta.teams for p in t.players}
        self.team_names = {t.team_id: t.name for t in meta.teams}
        self.players = set(self.player_names)
        self.teams = set(self.team_names)
        self._n = 0
        self.dropped = 0

    # -- helpers --------------------------------------------------------

    def _lens(self, entry: LedgerEntry) -> Lens:
        for sid in entry.subject_ids:
            if sid in self.players:
                return Lens(type=LensType.PLAYER, target_id=sid,
                            depth="standard")
        for sid in entry.subject_ids:
            if sid in self.teams:
                return Lens(type=LensType.CLUB, target_id=sid, depth="standard")
        return Lens()

    def _absolute_ms(self, entry: LedgerEntry) -> int:
        """Match clock, continuous across periods - what a renderer cues on."""
        offset = 0
        for info in self.meta.periods:
            if info.period == entry.period:
                break
            offset += info.duration_ms
        return offset + entry.t_ms

    def packet_for(self, entry: LedgerEntry) -> Optional[OverlayPacket]:
        if self.require_verified and entry.status is not VerificationStatus.SUPPORTED:
            return None

        method = entry.method.split("@")[0]
        overlay, safe_area, priority, seconds = STYLE.get(method, DEFAULT_STYLE)

        data: dict = {"claim_type": entry.claim_type.value,
                      "method": entry.method}
        if entry.value is not None:
            data["value"] = entry.value
            data["unit"] = entry.unit
        if entry.claim_type is ClaimType.MILESTONE:
            data["milestone"] = True
        for sid in entry.subject_ids:
            if sid in self.players:
                data["player"] = self.player_names[sid]
            elif sid in self.teams:
                data["team"] = self.team_names[sid]

        text = _body(entry, self.locale)

        self._n += 1
        return OverlayPacket(
            packet_id=f"ov_{self._n:05d}",
            match_id=entry.match_id,
            valid_from_ms=self._absolute_ms(entry),
            duration_ms=int(seconds * 1000),
            priority=priority,
            overlay_type=overlay,
            lens=self._lens(entry),
            locale=self.locale,
            headline=language.headline(entry.method, self.locale),
            body=text,
            speech_text=text,
            data=data,
            render_hints=RenderHints(safe_area=safe_area,
                                     animation_in="wipe" if priority >= 8
                                     else "fade"),
            evidence=[entry.ledger_id],
        )

    # -- scheduling -----------------------------------------------------

    def direct(self, entries: Iterable[LedgerEntry]) -> list[OverlayPacket]:
        """
        Build packets and resolve contention. Two overlays cannot share a
        safe area at the same moment; the higher priority keeps the slot and
        the loser is dropped rather than queued, because a stat bug about
        the 41st minute is worthless at the 44th.
        """
        candidates: list[OverlayPacket] = []
        for entry in entries:
            packet = self.packet_for(entry)
            if packet is not None:
                candidates.append(packet)

        # Highest priority first, then earliest, so winners claim slots.
        candidates.sort(key=lambda p: (-p.priority, p.valid_from_ms))

        busy: dict[str, list[tuple[int, int]]] = {}
        kept: list[OverlayPacket] = []
        for packet in candidates:
            area = (packet.render_hints.safe_area
                    if packet.render_hints else "full")
            start = packet.valid_from_ms
            end = start + packet.duration_ms
            spans = busy.setdefault(area, [])
            if any(start < b and a < end for a, b in spans):
                self.dropped += 1
                continue
            spans.append((start, end))
            kept.append(packet)

        kept.sort(key=lambda p: p.valid_from_ms)
        return kept


def direct(meta: MatchMeta, entries: Iterable[LedgerEntry],
           **kw) -> list[OverlayPacket]:
    return Director(meta, **kw).direct(entries)
