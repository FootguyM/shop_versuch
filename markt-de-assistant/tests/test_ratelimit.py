from datetime import time as dtime
from datetime import timedelta

import pytest

from marktbot.config import LimitsConfig, QuietHours, ScheduleConfig
from marktbot.core.ratelimit import ACTION_REPLY, RateLimiter
from marktbot.models import utcnow
from marktbot.storage import Storage


@pytest.fixture
def store(tmp_path):
    storage = Storage(tmp_path / "limits.db")
    yield storage
    storage.close()


def make_schedule(**limit_kwargs) -> ScheduleConfig:
    return ScheduleConfig(
        quiet_hours=QuietHours(enabled=False),
        limits=LimitsConfig(**{
            "replies_per_hour": 5,
            "replies_per_day": 10,
            "ads_per_day": 2,
            "min_seconds_between_replies": 0,
            **limit_kwargs,
        }),
    )


def test_leeres_konto_darf_senden(store):
    limiter = RateLimiter(store, make_schedule())
    assert limiter.can_send_reply().allowed


def test_stundenlimit_greift(store):
    limiter = RateLimiter(store, make_schedule(replies_per_hour=2))
    for _ in range(2):
        store.log_action(ACTION_REPLY)
    decision = limiter.can_send_reply()
    assert not decision.allowed
    assert "Stundenlimit" in decision.reason


def test_tageslimit_greift(store):
    limiter = RateLimiter(store, make_schedule(replies_per_hour=100, replies_per_day=3))
    for _ in range(3):
        store.log_action(ACTION_REPLY)
    decision = limiter.can_send_reply()
    assert not decision.allowed
    assert "Tageslimit" in decision.reason


def test_mindestabstand_greift(store):
    limiter = RateLimiter(store, make_schedule(min_seconds_between_replies=300))
    store.log_action(ACTION_REPLY)
    decision = limiter.can_send_reply()
    assert not decision.allowed
    assert "Mindestabstand" in decision.reason
    assert decision.retry_after is not None


def test_fehlgeschlagene_versuche_zaehlen_nicht_gegen_das_limit(store):
    limiter = RateLimiter(store, make_schedule(replies_per_hour=2))
    for _ in range(5):
        store.log_action(ACTION_REPLY, ok=False)
    assert limiter.can_send_reply().allowed


def test_alte_eintraege_fallen_aus_dem_stundenfenster(store):
    limiter = RateLimiter(store, make_schedule(replies_per_hour=1))
    store.log_action(ACTION_REPLY)
    assert not limiter.can_send_reply().allowed
    # Eintrag kuenstlich altern lassen
    with store._lock:  # noqa: SLF001 - Testzugriff auf die Verbindung
        store._conn.execute(
            "UPDATE actions SET created_at = ?",
            ((utcnow() - timedelta(hours=2)).isoformat(),),
        )
        store._conn.commit()
    assert limiter.can_send_reply().allowed


# --- Ruhezeiten ------------------------------------------------------------

@pytest.mark.parametrize("moment,expected", [
    (dtime(23, 45), True),
    (dtime(2, 0), True),
    (dtime(7, 0), True),
    (dtime(7, 30), False),
    (dtime(12, 0), False),
    (dtime(23, 29), False),
])
def test_ruhezeit_ueber_mitternacht(moment, expected):
    quiet = QuietHours(enabled=True, start=dtime(23, 30), end=dtime(7, 30))
    assert quiet.contains(moment) is expected


@pytest.mark.parametrize("moment,expected", [
    (dtime(9, 0), False),
    (dtime(13, 0), True),
    (dtime(14, 59), True),
    (dtime(15, 0), False),
])
def test_ruhezeit_innerhalb_eines_tages(moment, expected):
    quiet = QuietHours(enabled=True, start=dtime(13, 0), end=dtime(15, 0))
    assert quiet.contains(moment) is expected


def test_abgeschaltete_ruhezeit_ist_nie_aktiv():
    quiet = QuietHours(enabled=False, start=dtime(0, 0), end=dtime(23, 59))
    assert quiet.contains(dtime(12, 0)) is False


def test_ruhezeit_blockt_das_senden(store):
    schedule = make_schedule()
    schedule.quiet_hours = QuietHours(enabled=True, start=dtime(0, 0), end=dtime(23, 59))
    limiter = RateLimiter(store, schedule)
    decision = limiter.can_send_reply()
    assert not decision.allowed
    assert "Ruhezeit" in decision.reason
