"""Metrics engine: frames in, events and indices out. No AI, no I/O."""

from chalkboard.metrics.events import EventDetector, derive
from chalkboard.metrics.indices import IndexEngine, IndexSnapshot, TeamIndices
from chalkboard.metrics.pipeline import analyse, collect

__all__ = [
    "EventDetector", "derive",
    "IndexEngine", "IndexSnapshot", "TeamIndices",
    "analyse", "collect",
]
