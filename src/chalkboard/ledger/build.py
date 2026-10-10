"""
build.py - frames in, a populated Fact Ledger out.

One streaming pass. Each frame is fed to the event detector, its events go
to the index engine and the claim builder, and snapshots produce claims on
their own cadence. Nothing buffers the match, so the same path runs live.

Milestone claims need every frame (top speeds, distance covered), which
would be wasteful at 25 Hz, so those are sampled. Everything else sees the
full stream.
"""

from __future__ import annotations

from typing import Iterable

from chalkboard.contracts import MatchEvent, MatchMeta, TrackingFrame
from chalkboard.ledger.claims import ClaimBuilder
from chalkboard.ledger.store import FactLedger
from chalkboard.metrics.events import EventDetector
from chalkboard.metrics.indices import IndexEngine, IndexSnapshot

SNAPSHOT_EVERY_S = 15
MILESTONE_EVERY = 5         # frames


class BuildResult:
    __slots__ = ("ledger", "events", "snapshots")

    def __init__(self, ledger: FactLedger, events: list[MatchEvent],
                 snapshots: list[IndexSnapshot]):
        self.ledger = ledger
        self.events = events
        self.snapshots = snapshots


def build(meta: MatchMeta, frames: Iterable[TrackingFrame],
          snapshot_every_s: int = SNAPSHOT_EVERY_S,
          keep: bool = True) -> BuildResult:
    """
    `keep=False` discards events and snapshots after use, for long runs
    where only the ledger is wanted.
    """
    detector = EventDetector(meta)
    engine = IndexEngine(meta)
    ledger = FactLedger(meta.match_id)
    builder = ClaimBuilder(meta, ledger)

    cadence = snapshot_every_s * meta.tracking_hz
    events: list[MatchEvent] = []
    snapshots: list[IndexSnapshot] = []
    last: TrackingFrame | None = None

    for frame in frames:
        detected = detector.feed(frame)
        engine.observe(frame, detected)

        for event in detected:
            builder.on_event(event)
        if keep:
            events.extend(detected)

        if frame.seq % MILESTONE_EVERY == 0:
            builder.on_frame(frame)

        if frame.seq and frame.seq % cadence == 0:
            snap = engine.snapshot(frame)
            builder.on_snapshot(snap)
            if keep:
                snapshots.append(snap)

        last = frame

    if last is not None:
        snap = engine.snapshot(last)
        builder.on_snapshot(snap)
        if keep:
            snapshots.append(snap)

    return BuildResult(ledger, events, snapshots)
