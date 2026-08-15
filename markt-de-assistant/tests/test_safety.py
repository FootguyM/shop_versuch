"""Der Sicherheitsfilter ist die wichtigste Komponente im Projekt.

Wenn hier etwas durchrutscht, geht eine automatische Antwort an jemanden
raus, der keine bekommen darf. Entsprechend ausfuehrlich getestet.
"""

import pytest

from marktbot.ai.safety import SafetyFilter


@pytest.fixture
def filt():
    return SafetyFilter(enabled=True)


# --- Harte Blocker ---------------------------------------------------------

@pytest.mark.parametrize("text", [
    "Bist du minderjährig?",
    "Ich suche jemanden unter 18",
    "17 jährige gesucht",
    "Hast du eine Schülerin im Angebot?",
])
def test_minderjaehrige_werden_blockiert(filt, text):
    verdict = filt.check_incoming(text)
    assert not verdict.allowed
    assert "Minderj" in verdict.reason


@pytest.mark.parametrize("text", [
    "Wirst du dazu gezwungen?",
    "Ich erpresse dich damit",
    "Du musst deine Schulden abarbeiten",
])
def test_noetigung_wird_blockiert(filt, text):
    assert not filt.check_incoming(text).allowed


@pytest.mark.parametrize("text", [
    "Geht das auch ohne Gummi?",
    "Machst du AO?",
    "bareback möglich?",
])
def test_ungeschuetzt_wird_blockiert(filt, text):
    assert not filt.check_incoming(text).allowed


@pytest.mark.parametrize("text", [
    "Ich schicke dir einen Amazon Gutschein",
    "Zahlung per Western Union ok?",
    "Ich überweise dir Bitcoin vorab",
])
def test_betrugsmuster_werden_blockiert(filt, text):
    assert not filt.check_incoming(text).allowed


# --- Uebergabe an den Menschen --------------------------------------------

@pytest.mark.parametrize("text", [
    "Was kostet das denn?",
    "Ich zahle 100 Euro",
    "Wie ist deine IBAN?",
    "Wo genau wohnst du?",
    "Schreib mir auf WhatsApp",
    "Meine Nummer ist 0171 2345678",
    "schreib mir an test@example.com",
])
def test_heikle_themen_gehen_an_den_menschen(filt, text):
    verdict = filt.check_incoming(text)
    assert not verdict.allowed, f"sollte eskalieren: {text!r}"


# --- Harmlose Nachrichten dürfen durch ------------------------------------

@pytest.mark.parametrize("text", [
    "Hallo, wie geht es dir?",
    "Bist du heute Abend da?",
    "Schönes Profil, sehen wir uns mal?",
    "Hey :)",
])
def test_harmlose_nachrichten_kommen_durch(filt, text):
    verdict = filt.check_incoming(text)
    assert verdict.allowed, f"Fehlalarm bei {text!r}: {verdict.reason}"


# --- Ausgehend -------------------------------------------------------------

@pytest.mark.parametrize("text", [
    "Meine IBAN ist DE89 3704 0044 0532 0130 00",
    "Ruf mich an: 0171 2345678",
    "Schreib an ich@example.de",
    "Ich wohne in der Musterstraße 12",
    "Komm nach 10115 Berlin",
])
def test_ausgehende_kontaktdaten_werden_gestoppt(filt, text):
    verdict = filt.check_outgoing(text)
    assert not verdict.allowed, f"sollte gestoppt werden: {text!r}"


def test_normale_antwort_darf_raus(filt):
    assert filt.check_outgoing("Hi! Danke für deine Nachricht, ich melde mich gleich.").allowed


def test_abgeschalteter_filter_laesst_alles_durch():
    filt = SafetyFilter(enabled=False)
    assert filt.check_incoming("unter 18").allowed
    assert filt.check_outgoing("IBAN DE89370400440532013000").allowed


def test_eigene_blockliste_greift():
    filt = SafetyFilter(enabled=True, extra_blocklist=[r"\bstammkunde\b"])
    assert not filt.check_incoming("Ich bin doch Stammkunde").allowed
    assert filt.check_incoming("Ich bin neu hier").allowed
