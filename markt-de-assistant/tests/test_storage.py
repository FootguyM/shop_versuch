from datetime import timedelta

import pytest

from marktbot.models import Direction, Draft, DraftStatus, Message, Thread, utcnow
from marktbot.storage import Storage


@pytest.fixture
def store(tmp_path):
    storage = Storage(tmp_path / "test.db")
    yield storage
    storage.close()


@pytest.fixture
def thread(store):
    thread = Thread(thread_id="abc123", partner_name="Testkontakt", url="https://example.com/t/1")
    store.upsert_thread(thread)
    return thread


def test_thread_speichern_und_lesen(store, thread):
    loaded = store.get_thread("abc123")
    assert loaded is not None
    assert loaded.partner_name == "Testkontakt"


def test_upsert_ueberschreibt_nicht_die_flags(store, thread):
    store.set_thread_flags("abc123", muted=True)
    store.upsert_thread(Thread(thread_id="abc123", partner_name="Neuer Name"))
    loaded = store.get_thread("abc123")
    assert loaded.partner_name == "Neuer Name"
    assert loaded.muted is True, "muted darf durch einen Postfach-Abruf nicht verloren gehen"


def test_gleiche_nachricht_landet_nur_einmal(store, thread):
    message = Message(thread_id="abc123", direction=Direction.INCOMING, body="Hallo du")
    first = store.add_message(message)
    second = store.add_message(
        Message(thread_id="abc123", direction=Direction.INCOMING, body="Hallo du")
    )
    assert first is not None
    assert second is None, "Duplikat haette ignoriert werden muessen"
    assert len(store.get_history("abc123")) == 1


def test_unterschiedliche_richtung_ist_kein_duplikat(store, thread):
    store.add_message(Message(thread_id="abc123", direction=Direction.INCOMING, body="Hallo"))
    store.add_message(Message(thread_id="abc123", direction=Direction.OUTGOING, body="Hallo"))
    assert len(store.get_history("abc123")) == 2


def test_externe_id_gewinnt_gegen_gleichen_text(store, thread):
    store.add_message(Message(
        thread_id="abc123", direction=Direction.INCOMING, body="Hi", external_id="m1"
    ))
    store.add_message(Message(
        thread_id="abc123", direction=Direction.INCOMING, body="Hi", external_id="m2"
    ))
    assert len(store.get_history("abc123")) == 2


def test_verlauf_kommt_chronologisch(store, thread):
    now = utcnow()
    for index in range(5):
        store.add_message(Message(
            thread_id="abc123",
            direction=Direction.INCOMING,
            body=f"Nachricht {index}",
            sent_at=now + timedelta(minutes=index),
        ))
    history = store.get_history("abc123")
    assert [m.body for m in history] == [f"Nachricht {i}" for i in range(5)]


def test_nachrichtenzaehler_waechst(store, thread):
    store.add_message(Message(thread_id="abc123", direction=Direction.INCOMING, body="eins"))
    store.add_message(Message(thread_id="abc123", direction=Direction.INCOMING, body="zwei"))
    assert store.get_thread("abc123").message_count == 2


# --- Entwürfe --------------------------------------------------------------

def test_entwurf_lebenszyklus(store, thread):
    draft_id = store.add_draft(Draft(thread_id="abc123", text="Ein Entwurf"))
    assert store.has_open_draft("abc123")

    store.update_draft(draft_id, status=DraftStatus.SENT)
    assert not store.has_open_draft("abc123")

    loaded = store.get_draft(draft_id)
    assert loaded.status is DraftStatus.SENT
    assert loaded.decided_at is not None


def test_abgelaufene_entwuerfe_werden_verworfen(store, thread):
    old = Draft(thread_id="abc123", text="alt", created_at=utcnow() - timedelta(hours=48))
    fresh = Draft(thread_id="abc123", text="neu")
    store.add_draft(old)
    store.add_draft(fresh)

    assert store.expire_stale_drafts(ttl_hours=12) == 1
    assert len(store.list_drafts(DraftStatus.PENDING)) == 1


def test_entwurf_bearbeiten(store, thread):
    draft_id = store.add_draft(Draft(thread_id="abc123", text="original"))
    store.update_draft(draft_id, text="geaendert")
    assert store.get_draft(draft_id).text == "geaendert"


# --- Aktionen --------------------------------------------------------------

def test_aktionen_zaehlen(store):
    for _ in range(3):
        store.log_action("reply_sent", "abc123", "text")
    store.log_action("reply_sent", "abc123", "fehler", ok=False)

    since = utcnow() - timedelta(hours=1)
    assert store.count_actions_since("reply_sent", since) == 3
    assert store.count_actions_since("reply_sent", since, only_ok=False) == 4
    assert store.count_actions_since("reply_sent", utcnow() + timedelta(minutes=1)) == 0


def test_letzte_aktion(store):
    assert store.last_action_at("reply_sent") is None
    store.log_action("reply_sent", "abc123")
    assert store.last_action_at("reply_sent") is not None


def test_kv_speicher(store):
    assert store.get_value("fehlt", "standard") == "standard"
    store.set_value("zahl", 42)
    store.set_value("liste", [1, 2, 3])
    assert store.get_value("zahl") == 42
    assert store.get_value("liste") == [1, 2, 3]
