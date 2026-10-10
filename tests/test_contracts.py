"""The four contracts validate, round-trip through JSON, and reject typos."""

import pytest
from pydantic import ValidationError

from chalkboard import contracts as c


@pytest.fixture
def frame() -> c.TrackingFrame:
    return c.TrackingFrame(
        match_id="m_0007", seq=1, period=1, t_ms=0,
        ball=c.BallState(pos=c.Point(x=0, y=0), vx=0, vy=0, speed=0),
        players=[c.PlayerState(player_id="p_1", pos=c.Point(x=-40, y=0),
                               vx=0, vy=0, speed=0)],
    )


@pytest.fixture
def event() -> c.MatchEvent:
    return c.MatchEvent(
        event_id="ev_1", match_id="m_0007", seq=2, period=1, t_ms=1200,
        type=c.EventType.PASS, team_id="t_home", player_id="p_1",
        start=c.Point(x=-40, y=0), frame_seq_range=(1, 30),
        detail=c.PassDetail(end=c.Point(x=-10, y=12), distance_m=32.3,
                            angle_deg=21.8, release_speed=18.4, completed=True,
                            receiver_id="p_7", opponents_bypassed=4,
                            progressive=True, difficulty=0.62),
    )


@pytest.fixture
def entry() -> c.LedgerEntry:
    return c.LedgerEntry(
        ledger_id="lg_1", match_id="m_0007", period=1, t_ms=1200,
        claim="Vance played a 32m pass that bypassed four opponents.",
        claim_type=c.ClaimType.METRIC, subject_ids=["p_1"],
        value=32.3, unit="m", window_ms=(0, 1200),
        evidence=[c.EvidenceRef(kind=c.EvidenceKind.EVENT, ids=["ev_1"])],
        method="pass_metrics@0.1", confidence=0.97,
        status=c.VerificationStatus.SUPPORTED,
    )


@pytest.fixture
def packet() -> c.OverlayPacket:
    return c.OverlayPacket(
        packet_id="ov_1", match_id="m_0007", valid_from_ms=1200,
        duration_ms=5000, priority=4,
        overlay_type=c.OverlayType.PLAYER_CARD,
        lens=c.Lens(type=c.LensType.PLAYER, target_id="p_1", depth="analyst"),
        headline="Line-breaking pass",
        data={"distance_m": 32.3, "bypassed": 4},
        render_hints=c.RenderHints(safe_area="lower_third", animation_in="wipe"),
        evidence=["lg_1"],
    )


def test_round_trip(frame, event, entry, packet):
    for obj in (frame, event, entry, packet):
        assert type(obj).model_validate_json(obj.model_dump_json()) == obj


def test_discriminated_detail(event):
    assert event.detail.type == "pass"
    assert event.detail.difficulty == pytest.approx(0.62)


def test_extra_field_rejected():
    with pytest.raises(ValidationError):
        c.Point(x=0, y=0, z=0)


def test_off_pitch_rejected():
    with pytest.raises(ValidationError):
        c.Point(x=99.0, y=0)


def test_evidence_is_mandatory():
    """A packet with no ledger backing is the exact thing the design forbids."""
    with pytest.raises(ValidationError):
        c.OverlayPacket(
            packet_id="ov_2", match_id="m_0007", valid_from_ms=0,
            duration_ms=1000, priority=1,
            overlay_type=c.OverlayType.STAT_BUG,
            headline="unsourced", evidence=[],
        )


def test_contracts_are_frozen(frame):
    with pytest.raises(ValidationError):
        frame.seq = 2
