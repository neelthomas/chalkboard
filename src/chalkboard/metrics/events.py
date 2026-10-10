"""
events.py - TrackingFrame -> MatchEvent.

Stage (b) of the brief: interpret raw tracking into meaningful football
events.

It works from frames alone. It never imports the simulator and never looks
at how the frames were produced, which is the point - the same detector
would run unchanged over a real tracking feed. If this module ever needs
something only the simulator knows, the contract is wrong.

Detection
    A flight begins when the ball leaves a player's feet (owner -> None)
    and ends one of two ways:

        a new owner appears at the ball   -> pass (or interception)
        the ball jumps discontinuously    -> shot

    The second rule is the interesting one. A shot is not identified by
    aiming at the goal - it is identified by the ball going dead and play
    restarting elsewhere. Where it restarts then says what happened: from
    the centre spot means a goal; from the edge of the goal area means
    saved, blocked or missed. That is the inference a human analyst makes
    from a tracking feed, and it needs no privileged knowledge.

Interface
    feed(frame) -> list[MatchEvent] is the primitive, so this can run live
    against a stream. run(frames) is the batch convenience wrapper.

Everything emitted carries frame_seq_range, so any claim built on an event
traces back to the exact tracking that produced it.
"""

from __future__ import annotations

import math
from typing import Iterable, Iterator, Optional

from chalkboard import football as fb
from chalkboard.contracts import (
    EventType,
    MatchEvent,
    MatchMeta,
    PassDetail,
    Point,
    PressureDetail,
    ShotDetail,
    TrackingFrame,
)
from chalkboard.fixtures import attack_direction

VERSION = "0.1"

# A ball discontinuity marks a dead ball. The threshold has to sit above
# the furthest the ball can legitimately move in one tick - 32 m/s at 25 Hz
# is 1.28 m - and below the smallest real restart displacement, which is a
# shot ending on the goal line at 52.5 restarting from the goal area at
# 47.5. At 15 m this missed every saved and off-target shot, which then got
# emitted as a pass to the opposition keeper: shot recall was 23%.
BALL_JUMP_M = 2.5
BALL_LIVE_SPEED = 1.0       # m/s below which the ball is not in flight
GOAL_LINE_X = 51.0          # ball this deep counts as reaching the line
RESTART_CENTRE_M = 6.0      # restart this close to the centre spot = goal
PRESSURE_RADIUS_M = 5.0
PRESSURE_MIN_MS = 600
CARRY_MIN_M = 5.0


def _dist(ax: float, ay: float, bx: float, by: float) -> float:
    return math.hypot(ax - bx, ay - by)


class EventDetector:
    """
        det = EventDetector(meta)
        for frame in frames:
            for event in det.feed(frame):
                ...
    """

    def __init__(self, meta: MatchMeta):
        self.meta = meta
        self.team_of: dict[str, str] = {
            p.player_id: t.team_id for t in meta.teams for p in t.players
        }
        self._n = 0
        self._prev: Optional[TrackingFrame] = None
        self._period: Optional[int] = None
        self._adir: dict[str, float] = {}
        self._reset_possession()

    def _reset_possession(self) -> None:
        self._releaser: Optional[str] = None
        self._release_pt: Optional[tuple[float, float]] = None
        self._release_seq = 0
        self._release_ms = 0
        self._peak_x = 0.0
        self._y_at_peak = 0.0
        self._opp_xs: list[float] = []
        self._pressure_at_release = 99.0
        self._carry_from: Optional[tuple[float, float]] = None
        self._carry_seq = 0
        self._press_since: Optional[int] = None
        self._press_seq = 0
        self._press_min = 99.0
        self._press_ids: list[str] = []
        self._last_team: Optional[str] = None

    # -- helpers --------------------------------------------------------

    def _event(self, kind: str, type_: EventType, frame: TrackingFrame,
               team_id: Optional[str], player_id: Optional[str],
               start: Optional[Point], first_seq: int, detail=None) -> MatchEvent:
        self._n += 1
        kwargs = dict(
            event_id=f"ev_{kind}_{self._n:05d}",
            match_id=frame.match_id,
            seq=frame.seq,
            period=frame.period,
            t_ms=frame.t_ms,
            type=type_,
            team_id=team_id,
            player_id=player_id,
            start=start,
            frame_seq_range=(first_seq, frame.seq),
        )
        if detail is not None:
            kwargs["detail"] = detail
        return MatchEvent(**kwargs)

    # -- main -----------------------------------------------------------

    def feed(self, frame: TrackingFrame) -> list[MatchEvent]:
        out: list[MatchEvent] = []
        prev = self._prev

        if frame.period != self._period:
            if prev is not None:
                out.append(self._event("pend", EventType.PERIOD_END, prev,
                                       None, None, None, prev.seq))
            self._period = frame.period
            self._adir = {t.team_id: attack_direction(self.meta, t.team_id,
                                                      frame.period)
                          for t in self.meta.teams}
            self._reset_possession()
            prev = None
            out.append(self._event("pstart", EventType.PERIOD_START, frame,
                                   None, None, None, frame.seq))

        owner = frame.ball.owner
        bx, by = frame.ball.pos.x, frame.ball.pos.y

        # ---- possession change ----------------------------------------
        if owner is not None:
            team = self.team_of[owner]
            if self._last_team is not None and team != self._last_team:
                out.append(self._event("poss", EventType.POSSESSION_CHANGE,
                                       frame, team, owner,
                                       Point(x=bx, y=by), frame.seq))
            self._last_team = team

        # ---- pressure on the carrier ----------------------------------
        if owner is not None:
            ot = self.team_of[owner]
            near = sorted(
                (_dist(bx, by, p.pos.x, p.pos.y), p.player_id)
                for p in frame.players if self.team_of[p.player_id] != ot
            )
            closest = near[0][0] if near else 99.0
            pressing = [pid for d, pid in near if d <= PRESSURE_RADIUS_M]
            if pressing:
                if self._press_since is None:
                    self._press_since = frame.t_ms
                    self._press_seq = frame.seq
                    self._press_min = closest
                    self._press_ids = pressing
                else:
                    self._press_min = min(self._press_min, closest)
                    self._press_ids = sorted(set(self._press_ids) | set(pressing))
            elif self._press_since is not None:
                held = frame.t_ms - self._press_since
                if held >= PRESSURE_MIN_MS:
                    out.append(self._event(
                        "press", EventType.PRESSURE, frame, ot, owner,
                        Point(x=bx, y=by), self._press_seq,
                        PressureDetail(
                            pressing_player_ids=self._press_ids,
                            min_distance_m=round(self._press_min, 2),
                            duration_ms=held,
                            forced_turnover=False,
                        ),
                    ))
                self._press_since = None
        else:
            self._press_since = None

        # ---- carries ---------------------------------------------------
        if owner is not None:
            if self._carry_from is None:
                self._carry_from = (bx, by)
                self._carry_seq = frame.seq
        elif self._carry_from is not None and prev is not None:
            travelled = _dist(*self._carry_from,
                              prev.ball.pos.x, prev.ball.pos.y)
            if travelled >= CARRY_MIN_M and prev.ball.owner is not None:
                out.append(self._event(
                    "carry", EventType.CARRY, prev,
                    self.team_of[prev.ball.owner], prev.ball.owner,
                    Point(x=self._carry_from[0], y=self._carry_from[1]),
                    self._carry_seq,
                ))
            self._carry_from = None

        # ---- flight begins ---------------------------------------------
        # The speed gate matters. A dead ball also has no owner, so without
        # it every restart reads as a second release: the ball sits still
        # for twelve seconds, the keeper picks it up, and that gets emitted
        # as a phantom shot or a pass to the opposition. A real flight is
        # moving far faster than this on the tick after release.
        if (prev is not None and prev.ball.owner is not None and owner is None
                and frame.ball.speed > BALL_LIVE_SPEED):
            self._releaser = prev.ball.owner
            self._release_pt = (prev.ball.pos.x, prev.ball.pos.y)
            self._release_seq = prev.seq
            self._release_ms = prev.t_ms
            self._peak_x, self._y_at_peak = abs(bx), by
            rteam = self.team_of[self._releaser]
            self._opp_xs = [p.pos.x for p in prev.players
                            if self.team_of[p.player_id] != rteam]
            self._pressure_at_release = min(
                (_dist(*self._release_pt, p.pos.x, p.pos.y)
                 for p in prev.players if self.team_of[p.player_id] != rteam),
                default=99.0,
            )

        # ---- flight continues / ends ------------------------------------
        if self._releaser is not None and self._release_pt is not None:
            if abs(bx) > self._peak_x:
                self._peak_x, self._y_at_peak = abs(bx), by

            jumped = prev is not None and _dist(
                bx, by, prev.ball.pos.x, prev.ball.pos.y) > BALL_JUMP_M

            if jumped:
                out.append(self._shot(frame, bx, by))
                self._releaser = self._release_pt = None
                self._last_team = None
                self._carry_from = None
            elif owner is not None:
                out.extend(self._pass(frame, owner))
                self._releaser = self._release_pt = None

        self._prev = frame
        return out

    def run(self, frames: Iterable[TrackingFrame]) -> Iterator[MatchEvent]:
        for frame in frames:
            yield from self.feed(frame)
        if self._prev is not None:
            yield self._event("pend", EventType.PERIOD_END, self._prev,
                              None, None, None, self._prev.seq)

    # -- emitters -------------------------------------------------------

    def _pass(self, frame: TrackingFrame, receiver: str) -> list[MatchEvent]:
        sx, sy = self._release_pt
        ex, ey = frame.ball.pos.x, frame.ball.pos.y
        shooter_team = self.team_of[self._releaser]
        direction = self._adir[shooter_team]
        dist = _dist(sx, sy, ex, ey)
        flight_ms = max(frame.t_ms - self._release_ms, 1)
        completed = self.team_of[receiver] == shooter_team
        bypassed = fb.opponents_bypassed(sx, ex, direction, self._opp_xs)

        events = [self._event(
            "pass", EventType.PASS, frame, shooter_team, self._releaser,
            Point(x=sx, y=sy), self._release_seq,
            PassDetail(
                end=Point(x=ex, y=ey),
                distance_m=round(dist, 2),
                angle_deg=round(math.degrees(math.atan2(ey - sy, ex - sx)), 1),
                release_speed=round(dist / (flight_ms / 1000), 2),
                completed=completed,
                receiver_id=receiver if completed else None,
                progressive=fb.is_progressive(sx, sy, ex, ey, direction),
                into_final_third=(not fb.in_final_third(sx, direction)
                                  and fb.in_final_third(ex, direction)),
                opponents_bypassed=bypassed,
                difficulty=fb.pass_difficulty(dist, bypassed,
                                              self._pressure_at_release,
                                              abs(ey - sy)),
            ),
        )]
        if not completed:
            events.append(self._event(
                "int", EventType.INTERCEPTION, frame,
                self.team_of[receiver], receiver, Point(x=ex, y=ey),
                self._release_seq,
            ))
        return events

    def _shot(self, frame: TrackingFrame,
              restart_x: float, restart_y: float) -> MatchEvent:
        sx, sy = self._release_pt
        team = self.team_of[self._releaser]
        direction = self._adir[team]
        d, _angle, xg = fb.shot_quality(sx, sy, direction)

        reached_line = self._peak_x >= GOAL_LINE_X
        within_posts = abs(self._y_at_peak) <= fb.GOAL_HALF
        scored = _dist(restart_x, restart_y, 0.0, 0.0) <= RESTART_CENTRE_M

        if scored or (reached_line and within_posts):
            on_target, blocked = True, False
        elif reached_line:
            on_target, blocked = False, False
        else:
            on_target, blocked = False, True

        flight_ms = max(frame.t_ms - self._release_ms, 1)
        end_x = math.copysign(min(self._peak_x, fb.PITCH_X), direction)
        end_y = max(-fb.PITCH_Y, min(fb.PITCH_Y, self._y_at_peak))

        return self._event(
            "shot", EventType.SHOT, frame, team, self._releaser,
            Point(x=sx, y=sy), self._release_seq,
            ShotDetail(
                end=Point(x=end_x, y=end_y),
                xg=round(xg, 4),
                shot_speed=round(_dist(sx, sy, end_x, end_y)
                                 / (flight_ms / 1000), 2),
                distance_m=round(d, 2),
                body_part="head" if d <= 8.0 else "right_foot",
                on_target=on_target,
                goal=scored,
                blocked=blocked,
            ),
        )


def derive(meta: MatchMeta, frames: Iterable[TrackingFrame]) -> Iterator[MatchEvent]:
    """Batch convenience wrapper."""
    return EventDetector(meta).run(frames)
