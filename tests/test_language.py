"""
Multi-language rendering. Brief (vi).

The important test is the last class: every template key the claim builders
actually emit must exist in every locale. A missing key is invisible in
English and only shows up as an untranslated sentence on a Spanish
broadcast caption, which is exactly the kind of fault that reaches air.
"""

import itertools
import re

import pytest

from chalkboard import language
from chalkboard.director import Director
from chalkboard.fixtures import build_match
from chalkboard.ledger import build
from chalkboard.sim import MatchSimulator


@pytest.fixture(scope="module")
def ledger():
    meta = build_match(2)
    frames = itertools.islice(MatchSimulator(meta).run(),
                              meta.tracking_hz * 60 * 20)
    return meta, build(meta, frames, keep=False).ledger


class TestCoverage:
    def test_every_locale_has_every_template(self):
        assert language.missing_keys() == {}

    def test_every_locale_has_every_headline(self):
        reference = set(language.HEADLINES[language.DEFAULT_LOCALE])
        for locale, table in language.HEADLINES.items():
            assert reference - set(table) == set(), f"{locale} is short"

    def test_declared_locales_all_have_tables(self):
        for locale in language.LOCALES:
            assert locale in language.TEMPLATES
            assert locale in language.HEADLINES
            assert locale in language.LOCALE_NAMES

    def test_templates_use_the_same_placeholders_across_locales(self):
        """
        A locale that omits a parameter silently drops a fact; one that
        invents a parameter raises KeyError at render time, mid-match.
        """
        def holes(text):
            return set(re.findall(r"\{(\w+)\}", text))

        for key, english in language.TEMPLATES[language.DEFAULT_LOCALE].items():
            expected = holes(english)
            for locale in language.LOCALES:
                got = holes(language.TEMPLATES[locale][key])
                assert got == expected, f"{locale}/{key}: {got} != {expected}"


class TestRendering:
    def test_locales_produce_different_text(self):
        params = {"player": "Vance", "team": "Rivermead Athletic",
                  "distance": 20.9, "xg": 0.09}
        rendered = {loc: language.render("goal", params, loc)
                    for loc in language.LOCALES}
        assert len(set(rendered.values())) == len(language.LOCALES)

    def test_decimal_comma_where_the_locale_uses_one(self):
        params = {"player": "Vance", "team": "T", "distance": 20.9, "xg": 0.09}
        assert "20.9" in language.render("goal", params, "en-GB")
        assert "20,9" in language.render("goal", params, "es-ES")
        assert "20,9" in language.render("goal", params, "fr-FR")

    def test_unknown_locale_falls_back_rather_than_raising(self):
        """Degrade to English on screen, do not take the render path down."""
        params = {"player": "Vance", "km": 5.0}
        out = language.render("distance", params, "xx-XX")
        assert out == language.render("distance", params, "en-GB")

    def test_unknown_template_raises(self):
        with pytest.raises(KeyError):
            language.render("no.such.key", {}, "en-GB")

    def test_headlines_are_localised(self):
        assert language.headline("goal_claim@0.1", "en-GB") == "GOAL"
        assert language.headline("goal_claim@0.1", "es-ES") == "GOL"
        assert language.headline("goal_claim@0.1", "fr-FR") == "BUT"

    def test_unknown_method_gets_a_default_headline(self):
        assert language.headline("something_new@9.9", "en-GB") == "Match"


class TestAgainstARealMatch:
    def test_every_claim_carries_a_template(self, ledger):
        _meta, lg = ledger
        for e in lg:
            assert e.template, f"{e.ledger_id} has no template"
            assert e.params, f"{e.ledger_id} has no params"

    def test_every_emitted_template_exists_in_every_locale(self, ledger):
        """The one that matters."""
        _meta, lg = ledger
        used = {e.template for e in lg}
        assert used
        for locale in language.LOCALES:
            missing = used - set(language.TEMPLATES[locale])
            assert not missing, f"{locale} is missing {sorted(missing)}"

    def test_every_claim_renders_in_every_locale(self, ledger):
        _meta, lg = ledger
        for e in lg:
            for locale in language.LOCALES:
                text = language.render(e.template, e.params, locale)
                assert text and "{" not in text, f"{e.template}/{locale}"

    def test_stored_claim_matches_its_english_rendering(self, ledger):
        """One source of truth - the sentence cannot drift from the template."""
        _meta, lg = ledger
        for e in lg:
            assert e.claim == language.render(e.template, e.params, "en-GB")

    def test_director_emits_packets_in_the_requested_locale(self, ledger):
        meta, lg = ledger
        for locale in language.LOCALES:
            packets = Director(meta, locale=locale).direct(lg)
            assert packets
            assert all(p.locale == locale for p in packets)
            assert all(p.body and p.speech_text for p in packets)

    def test_the_same_fact_differs_by_locale_on_the_wire(self, ledger):
        meta, lg = ledger
        bodies = {}
        for locale in language.LOCALES:
            packets = Director(meta, locale=locale).direct(lg)
            bodies[locale] = packets[0].body
        assert len(set(bodies.values())) == len(language.LOCALES)
