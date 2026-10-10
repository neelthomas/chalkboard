"""
Director: LedgerEntry -> OverlayPacket.

Stage (d). The packets are render instructions, not pictures: what graphic,
carrying which numbers, on screen from when until when, at what priority.
"""

import itertools

import pytest

from chalkboard.contracts import LensType, OverlayPacket, VerificationStatus
from chalkboard.director import Director
from chalkboard.fixtures import build_match
from chalkboard.ledger import build
from chalkboard.sim import MatchSimulator

SEED = 7
MINUTES = 25


@pytest.fixture(scope="module")
def directed():
    meta = build_match(SEED)
    frames = itertools.islice(MatchSimulator(meta).run(),
                              meta.tracking_hz * 60 * MINUTES)
    result = build(meta, frames, keep=False)
    director = Director(meta)
    return meta, result.ledger, director, director.direct(result.ledger)


class TestPackets:
    def test_packets_are_produced(self, directed):
        _m, ledger, _d, packets = directed
        assert 0 < len(packets) <= len(ledger)

    def test_every_packet_cites_a_real_ledger_entry(self, directed):
        """Nothing reaches the screen without provenance."""
        _m, ledger, _d, packets = directed
        for p in packets:
            assert p.evidence
            for lid in p.evidence:
                assert ledger.get(lid) is not None

    def test_packets_are_contract_instances(self, directed):
        _m, _l, _d, packets = directed
        assert all(isinstance(p, OverlayPacket) for p in packets)

    def test_data_is_separate_from_text(self, directed):
        """
        A renderer binds `data` to graphics. Shipping only a formatted
        sentence would make the packet renderable as a caption and nothing
        else, which fails the brief's "machine-readable" requirement.
        """
        _m, _l, _d, packets = directed
        with_values = [p for p in packets if "value" in p.data]
        assert len(with_values) > 5
        for p in with_values:
            assert p.data["unit"]
            assert p.data["method"]

    def test_speech_text_is_present(self, directed):
        _m, _l, _d, packets = directed
        assert all(p.speech_text for p in packets)

    def test_goals_outrank_everything(self, directed):
        _m, ledger, _d, packets = directed
        goals = [p for p in packets if p.headline == "GOAL"]
        if goals:
            assert all(p.priority == 9 for p in goals)
            assert max(p.priority for p in packets) == 9

    def test_player_claims_get_a_player_lens(self, directed):
        """Brief (e): a player-focused mode needs packets that know their subject."""
        _m, _l, _d, packets = directed
        lensed = [p for p in packets if p.lens.type is LensType.PLAYER]
        assert len(lensed) > len(packets) * 0.2
        assert all(p.lens.target_id for p in lensed)


class TestTiming:
    def test_clock_is_continuous_across_periods(self, directed):
        meta, _l, _d, packets = directed
        times = [p.valid_from_ms for p in packets]
        assert times == sorted(times)
        first_half = meta.periods[0].duration_ms
        second = [p for p in packets if p.valid_from_ms > first_half]
        # A 25-minute clip should not reach the second half at all.
        assert not second

    def test_durations_are_positive_and_sane(self, directed):
        _m, _l, _d, packets = directed
        for p in packets:
            assert 1000 <= p.duration_ms <= 15000


class TestContention:
    def test_no_two_packets_share_a_safe_area_at_once(self, directed):
        """A real feed cannot have two lower-thirds fighting for the strip."""
        _m, _l, _d, packets = directed
        spans: dict[str, list[tuple[int, int]]] = {}
        for p in packets:
            area = p.render_hints.safe_area
            start, end = p.valid_from_ms, p.valid_from_ms + p.duration_ms
            for a, b in spans.setdefault(area, []):
                assert not (start < b and a < end), (
                    f"{area}: {start}-{end} overlaps {a}-{b}")
            spans[area].append((start, end))

    def test_dropping_is_counted_not_silent(self, directed):
        """
        Dropping an overlay is a decision, not a failure, so it is reported.
        Over 25 minutes there is enough traffic that some must be dropped -
        if nothing ever contends, the scheduler is not being exercised.
        """
        _m, ledger, director, packets = directed
        assert director.dropped > 0
        assert len(packets) + director.dropped == len(ledger)


class TestVerificationGate:
    def test_require_verified_blocks_unchecked_claims(self, directed):
        """
        With the gate on, nothing reaches the screen until the Verifier has
        passed it. Nothing is verified yet, so nothing should render.
        """
        meta, ledger, _d, _p = directed
        strict = Director(meta, require_verified=True)
        assert strict.direct(ledger) == []

    def test_verified_claims_pass_the_gate(self, directed):
        meta, ledger, _d, _p = directed
        entry = next(iter(ledger))
        ledger.mark(entry.ledger_id, VerificationStatus.SUPPORTED)
        strict = Director(meta, require_verified=True)
        out = strict.direct(ledger)
        assert [p.evidence[0] for p in out] == [entry.ledger_id]


def test_locale_is_carried(directed):
    """Brief (vi): the packet, not the renderer, says which language it is."""
    meta, ledger, _d, _p = directed
    fr = Director(meta, locale="fr-FR").direct(ledger)
    assert fr and all(p.locale == "fr-FR" for p in fr)
