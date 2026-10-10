"""
engine.py - synthetic match simulator.

Produces TrackingFrames at MatchMeta.tracking_hz. Seeded: same seed, same
match, every time.

Motion model
    Each player steers toward a desired position made of three parts - their
    formation anchor, a team block shift toward the ball, and a role-weighted
    pull toward the ball. Speed is proportional to remaining distance and
    capped by role, so players decelerate as they arrive and stop inside a
    deadzone. Acceleration is limited.

    Positional noise is resampled roughly once a second, not once a tick.
    Per-tick noise at 25 Hz makes every player chase a target that teleports
    25 times a second, pinning them at sprint speed for the whole match.
    That bug produced 28 km per player per 90 and a mean speed of 5.1 m/s.

    The block shift is asymmetric: the team in possession pushes up, the
    team out of possession drops off. A symmetric shift leaves both teams
    compressed on the ball and the match never changes territory.

Possession model
    The carrier holds for a sampled dwell, then either shoots - if in range
    and the chance is worth taking - or passes to the best of a few
    candidates, scored on forward progress against distance. Passes may be
    intercepted by a tight opponent or lost to a bad touch.

Shooting
    Shot quality comes from chalkboard.football, shared with the metrics
    engine so xG is computed in exactly one place. The outcome is drawn
    against xG, the ball flies to a target consistent with that outcome,
    and play restarts from a kickoff or goal kick after a dead-ball pause.
"""

from __future__ import annotations

import math
import random
from typing import Iterator

from chalkboard import football as fb
from chalkboard.contracts import (
    BallState,
    MatchMeta,
    PlayerState,
    Point,
    TrackingFrame,
)
from chalkboard.fixtures import anchors

PITCH_X = 52.5
PITCH_Y = 34.0

# Per-role behaviour. `pull` is the draw toward the ball on top of the block
# shift; `vmax` is the speed ceiling in m/s.
ROLE_PARAMS: dict[str, dict[str, float]] = {
    "GK":  {"pull": 0.03, "vmax": 5.5, "noise": 0.25},
    "DEF": {"pull": 0.16, "vmax": 7.6, "noise": 0.55},
    "MID": {"pull": 0.26, "vmax": 7.8, "noise": 0.75},
    "FWD": {"pull": 0.22, "vmax": 8.2, "noise": 0.80},
}

BLOCK_SHIFT = 0.42
ATTACK_PUSH = 11.5
DEFEND_DROP = 4.0
BLOCK_LIMIT = 30.0
SHIFT_LERP = 0.055          # per tick; ~0.7 s; smooths the snap without averaging the block away
MAX_ACCEL = 5.0
ARRIVE_RADIUS = 2.0
APPROACH_GAIN = 1.1
NOISE_PERIOD_MS = 1000

DWELL_MIN_MS, DWELL_MAX_MS = 1200, 6000
PASS_SPEED_MIN, PASS_SPEED_MAX = 9.0, 26.0
IDEAL_PASS_M = 13.0
INTERCEPT_RADIUS = 3.3
INTERCEPT_P = 0.62
MISCONTROL_P = 0.03

SHOOT_RANGE_M = 26.0
SHOOT_EAGERNESS = 1.45       # scales xG into a shoot-or-pass probability
MIN_SHOT_XG = 0.050        # do not shoot from hopeless positions
SHOT_SPEED_MIN, SHOT_SPEED_MAX = 18.0, 32.0
KICKOFF_DEAD_MS = 18_000
RESTART_DEAD_MS = 12_000


def _clamp(v: float, lo: float, hi: float) -> float:
    return lo if v < lo else hi if v > hi else v


def _role_of(position: str) -> str:
    if position == "GK":
        return "GK"
    if position in ("RB", "LB", "RCB", "LCB"):
        return "DEF"
    if position in ("DM", "RCM", "LCM", "RM", "LM"):
        return "MID"
    return "FWD"


class _Agent:
    """Mutable per-player state. Internal to the sim - not a contract."""

    __slots__ = ("pid", "team_id", "role", "pull", "vmax", "noise_amp",
                 "ax", "ay", "x", "y", "vx", "vy", "nx", "ny", "next_noise_ms")

    def __init__(self, pid: str, team_id: str, position: str,
                 ax: float, ay: float):
        self.pid = pid
        self.team_id = team_id
        self.role = _role_of(position)
        params = ROLE_PARAMS[self.role]
        self.pull = params["pull"]
        self.vmax = params["vmax"]
        self.noise_amp = params["noise"]

        self.ax, self.ay = ax, ay
        self.x, self.y = ax, ay
        self.vx = self.vy = 0.0
        self.nx = self.ny = 0.0
        self.next_noise_ms = 0

    def reset_to_anchor(self) -> None:
        self.x, self.y = self.ax, self.ay
        self.vx = self.vy = 0.0
        self.nx = self.ny = 0.0

    def step(self, dt: float, now_ms: int, ball_x: float, ball_y: float,
             shift_x: float, pull_scale: float, rng: random.Random) -> None:
        if now_ms >= self.next_noise_ms:
            self.nx = rng.gauss(0.0, self.noise_amp)
            self.ny = rng.gauss(0.0, self.noise_amp)
            self.next_noise_ms = now_ms + int(rng.uniform(0.6, 1.6) * NOISE_PERIOD_MS)

        base_x = self.ax + (0.0 if self.role == "GK" else shift_x)
        base_y = self.ay
        pull = self.pull * pull_scale
        tx = base_x + (ball_x - base_x) * pull + self.nx
        ty = base_y + (ball_y - base_y) * pull + self.ny
        tx = _clamp(tx, -PITCH_X + 1.0, PITCH_X - 1.0)
        ty = _clamp(ty, -PITCH_Y + 1.0, PITCH_Y - 1.0)

        dx, dy = tx - self.x, ty - self.y
        dist = math.hypot(dx, dy)

        if dist <= ARRIVE_RADIUS:
            desired_vx = desired_vy = 0.0
        else:
            speed = min((dist - ARRIVE_RADIUS) * APPROACH_GAIN, self.vmax)
            desired_vx = dx / dist * speed
            desired_vy = dy / dist * speed

        dvx, dvy = desired_vx - self.vx, desired_vy - self.vy
        dv = math.hypot(dvx, dvy)
        cap = MAX_ACCEL * dt
        if dv > cap:
            dvx, dvy = dvx / dv * cap, dvy / dv * cap
        self.vx += dvx
        self.vy += dvy

        self.x = _clamp(self.x + self.vx * dt, -PITCH_X, PITCH_X)
        self.y = _clamp(self.y + self.vy * dt, -PITCH_Y, PITCH_Y)

    def state(self) -> PlayerState:
        return PlayerState(
            player_id=self.pid,
            pos=Point(x=round(self.x, 3), y=round(self.y, 3)),
            vx=round(self.vx, 3),
            vy=round(self.vy, 3),
            speed=round(math.hypot(self.vx, self.vy), 3),
        )


class MatchSimulator:
    """
        meta = build_match(seed=7)
        sim = MatchSimulator(meta)
        for frame in sim.run():
            ...
        print(sim.score, sim.stats)
    """

    def __init__(self, meta: MatchMeta):
        self.meta = meta
        self.hz = meta.tracking_hz
        self.dt = 1.0 / self.hz
        self.rng = random.Random(meta.seed)
        self.stats: dict[str, float] = {
            "passes": 0, "completed": 0, "intercepted": 0, "pass_distance_m": 0.0,
            "shots": 0, "on_target": 0, "blocked": 0, "goals": 0, "xg": 0.0,
        }
        self.score: dict[str, int] = {t.team_id: 0 for t in meta.teams}

    # -- setup ----------------------------------------------------------

    def _build_agents(self, period: int) -> tuple[list[_Agent], dict[str, float]]:
        agents: list[_Agent] = []
        attack_dir: dict[str, float] = {}
        for team in self.meta.teams:
            anch = anchors(self.meta, team.team_id, period)
            for player in team.players:
                ax, ay = anch[player.player_id]
                agents.append(
                    _Agent(player.player_id, team.team_id, player.position, ax, ay)
                )
                if player.position == "GK":
                    attack_dir[team.team_id] = -math.copysign(1.0, ax)
        return agents, attack_dir

    # -- decisions ------------------------------------------------------

    def _choose_receiver(self, agents: list[_Agent], holder: _Agent,
                         attack_dir: dict[str, float]) -> _Agent:
        mates = [a for a in agents
                 if a.team_id == holder.team_id and a is not holder and a.role != "GK"]
        candidates = self.rng.sample(mates, k=min(4, len(mates)))
        direction = attack_dir[holder.team_id]

        def score(a: _Agent) -> float:
            progress = (a.x - holder.x) * direction
            dist = math.hypot(a.x - holder.x, a.y - holder.y)
            return progress * 1.8 - abs(dist - IDEAL_PASS_M) * 0.30

        return max(candidates, key=score)

    def _contest(self, agents: list[_Agent], receiver: _Agent) -> _Agent:
        opponents = [a for a in agents if a.team_id != receiver.team_id]
        nearest = min(opponents,
                      key=lambda a: math.hypot(a.x - receiver.x, a.y - receiver.y))
        gap = math.hypot(nearest.x - receiver.x, nearest.y - receiver.y)
        if self.rng.random() < MISCONTROL_P or (
            gap < INTERCEPT_RADIUS and self.rng.random() < INTERCEPT_P
        ):
            self.stats["intercepted"] += 1
            return nearest
        self.stats["completed"] += 1
        return receiver

    def _resolve_shot(self, holder: _Agent, direction: float
                      ) -> tuple[str, tuple[float, float], float]:
        """Decide the outcome up front, then aim the ball to match it."""
        d, _angle, xg = fb.shot_quality(holder.x, holder.y, direction)
        self.stats["shots"] += 1
        self.stats["xg"] += xg

        gx = math.copysign(PITCH_X, direction)
        if self.rng.random() < xg:
            outcome = "goal"
            target = (gx, self.rng.uniform(-fb.GOAL_HALF * 0.82, fb.GOAL_HALF * 0.82))
            self.stats["on_target"] += 1
            self.stats["goals"] += 1
        else:
            r = self.rng.random()
            if r < 0.28:
                outcome = "blocked"
                f = self.rng.uniform(0.15, 0.5)
                target = (holder.x + (gx - holder.x) * f, holder.y * (1 - f))
                self.stats["blocked"] += 1
            elif r < 0.62:
                outcome = "off_target"
                side = self.rng.choice((-1.0, 1.0))
                target = (gx, _clamp(side * self.rng.uniform(fb.GOAL_HALF * 1.15,
                                                            fb.GOAL_HALF * 2.4),
                                     -PITCH_Y + 1, PITCH_Y - 1))
            else:
                outcome = "saved"
                target = (gx, self.rng.uniform(-fb.GOAL_HALF * 0.95,
                                               fb.GOAL_HALF * 0.95))
                self.stats["on_target"] += 1

        speed = _clamp(SHOT_SPEED_MIN + d * 0.35, SHOT_SPEED_MIN, SHOT_SPEED_MAX)
        return outcome, target, speed

    # -- main loop ------------------------------------------------------

    def run(self) -> Iterator[TrackingFrame]:
        seq = 0
        for info in self.meta.periods:
            agents, attack_dir = self._build_agents(info.period)
            by_id = {a.pid: a for a in agents}
            keepers = {a.team_id: a for a in agents if a.role == "GK"}

            holder: _Agent = self.rng.choice([a for a in agents if a.role != "GK"])
            ball_x, ball_y = holder.x, holder.y
            flight_target: tuple[float, float] | None = None
            flight_receiver: _Agent | None = None
            flight_speed = 0.0
            shot_outcome: str | None = None
            hold_until_ms = self.rng.randint(DWELL_MIN_MS, DWELL_MAX_MS)
            dead_until_ms = 0
            pending_holder: _Agent | None = None
            shift_state: dict[str, float] = {tid: 0.0 for tid in attack_dir}

            ticks = int(info.duration_ms / 1000 * self.hz)
            for tick in range(ticks):
                t_ms = int(tick * 1000 / self.hz)
                bvx = bvy = 0.0

                if t_ms < dead_until_ms:
                    # Dead ball: the block eases back, nobody chases the ball.
                    for tid in shift_state:
                        shift_state[tid] += (0.0 - shift_state[tid]) * SHIFT_LERP
                    for a in agents:
                        a.step(self.dt, t_ms, ball_x, ball_y,
                               shift_state[a.team_id], 0.25, self.rng)
                    yield self._frame(seq, info.period, t_ms, ball_x, ball_y,
                                      0.0, 0.0, None, agents, by_id)
                    seq += 1
                    continue

                if pending_holder is not None:
                    holder = pending_holder
                    pending_holder = None
                    ball_x, ball_y = holder.x, holder.y
                    hold_until_ms = t_ms + self.rng.randint(DWELL_MIN_MS, DWELL_MAX_MS)

                # The block eases toward its target rather than snapping to it.
                # Every turnover flips the shift by ATTACK_PUSH + DEFEND_DROP,
                # and making 11 players sprint that whole distance on each of
                # ~200 turnovers is what pushed distance covered to 14 km.
                # Real teams reorganise over seconds, not instantly.
                base = _clamp(ball_x * BLOCK_SHIFT, -22.0, 22.0)
                for tid, direction in attack_dir.items():
                    target = _clamp(
                        base + direction * (ATTACK_PUSH if tid == holder.team_id
                                            else -DEFEND_DROP),
                        -BLOCK_LIMIT, BLOCK_LIMIT,
                    )
                    shift_state[tid] += (target - shift_state[tid]) * SHIFT_LERP
                shift = shift_state
                for a in agents:
                    a.step(self.dt, t_ms, ball_x, ball_y, shift[a.team_id],
                           1.0, self.rng)

                if flight_target is None:
                    ball_x, ball_y = holder.x, holder.y
                    if t_ms >= hold_until_ms:
                        direction = attack_dir[holder.team_id]
                        d, _a, xg = fb.shot_quality(holder.x, holder.y, direction)
                        if (holder.role != "GK" and d <= SHOOT_RANGE_M and xg >= MIN_SHOT_XG
                                and self.rng.random() < _clamp(xg * SHOOT_EAGERNESS,
                                                               0.01, 0.45)):
                            shot_outcome, flight_target, flight_speed = \
                                self._resolve_shot(holder, direction)
                            flight_receiver = None
                        else:
                            flight_receiver = self._choose_receiver(
                                agents, holder, attack_dir)
                            flight_target = (flight_receiver.x, flight_receiver.y)
                            dist = math.hypot(flight_target[0] - ball_x,
                                              flight_target[1] - ball_y)
                            flight_speed = _clamp(8.0 + dist * 0.55,
                                                  PASS_SPEED_MIN, PASS_SPEED_MAX)
                            self.stats["passes"] += 1
                            self.stats["pass_distance_m"] += dist
                            shot_outcome = None

                        # The ball leaves with velocity on the tick it is
                        # released. Emitting a release frame at zero speed is
                        # physically wrong, and it makes a live ball
                        # indistinguishable from a dead one - the event
                        # detector cannot tell a pass from a goal kick.
                        tdx = flight_target[0] - ball_x
                        tdy = flight_target[1] - ball_y
                        tdist = math.hypot(tdx, tdy)
                        if tdist > 1e-6:
                            bvx = tdx / tdist * flight_speed
                            bvy = tdy / tdist * flight_speed
                            ball_x += bvx * self.dt
                            ball_y += bvy * self.dt
                else:
                    if flight_receiver is not None:
                        flight_target = (flight_receiver.x, flight_receiver.y)
                    tx, ty = flight_target
                    dx, dy = tx - ball_x, ty - ball_y
                    dist = math.hypot(dx, dy)

                    if dist <= flight_speed * self.dt:
                        ball_x, ball_y = tx, ty
                        if shot_outcome is None:
                            holder = self._contest(agents, flight_receiver)
                            hold_until_ms = t_ms + self.rng.randint(
                                DWELL_MIN_MS, DWELL_MAX_MS)
                        else:
                            conceding = next(t for t in attack_dir
                                             if t != holder.team_id)
                            if shot_outcome == "goal":
                                self.score[holder.team_id] += 1
                                ball_x = ball_y = 0.0
                                dead_until_ms = t_ms + KICKOFF_DEAD_MS
                                pending_holder = self.rng.choice(
                                    [a for a in agents
                                     if a.team_id == conceding and a.role == "MID"])
                                # Deliberately NOT teleporting everyone back to
                                # their anchors. A tracking feed with teleports
                                # is physically invalid: it registers as infinite
                                # speed and poisons every distance and speed
                                # metric downstream. The dead-ball window is long
                                # enough for them to walk back.
                            else:
                                ball_x = math.copysign(PITCH_X - 5.0,
                                                       -attack_dir[conceding])
                                ball_y = self.rng.uniform(-6.0, 6.0)
                                dead_until_ms = t_ms + RESTART_DEAD_MS
                                pending_holder = keepers[conceding]
                            shot_outcome = None
                        flight_target = None
                        flight_receiver = None
                    else:
                        bvx = dx / dist * flight_speed
                        bvy = dy / dist * flight_speed
                        ball_x += bvx * self.dt
                        ball_y += bvy * self.dt

                yield self._frame(
                    seq, info.period, t_ms, ball_x, ball_y, bvx, bvy,
                    None if flight_target is not None else holder.pid,
                    agents, by_id,
                )
                seq += 1

    def _frame(self, seq: int, period: int, t_ms: int, bx: float, by: float,
               bvx: float, bvy: float, owner: str | None,
               agents: list[_Agent], by_id: dict[str, _Agent]) -> TrackingFrame:
        return TrackingFrame(
            match_id=self.meta.match_id,
            seq=seq,
            period=period,
            t_ms=t_ms,
            ball=BallState(
                pos=Point(x=round(_clamp(bx, -PITCH_X, PITCH_X), 3),
                          y=round(_clamp(by, -PITCH_Y, PITCH_Y), 3)),
                vx=round(bvx, 3), vy=round(bvy, 3),
                speed=round(math.hypot(bvx, bvy), 3),
                owner=owner,
            ),
            players=[by_id[a.pid].state() for a in agents],
        )


# TODO, ordered by what the brief scores:
#   1. possession phases - build-up / progression / final third / transition
#   2. a real pressing model -> brief (iv) "tactical pressure changes"
#   3. off-ball runs, so pass difficulty means something
#   4. throw-ins, corners, fouls, cards, substitutions
#   5. fatigue, so second-half speed metrics are not flat


if __name__ == "__main__":
    from chalkboard.fixtures import build_match

    meta = build_match(7)
    sim = MatchSimulator(meta)
    for _ in sim.run():
        pass
    home, away = meta.teams
    print(f"{home.name} {sim.score[home.team_id]} - "
          f"{sim.score[away.team_id]} {away.name}")
    print(sim.stats)








