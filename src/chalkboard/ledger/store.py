"""
store.py - the Fact Ledger.

Append-only. Every entry is one atomic, evidence-backed claim. The
Storyteller may not write a sentence that is not backed by an entry here,
and the Verifier is the gate that enforces it.

Three properties the rest of the system depends on:

    append-only     entries are never edited. Verification and supersession
                    both work by writing a new entry, so the history of what
                    was believed and when stays intact. If a recap ever
                    contradicts itself, the ledger can say why.

    superseding     "Calderwick are controlling this" is true at 55' and
                    false at 75'. Claims expire. An entry can supersede an
                    earlier one, and `active_at` answers what was still
                    standing at a given moment - which is what a recap needs
                    so it does not assemble a story out of stale facts.

    evidence        no entry without at least one EvidenceRef, enforced by
                    the contract itself. `trace` walks a claim down to the
                    frames behind it.
"""

from __future__ import annotations

from collections import Counter
from typing import Iterable, Iterator, Optional

from chalkboard.contracts import (
    ClaimType,
    EvidenceKind,
    LedgerEntry,
    VerificationStatus,
)


class FactLedger:
    """
        ledger = FactLedger("m_0007")
        entry = ledger.append(claim)
        ledger.mark(entry.ledger_id, VerificationStatus.SUPPORTED)
        for e in ledger.active_at(t_ms=2_700_000):
            ...
    """

    def __init__(self, match_id: str):
        self.match_id = match_id
        self._entries: list[LedgerEntry] = []
        self._by_id: dict[str, LedgerEntry] = {}
        self._superseded: set[str] = set()
        self._n = 0

    # -- writing --------------------------------------------------------

    def next_id(self) -> str:
        self._n += 1
        return f"lg_{self._n:06d}"

    def append(self, entry: LedgerEntry) -> LedgerEntry:
        if entry.match_id != self.match_id:
            raise ValueError(
                f"entry belongs to {entry.match_id}, ledger is {self.match_id}")
        if entry.ledger_id in self._by_id:
            raise ValueError(f"{entry.ledger_id} already in the ledger")

        if entry.supersedes:
            if entry.supersedes not in self._by_id:
                raise ValueError(f"cannot supersede unknown {entry.supersedes}")
            self._superseded.add(entry.supersedes)

        self._entries.append(entry)
        self._by_id[entry.ledger_id] = entry
        return entry

    def extend(self, entries: Iterable[LedgerEntry]) -> list[LedgerEntry]:
        return [self.append(e) for e in entries]

    def mark(self, ledger_id: str, status: VerificationStatus,
             note: Optional[str] = None) -> LedgerEntry:
        """
        Record a verdict. Entries are frozen, so this replaces the stored
        object with an updated copy rather than mutating in place - the
        claim, its evidence and its method are untouched.
        """
        original = self._by_id[ledger_id]
        updated = original.model_copy(
            update={"status": status, "verifier_note": note})
        self._by_id[ledger_id] = updated
        self._entries[self._entries.index(original)] = updated
        return updated

    # -- reading --------------------------------------------------------

    def get(self, ledger_id: str) -> LedgerEntry:
        return self._by_id[ledger_id]

    def __len__(self) -> int:
        return len(self._entries)

    def __iter__(self) -> Iterator[LedgerEntry]:
        return iter(self._entries)

    def is_superseded(self, ledger_id: str) -> bool:
        return ledger_id in self._superseded

    def query(self, *, claim_type: Optional[ClaimType] = None,
              subject: Optional[str] = None,
              period: Optional[int] = None,
              since_ms: Optional[int] = None,
              until_ms: Optional[int] = None,
              status: Optional[VerificationStatus] = None,
              usable_only: bool = False,
              live_only: bool = False) -> list[LedgerEntry]:
        """
        `usable_only` drops anything the Verifier rejected or has not seen -
        this is what the Storyteller reads.
        `live_only` drops anything a later claim has superseded.
        """
        out = []
        for e in self._entries:
            if claim_type is not None and e.claim_type is not claim_type:
                continue
            if subject is not None and subject not in e.subject_ids:
                continue
            if period is not None and e.period != period:
                continue
            if since_ms is not None and e.t_ms < since_ms:
                continue
            if until_ms is not None and e.t_ms > until_ms:
                continue
            if status is not None and e.status is not status:
                continue
            if usable_only and e.status is not VerificationStatus.SUPPORTED:
                continue
            if live_only and e.ledger_id in self._superseded:
                continue
            out.append(e)
        return out

    def active_at(self, t_ms: int, period: Optional[int] = None,
                  **kw) -> list[LedgerEntry]:
        """
        What was still standing at this moment: claims made by then, which
        nothing made by then has since overruled.
        """
        made_by_now = [
            e for e in self.query(period=period, until_ms=t_ms, **kw)
        ]
        overruled = {
            e.supersedes for e in made_by_now
            if e.supersedes is not None
        }
        return [e for e in made_by_now if e.ledger_id not in overruled]

    def latest(self, *, claim_type: Optional[ClaimType] = None,
               subject: Optional[str] = None,
               method: Optional[str] = None) -> Optional[LedgerEntry]:
        """Most recent matching entry, for building a supersession chain."""
        for e in reversed(self._entries):
            if claim_type is not None and e.claim_type is not claim_type:
                continue
            if subject is not None and subject not in e.subject_ids:
                continue
            if method is not None and e.method != method:
                continue
            return e
        return None

    # -- provenance -----------------------------------------------------

    def trace(self, ledger_id: str, _seen: Optional[set[str]] = None) -> dict:
        """
        Flatten a claim down to the raw evidence behind it, following
        ledger-on-ledger references. This is what makes a sentence
        clickable all the way to the tracking frames.
        """
        seen = _seen if _seen is not None else set()
        if ledger_id in seen:
            return {"events": set(), "frames": set(), "metrics": set(),
                    "ledger": set()}
        seen.add(ledger_id)

        entry = self._by_id[ledger_id]
        out = {"events": set(), "frames": set(), "metrics": set(),
               "ledger": {ledger_id}}
        for ref in entry.evidence:
            if ref.kind is EvidenceKind.EVENT:
                out["events"].update(ref.ids)
            elif ref.kind is EvidenceKind.FRAME:
                out["frames"].update(ref.ids)
            elif ref.kind is EvidenceKind.METRIC:
                out["metrics"].update(ref.ids)
            elif ref.kind is EvidenceKind.LEDGER:
                for parent in ref.ids:
                    if parent in self._by_id:
                        deeper = self.trace(parent, seen)
                        for key in out:
                            out[key].update(deeper[key])
        return out

    # -- reporting ------------------------------------------------------

    def summary(self) -> dict:
        by_type = Counter(e.claim_type.value for e in self._entries)
        by_status = Counter(e.status.value for e in self._entries)
        return {
            "total": len(self._entries),
            "superseded": len(self._superseded),
            "by_type": dict(by_type),
            "by_status": dict(by_status),
            "mean_evidence_refs": (
                sum(len(e.evidence) for e in self._entries) / len(self._entries)
                if self._entries else 0.0
            ),
        }
