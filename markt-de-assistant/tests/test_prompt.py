import pytest

from marktbot.ai.prompt import build_system_prompt, build_turns, clean_reply
from marktbot.config import PersonaConfig, RepliesConfig
from marktbot.models import Direction, Message, Thread


@pytest.fixture
def persona():
    return PersonaConfig(
        display_name="Alex",
        description="Locker und kurz.",
        rules=["Antworte auf Deutsch.", "Maximal 3 Sätze."],
        handover_topics=["Preisverhandlung"],
    )


@pytest.fixture
def replies():
    return RepliesConfig(disclosure="")


def test_systemprompt_enthaelt_persona(persona):
    prompt = build_system_prompt(persona)
    assert "Alex" in prompt
    assert "Locker und kurz." in prompt
    assert "Maximal 3 Sätze." in prompt
    assert "Preisverhandlung" in prompt


def test_turns_enthalten_verlauf(persona):
    thread = Thread(thread_id="t1", partner_name="Chris", ad_title="Meine Anzeige")
    history = [
        Message(thread_id="t1", direction=Direction.INCOMING, body="Hallo"),
        Message(thread_id="t1", direction=Direction.OUTGOING, body="Hi zurück"),
        Message(thread_id="t1", direction=Direction.INCOMING, body="Bist du da?"),
    ]
    turns = build_turns(persona, thread, history)

    assert len(turns) == 2
    assert turns[0].role == "system"
    context = turns[1].content
    assert "Chris" in context
    assert "Er/Sie: Hallo" in context
    assert "Ich: Hi zurück" in context


def test_verlauf_wird_gekuerzt(persona):
    thread = Thread(thread_id="t1")
    history = [
        Message(thread_id="t1", direction=Direction.INCOMING, body=f"Nachricht {i}")
        for i in range(30)
    ]
    context = build_turns(persona, thread, history, max_history=5)[1].content
    assert "Nachricht 29" in context
    assert "Nachricht 10" not in context


# --- Nachbearbeitung -------------------------------------------------------

@pytest.mark.parametrize("raw,expected", [
    ('"Hi, alles klar!"', "Hi, alles klar!"),
    ("Antwort: Hi, alles klar!", "Hi, alles klar!"),
    ("Ich: Hi, alles klar!", "Hi, alles klar!"),
    ("<think>Überlegung</think>Hi, alles klar!", "Hi, alles klar!"),
    ("  Hi, alles klar!  ", "Hi, alles klar!"),
])
def test_modell_artefakte_werden_entfernt(raw, expected, replies):
    assert clean_reply(raw, replies) == expected


def test_zu_langer_text_wird_an_satzgrenze_gekuerzt(replies):
    text = "Erster Satz. " * 100
    result = clean_reply(text, replies, max_chars=100)
    assert len(result) <= 100
    assert result.endswith(".")


def test_hinweis_wird_angehaengt():
    replies = RepliesConfig(disclosure="(automatische Antwort)")
    result = clean_reply("Hallo!", replies)
    assert result.endswith("(automatische Antwort)")


def test_hinweis_wird_nicht_doppelt_angehaengt():
    replies = RepliesConfig(disclosure="(automatisch)")
    once = clean_reply("Hallo!", replies)
    twice = clean_reply(once, replies)
    assert twice.count("(automatisch)") == 1


def test_leerzeilen_werden_zusammengefasst(replies):
    assert clean_reply("A\n\n\n\n\nB", replies) == "A\n\nB"
