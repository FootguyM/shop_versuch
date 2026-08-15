"""Bandbreitenfilter. Relevant, weil Residential-Proxys pro Gigabyte
abrechnen - und weil ein zu scharfer Filter Captchas unsichtbar macht."""

from dataclasses import dataclass

import pytest

from marktbot.browser.blocking import (
    DEFAULT_BLOCKED_TYPES,
    ResourceBlocker,
)


@dataclass
class FakeRequest:
    url: str
    resource_type: str


class FakeRoute:
    """Minimaler Ersatz fuer playwright.Route."""

    def __init__(self, url: str, resource_type: str) -> None:
        self.request = FakeRequest(url, resource_type)
        self.action: str | None = None

    async def continue_(self) -> None:
        self.action = "continue"

    async def abort(self) -> None:
        self.action = "abort"


async def run(blocker: ResourceBlocker, url: str, resource_type: str) -> str:
    route = FakeRoute(url, resource_type)
    await blocker.handle(route)
    return route.action


@pytest.fixture
def blocker():
    return ResourceBlocker()


# --- Was geblockt wird -----------------------------------------------------

@pytest.mark.parametrize("resource_type", DEFAULT_BLOCKED_TYPES)
async def test_schwere_ressourcen_werden_geblockt(blocker, resource_type):
    assert await run(blocker, "https://www.markt.de/x", resource_type) == "abort"


@pytest.mark.parametrize("resource_type", ["document", "script", "xhr", "fetch"])
async def test_inhalt_kommt_durch(blocker, resource_type):
    assert await run(blocker, "https://www.markt.de/postfach/", resource_type) == "continue"


async def test_stylesheets_kommen_standardmaessig_durch(blocker):
    """Ohne CSS wird Playwrights Sichtbarkeitspruefung unzuverlaessig."""
    assert await run(blocker, "https://www.markt.de/style.css", "stylesheet") == "continue"


async def test_tracker_werden_geblockt(blocker):
    assert await run(blocker, "https://www.google-analytics.com/collect", "script") == "abort"
    assert await run(blocker, "https://connect.facebook.net/sdk.js", "script") == "abort"


async def test_eigene_domainliste_ersetzt_die_standardliste():
    blocker = ResourceBlocker(blocked_domains=["boese.example"])
    assert await run(blocker, "https://boese.example/x.js", "script") == "abort"
    assert await run(blocker, "https://www.google-analytics.com/c", "script") == "continue"


# --- Was nie geblockt wird -------------------------------------------------

@pytest.mark.parametrize("url", [
    "https://www.google.com/recaptcha/api2/anchor",
    "https://hcaptcha.com/challenge.png",
    "https://www.markt.de/captcha/image.png",
    "https://challenges.cloudflare.com/turnstile/v0/api.js",
    "https://www.markt.de/verifizierung/bild.jpg",
])
async def test_captcha_ressourcen_kommen_immer_durch(blocker, url):
    """Sonst bekommt man per Telegram einen Screenshot ohne Sicherheitsabfrage."""
    assert await run(blocker, url, "image") == "continue", url


# --- Schalter und Statistik ------------------------------------------------

async def test_abgeschalteter_filter_laesst_alles_durch():
    blocker = ResourceBlocker(enabled=False)
    assert await run(blocker, "https://www.markt.de/bild.jpg", "image") == "continue"
    assert blocker.stats.blocked == 0


async def test_leere_typenliste_blockt_keine_typen():
    blocker = ResourceBlocker(blocked_types=[])
    assert await run(blocker, "https://www.markt.de/bild.jpg", "image") == "continue"


async def test_unbekannte_typen_werden_verworfen():
    blocker = ResourceBlocker(blocked_types=["image", "quatsch"])
    assert blocker.blocked_types == {"image"}


async def test_statistik_zaehlt_richtig(blocker):
    for _ in range(3):
        await run(blocker, "https://www.markt.de/b.jpg", "image")
    await run(blocker, "https://www.google-analytics.com/c", "script")
    await run(blocker, "https://www.markt.de/postfach/", "document")

    assert blocker.stats.blocked == 4
    assert blocker.stats.allowed == 1
    assert blocker.stats.total == 5
    assert blocker.stats.blocked_share == pytest.approx(80.0)
    assert blocker.stats.per_type["image"] == 3
    assert "geblockt" in blocker.stats.summary()


async def test_statistik_ohne_requests(blocker):
    assert blocker.stats.blocked_share == 0.0
    assert "Noch keine" in blocker.stats.summary()
