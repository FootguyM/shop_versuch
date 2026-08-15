"""Anzeigen anlegen, auflisten, hochschieben, pausieren, loeschen."""

from __future__ import annotations

import logging
import re
from pathlib import Path
from urllib.parse import urljoin, urlparse

import yaml
from playwright.async_api import Locator

from ..browser.humanize import Humanizer
from ..browser.session import BrowserSession
from ..models import Ad, AdStatus, AdTemplate, utcnow
from .auth import BASE_URL
from .selectors import SelectorNotFound, Selectors

log = logging.getLogger(__name__)

MY_ADS_URL = f"{BASE_URL}/meins/anzeigen/"
NEW_AD_URL = f"{BASE_URL}/anzeige-aufgeben/"

_STATUS_WORDS = {
    "aktiv": AdStatus.ACTIVE,
    "online": AdStatus.ACTIVE,
    "veroeffentlicht": AdStatus.ACTIVE,
    "veröffentlicht": AdStatus.ACTIVE,
    "pausiert": AdStatus.PAUSED,
    "deaktiviert": AdStatus.PAUSED,
    "inaktiv": AdStatus.PAUSED,
    "abgelaufen": AdStatus.EXPIRED,
    "beendet": AdStatus.EXPIRED,
    "entwurf": AdStatus.DRAFT,
}


class AdError(RuntimeError):
    pass


def _ad_id_from_url(url: str) -> str:
    path = urlparse(url).path
    match = re.search(r"(\d{6,})", path)
    if match:
        return match.group(1)
    segments = [seg for seg in path.split("/") if seg]
    return segments[-1] if segments else url


def _parse_status(text: str) -> AdStatus:
    lowered = text.lower()
    for word, status in _STATUS_WORDS.items():
        if word in lowered:
            return status
    return AdStatus.UNKNOWN


def load_templates(directory: str | Path) -> dict[str, AdTemplate]:
    """Alle ads/*.yaml als Vorlagen einlesen."""
    directory = Path(directory)
    templates: dict[str, AdTemplate] = {}
    if not directory.exists():
        return templates
    for path in sorted(directory.glob("*.y*ml")):
        try:
            with path.open("r", encoding="utf-8") as handle:
                data = yaml.safe_load(handle) or {}
            if not isinstance(data, dict):
                log.warning("Vorlage %s ignoriert: kein YAML-Mapping.", path.name)
                continue
            templates[path.stem] = AdTemplate.from_dict(path.stem, data)
        except (ValueError, yaml.YAMLError) as exc:
            log.warning("Vorlage %s ignoriert: %s", path.name, exc)
    return templates


class AdManager:
    def __init__(
        self,
        session: BrowserSession,
        selectors: Selectors,
        humanizer: Humanizer,
        template_dir: str | Path = "ads",
    ) -> None:
        self.session = session
        self.selectors = selectors
        self.humanizer = humanizer
        self.template_dir = Path(template_dir)

    # -- Lesen --------------------------------------------------------------

    async def list_ads(self) -> list[Ad]:
        page = await self.session.goto(MY_ADS_URL)
        await self.humanizer.pause()
        await self.humanizer.browse_page(page)

        items = await self.selectors.find_all(page, "ads_list_item")
        if not items:
            dump = await self.session.dump_html("anzeigen-leer")
            log.warning("Keine Anzeigen erkannt. HTML-Dump: %s", dump)
            return []

        ads: list[Ad] = []
        for item in items:
            ad = await self._parse_ad_item(item)
            if ad:
                ads.append(ad)
        log.info("%d Anzeigen im Account gefunden.", len(ads))
        return ads

    async def _parse_ad_item(self, item: Locator) -> Ad | None:
        try:
            href = await item.get_attribute("href")
            if not href:
                link = item.locator("a[href]").first
                href = await link.get_attribute("href") if await link.count() else None
            url = urljoin(BASE_URL, href) if href else ""

            title = ""
            for candidate in self.selectors.candidates("ad_title"):
                node = item.locator(candidate).first
                if await node.count():
                    title = (await node.inner_text()).strip()
                    if title:
                        break
            if not title:
                lines = [ln.strip() for ln in (await item.inner_text()).splitlines() if ln.strip()]
                title = lines[0] if lines else "(ohne Titel)"

            status_text = ""
            for candidate in self.selectors.candidates("ad_status"):
                node = item.locator(candidate).first
                if await node.count():
                    status_text = (await node.inner_text()).strip()
                    break

            views = 0
            for candidate in self.selectors.candidates("ad_views"):
                node = item.locator(candidate).first
                if await node.count():
                    match = re.search(r"\d+", await node.inner_text())
                    if match:
                        views = int(match.group())
                    break

            return Ad(
                ad_id=_ad_id_from_url(url) if url else title[:40],
                title=title,
                url=url,
                status=_parse_status(status_text),
                views=views,
            )
        except Exception as exc:  # noqa: BLE001
            log.debug("Anzeigeneintrag nicht lesbar: %s", exc)
            return None

    # -- Schreiben ----------------------------------------------------------

    async def create_ad(self, template: AdTemplate) -> Ad:
        """Neue Anzeige aus einer Vorlage aufgeben.

        Der Formularaufbau bei markt.de haengt an der Kategorie und ist
        mehrstufig. Diese Methode fuellt die Standardfelder und laesst das
        Formular auf der letzten Seite stehen, wenn ein Schritt unklar ist -
        dann kommt ein Screenshot per Telegram und du klickst zu Ende.
        """
        page = await self.session.goto(NEW_AD_URL)
        await self.humanizer.pause((1.0, 2.5))

        title_field = await self.selectors.find(page, "new_ad_title", timeout=10000, required=False)
        if title_field is None:
            shot = await self.session.screenshot("anzeige-kategorie")
            raise AdError(
                "Auf der Seite 'Anzeige aufgeben' ist noch kein Titelfeld sichtbar - "
                "vermutlich muss zuerst eine Kategorie gewaehlt werden. "
                f"Screenshot: {shot}. Kategorie einmal von Hand waehlen, dann greift "
                "die Vorlage beim naechsten Mal."
            )

        await self.humanizer.type_text(title_field, template.title)
        await self.humanizer.pause()

        description_field = await self.selectors.find(page, "new_ad_description", required=False)
        if description_field is not None:
            await self.humanizer.type_text(description_field, template.description)
            await self.humanizer.pause()

        if template.price:
            price_field = await self.selectors.find(page, "new_ad_price", required=False)
            if price_field is not None:
                await self.humanizer.type_text(price_field, template.price)

        if template.postal_code:
            zip_field = await self.selectors.find(page, "new_ad_postal_code", required=False)
            if zip_field is not None:
                await self.humanizer.type_text(zip_field, template.postal_code)

        if template.images:
            await self._upload_images(template.images)

        await self.humanizer.pause_before_submit()
        submit = await self.selectors.find(page, "new_ad_submit", required=False)
        if submit is None:
            shot = await self.session.screenshot("anzeige-kein-absenden")
            raise AdError(
                f"Absende-Button nicht gefunden. Formular ist ausgefuellt und offen. "
                f"Screenshot: {shot}"
            )
        await self.humanizer.click(submit)
        await self.humanizer.pause((2.0, 4.0))

        url = await self.session.current_url()
        ad = Ad(
            ad_id=_ad_id_from_url(url),
            title=template.title,
            description=template.description,
            category=template.category,
            price=template.price,
            location=template.location,
            url=url,
            status=AdStatus.ACTIVE,
            created_at=utcnow(),
            images=list(template.images),
        )
        log.info("Anzeige '%s' aufgegeben (%s).", ad.title, ad.url)
        return ad

    async def _upload_images(self, images: list[str]) -> None:
        page = await self.session.page()
        existing = [str(Path(img)) for img in images if Path(img).exists()]
        missing = [img for img in images if not Path(img).exists()]
        if missing:
            log.warning("Bilder nicht gefunden und uebersprungen: %s", ", ".join(missing))
        if not existing:
            return
        file_input = await self.selectors.find(page, "new_ad_image_input", required=False)
        if file_input is None:
            log.warning("Kein Datei-Upload-Feld gefunden, Bilder uebersprungen.")
            return
        await file_input.set_input_files(existing)
        await self.humanizer.pause((2.0, 5.0))
        log.info("%d Bild(er) hochgeladen.", len(existing))

    async def renew_ad(self, ad: Ad) -> bool:
        """Anzeige hochschieben / erneuern."""
        return await self._ad_action(ad, "ad_renew_button", "hochgeschoben", confirm=True)

    async def pause_ad(self, ad: Ad) -> bool:
        return await self._ad_action(ad, "ad_deactivate_button", "pausiert", confirm=True)

    async def delete_ad(self, ad: Ad) -> bool:
        return await self._ad_action(ad, "ad_delete_button", "geloescht", confirm=True)

    async def _ad_action(self, ad: Ad, selector_key: str, verb: str, confirm: bool) -> bool:
        target = ad.url or MY_ADS_URL
        page = await self.session.goto(target)
        await self.humanizer.pause()

        try:
            button = await self.selectors.find(page, selector_key, timeout=8000)
        except SelectorNotFound as exc:
            shot = await self.session.screenshot(f"aktion-{selector_key}")
            raise AdError(
                f"Aktion '{verb}' fuer Anzeige {ad.ad_id} nicht moeglich: {exc} "
                f"Screenshot: {shot}"
            ) from exc

        await self.humanizer.click(button)
        await self.humanizer.pause((0.8, 2.0))

        if confirm:
            confirm_button = await self.selectors.find(
                page, "confirm_button", timeout=4000, required=False
            )
            if confirm_button is not None:
                await self.humanizer.click(confirm_button)
                await self.humanizer.pause((1.0, 2.5))

        log.info("Anzeige %s (%s) %s.", ad.ad_id, ad.title, verb)
        return True

    async def edit_ad(self, ad: Ad, *, title: str | None = None, description: str | None = None) -> bool:
        """Titel und/oder Beschreibung einer bestehenden Anzeige aendern."""
        if title is None and description is None:
            raise AdError("Nichts zu aendern - weder Titel noch Beschreibung angegeben.")

        page = await self.session.goto(ad.url or MY_ADS_URL)
        await self.humanizer.pause()

        edit_button = await self.selectors.find(page, "ad_edit_button", timeout=8000, required=False)
        if edit_button is not None:
            await self.humanizer.click(edit_button)
            await self.humanizer.pause((1.5, 3.0))

        if title is not None:
            field = await self.selectors.find(page, "new_ad_title", timeout=8000)
            await self.humanizer.type_text(field, title)
            await self.humanizer.pause()

        if description is not None:
            field = await self.selectors.find(page, "new_ad_description", timeout=8000)
            await self.humanizer.type_text(field, description)
            await self.humanizer.pause()

        await self.humanizer.pause_before_submit()
        submit = await self.selectors.find(page, "new_ad_submit", required=False)
        if submit is None:
            shot = await self.session.screenshot(f"bearbeiten-{ad.ad_id}")
            raise AdError(f"Speichern-Button nicht gefunden. Screenshot: {shot}")
        await self.humanizer.click(submit)
        await self.humanizer.pause((1.5, 3.0))

        log.info("Anzeige %s bearbeitet.", ad.ad_id)
        return True
