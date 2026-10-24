"""
language.py - rendering claims in a locale. Brief (vi).

    "Multi-language storytelling: generate clear natural-language outputs
     that could support global studio and streaming scenarios in multiple
     languages."

No model call. A ledger entry carries a **template key and parameters**, not
a finished sentence, so the same fact renders into any supported locale at
the point it reaches a screen. Storing one translated string per language on
every claim would bloat the ledger and make the Verifier check prose in four
languages instead of checking evidence once.

Why variant keys rather than assembled fragments
    "a 27 m pass" + "past 6 opponents" + "into the final third" glued
    together works in English and produces broken grammar in Spanish and
    French, where the clauses inflect and reorder. So each shape of claim is
    a whole sentence per locale. More strings to write, correct output.

Numbers are formatted per locale too - a Spanish or French broadcast caption
reading "21.1 m" instead of "21,1 m" looks wrong to the audience it is for.

Adding a locale is adding one dict. Nothing else changes.
"""

from __future__ import annotations

DEFAULT_LOCALE = "en-GB"

#: Locales with a full template set, in display order.
LOCALES: tuple[str, ...] = ("en-GB", "es-ES", "fr-FR")

LOCALE_NAMES = {
    "en-GB": "English",
    "es-ES": "Espanol",
    "fr-FR": "Francais",
}

#: Locales that write 1,5 rather than 1.5
DECIMAL_COMMA = {"es-ES", "fr-FR"}


TEMPLATES: dict[str, dict[str, str]] = {
    "en-GB": {
        "goal":
            "{player} scored for {team} from {distance} m, "
            "a chance worth {xg} expected goals.",
        "milestone.brace":
            "{player} has scored twice in this match.",
        "milestone.hattrick":
            "{player} has a hat-trick.",
        "milestone.many":
            "{player} has scored {goals} times in this match.",

        "shot.on_target":
            "{player} shot from {distance} m and forced a save; "
            "the chance was worth {xg} expected goals.",
        "shot.off_target":
            "{player} shot from {distance} m and missed the target; "
            "the chance was worth {xg} expected goals.",
        "shot.blocked":
            "{player} shot from {distance} m and it was blocked; "
            "the chance was worth {xg} expected goals.",

        "pass.plain":
            "{player} completed a {distance} m pass, "
            "rated {difficulty} for difficulty.",
        "pass.bypassed":
            "{player} completed a {distance} m pass past {bypassed} "
            "opponents, rated {difficulty} for difficulty.",
        "pass.final_third":
            "{player} completed a {distance} m pass into the final third, "
            "rated {difficulty} for difficulty.",
        "pass.bypassed_final_third":
            "{player} completed a {distance} m pass past {bypassed} "
            "opponents and into the final third, "
            "rated {difficulty} for difficulty.",

        "pressure":
            "{player} was closed down by {opponents} opponents for "
            "{seconds} s, the nearest within {distance} m.",

        "control.leader":
            "{team} are controlling the game: {possession}% of the ball, "
            "{completion}% pass completion, territory {territory}.",
        "control.balanced":
            "Neither side is controlling the game: possession is "
            "{possession}% to {possession_other}%, with chaos at {chaos}.",

        "press.up":
            "{team} have stepped up their press: pressure index {before} "
            "to {after}, line height {line_height}.",
        "press.down":
            "{team} have dropped off their press: pressure index {before} "
            "to {after}, line height {line_height}.",

        "tempo.up":
            "The game has quickened: {before} to {after} passes per "
            "minute, rhythm {rhythm}.",
        "tempo.down":
            "The game has slowed: {before} to {after} passes per minute, "
            "rhythm {rhythm}.",

        "speed":
            "{player} hit {speed} m/s, their quickest of the match so far.",
        "distance":
            "{player} has covered {km} km.",
    },

    "es-ES": {
        "goal":
            "{player} marco para {team} desde {distance} m, "
            "una ocasion de {xg} goles esperados.",
        "milestone.brace":
            "{player} lleva dos goles en este partido.",
        "milestone.hattrick":
            "{player} ha firmado un triplete.",
        "milestone.many":
            "{player} lleva {goals} goles en este partido.",

        "shot.on_target":
            "{player} disparo desde {distance} m y obligo a la parada; "
            "la ocasion valia {xg} goles esperados.",
        "shot.off_target":
            "{player} disparo desde {distance} m y fallo el objetivo; "
            "la ocasion valia {xg} goles esperados.",
        "shot.blocked":
            "{player} disparo desde {distance} m y fue bloqueado; "
            "la ocasion valia {xg} goles esperados.",

        "pass.plain":
            "{player} completo un pase de {distance} m, "
            "con una dificultad de {difficulty}.",
        "pass.bypassed":
            "{player} completo un pase de {distance} m superando a "
            "{bypassed} rivales, con una dificultad de {difficulty}.",
        "pass.final_third":
            "{player} completo un pase de {distance} m hacia el ultimo "
            "tercio, con una dificultad de {difficulty}.",
        "pass.bypassed_final_third":
            "{player} completo un pase de {distance} m superando a "
            "{bypassed} rivales y hacia el ultimo tercio, "
            "con una dificultad de {difficulty}.",

        "pressure":
            "{player} fue presionado por {opponents} rivales durante "
            "{seconds} s, con el mas cercano a {distance} m.",

        "control.leader":
            "{team} domina el partido: {possession}% de posesion, "
            "{completion}% de acierto en el pase, territorio {territory}.",
        "control.balanced":
            "Ningun equipo domina el partido: la posesion es "
            "{possession}% frente a {possession_other}%, "
            "con un caos de {chaos}.",

        "press.up":
            "{team} ha intensificado su presion: indice de presion de "
            "{before} a {after}, altura de la linea {line_height}.",
        "press.down":
            "{team} ha relajado su presion: indice de presion de "
            "{before} a {after}, altura de la linea {line_height}.",

        "tempo.up":
            "El partido se ha acelerado: de {before} a {after} pases por "
            "minuto, ritmo {rhythm}.",
        "tempo.down":
            "El partido se ha ralentizado: de {before} a {after} pases por "
            "minuto, ritmo {rhythm}.",

        "speed":
            "{player} alcanzo {speed} m/s, su maxima velocidad del partido.",
        "distance":
            "{player} ha recorrido {km} km.",
    },

    "fr-FR": {
        "goal":
            "{player} a marque pour {team} a {distance} m, "
            "une occasion valant {xg} buts attendus.",
        "milestone.brace":
            "{player} a inscrit un double dans ce match.",
        "milestone.hattrick":
            "{player} signe un triple.",
        "milestone.many":
            "{player} a inscrit {goals} buts dans ce match.",

        "shot.on_target":
            "{player} a tire a {distance} m et oblige le gardien a "
            "intervenir ; l'occasion valait {xg} buts attendus.",
        "shot.off_target":
            "{player} a tire a {distance} m et manque le cadre ; "
            "l'occasion valait {xg} buts attendus.",
        "shot.blocked":
            "{player} a tire a {distance} m et a ete contre ; "
            "l'occasion valait {xg} buts attendus.",

        "pass.plain":
            "{player} a reussi une passe de {distance} m, "
            "d'une difficulte de {difficulty}.",
        "pass.bypassed":
            "{player} a reussi une passe de {distance} m en eliminant "
            "{bypassed} adversaires, d'une difficulte de {difficulty}.",
        "pass.final_third":
            "{player} a reussi une passe de {distance} m vers le dernier "
            "tiers, d'une difficulte de {difficulty}.",
        "pass.bypassed_final_third":
            "{player} a reussi une passe de {distance} m en eliminant "
            "{bypassed} adversaires et vers le dernier tiers, "
            "d'une difficulte de {difficulty}.",

        "pressure":
            "{player} a ete presse par {opponents} adversaires pendant "
            "{seconds} s, le plus proche a {distance} m.",

        "control.leader":
            "{team} controle le match : {possession}% de possession, "
            "{completion}% de passes reussies, territoire {territory}.",
        "control.balanced":
            "Aucune equipe ne controle le match : la possession est de "
            "{possession}% contre {possession_other}%, "
            "avec un chaos de {chaos}.",

        "press.up":
            "{team} a intensifie son pressing : indice de pression de "
            "{before} a {after}, hauteur de ligne {line_height}.",
        "press.down":
            "{team} a relache son pressing : indice de pression de "
            "{before} a {after}, hauteur de ligne {line_height}.",

        "tempo.up":
            "Le match s'est accelere : de {before} a {after} passes par "
            "minute, rythme {rhythm}.",
        "tempo.down":
            "Le match s'est ralenti : de {before} a {after} passes par "
            "minute, rythme {rhythm}.",

        "speed":
            "{player} a atteint {speed} m/s, sa pointe du match.",
        "distance":
            "{player} a parcouru {km} km.",
    },
}


#: Short labels for the graphic itself, keyed by claim method.
HEADLINES: dict[str, dict[str, str]] = {
    "en-GB": {
        "goal_claim": "GOAL", "scoring_milestone": "Milestone",
        "shot_claim": "Shot", "pass_claim": "Pass",
        "speed_milestone": "Top speed", "distance_milestone": "Distance",
        "control_state": "Control", "pressure_state": "Press",
        "tempo_compare": "Tempo", "pressure_event": "Under pressure",
        "_default": "Match",
    },
    "es-ES": {
        "goal_claim": "GOL", "scoring_milestone": "Hito",
        "shot_claim": "Disparo", "pass_claim": "Pase",
        "speed_milestone": "Velocidad maxima", "distance_milestone": "Distancia",
        "control_state": "Control", "pressure_state": "Presion",
        "tempo_compare": "Ritmo", "pressure_event": "Bajo presion",
        "_default": "Partido",
    },
    "fr-FR": {
        "goal_claim": "BUT", "scoring_milestone": "Etape",
        "shot_claim": "Tir", "pass_claim": "Passe",
        "speed_milestone": "Vitesse de pointe", "distance_milestone": "Distance",
        "control_state": "Controle", "pressure_state": "Pressing",
        "tempo_compare": "Rythme", "pressure_event": "Sous pression",
        "_default": "Match",
    },
}


def headline(method: str, locale: str = DEFAULT_LOCALE) -> str:
    """Short on-screen label for a claim produced by `method`."""
    bare = method.split("@")[0]
    table = HEADLINES.get(locale) or HEADLINES[DEFAULT_LOCALE]
    return table.get(bare) or table["_default"]


def supported(locale: str) -> bool:
    return locale in TEMPLATES


def format_number(value: float, locale: str, places: int = 1) -> str:
    """Decimal comma where the locale uses one."""
    text = f"{value:.{places}f}"
    return text.replace(".", ",") if locale in DECIMAL_COMMA else text


def render(template_key: str, params: dict, locale: str = DEFAULT_LOCALE) -> str:
    """
    Render one claim. Falls back to the default locale for an unknown one
    rather than raising - a missing translation should degrade to English
    on screen, not take the render path down mid-match.
    """
    table = TEMPLATES.get(locale) or TEMPLATES[DEFAULT_LOCALE]
    template = table.get(template_key) or TEMPLATES[DEFAULT_LOCALE].get(template_key)
    if template is None:
        raise KeyError(f"no template for {template_key!r}")

    localised = {
        key: (format_number(value, locale,
                            2 if key in ("xg", "difficulty", "territory",
                                         "chaos", "rhythm", "before", "after",
                                         "line_height") else 1)
              if isinstance(value, float) else value)
        for key, value in params.items()
    }
    return template.format(**localised)


def missing_keys() -> dict[str, list[str]]:
    """Which templates a locale is short of. Used by the tests."""
    reference = set(TEMPLATES[DEFAULT_LOCALE])
    return {
        locale: sorted(reference - set(table))
        for locale, table in TEMPLATES.items()
        if reference - set(table)
    }
