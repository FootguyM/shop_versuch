"""Durchstich durch den Assistenzmodus: Konfiguration laden, Responder bauen,
Antwort erzeugen. Nutzt das Template-Backend, damit kein Modell noetig ist."""

import textwrap

import pytest

from marktbot.ai.disclosure import claims_to_be_human, contains_disclosure
from marktbot.ai.responder import Responder
from marktbot.config import ConfigError, load_config
from marktbot.models import Direction, Message, Thread

BASE_CONFIG = """
assistant:
  enabled: true
  assistant_name: "Robin"
  operator_name: "Alex"
  identification: "Ich bin Robin, der digitale Assistent von Alex - ein Programm, kein Mensch."
  signature: "– Robin (automatisch)"
  identify_on_first_reply: true
  deflect_handover_topics: true

replies:
  require_approval: false
  always_approve_first_contact: false

persona:
  display_name: "Alex"
  description: "Sachlich und knapp."
  rules:
    - "Antworte auf Deutsch."
  handover_topics:
    - "Preisverhandlung"

ai:
  backend: "template"

safety:
  enabled: true
"""


def write_config(tmp_path, body: str = BASE_CONFIG):
    path = tmp_path / "config.yaml"
    path.write_text(textwrap.dedent(body), encoding="utf-8")
    return path


@pytest.fixture
def config(tmp_path):
    return load_config(write_config(tmp_path), root=tmp_path)


@pytest.fixture
def thread():
    return Thread(thread_id="t1", partner_name="Chris", ad_title="Testanzeige")


def incoming(body: str) -> list[Message]:
    return [Message(thread_id="t1", direction=Direction.INCOMING, body=body)]


# --- Konfiguration ---------------------------------------------------------

def test_assistenzmodus_ohne_kennzeichnung_wird_abgelehnt(tmp_path):
    body = BASE_CONFIG.replace(
        'identification: "Ich bin Robin, der digitale Assistent von Alex - ein Programm, kein Mensch."',
        'identification: ""',
    )
    with pytest.raises(ConfigError, match="identification"):
        load_config(write_config(tmp_path, body), root=tmp_path)


def test_operator_faellt_auf_display_name_zurueck(tmp_path):
    body = BASE_CONFIG.replace('operator_name: "Alex"', 'operator_name: ""')
    config = load_config(write_config(tmp_path, body), root=tmp_path)
    assert config.assistant.operator_name == "Alex"


# --- Antworten -------------------------------------------------------------

async def test_erste_antwort_stellt_sich_vor(config, thread):
    responder = Responder(config)
    result = await responder.draft_reply(thread, incoming("Hallo, ist das noch da?"))

    assert result.ok
    assert result.text.startswith(config.assistant.identification)
    assert contains_disclosure(result.text)


async def test_spaetere_antwort_traegt_die_signatur(config, thread):
    history = [
        Message(thread_id="t1", direction=Direction.INCOMING, body="Hallo"),
        Message(thread_id="t1", direction=Direction.OUTGOING, body="Hi, ich bin ein Programm."),
        Message(thread_id="t1", direction=Direction.INCOMING, body="Alles klar, danke"),
    ]
    responder = Responder(config)
    result = await responder.draft_reply(thread, history)

    assert result.ok
    assert not result.text.startswith(config.assistant.identification)
    assert config.assistant.signature in result.text


async def test_identitaetsfrage_wird_ehrlich_beantwortet(config, thread):
    responder = Responder(config)
    history = [
        Message(thread_id="t1", direction=Direction.INCOMING, body="Hallo"),
        Message(thread_id="t1", direction=Direction.OUTGOING, body="Hi, ich bin ein Programm."),
        Message(thread_id="t1", direction=Direction.INCOMING, body="Moment, bist du ein Bot?"),
    ]
    result = await responder.draft_reply(thread, history)

    assert result.ok
    assert contains_disclosure(result.text)
    assert not claims_to_be_human(result.text)


async def test_heikles_thema_wird_ausgewichen_statt_blockiert(config, thread):
    """Im Assistenzmodus bleibt der Absender nicht ohne Rueckmeldung."""
    responder = Responder(config)
    result = await responder.draft_reply(thread, incoming("Was kostet das denn?"))

    assert result.ok, "im Assistenzmodus soll ausgewichen, nicht geschwiegen werden"
    assert result.deflected
    assert contains_disclosure(result.text)
    assert "Alex" in result.text


async def test_ausweichen_abschaltbar(tmp_path, thread):
    body = BASE_CONFIG.replace(
        "deflect_handover_topics: true", "deflect_handover_topics: false"
    )
    config = load_config(write_config(tmp_path, body), root=tmp_path)
    responder = Responder(config)
    result = await responder.draft_reply(thread, incoming("Was kostet das denn?"))

    assert result.blocked


async def test_harte_blocker_gelten_auch_im_assistenzmodus(config, thread):
    responder = Responder(config)
    result = await responder.draft_reply(thread, incoming("Suchst du auch Leute unter 18?"))

    assert result.blocked
    assert not result.text


async def test_handbetippter_text_darf_sich_nicht_als_mensch_ausgeben(config):
    responder = Responder(config)
    verdict = responder.check_manual_text("Nein, ich bin ein Mensch.")
    assert not verdict.allowed

    assert responder.check_manual_text("Ich gebe das an Alex weiter.").allowed


# --- Gegenprobe: Standardmodus verhaelt sich unveraendert ------------------

async def test_ohne_assistenzmodus_keine_kennzeichnung(tmp_path, thread):
    body = BASE_CONFIG.replace("enabled: true", "enabled: false", 1)
    config = load_config(write_config(tmp_path, body), root=tmp_path)
    responder = Responder(config)

    assert responder.disclosure is None
    result = await responder.draft_reply(thread, incoming("Hallo, ist das noch da?"))
    assert result.ok
    assert not contains_disclosure(result.text)


async def test_ohne_assistenzmodus_wird_heikles_thema_blockiert(tmp_path, thread):
    body = BASE_CONFIG.replace("enabled: true", "enabled: false", 1)
    config = load_config(write_config(tmp_path, body), root=tmp_path)
    responder = Responder(config)
    result = await responder.draft_reply(thread, incoming("Was kostet das denn?"))
    assert result.blocked


# --- Freigabe-Modus: Entwuerfe auch fuer heikle Themen ---------------------

REVIEW_CONFIG = BASE_CONFIG.replace("enabled: true", "enabled: false", 1).replace(
    "require_approval: false", "require_approval: true"
)


async def test_heikles_thema_erzeugt_entwurf_mit_warnung(tmp_path, thread):
    """Wer jede Nachricht selbst freigibt, will auch fuer Preisfragen einen
    Vorschlag sehen - aber deutlich markiert."""
    config = load_config(write_config(tmp_path, REVIEW_CONFIG), root=tmp_path)
    assert config.replies.draft_sensitive_topics

    responder = Responder(config)
    result = await responder.draft_reply(thread, incoming("Was kostet das denn?"))

    assert result.ok, "mit Freigabe soll ein Entwurf entstehen"
    assert result.warning
    assert "Geld und Preise" in result.warning
    assert not contains_disclosure(result.text), "kein KI-Hinweis im Freigabe-Modus"


async def test_harte_blocker_erzeugen_nie_einen_entwurf(tmp_path, thread):
    """Auch mit Freigabe: hier soll kein fertiger Text zum Durchwinken liegen."""
    config = load_config(write_config(tmp_path, REVIEW_CONFIG), root=tmp_path)
    responder = Responder(config)
    result = await responder.draft_reply(thread, incoming("Suchst du auch Leute unter 18?"))

    assert result.blocked
    assert not result.text


async def test_abschaltbar(tmp_path, thread):
    body = REVIEW_CONFIG.replace(
        "  require_approval: true", "  require_approval: true\n  draft_sensitive_topics: false"
    )
    config = load_config(write_config(tmp_path, body), root=tmp_path)
    responder = Responder(config)
    result = await responder.draft_reply(thread, incoming("Was kostet das denn?"))
    assert result.blocked


async def test_ohne_freigabe_kein_entwurf_zu_heiklen_themen(tmp_path, thread):
    """Vollautomatik ohne Assistenzmodus: heikle Themen bleiben blockiert."""
    body = BASE_CONFIG.replace("enabled: true", "enabled: false", 1)
    config = load_config(write_config(tmp_path, body), root=tmp_path)
    assert not config.replies.require_approval
    responder = Responder(config)
    result = await responder.draft_reply(thread, incoming("Wie ist deine Adresse?"))
    assert result.blocked
