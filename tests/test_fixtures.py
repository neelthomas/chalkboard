"""Fixtures are deterministic, internally consistent, and trademark-safe."""

import re

from chalkboard.fixtures import CLUBS, FORMATIONS, anchors, build_match


def test_deterministic():
    assert build_match(7) == build_match(7)
    assert build_match(7) != build_match(8)


def test_surnames_unique_across_the_match():
    """Two players sharing a surname makes narration ambiguous."""
    players = [p for t in build_match(7).teams for p in t.players]
    surnames = [p.name.split()[-1] for p in players]
    assert len(set(surnames)) == len(surnames) == 22


def test_shirt_numbers_unique_within_team():
    for team in build_match(7).teams:
        shirts = [p.shirt for p in team.players]
        assert len(set(shirts)) == 11


def test_squad_matches_formation():
    for team in build_match(7).teams:
        expected = [pos for pos, _x, _y in FORMATIONS[team.formation]]
        assert [p.position for p in team.players] == expected


def test_teams_defend_opposite_ends():
    meta = build_match(7)
    home_gk = anchors(meta, "t_home", 1)["t_home_p01"]
    away_gk = anchors(meta, "t_away", 1)["t_away_p01"]
    assert home_gk[0] * away_gk[0] < 0, "both keepers ended up in the same goal"


def test_teams_swap_ends_at_half_time():
    meta = build_match(7)
    first = anchors(meta, "t_home", 1)["t_home_p01"]
    second = anchors(meta, "t_home", 2)["t_home_p01"]
    assert first[0] * second[0] < 0


def test_no_real_club_names():
    """
    Rules 4.4 forbid third-party trademarks. This is a tripwire, not proof -
    the real check is a human read of CLUBS before the video is cut.
    """
    banned = re.compile(
        r"arsenal|chelsea|liverpool|everton|tottenham|spurs|man(chester)?\s*(utd|united|city)"
        r"|newcastle|villa|wolves|fulham|brentford|brighton|palace|forest|bournemouth"
        r"|premier\s*league",
        re.IGNORECASE,
    )
    for name, short, venue in CLUBS:
        assert not banned.search(f"{name} {short} {venue}"), name

    meta = build_match(7)
    assert not banned.search(meta.competition)
