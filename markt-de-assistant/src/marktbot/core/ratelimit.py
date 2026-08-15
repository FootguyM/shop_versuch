"""Rate-Limits und Ruhezeiten.

Alle Zaehler kommen aus der actions-Tabelle. Damit ueberleben die Limits einen
Neustart des Prozesses - sonst koennte man das Tageslimit durch einen Restart
umgehen, was den Sinn der Sache zerstoert.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from ..config import ScheduleConfig
from ..models import utcnow
from ..storage import Storage

log = logging.getLogger(__name__)

ACTION_REPLY = "reply_sent"
ACTION_AD_CREATE = "ad_created"
ACTION_AD_RENEW = "ad_renewed"


@dataclass(slots=True)
class LimitDecision:
    allowed: bool
    reason: str = ""
    retry_after: timedelta | None = None

    @classmethod
    def yes(cls) -> LimitDecision:
        return cls(allowed=True)

    @classmethod
    def no(cls, reason: str, retry_after: timedelta | None = None) -> LimitDecision:
        return cls(allowed=False, reason=reason, retry_after=retry_after)


class RateLimiter:
    def __init__(
        self,
        storage: Storage,
        schedule: ScheduleConfig,
        timezone: str = "Europe/Berlin",
    ) -> None:
        self.storage = storage
        self.schedule = schedule
        self.tz = ZoneInfo(timezone)

    # -- Ruhezeiten ---------------------------------------------------------

    def local_now(self) -> datetime:
        return utcnow().astimezone(self.tz)

    def in_quiet_hours(self, moment: datetime | None = None) -> bool:
        local = (moment or utcnow()).astimezone(self.tz)
        return self.schedule.quiet_hours.contains(local.time())

    def seconds_until_quiet_end(self) -> float:
        """Wie lange noch bis zum Ende der Ruhezeit."""
        quiet = self.schedule.quiet_hours
        local = self.local_now()
        end_today = local.replace(
            hour=quiet.end.hour, minute=quiet.end.minute, second=0, microsecond=0
        )
        if end_today <= local:
            end_today += timedelta(days=1)
        return (end_today - local).total_seconds()

    # -- Limits -------------------------------------------------------------

    def can_send_reply(self) -> LimitDecision:
        limits = self.schedule.limits
        now = utcnow()

        if self.in_quiet_hours(now):
            wait = timedelta(seconds=self.seconds_until_quiet_end())
            return LimitDecision.no(
                f"Ruhezeit ({self.schedule.quiet_hours.start:%H:%M}-"
                f"{self.schedule.quiet_hours.end:%H:%M} Uhr).",
                wait,
            )

        last = self.storage.last_action_at(ACTION_REPLY)
        if last is not None:
            elapsed = (now - last).total_seconds()
            gap = limits.min_seconds_between_replies
            if elapsed < gap:
                return LimitDecision.no(
                    f"Mindestabstand zwischen zwei Antworten noch nicht erreicht "
                    f"({int(elapsed)}s von {gap}s).",
                    timedelta(seconds=gap - elapsed),
                )

        hourly = self.storage.count_actions_since(ACTION_REPLY, now - timedelta(hours=1))
        if hourly >= limits.replies_per_hour:
            return LimitDecision.no(
                f"Stundenlimit erreicht ({hourly}/{limits.replies_per_hour}).",
                timedelta(hours=1),
            )

        daily = self.storage.count_actions_since(ACTION_REPLY, self._day_start())
        if daily >= limits.replies_per_day:
            return LimitDecision.no(
                f"Tageslimit erreicht ({daily}/{limits.replies_per_day}).",
                timedelta(seconds=self._seconds_until_midnight()),
            )

        return LimitDecision.yes()

    def can_create_ad(self) -> LimitDecision:
        limits = self.schedule.limits
        if self.in_quiet_hours():
            return LimitDecision.no(
                "Ruhezeit - Anzeigen werden nicht mitten in der Nacht geschaltet.",
                timedelta(seconds=self.seconds_until_quiet_end()),
            )
        today = self.storage.count_actions_since(ACTION_AD_CREATE, self._day_start())
        if today >= limits.ads_per_day:
            return LimitDecision.no(
                f"Tageslimit fuer neue Anzeigen erreicht ({today}/{limits.ads_per_day}).",
                timedelta(seconds=self._seconds_until_midnight()),
            )
        return LimitDecision.yes()

    # -- Zaehlerstaende -----------------------------------------------------

    def replies_today(self) -> int:
        return self.storage.count_actions_since(ACTION_REPLY, self._day_start())

    def replies_last_hour(self) -> int:
        return self.storage.count_actions_since(ACTION_REPLY, utcnow() - timedelta(hours=1))

    def usage_summary(self) -> str:
        limits = self.schedule.limits
        return (
            f"Antworten heute: {self.replies_today()}/{limits.replies_per_day} | "
            f"letzte Stunde: {self.replies_last_hour()}/{limits.replies_per_hour}"
        )

    # -- Intern -------------------------------------------------------------

    def _day_start(self) -> datetime:
        """Mitternacht lokaler Zeit, als UTC-Zeitpunkt."""
        local = self.local_now()
        midnight = local.replace(hour=0, minute=0, second=0, microsecond=0)
        return midnight.astimezone(utcnow().tzinfo)

    def _seconds_until_midnight(self) -> float:
        local = self.local_now()
        tomorrow = (local + timedelta(days=1)).replace(
            hour=0, minute=0, second=0, microsecond=0
        )
        return (tomorrow - local).total_seconds()
