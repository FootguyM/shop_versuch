""".env-Handling der Oberflaeche.

Die Datei enthaelt Zugangsdaten und die kommentierten Erklaerungen aus
.env.example. Ein Schreibvorgang, der Kommentare oder fremde Schluessel
verschluckt, faellt erst auf, wenn etwas nicht mehr geht.
"""

import pytest

from marktbot.ui.envfile import read_env, write_env


@pytest.fixture
def env_file(tmp_path):
    path = tmp_path / ".env"
    path.write_text(
        "# markt.de Zugangsdaten\n"
        "MARKT_USERNAME=alt@example.de\n"
        "MARKT_PASSWORD=altesgeheimnis\n"
        "\n"
        "# Telegram\n"
        "TELEGRAM_BOT_TOKEN=\n"
        "TELEGRAM_CHAT_ID=123\n",
        encoding="utf-8",
    )
    return path


# --- Lesen -----------------------------------------------------------------

def test_werte_lesen(env_file):
    values = read_env(env_file)
    assert values["MARKT_USERNAME"] == "alt@example.de"
    assert values["TELEGRAM_CHAT_ID"] == "123"
    assert values["TELEGRAM_BOT_TOKEN"] == ""


def test_kommentare_sind_keine_werte(env_file):
    assert not any(key.startswith("#") for key in read_env(env_file))


def test_fehlende_datei_ergibt_leeres_ergebnis(tmp_path):
    assert read_env(tmp_path / "gibtesnicht") == {}


def test_gleichheitszeichen_im_wert(tmp_path):
    path = tmp_path / ".env"
    path.write_text("PROXY_PASSWORD=ab=cd=ef\n", encoding="utf-8")
    assert read_env(path)["PROXY_PASSWORD"] == "ab=cd=ef"


# --- Schreiben -------------------------------------------------------------

def test_wert_wird_ersetzt(env_file):
    write_env(env_file, {"MARKT_USERNAME": "neu@example.de"})
    assert read_env(env_file)["MARKT_USERNAME"] == "neu@example.de"


def test_kommentare_bleiben_erhalten(env_file):
    write_env(env_file, {"MARKT_PASSWORD": "neu"})
    content = env_file.read_text(encoding="utf-8")
    assert "# markt.de Zugangsdaten" in content
    assert "# Telegram" in content


def test_andere_werte_bleiben_unangetastet(env_file):
    write_env(env_file, {"MARKT_USERNAME": "neu@example.de"})
    values = read_env(env_file)
    assert values["MARKT_PASSWORD"] == "altesgeheimnis"
    assert values["TELEGRAM_CHAT_ID"] == "123"


def test_neuer_schluessel_wird_angehaengt(env_file):
    write_env(env_file, {"HUGGINGFACE_TOKEN": "hf_xyz"})
    values = read_env(env_file)
    assert values["HUGGINGFACE_TOKEN"] == "hf_xyz"
    assert values["MARKT_USERNAME"] == "alt@example.de"


def test_leerer_wert_loescht_den_eintrag_nicht(env_file):
    write_env(env_file, {"MARKT_PASSWORD": ""})
    content = env_file.read_text(encoding="utf-8")
    assert "MARKT_PASSWORD=" in content
    assert read_env(env_file)["MARKT_PASSWORD"] == ""


def test_reihenfolge_bleibt_stabil(env_file):
    write_env(env_file, {"TELEGRAM_BOT_TOKEN": "abc"})
    keys = [
        line.split("=")[0]
        for line in env_file.read_text(encoding="utf-8").splitlines()
        if line and not line.startswith("#") and "=" in line
    ]
    assert keys == [
        "MARKT_USERNAME", "MARKT_PASSWORD", "TELEGRAM_BOT_TOKEN", "TELEGRAM_CHAT_ID"
    ]


def test_schreiben_ohne_vorhandene_datei(tmp_path):
    path = tmp_path / ".env"
    write_env(path, {"MARKT_USERNAME": "neu@example.de"})
    assert read_env(path) == {"MARKT_USERNAME": "neu@example.de"}


def test_mehrfaches_schreiben_dupliziert_nicht(env_file):
    for value in ("eins", "zwei", "drei"):
        write_env(env_file, {"TELEGRAM_BOT_TOKEN": value})
    content = env_file.read_text(encoding="utf-8")
    assert content.count("TELEGRAM_BOT_TOKEN=") == 1
    assert read_env(env_file)["TELEGRAM_BOT_TOKEN"] == "drei"


def test_umlaute_ueberleben(tmp_path):
    path = tmp_path / ".env"
    write_env(path, {"MARKT_PASSWORD": "Grüße&Küsse"})
    assert read_env(path)["MARKT_PASSWORD"] == "Grüße&Küsse"
