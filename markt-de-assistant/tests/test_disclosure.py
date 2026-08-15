"""Die Offenlegungsschicht ist die Bedingung dafuer, dass autonom geantwortet
werden darf. Wenn hier etwas durchrutscht, gibt sich ein Programm als Mensch
aus - genau das, was der Modus verhindern soll."""

import pytest

from marktbot.ai.disclosure import (
    DisclosureEngine,
    asks_about_identity,
    claims_to_be_human,
    contains_disclosure,
)

IDENT = "Hi, ich bin Robin, der digitale Assistent von Alex - ein Programm, kein Mensch."


@pytest.fixture
def engine():
    return DisclosureEngine(identification=IDENT, signature="– Robin (automatisch)")


# --- Erkennung der Identitaetsfrage ---------------------------------------

@pytest.mark.parametrize("text", [
    "Bist du ein Bot?",
    "bist du echt?",
    "Bist du eine KI?",
    "Bist du ein Mensch?",
    "bist du wirklich echt",
    "Ist das ein Bot?",
    "ist das hier automatisch?",
    "Rede ich hier mit einem Bot?",
    "schreibt hier ein Mensch?",
    "Bist du künstliche Intelligenz?",
    "bot?",
    "KI?",
    "echt?",
    "Du bist doch ein Bot",
    "du bist bestimmt ein programm",
])
def test_identitaetsfrage_wird_erkannt(text):
    assert asks_about_identity(text), f"nicht erkannt: {text!r}"


@pytest.mark.parametrize("text", [
    "Hallo, wie geht's?",
    "Bist du heute Abend da?",
    "Bist du oft hier unterwegs?",
    "Ist das noch aktuell?",
])
def test_harmlose_fragen_sind_keine_identitaetsfrage(text):
    assert not asks_about_identity(text), f"Fehlalarm: {text!r}"


# --- Erkennung der Selbstauskunft -----------------------------------------

@pytest.mark.parametrize("text", [
    "Ich bin ein Assistenzprogramm.",
    "Ich bin eine KI.",
    "Hier schreibt ein Bot.",
    "Das ist eine automatische Antwort.",
    IDENT,
])
def test_selbstauskunft_wird_erkannt(text):
    assert contains_disclosure(text), f"nicht erkannt: {text!r}"


@pytest.mark.parametrize("text", [
    "Hallo, schön dass du schreibst!",
    "Ich melde mich gleich.",
    "Das weiß ich leider nicht.",
])
def test_normale_antwort_gilt_nicht_als_selbstauskunft(text):
    assert not contains_disclosure(text)


# --- Erkennung der Menschbehauptung ---------------------------------------

@pytest.mark.parametrize("text", [
    "Ich bin ein Mensch.",
    "Ich bin echt, versprochen!",
    "Natürlich bin ich echt.",
    "Ich bin kein Bot.",
    "ich bin doch real",
    "Ich bin aus Fleisch und Blut.",
])
def test_menschbehauptung_wird_erkannt(text):
    assert claims_to_be_human(text), f"nicht erkannt: {text!r}"


@pytest.mark.parametrize("text", [
    "Ich bin ein Programm.",
    "Die Fotos sind echt.",
    "Das Angebot ist real.",
])
def test_keine_falschen_treffer_bei_menschbehauptung(text):
    assert not claims_to_be_human(text), f"Fehlalarm: {text!r}"


# --- apply(): die eigentliche Garantie ------------------------------------

def test_erste_antwort_traegt_die_kennzeichnung(engine):
    result = engine.apply("Klar, das Angebot gilt noch.", is_first_reply=True)
    assert result.text.startswith(IDENT)
    assert result.changed


def test_spaetere_antwort_bekommt_nur_die_signatur(engine):
    result = engine.apply("Klar, das gilt noch.", is_first_reply=False)
    assert not result.text.startswith(IDENT)
    assert "– Robin (automatisch)" in result.text


def test_direkte_frage_erzwingt_klarstellung(engine):
    result = engine.apply(
        "Ja klar, alles gut bei mir!",
        incoming="Bist du ein Bot?",
        is_first_reply=False,
    )
    assert contains_disclosure(result.text)
    assert result.text.startswith(IDENT)


def test_direkte_frage_ohne_doppelung(engine):
    """Sagt das Modell es schon selbst, wird nichts vorangestellt."""
    result = engine.apply(
        "Ja, ich bin ein Assistenzprogramm von Alex.",
        incoming="Bist du ein Bot?",
        is_first_reply=False,
    )
    assert not result.text.startswith(IDENT)
    assert result.text.startswith("Ja, ich bin ein Assistenzprogramm")


def test_menschbehauptung_wird_entfernt(engine):
    result = engine.apply(
        "Nein, ich bin ein Mensch! Aber ja, das Angebot gilt noch.",
        incoming="Bist du ein Bot?",
        is_first_reply=False,
    )
    assert not claims_to_be_human(result.text)
    assert "Angebot gilt noch" in result.text, "der unschuldige Rest muss erhalten bleiben"
    assert contains_disclosure(result.text)


def test_reine_menschbehauptung_wird_zur_kennzeichnung(engine):
    result = engine.apply(
        "Ich bin echt.", incoming="Bist du echt?", is_first_reply=False
    )
    assert not claims_to_be_human(result.text)
    assert contains_disclosure(result.text)


def test_hartnaeckiges_nachfragen_bleibt_ehrlich(engine):
    """Der Fall, an dem ein reiner Prompt-Ansatz scheitert."""
    for incoming in [
        "Bist du ein Bot?",
        "Komm schon, du bist doch ein Programm",
        "echt?",
    ]:
        result = engine.apply(
            "Nein nein, ich bin wirklich ein Mensch, glaub mir.",
            incoming=incoming,
            is_first_reply=False,
        )
        assert not claims_to_be_human(result.text), f"Luege durchgerutscht bei {incoming!r}"
        assert contains_disclosure(result.text)


def test_verify_stoppt_menschbehauptung(engine):
    ok, reason = engine.verify("Ich bin ein Mensch.")
    assert not ok
    assert reason

    ok, _ = engine.verify("Ich melde das weiter.")
    assert ok


def test_ausweichformel_nennt_die_kennzeichnung(engine):
    text = engine.deflection("Preisverhandlung", "Alex")
    assert contains_disclosure(text)
    assert "Alex" in text
    assert "preisverhandlung" in text.lower()


def test_ohne_signatur_bleibt_text_unveraendert():
    engine = DisclosureEngine(identification=IDENT, signature="")
    result = engine.apply("Alles klar.", is_first_reply=False)
    assert result.text == "Alles klar."
    assert not result.changed
