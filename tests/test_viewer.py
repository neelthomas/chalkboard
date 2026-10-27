"""
Viewer export: the timing contract behind the live feed.

The feed is only live if every claim carries the moment it became known
(`at`). Two faults here would be invisible in a still screenshot and obvious
in motion: a claim announced before it happened, and a feed that is not in
time order.
"""

import json
import re

import pytest

from chalkboard import viewer


@pytest.fixture(scope="module")
def data():
    path = viewer.export(seed=7, minutes=8, hz=5, open_browser=False)
    html = path.read_text(encoding="utf-8")
    match = re.search(r"const D = (\{.*?\});\s*const PITCH_L", html, re.S)
    assert match, "could not find the embedded data"
    return json.loads(match.group(1))


def test_every_claim_has_a_moment(data):
    assert data["claims"]
    for c in data["claims"]:
        assert isinstance(c["at"], int) and c["at"] >= 0


def test_claims_are_in_time_order(data):
    ats = [c["at"] for c in data["claims"]]
    assert ats == sorted(ats)


def test_a_claim_is_never_announced_before_its_evidence_ends(data):
    """
    The leak this guards: a claim about a two-minute window used to be keyed
    to the start of that window, so "controlling the game" appeared two
    minutes before it was true.
    """
    for c in data["claims"]:
        assert c["at"] >= c["row"], f"{c['id']} appears before it starts"
        assert c["at"] >= c["to"], f"{c['id']} appears before its evidence ends"


def test_window_claims_are_keyed_to_when_the_window_closes(data):
    control = [c for c in data["claims"] if c["method"].startswith("control_state")]
    assert control
    for c in control:
        assert c["row"] == c["at"]


def test_nothing_appears_at_the_whistle(data):
    """A feed that dumps everything at the end is not live."""
    last = len(data["frames"]) - 1
    ats = [c["at"] for c in data["claims"]]
    assert sum(1 for a in ats if a >= last) <= 2
    assert len({a // 200 for a in ats}) > 3, "claims are bunched together"


def test_every_locale_is_present_on_every_claim(data):
    codes = [loc["code"] for loc in data["locales"]]
    for c in data["claims"]:
        assert set(c["body"]) == set(codes)
        assert set(c["head"]) == set(codes)
