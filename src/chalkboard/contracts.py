"""
contracts.py - the four data contracts.

    TrackingFrame   simulator        -> metrics engine
    MatchEvent      metrics engine   -> Scout, Analyst
    LedgerEntry     Analyst          -> Verifier, Storyteller
    OverlayPacket   Director         -> frontend / rendering partner

Conventions, fixed once here so nothing downstream has to guess:

    space     metres. Origin at the centre spot. x in [-52.5, 52.5],
              y in [-34.0, 34.0]. Absolute pitch coordinates - teams swap
              ends at half time, so direction of attack lives in MatchMeta
              per period, NOT in the frames. Frames are pure observation.
    time      `period` + `t_ms` (milliseconds since the start of that period).
              `seq` is monotonic across the whole match and is the only
              thing you should sort on.
    speed     metres per second.
    ids       opaque strings. p_* players, t_* teams, m_* matches,
              ev_* events, lg_* ledger entries, ov_* overlay packets.

All club and player names MUST be fictional. Hackathon rules 4.4 prohibit
third-party trademarks in the submission video, which rules out real
Premier League clubs, badges and player names.

Pydantic v2.  `extra="forbid"` everywhere on purpose: a typo'd field name
should fail loudly at the boundary, which is the entire point of having
contracts in the first place.
"""

from __future__ import annotations

from enum import Enum
from typing import Annotated, Literal, Optional, Union

from pydantic import BaseModel, ConfigDict, Field

PITCH_LENGTH_M = 105.0
PITCH_WIDTH_M = 68.0
SCHEMA_VERSION = "0.1.0"


class Contract(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


# ----------------------------------------------------------------------
# supporting types
# ----------------------------------------------------------------------

class Side(str, Enum):
    HOME = "home"
    AWAY = "away"


class AttackDirection(str, Enum):
    """Which way a team is shooting during a given period."""
    POS_X = "pos_x"
    NEG_X = "neg_x"


class Point(Contract):
    x: float = Field(ge=-PITCH_LENGTH_M / 2, le=PITCH_LENGTH_M / 2)
    y: float = Field(ge=-PITCH_WIDTH_M / 2, le=PITCH_WIDTH_M / 2)


class PeriodInfo(Contract):
    period: int = Field(ge=1, le=4)
    home_attacks: AttackDirection
    duration_ms: int


class PlayerMeta(Contract):
    player_id: str
    name: str                      # fictional
    shirt: int = Field(ge=1, le=99)
    position: str                  # "GK", "CB", "DM", "RW", ...
    team_id: str


class TeamMeta(Contract):
    team_id: str
    name: str                      # fictional
    short_name: str
    side: Side
    formation: str                 # "4-3-3"
    players: list[PlayerMeta]


class MatchMeta(Contract):
    """Emitted once at kickoff. Everything downstream resolves ids against this."""
    schema_version: str = SCHEMA_VERSION
    match_id: str
    seed: int                      # replay the exact same match from this
    competition: str               # fictional
    kickoff_utc: str
    venue: str
    teams: list[TeamMeta] = Field(min_length=2, max_length=2)
    periods: list[PeriodInfo]
    tracking_hz: int = 25


# ----------------------------------------------------------------------
# 1. TrackingFrame
# ----------------------------------------------------------------------

class BallState(Contract):
    pos: Point
    z: float = Field(default=0.0, ge=0.0)      # height, metres
    vx: float
    vy: float
    vz: float = 0.0
    speed: float = Field(ge=0.0)               # magnitude, m/s
    in_play: bool = True
    owner: Optional[str] = None                # player_id in control, if any


class PlayerState(Contract):
    player_id: str
    pos: Point
    vx: float
    vy: float
    speed: float = Field(ge=0.0)
    on_pitch: bool = True


class TrackingFrame(Contract):
    """
    One per tick, carrying every actor. Wide, not tall: at 25 Hz that is
    25 messages/sec instead of 575, and every spatial metric you care about
    (pressure, control, nearest opponent, line height) needs all positions
    at the same instant anyway.
    """
    schema_version: str = SCHEMA_VERSION
    match_id: str
    seq: int                       # monotonic across the match
    period: int = Field(ge=1, le=4)
    t_ms: int = Field(ge=0)        # since start of this period
    ball: BallState
    players: list[PlayerState]


# ----------------------------------------------------------------------
# 2. MatchEvent
# ----------------------------------------------------------------------

class EventType(str, Enum):
    PERIOD_START = "period_start"
    PERIOD_END = "period_end"
    PASS = "pass"
    CARRY = "carry"
    SHOT = "shot"
    TACKLE = "tackle"
    INTERCEPTION = "interception"
    CLEARANCE = "clearance"
    PRESSURE = "pressure"
    DUEL = "duel"
    SAVE = "save"
    FOUL = "foul"
    CARD = "card"
    SUBSTITUTION = "substitution"
    POSSESSION_CHANGE = "possession_change"
    GOAL = "goal"


class PassDetail(Contract):
    type: Literal["pass"] = "pass"
    end: Point
    distance_m: float = Field(ge=0.0)
    angle_deg: float
    release_speed: float = Field(ge=0.0)
    completed: bool
    receiver_id: Optional[str] = None
    progressive: bool = False
    into_final_third: bool = False
    opponents_bypassed: int = Field(default=0, ge=0)
    difficulty: float = Field(ge=0.0, le=1.0)   # brief (ii): pass difficulty rating


class ShotDetail(Contract):
    type: Literal["shot"] = "shot"
    end: Point
    xg: float = Field(ge=0.0, le=1.0)
    shot_speed: float = Field(ge=0.0)           # brief (ii): shot speed
    distance_m: float = Field(ge=0.0)
    body_part: Literal["left_foot", "right_foot", "head", "other"]
    on_target: bool
    goal: bool
    blocked: bool = False


class PressureDetail(Contract):
    type: Literal["pressure"] = "pressure"
    pressing_player_ids: list[str]
    min_distance_m: float = Field(ge=0.0)
    duration_ms: int = Field(ge=0)
    forced_turnover: bool = False


class GenericDetail(Contract):
    """Fallback for event types that need no structured payload yet."""
    type: Literal["generic"] = "generic"
    note: Optional[str] = None


EventDetail = Annotated[
    Union[PassDetail, ShotDetail, PressureDetail, GenericDetail],
    Field(discriminator="type"),
]


class MatchEvent(Contract):
    """
    Derived from frames, never authored by hand. `frame_seq_range` is the
    provenance link back to the tracking that produced it - this is what
    makes a ledger claim clickable all the way down to raw positions.
    """
    schema_version: str = SCHEMA_VERSION
    event_id: str
    match_id: str
    seq: int
    period: int = Field(ge=1, le=4)
    t_ms: int = Field(ge=0)
    type: EventType
    team_id: Optional[str] = None
    player_id: Optional[str] = None
    start: Optional[Point] = None
    frame_seq_range: tuple[int, int]
    detail: EventDetail = GenericDetail()


# ----------------------------------------------------------------------
# 3. LedgerEntry
# ----------------------------------------------------------------------

class ClaimType(str, Enum):
    METRIC = "metric"            # "City's pressure index is 0.71"
    COMPARISON = "comparison"    # "double their first-half figure"
    CAUSAL = "causal"            # "because the press moved 8m higher"
    MILESTONE = "milestone"      # brief (iii): notable milestones
    PATTERN = "pattern"          # brief (iv): rhythm, control vs chaos


class EvidenceKind(str, Enum):
    FRAME = "frame"
    EVENT = "event"
    METRIC = "metric"
    LEDGER = "ledger"            # a claim built on an earlier claim


class EvidenceRef(Contract):
    kind: EvidenceKind
    ids: list[str]
    note: Optional[str] = None


class VerificationStatus(str, Enum):
    UNVERIFIED = "unverified"
    SUPPORTED = "supported"
    OVERSTATED = "overstated"    # true but stronger than evidence allows
    UNSUPPORTED = "unsupported"  # rejected - Storyteller may not use it


class LedgerEntry(Contract):
    """
    One atomic, checkable assertion. The Storyteller may not write a sentence
    that is not backed by one of these, and the Verifier is the gate.

    `method` is what makes this auditable rather than merely plausible: it
    names the exact function and version that produced the number, so any
    claim can be recomputed from the frames years later.

    `supersedes` matters more than it looks. "City are dominant" is true at
    55' and false at 75'. Claims expire; the ledger has to model that or the
    recap will contradict itself.
    """
    schema_version: str = SCHEMA_VERSION
    ledger_id: str
    match_id: str
    period: int = Field(ge=1, le=4)
    t_ms: int = Field(ge=0)

    claim: str                                  # one sentence, atomic, neutral
    claim_type: ClaimType
    subject_ids: list[str]                      # players / teams this is about

    value: Optional[float] = None
    unit: Optional[str] = None                  # "m/s", "%", "xG", "index"
    window_ms: Optional[tuple[int, int]] = None # what span it describes

    evidence: list[EvidenceRef] = Field(min_length=1)
    method: str                                 # "pressure_index@1.2"
    confidence: float = Field(ge=0.0, le=1.0)

    status: VerificationStatus = VerificationStatus.UNVERIFIED
    verifier_note: Optional[str] = None
    supersedes: Optional[str] = None


# ----------------------------------------------------------------------
# 4. OverlayPacket
# ----------------------------------------------------------------------

class OverlayType(str, Enum):
    LOWER_THIRD = "lower_third"
    PLAYER_CARD = "player_card"
    STAT_BUG = "stat_bug"
    PRESSURE_METER = "pressure_meter"
    SHOT_MAP = "shot_map"
    MOMENTUM_STRIP = "momentum_strip"
    RECAP_SEGMENT = "recap_segment"


class LensType(str, Enum):
    NONE = "none"
    PLAYER = "player"            # brief (e): player-focused mode
    CLUB = "club"
    METRIC = "metric"


class Lens(Contract):
    type: LensType = LensType.NONE
    target_id: Optional[str] = None
    depth: Literal["casual", "standard", "analyst"] = "standard"


class RenderHints(Contract):
    safe_area: Literal["lower_third", "upper_right", "full", "sidebar"]
    animation_in: Literal["cut", "wipe", "fade", "slide"] = "fade"
    theme: Literal["light", "dark", "auto"] = "auto"


class OverlayPacket(Contract):
    """
    What a rendering partner consumes. Timed, machine-readable, bindable.

    `text` and `data` are deliberately separate: the renderer binds `data`
    to graphics and the strings to type. Shipping a pre-formatted sentence
    would make the packet unrenderable as anything but a caption.

    `speech_text` carries the audio-description / TTS variant, which is not
    the same as the on-screen copy - screen copy can lean on the graphic,
    spoken copy cannot.
    """
    schema_version: str = SCHEMA_VERSION
    packet_id: str
    match_id: str

    valid_from_ms: int = Field(ge=0)            # match clock, not wall clock
    duration_ms: int = Field(gt=0)
    priority: int = Field(ge=0, le=9)           # 9 preempts everything

    overlay_type: OverlayType
    lens: Lens = Lens()
    locale: str = "en-GB"                       # brief (vi): multi-language

    headline: str
    body: Optional[str] = None
    speech_text: Optional[str] = None

    data: dict = Field(default_factory=dict)    # typed per overlay_type
    render_hints: Optional[RenderHints] = None
    evidence: list[str] = Field(min_length=1)   # ledger_ids - never empty


# ----------------------------------------------------------------------

__all__ = [
    "MatchMeta", "TeamMeta", "PlayerMeta", "PeriodInfo", "Point", "Side",
    "AttackDirection",
    "TrackingFrame", "BallState", "PlayerState",
    "MatchEvent", "EventType", "PassDetail", "ShotDetail", "PressureDetail",
    "GenericDetail",
    "LedgerEntry", "ClaimType", "EvidenceRef", "EvidenceKind",
    "VerificationStatus",
    "OverlayPacket", "OverlayType", "Lens", "LensType", "RenderHints",
    "PITCH_LENGTH_M", "PITCH_WIDTH_M", "SCHEMA_VERSION",
]
