"""
fixtures.py - deterministic match metadata.

Every club, player and competition name here is invented. Hackathon rules
4.4 prohibit third-party trademarks in the submission, which rules out real
clubs, badges and player names. Keeping the invented names in one module
means there is exactly one place to audit before the video is cut.

Same seed in, same teams out.
"""

from __future__ import annotations

import random

from chalkboard.contracts import (
    AttackDirection,
    MatchMeta,
    PeriodInfo,
    PlayerMeta,
    Side,
    TeamMeta,
)

COMPETITION = "Meridian League"

CLUBS: list[tuple[str, str, str]] = [
    # (name, short, venue)
    ("Rivermead Athletic", "RVM", "The Causeway"),
    ("Calderwick City", "CDW", "Marlin Park"),
    ("Selmouth Town", "SEL", "Harbourside"),
    ("Hallowfield United", "HAL", "Vicarage Lane"),
    ("Port Brennan FC", "PBR", "The Quay"),
    ("Ashcombe Rovers", "ASH", "Coldstream Road"),
]

FIRST_NAMES = [
    "Tomas", "Idris", "Mateo", "Kwame", "Lucas", "Niall", "Rafael", "Dmitri",
    "Jonah", "Emeka", "Aziz", "Sven", "Callum", "Hiro", "Pierre", "Andres",
    "Omar", "Felix", "Jasper", "Milan", "Teodor", "Kai", "Diego", "Arne",
    "Yusuf", "Lorenzo", "Bastien", "Nikola", "Elias", "Samir",
]

# Surnames must be unique across the whole match. Two players sharing one
# makes narration ambiguous ("Vance wins it back" - which Vance?) and makes
# provenance impossible to eyeball. The pool is sized for 22 starters plus
# room for substitutes later.
LAST_NAMES = [
    "Vance", "Okafor", "Lindqvist", "Marchetti", "Bello", "Hartnell",
    "Duarte", "Novak", "Whitlock", "Asante", "Farouk", "Berglund",
    "Reyes", "Tanaka", "Lefevre", "Castillo", "Haddad", "Brennan",
    "Kowalski", "Mensah", "Albright", "Sorensen", "Varga", "Oyelaran",
    "Strand", "Pereira", "Calloway", "Kazan", "Ferreira", "Dunmore",
    "Sattler", "Nwosu", "Ivarsson", "Delacroix",
]

# Formation anchors in a frame where the team attacks +x and defends the
# -x goal. Mirrored for the other side at build time.
FORMATIONS: dict[str, list[tuple[str, float, float]]] = {
    "4-3-3": [
        ("GK", -48.0, 0.0),
        ("RB", -30.0, -24.0),
        ("RCB", -34.0, -8.0),
        ("LCB", -34.0, 8.0),
        ("LB", -30.0, 24.0),
        ("DM", -16.0, 0.0),
        ("RCM", -8.0, -12.0),
        ("LCM", -8.0, 12.0),
        ("RW", 6.0, -22.0),
        ("ST", 9.0, 0.0),
        ("LW", 6.0, 22.0),
    ],
    "4-4-2": [
        ("GK", -48.0, 0.0),
        ("RB", -30.0, -24.0),
        ("RCB", -34.0, -8.0),
        ("LCB", -34.0, 8.0),
        ("LB", -30.0, 24.0),
        ("RM", -10.0, -24.0),
        ("RCM", -14.0, -8.0),
        ("LCM", -14.0, 8.0),
        ("LM", -10.0, 24.0),
        ("RS", 8.0, -7.0),
        ("LS", 8.0, 7.0),
    ],
}


def _squad(
    rng: random.Random,
    team_id: str,
    formation: str,
    surnames: list[str],
) -> list[PlayerMeta]:
    """`surnames` is pre-allocated by build_match so they stay unique match-wide."""
    firsts = [rng.choice(FIRST_NAMES) for _ in range(11)]
    shirts = rng.sample(range(1, 40), 11)
    return [
        PlayerMeta(
            player_id=f"{team_id}_p{i + 1:02d}",
            name=f"{firsts[i]} {surnames[i]}",
            shirt=shirts[i],
            position=pos,
            team_id=team_id,
        )
        for i, (pos, _x, _y) in enumerate(FORMATIONS[formation])
    ]


def build_match(seed: int = 7) -> MatchMeta:
    """Deterministic MatchMeta. Same seed always yields the same fixture."""
    rng = random.Random(seed)
    home_club, away_club = rng.sample(CLUBS, 2)

    home_formation = rng.choice(list(FORMATIONS))
    away_formation = rng.choice(list(FORMATIONS))

    # One draw for the whole match, so no surname appears twice.
    surnames = rng.sample(LAST_NAMES, 22)

    home = TeamMeta(
        team_id="t_home", name=home_club[0], short_name=home_club[1],
        side=Side.HOME, formation=home_formation,
        players=_squad(rng, "t_home", home_formation, surnames[:11]),
    )
    away = TeamMeta(
        team_id="t_away", name=away_club[0], short_name=away_club[1],
        side=Side.AWAY, formation=away_formation,
        players=_squad(rng, "t_away", away_formation, surnames[11:]),
    )

    return MatchMeta(
        match_id=f"m_{seed:04d}",
        seed=seed,
        competition=COMPETITION,
        kickoff_utc="2026-10-18T14:00:00Z",
        venue=home_club[2],
        teams=[home, away],
        periods=[
            # Home attacks +x in the first half, then they swap ends.
            PeriodInfo(period=1, home_attacks=AttackDirection.POS_X,
                       duration_ms=45 * 60 * 1000),
            PeriodInfo(period=2, home_attacks=AttackDirection.NEG_X,
                       duration_ms=45 * 60 * 1000),
        ],
        tracking_hz=25,
    )


def attack_direction(meta: MatchMeta, team_id: str, period: int) -> float:
    """+1 if this team shoots toward +x in this period, -1 otherwise."""
    team = next(t for t in meta.teams if t.team_id == team_id)
    info = next(p for p in meta.periods if p.period == period)
    home_pos_x = info.home_attacks == AttackDirection.POS_X
    attacks_pos_x = home_pos_x if team.side == Side.HOME else not home_pos_x
    return 1.0 if attacks_pos_x else -1.0


def anchors(meta: MatchMeta, team_id: str, period: int) -> dict[str, tuple[float, float]]:
    """
    Formation anchors for one team in a given period, in absolute pitch
    coordinates - i.e. already flipped if they are attacking -x.
    """
    team = next(t for t in meta.teams if t.team_id == team_id)
    info = next(p for p in meta.periods if p.period == period)
    home_pos_x = info.home_attacks == AttackDirection.POS_X
    attacks_pos_x = home_pos_x if team.side == Side.HOME else not home_pos_x
    flip = 1.0 if attacks_pos_x else -1.0

    # Per-team shape variation. Without it, two sides in the same formation
    # line up as exact mirrors - every player marked by his opposite number
    # at zero distance - and the match degenerates: seed 21 (4-4-2 v 4-4-2)
    # produced 65% pass completion and 13 shots against ~91% and ~35 for
    # every mismatched fixture. Real teams never set up identically.
    shape = random.Random(f"{meta.seed}:{team_id}:shape")

    layout = FORMATIONS[team.formation]
    out: dict[str, tuple[float, float]] = {}
    for player, (pos, x, y) in zip(team.players, layout):
        if pos == "GK":
            out[player.player_id] = (x * flip, y * flip)
            continue
        dx = shape.uniform(-2.5, 2.5)
        dy = shape.uniform(-3.0, 3.0)
        out[player.player_id] = ((x + dx) * flip, (y + dy) * flip)
    return out


if __name__ == "__main__":
    m = build_match(7)
    print(f"{m.competition} - {m.venue}")
    for t in m.teams:
        print(f"\n{t.name} ({t.short_name}) {t.formation}")
        for p in t.players:
            print(f"  {p.shirt:>2}  {p.position:<4} {p.name}")
