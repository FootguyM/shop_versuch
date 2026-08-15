"""Request-Filter zum Sparen von Bandbreite.

Der Grund ist handfest: Residential-Proxys rechnen pro Gigabyte ab, und
Playwright laedt standardmaessig die komplette Seite - Bilder, Videos, Fonts,
Werbe- und Trackingskripte. Ein einzelner Postfach-Aufruf kann so zweistellige
Megabyte kosten, obwohl der Bot nur ein paar Zeilen Text braucht. Bei ein paar
hundert Abrufen am Tag uebersteigen die Proxy-Kosten schnell die Serverkosten.

Geblockt werden deshalb Bilder, Videos, Fonts und bekannte Tracker. Das spart
in der Praxis den Grossteil des Volumens.

Zwei Dinge bleiben bewusst erlaubt:

  - Stylesheets. Playwright entscheidet ueber `state="visible"` anhand des
    tatsaechlichen Layouts. Ohne CSS aendert sich Sichtbarkeit und Groesse von
    Elementen, und Selektoren fangen an, sprunghaft zu versagen. Die paar
    Kilobyte sind den Aerger nicht wert.
  - Alles, was nach Captcha aussieht. Wenn markt.de eine Sicherheitsabfrage
    zeigt, muss das Bild geladen werden - sonst bekommst du per Telegram einen
    Screenshot, auf dem nichts zu sehen ist.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:  # nur fuer die Typpruefung - der Filter kommt ohne
    from playwright.async_api import Route  # Playwright zur Laufzeit aus

log = logging.getLogger(__name__)

# Ressourcentypen, die Playwright unterscheidet und die wir blocken koennen.
BLOCKABLE_TYPES = {
    "image", "media", "font", "stylesheet", "websocket", "manifest", "other",
}

DEFAULT_BLOCKED_TYPES = ["image", "media", "font"]

# Reine Bandbreitenverschwendung - Tracking, Werbung, Fremdanalytik.
DEFAULT_BLOCKED_DOMAINS = [
    "google-analytics.com",
    "googletagmanager.com",
    "googlesyndication.com",
    "doubleclick.net",
    "facebook.net",
    "facebook.com/tr",
    "connect.facebook.net",
    "hotjar.com",
    "criteo.com",
    "taboola.com",
    "outbrain.com",
    "adnxs.com",
    "scorecardresearch.com",
    "cloudflareinsights.com",
    "sentry.io",
    "bugsnag.com",
    "newrelic.com",
]

# Wird nie geblockt, egal was sonst konfiguriert ist.
ALWAYS_ALLOW = re.compile(
    r"(captcha|recaptcha|hcaptcha|turnstile|challenge|verif)",
    re.IGNORECASE,
)


@dataclass(slots=True)
class BlockStats:
    """Mitschrift, wie viel der Filter tatsaechlich bringt."""

    allowed: int = 0
    blocked_by_type: int = 0
    blocked_by_domain: int = 0
    per_type: dict[str, int] = field(default_factory=dict)

    @property
    def blocked(self) -> int:
        return self.blocked_by_type + self.blocked_by_domain

    @property
    def total(self) -> int:
        return self.allowed + self.blocked

    @property
    def blocked_share(self) -> float:
        return (self.blocked / self.total * 100) if self.total else 0.0

    def summary(self) -> str:
        if not self.total:
            return "Noch keine Requests."
        details = ", ".join(
            f"{name}: {count}" for name, count in sorted(
                self.per_type.items(), key=lambda item: -item[1]
            )
        )
        return (
            f"{self.blocked} von {self.total} Requests geblockt "
            f"({self.blocked_share:.0f} %)" + (f" - {details}" if details else "")
        )

    def reset(self) -> None:
        self.allowed = 0
        self.blocked_by_type = 0
        self.blocked_by_domain = 0
        self.per_type.clear()


class ResourceBlocker:
    def __init__(
        self,
        blocked_types: list[str] | None = None,
        blocked_domains: list[str] | None = None,
        enabled: bool = True,
    ) -> None:
        self.enabled = enabled
        types = blocked_types if blocked_types is not None else DEFAULT_BLOCKED_TYPES
        unknown = set(types) - BLOCKABLE_TYPES
        if unknown:
            log.warning(
                "Unbekannte Ressourcentypen in browser.blocked_resource_types: %s. "
                "Erlaubt sind: %s",
                ", ".join(sorted(unknown)),
                ", ".join(sorted(BLOCKABLE_TYPES)),
            )
        self.blocked_types = set(types) & BLOCKABLE_TYPES
        self.blocked_domains = [
            d.lower() for d in (
                blocked_domains if blocked_domains is not None else DEFAULT_BLOCKED_DOMAINS
            )
        ]
        self.stats = BlockStats()

        if "stylesheet" in self.blocked_types:
            log.warning(
                "browser.blocked_resource_types blockt 'stylesheet'. Das spart wenig "
                "Bandbreite, kann aber die Sichtbarkeitspruefung von Elementen "
                "durcheinanderbringen. Im Zweifel wieder herausnehmen."
            )

    async def handle(self, route: Route) -> None:
        """Route-Handler fuer Playwright."""
        request = route.request

        if not self.enabled:
            self.stats.allowed += 1
            await route.continue_()
            return

        url = request.url

        # Sicherheitsabfragen muessen immer durch.
        if ALWAYS_ALLOW.search(url):
            self.stats.allowed += 1
            await route.continue_()
            return

        if request.resource_type in self.blocked_types:
            self.stats.blocked_by_type += 1
            self.stats.per_type[request.resource_type] = (
                self.stats.per_type.get(request.resource_type, 0) + 1
            )
            await route.abort()
            return

        lowered = url.lower()
        if any(domain in lowered for domain in self.blocked_domains):
            self.stats.blocked_by_domain += 1
            self.stats.per_type["tracker"] = self.stats.per_type.get("tracker", 0) + 1
            await route.abort()
            return

        self.stats.allowed += 1
        await route.continue_()
