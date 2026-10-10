"""
The Fact Ledger: append-only storage, supersession, provenance, and the
deterministic claim builders.

The invariant the whole narrative layer rests on is that no claim exists
without evidence that reaches the tracking. Several tests here exist only
to make that expensive to break.
"""

import itertools

import pytest
from pydantic import ValidationError

from chalkboard.contracts import (
    ClaimType,
    EvidenceKind,
    EvidenceRef,
    LedgerEntry,
    VerificationStatus,
)
from chalkboard.fixtures import build_match
from chalkboard.ledger import FactLedger, build
from chalkboard.sim import MatchSimulator

SEED = 7


@pytest.fixture(scope="module")
def match():
    meta = build_match(SEED)
    sim = MatchSimulator(meta)
    result = build(meta, sim.run())
    return meta, sim, result


def entry(ledger: FactLedger, **kw) -> LedgerEntry:
    defaults = dict(
        ledger_id=ledger.next_id(),
        match_id=ledger.match_id,
        period=1,
        t_ms=1000,
        claim="something happened",
        claim_type=ClaimType.METRIC,
        subject_ids=["p_1"],
        evidence=[EvidenceRef(kind=EvidenceKind.EVENT, ids=["ev_1"])],
        method="test@0.1",
        confidence=0.9,
    )
    defaults.update(kw)
    return LedgerEntry(**defaults)


# --- store mechanics ----------------------------------------------------

class TestStore:
    def test_append_and_get(self):
        lg = FactLedger("m_0007")
        e = lg.append(entry(lg))
        assert lg.get(e.ledger_id) == e
        assert len(lg) == 1

    def test_rejects_foreign_match(self):
        lg = FactLedger("m_0007")
        with pytest.raises(ValueError, match="belongs to"):
            lg.append(entry(lg, match_id="m_9999"))

    def test_rejects_duplicate_id(self):
        lg = FactLedger("m_0007")
        e = lg.append(entry(lg))
        with pytest.raises(ValueError, match="already in the ledger"):
            lg.append(entry(lg, ledger_id=e.ledger_id))

    def test_rejects_superseding_unknown(self):
        lg = FactLedger("m_0007")
        with pytest.raises(ValueError, match="cannot supersede"):
            lg.append(entry(lg, supersedes="lg_999999"))

    def test_a_claim_without_evidence_cannot_be_built(self):
        """The contract refuses it, so the ledger never has to."""
        lg = FactLedger("m_0007")
        with pytest.raises(ValidationError):
            entry(lg, evidence=[])

    def test_marking_preserves_the_claim(self):
        lg = FactLedger("m_0007")
        e = lg.append(entry(lg))
        marked = lg.mark(e.ledger_id, VerificationStatus.SUPPORTED, "checked")
        assert marked.status is VerificationStatus.SUPPORTED
        assert marked.verifier_note == "checked"
        assert marked.claim == e.claim
        assert marked.evidence == e.evidence
        assert marked.method == e.method
        assert lg.get(e.ledger_id).status is VerificationStatus.SUPPORTED
        assert len(lg) == 1

    def test_usable_only_hides_unverified(self):
        lg = FactLedger("m_0007")
        a = lg.append(entry(lg))
        b = lg.append(entry(lg))
        lg.mark(b.ledger_id, VerificationStatus.SUPPORTED)
        usable = lg.query(usable_only=True)
        assert [x.ledger_id for x in usable] == [b.ledger_id]
        assert a.ledger_id not in {x.ledger_id for x in usable}


class TestSupersession:
    def test_superseded_claims_drop_out(self):
        lg = FactLedger("m_0007")
        old = lg.append(entry(lg, t_ms=1000, claim="they are on top"))
        new = lg.append(entry(lg, t_ms=5000, claim="no longer",
                              supersedes=old.ledger_id))
        assert lg.is_superseded(old.ledger_id)
        live = lg.query(live_only=True)
        assert [x.ledger_id for x in live] == [new.ledger_id]

    def test_active_at_respects_the_clock(self):
        """
        Before the correction exists, the original claim is still what was
        believed. A recap of the 60th minute must not use 80th-minute facts.
        """
        lg = FactLedger("m_0007")
        old = lg.append(entry(lg, t_ms=1000))
        lg.append(entry(lg, t_ms=9000, supersedes=old.ledger_id))
        early = lg.active_at(5000)
        assert [x.ledger_id for x in early] == [old.ledger_id]
        late = lg.active_at(10_000)
        assert old.ledger_id not in {x.ledger_id for x in late}

    def test_latest_finds_the_chain_head(self):
        lg = FactLedger("m_0007")
        lg.append(entry(lg, t_ms=1000, method="control@0.1"))
        second = lg.append(entry(lg, t_ms=2000, method="control@0.1"))
        assert lg.latest(method="control@0.1").ledger_id == second.ledger_id


class TestTrace:
    def test_trace_collects_direct_evidence(self):
        lg = FactLedger("m_0007")
        e = lg.append(entry(lg, evidence=[
            EvidenceRef(kind=EvidenceKind.EVENT, ids=["ev_1", "ev_2"]),
            EvidenceRef(kind=EvidenceKind.FRAME, ids=["10", "40"]),
        ]))
        tr = lg.trace(e.ledger_id)
        assert tr["events"] == {"ev_1", "ev_2"}
        assert tr["frames"] == {"10", "40"}

    def test_trace_follows_claims_built_on_claims(self):
        lg = FactLedger("m_0007")
        base = lg.append(entry(lg, evidence=[
            EvidenceRef(kind=EvidenceKind.FRAME, ids=["7"])]))
        derived = lg.append(entry(lg, evidence=[
            EvidenceRef(kind=EvidenceKind.LEDGER, ids=[base.ledger_id])]))
        assert lg.trace(derived.ledger_id)["frames"] == {"7"}

    def test_trace_survives_a_cycle(self):
        lg = FactLedger("m_0007")
        a = lg.append(entry(lg, evidence=[
            EvidenceRef(kind=EvidenceKind.FRAME, ids=["1"])]))
        b = lg.append(entry(lg, evidence=[
            EvidenceRef(kind=EvidenceKind.LEDGER, ids=[a.ledger_id])]))
        # Not reachable through the API, but a cycle must not hang.
        lg._by_id[a.ledger_id] = a.model_copy(update={"evidence": [
            EvidenceRef(kind=EvidenceKind.LEDGER, ids=[b.ledger_id])]})
        assert lg.trace(b.ledger_id) is not None


# --- built from a real match --------------------------------------------

class TestBuiltLedger:
    def test_it_produced_claims(self, match):
        _m, _sim, r = match
        assert len(r.ledger) > 100

    def test_every_claim_has_evidence_reaching_tracking(self, match):
        """The invariant the narrative layer rests on."""
        _m, _sim, r = match
        for e in r.ledger:
            tr = r.ledger.trace(e.ledger_id)
            assert tr["events"] or tr["frames"], f"{e.ledger_id} floats free"

    def test_every_claim_names_a_versioned_method(self, match):
        _m, _sim, r = match
        for e in r.ledger:
            assert "@" in e.method, e.method

    def test_goal_claims_match_the_scoreline(self, match):
        _m, sim, r = match
        scored = [e for e in r.ledger.query(claim_type=ClaimType.METRIC)
                  if e.method.startswith("goal_claim")]
        assert len(scored) == sum(sim.score.values())

    def test_shot_claims_match_detected_shots(self, match):
        _m, sim, r = match
        shots = [e for e in r.ledger if e.method.startswith(("shot_claim",
                                                             "goal_claim"))]
        assert len(shots) == sim.stats["shots"]

    def test_control_claims_form_a_supersession_chain(self, match):
        _m, _sim, r = match
        control = [e for e in r.ledger
                   if e.method.startswith("control_state")]
        assert len(control) > 5
        # All but the first supersede their predecessor.
        assert sum(1 for e in control if e.supersedes) == len(control) - 1

    def test_only_a_handful_of_patterns_survive_to_full_time(self, match):
        """
        Supersession is what stops a recap assembling a story from stale
        facts. Dozens asserted, a few still standing.
        """
        _m, _sim, r = match
        asserted = r.ledger.query(claim_type=ClaimType.PATTERN)
        end = max(e.t_ms for e in r.ledger)
        standing = [e for e in r.ledger.active_at(end, period=2)
                    if e.claim_type is ClaimType.PATTERN]
        assert len(asserted) > 20
        assert len(standing) < 10

    def test_claims_are_time_ordered(self, match):
        _m, _sim, r = match
        for period in (1, 2):
            times = [e.t_ms for e in r.ledger.query(period=period)]
            assert times == sorted(times)

    def test_subjects_resolve_to_real_entities(self, match):
        meta, _sim, r = match
        known = ({p.player_id for t in meta.teams for p in t.players}
                 | {t.team_id for t in meta.teams})
        for e in r.ledger:
            for sid in e.subject_ids:
                assert sid in known, sid

    def test_values_carry_units(self, match):
        _m, _sim, r = match
        for e in r.ledger:
            if e.value is not None:
                assert e.unit, f"{e.ledger_id} has a value with no unit"

    def test_deterministic(self):
        """Ten minutes is enough to prove it; a full match twice is not."""
        def run():
            meta = build_match(SEED)
            frames = itertools.islice(MatchSimulator(meta).run(),
                                      meta.tracking_hz * 60 * 10)
            r = build(meta, frames, keep=False)
            return [(e.ledger_id, e.claim) for e in r.ledger]
        first = run()
        assert len(first) > 10
        assert first == run()

