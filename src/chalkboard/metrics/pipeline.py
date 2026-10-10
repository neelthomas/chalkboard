"""
pipeline.py - frames in, events and index snapshots out.

One pass, streaming, no buffering of the match. This is the shape the live
path needs: each frame is fed to the detector, its events go straight to
the index engine, and a snapshot is emitted on a fixed cadence.
"""

from __future__ import annotations

from typing import Iterable, Iterator, Union

from chalkboard.contracts import MatchEvent, MatchMeta, TrackingFrame
from chalkboard.metrics.events import EventDetector
from chalkboard.metrics.indices import IndexEngine, IndexSnapshot

Output = Union[MatchEvent, IndexSnapshot]

SNAPSHOT_EVERY_S = 15


def analyse(meta: MatchMeta, frames: Iterable[TrackingFrame],
            snapshot_every_s: int = SNAPSHOT_EVERY_S) -> Iterator[Output]:
    """Yields MatchEvents as they are detected, interleaved with snapshots."""
    detector = EventDetector(meta)
    engine = IndexEngine(meta)
    cadence = snapshot_every_s * meta.tracking_hz
    last: TrackingFrame | None = None

    for frame in frames:
        events = detector.feed(frame)
        engine.observe(frame, events)
        yield from events
        if frame.seq and frame.seq % cadence == 0:
            yield engine.snapshot(frame)
        last = frame

    if last is not None:
        yield engine.snapshot(last)


def collect(meta: MatchMeta, frames: Iterable[TrackingFrame],
            snapshot_every_s: int = SNAPSHOT_EVERY_S
            ) -> tuple[list[MatchEvent], list[IndexSnapshot]]:
    """Batch helper for tests and reports."""
    events: list[MatchEvent] = []
    snaps: list[IndexSnapshot] = []
    for item in analyse(meta, frames, snapshot_every_s):
        (snaps if isinstance(item, IndexSnapshot) else events).append(item)
    return events, snaps
