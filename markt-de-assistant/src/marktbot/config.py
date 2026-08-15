"""Konfiguration laden: config.yaml fuer Verhalten, .env fuer Geheimnisse.

Bewusst ohne pydantic - das spart auf dem Raspberry Pi eine Abhaengigkeit und
die Struktur ist flach genug, dass Dataclasses reichen.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from datetime import time as dtime
from pathlib import Path
from typing import Any

import yaml
from dotenv import load_dotenv

log = logging.getLogger(__name__)


class ConfigError(RuntimeError):
    """Konfiguration fehlt oder ist unbrauchbar."""


# --------------------------------------------------------------------------
# Hilfsfunktionen
# --------------------------------------------------------------------------


def _get(data: dict[str, Any], path: str, default: Any = None) -> Any:
    """Verschachtelten Wert per "a.b.c" holen."""
    node: Any = data
    for part in path.split("."):
        if not isinstance(node, dict) or part not in node:
            return default
        node = node[part]
    return node


def _parse_hhmm(value: str, field_name: str) -> dtime:
    try:
        hour, minute = value.strip().split(":")
        return dtime(int(hour), int(minute))
    except (ValueError, AttributeError) as exc:
        raise ConfigError(f"{field_name}: '{value}' ist keine Uhrzeit im Format HH:MM") from exc


def _range(value: Any, field_name: str) -> tuple[float, float]:
    if not isinstance(value, (list, tuple)) or len(value) != 2:
        raise ConfigError(f"{field_name} muss eine Liste [min, max] sein, war: {value!r}")
    low, high = float(value[0]), float(value[1])
    if low > high:
        raise ConfigError(f"{field_name}: min ({low}) ist groesser als max ({high})")
    return low, high


# --------------------------------------------------------------------------
# Abschnitte
# --------------------------------------------------------------------------


@dataclass(slots=True)
class ProxyConfig:
    server: str = ""
    username: str = ""
    password: str = ""

    @property
    def configured(self) -> bool:
        return bool(self.server)

    def as_playwright(self) -> dict[str, str] | None:
        if not self.configured:
            return None
        proxy: dict[str, str] = {"server": self.server}
        if self.username:
            proxy["username"] = self.username
            proxy["password"] = self.password
        return proxy


@dataclass(slots=True)
class BrowserConfig:
    profile_dir: Path = Path("profiles/default")
    headless: bool = False
    locale: str = "de-DE"
    timezone: str = "Europe/Berlin"
    viewport_width: int = 1536
    viewport_height: int = 864
    use_proxy: bool = False
    nav_timeout: float = 45.0
    proxy: ProxyConfig = field(default_factory=ProxyConfig)
    # Auf ARM (Raspberry Pi) gibt es keine fertigen Playwright-Browser.
    # Dort zeigt PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH auf das System-Chromium.
    executable_path: str = ""


@dataclass(slots=True)
class HumanizeConfig:
    typing_cpm_min: int = 190
    typing_cpm_max: int = 340
    pause_before_submit: tuple[float, float] = (1.5, 4.5)
    action_delay: tuple[float, float] = (0.8, 3.0)
    reading_speed: tuple[float, float] = (1.2, 2.6)
    random_scroll: bool = True


@dataclass(slots=True)
class LimitsConfig:
    replies_per_hour: int = 8
    replies_per_day: int = 40
    ads_per_day: int = 5
    min_seconds_between_replies: int = 90


@dataclass(slots=True)
class QuietHours:
    enabled: bool = True
    start: dtime = dtime(23, 30)
    end: dtime = dtime(7, 30)

    def contains(self, moment: dtime) -> bool:
        """Auch ueber Mitternacht hinweg korrekt."""
        if not self.enabled:
            return False
        if self.start <= self.end:
            return self.start <= moment < self.end
        return moment >= self.start or moment < self.end


@dataclass(slots=True)
class ScheduleConfig:
    inbox_poll_min: int = 240
    inbox_poll_max: int = 900
    quiet_hours: QuietHours = field(default_factory=QuietHours)
    limits: LimitsConfig = field(default_factory=LimitsConfig)


@dataclass(slots=True)
class GenerationConfig:
    max_new_tokens: int = 220
    temperature: float = 0.75
    top_p: float = 0.9


@dataclass(slots=True)
class AIConfig:
    backend: str = "llama_cpp"
    llama_repo_id: str = "bartowski/Qwen2.5-7B-Instruct-GGUF"
    llama_filename: str = "Qwen2.5-7B-Instruct-Q4_K_M.gguf"
    llama_context_size: int = 4096
    llama_threads: int = 0
    llama_gpu_layers: int = 0
    transformers_model_id: str = "Qwen/Qwen2.5-7B-Instruct"
    transformers_device: str = "auto"
    hf_model_id: str = "Qwen/Qwen2.5-7B-Instruct"
    hf_token: str = ""
    generation: GenerationConfig = field(default_factory=GenerationConfig)


@dataclass(slots=True)
class PersonaConfig:
    display_name: str = "Alex"
    description: str = ""
    rules: list[str] = field(default_factory=list)
    handover_topics: list[str] = field(default_factory=list)


@dataclass(slots=True)
class RepliesConfig:
    require_approval: bool = True
    disclosure: str = ""
    always_approve_first_contact: bool = True
    draft_ttl_hours: int = 12


@dataclass(slots=True)
class AssistantConfig:
    """Assistenzmodus: autonom antworten, dafuer offen als KI auftreten.

    Der Tausch ist bewusst: volle Autonomie gibt es nur mit Offenlegung. Wer
    `enabled` einschaltet, aber `identification` leert, bekommt beim Laden der
    Konfiguration einen Fehler.
    """

    enabled: bool = False
    assistant_name: str = "Assistent"
    operator_name: str = ""
    identification: str = ""
    signature: str = ""
    identify_on_first_reply: bool = True
    # Heikle Themen (Preis, Adresse, Kontaktdaten) autonom mit einer festen
    # Weiterleitungsformel beantworten, statt sie unbeantwortet zu lassen.
    deflect_handover_topics: bool = True


@dataclass(slots=True)
class SafetyConfig:
    enabled: bool = True
    on_block: str = "escalate"
    extra_blocklist: list[str] = field(default_factory=list)


@dataclass(slots=True)
class AdsConfig:
    auto_renew: bool = False
    auto_renew_after_days: int = 7
    template_dir: Path = Path("ads")


@dataclass(slots=True)
class UIConfig:
    enabled: bool = True
    host: str = "127.0.0.1"
    port: int = 8765
    password: str = ""


@dataclass(slots=True)
class TelegramConfig:
    enabled: bool = True
    token: str = ""
    chat_id: int = 0
    notify_new_message: bool = True
    notify_errors: bool = True

    @property
    def configured(self) -> bool:
        return bool(self.token and self.chat_id)


@dataclass(slots=True)
class LoggingConfig:
    level: str = "INFO"
    file: Path = Path("logs/marktbot.log")
    log_message_bodies: bool = False


@dataclass(slots=True)
class Credentials:
    username: str = ""
    password: str = ""

    @property
    def configured(self) -> bool:
        return bool(self.username and self.password)


@dataclass(slots=True)
class Config:
    root: Path
    credentials: Credentials
    browser: BrowserConfig
    humanize: HumanizeConfig
    schedule: ScheduleConfig
    ai: AIConfig
    persona: PersonaConfig
    replies: RepliesConfig
    assistant: AssistantConfig
    safety: SafetyConfig
    ads: AdsConfig
    ui: UIConfig
    telegram: TelegramConfig
    logging: LoggingConfig
    data_dir: Path = Path("data")

    @property
    def db_path(self) -> Path:
        return self.data_dir / "marktbot.db"

    @property
    def screenshot_dir(self) -> Path:
        return self.data_dir / "screenshots"


# --------------------------------------------------------------------------
# Laden
# --------------------------------------------------------------------------


def load_config(config_path: str | Path | None = None, root: str | Path | None = None) -> Config:
    """config.yaml + .env einlesen und zu einem Config-Objekt verschmelzen.

    Relative Pfade in der YAML sind immer relativ zum Projektverzeichnis.
    """
    root_path = Path(root).resolve() if root else Path(__file__).resolve().parents[2]
    load_dotenv(root_path / ".env")

    if config_path is None:
        config_path = root_path / "config.yaml"
    config_path = Path(config_path)

    if not config_path.exists():
        example = root_path / "config.example.yaml"
        raise ConfigError(
            f"{config_path} nicht gefunden.\n"
            f"Loesung: 'cp {example.name} config.yaml' und anpassen."
        )

    with config_path.open("r", encoding="utf-8") as handle:
        raw = yaml.safe_load(handle) or {}
    if not isinstance(raw, dict):
        raise ConfigError(f"{config_path} enthaelt kein YAML-Mapping.")

    def resolve(value: str | Path) -> Path:
        path = Path(value)
        return path if path.is_absolute() else root_path / path

    browser = BrowserConfig(
        profile_dir=resolve(_get(raw, "browser.profile_dir", "profiles/default")),
        headless=bool(_get(raw, "browser.headless", False)),
        locale=_get(raw, "browser.locale", "de-DE"),
        timezone=_get(raw, "browser.timezone", "Europe/Berlin"),
        viewport_width=int(_get(raw, "browser.viewport.width", 1536)),
        viewport_height=int(_get(raw, "browser.viewport.height", 864)),
        use_proxy=bool(_get(raw, "browser.use_proxy", False)),
        nav_timeout=float(_get(raw, "browser.nav_timeout", 45)),
        proxy=ProxyConfig(
            server=os.getenv("PROXY_SERVER", "").strip(),
            username=os.getenv("PROXY_USERNAME", "").strip(),
            password=os.getenv("PROXY_PASSWORD", "").strip(),
        ),
        executable_path=os.getenv("PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH", "").strip(),
    )
    if browser.use_proxy and not browser.proxy.configured:
        raise ConfigError(
            "browser.use_proxy ist true, aber PROXY_SERVER ist in .env leer."
        )

    humanize = HumanizeConfig(
        typing_cpm_min=int(_get(raw, "humanize.typing_cpm_min", 190)),
        typing_cpm_max=int(_get(raw, "humanize.typing_cpm_max", 340)),
        pause_before_submit=_range(_get(raw, "humanize.pause_before_submit", [1.5, 4.5]), "humanize.pause_before_submit"),
        action_delay=_range(_get(raw, "humanize.action_delay", [0.8, 3.0]), "humanize.action_delay"),
        reading_speed=_range(_get(raw, "humanize.reading_speed", [1.2, 2.6]), "humanize.reading_speed"),
        random_scroll=bool(_get(raw, "humanize.random_scroll", True)),
    )
    if humanize.typing_cpm_min > humanize.typing_cpm_max:
        raise ConfigError("humanize.typing_cpm_min darf nicht groesser als typing_cpm_max sein.")

    poll_min = int(_get(raw, "schedule.inbox_poll_min", 240))
    poll_max = int(_get(raw, "schedule.inbox_poll_max", 900))
    if poll_min > poll_max:
        raise ConfigError("schedule.inbox_poll_min darf nicht groesser als inbox_poll_max sein.")

    schedule = ScheduleConfig(
        inbox_poll_min=poll_min,
        inbox_poll_max=poll_max,
        quiet_hours=QuietHours(
            enabled=bool(_get(raw, "schedule.quiet_hours.enabled", True)),
            start=_parse_hhmm(_get(raw, "schedule.quiet_hours.start", "23:30"), "quiet_hours.start"),
            end=_parse_hhmm(_get(raw, "schedule.quiet_hours.end", "07:30"), "quiet_hours.end"),
        ),
        limits=LimitsConfig(
            replies_per_hour=int(_get(raw, "schedule.limits.replies_per_hour", 8)),
            replies_per_day=int(_get(raw, "schedule.limits.replies_per_day", 40)),
            ads_per_day=int(_get(raw, "schedule.limits.ads_per_day", 5)),
            min_seconds_between_replies=int(
                _get(raw, "schedule.limits.min_seconds_between_replies", 90)
            ),
        ),
    )

    ai = AIConfig(
        backend=str(_get(raw, "ai.backend", "llama_cpp")).lower(),
        llama_repo_id=_get(raw, "ai.llama_cpp.repo_id", "bartowski/Qwen2.5-7B-Instruct-GGUF"),
        llama_filename=_get(raw, "ai.llama_cpp.filename", "Qwen2.5-7B-Instruct-Q4_K_M.gguf"),
        llama_context_size=int(_get(raw, "ai.llama_cpp.context_size", 4096)),
        llama_threads=int(_get(raw, "ai.llama_cpp.threads", 0)),
        llama_gpu_layers=int(_get(raw, "ai.llama_cpp.gpu_layers", 0)),
        transformers_model_id=_get(raw, "ai.transformers.model_id", "Qwen/Qwen2.5-7B-Instruct"),
        transformers_device=_get(raw, "ai.transformers.device", "auto"),
        hf_model_id=_get(raw, "ai.hf_inference.model_id", "Qwen/Qwen2.5-7B-Instruct"),
        hf_token=os.getenv("HUGGINGFACE_TOKEN", "").strip(),
        generation=GenerationConfig(
            max_new_tokens=int(_get(raw, "ai.generation.max_new_tokens", 220)),
            temperature=float(_get(raw, "ai.generation.temperature", 0.75)),
            top_p=float(_get(raw, "ai.generation.top_p", 0.9)),
        ),
    )
    known_backends = {"llama_cpp", "transformers", "hf_inference", "template"}
    if ai.backend not in known_backends:
        raise ConfigError(
            f"ai.backend '{ai.backend}' ist unbekannt. Erlaubt: {', '.join(sorted(known_backends))}"
        )
    if ai.backend == "hf_inference" and not ai.hf_token:
        raise ConfigError(
            "ai.backend 'hf_inference' braucht HUGGINGFACE_TOKEN in .env. "
            "Ohne Token nimm 'llama_cpp' - das laeuft komplett lokal."
        )

    persona = PersonaConfig(
        display_name=_get(raw, "persona.display_name", "Alex"),
        description=(_get(raw, "persona.description", "") or "").strip(),
        rules=list(_get(raw, "persona.rules", []) or []),
        handover_topics=list(_get(raw, "persona.handover_topics", []) or []),
    )

    replies = RepliesConfig(
        require_approval=bool(_get(raw, "replies.require_approval", True)),
        disclosure=(_get(raw, "replies.disclosure", "") or "").strip(),
        always_approve_first_contact=bool(_get(raw, "replies.always_approve_first_contact", True)),
        draft_ttl_hours=int(_get(raw, "replies.draft_ttl_hours", 12)),
    )

    assistant = AssistantConfig(
        enabled=bool(_get(raw, "assistant.enabled", False)),
        assistant_name=_get(raw, "assistant.assistant_name", "Assistent"),
        operator_name=_get(raw, "assistant.operator_name", "") or persona.display_name,
        identification=(_get(raw, "assistant.identification", "") or "").strip(),
        signature=(_get(raw, "assistant.signature", "") or "").strip(),
        identify_on_first_reply=bool(_get(raw, "assistant.identify_on_first_reply", True)),
        deflect_handover_topics=bool(_get(raw, "assistant.deflect_handover_topics", True)),
    )
    if assistant.enabled and not assistant.identification:
        raise ConfigError(
            "assistant.enabled ist true, aber assistant.identification ist leer.\n"
            "Der Assistenzmodus antwortet ohne Rueckfrage - dafuer muss jede Antwort "
            "erkennbar machen, dass ein Programm schreibt. Beispiel:\n"
            '  identification: "Hi, ich bin der digitale Assistent von Alex - '
            'ein Programm, kein Mensch."'
        )
    if assistant.enabled and replies.require_approval:
        log.info(
            "Assistenzmodus mit eingeschalteter Freigabe: Entwuerfe werden weiterhin "
            "vorgelegt. Fuer den autonomen Betrieb replies.require_approval auf false setzen."
        )

    safety = SafetyConfig(
        enabled=bool(_get(raw, "safety.enabled", True)),
        on_block=str(_get(raw, "safety.on_block", "escalate")).lower(),
        extra_blocklist=list(_get(raw, "safety.extra_blocklist", []) or []),
    )

    ads = AdsConfig(
        auto_renew=bool(_get(raw, "ads.auto_renew", False)),
        auto_renew_after_days=int(_get(raw, "ads.auto_renew_after_days", 7)),
        template_dir=resolve(_get(raw, "ads.template_dir", "ads")),
    )

    ui = UIConfig(
        enabled=bool(_get(raw, "ui.enabled", True)),
        host=_get(raw, "ui.host", "127.0.0.1"),
        port=int(_get(raw, "ui.port", 8765)),
        password=os.getenv("UI_PASSWORD", "").strip(),
    )
    if ui.enabled and ui.host not in ("127.0.0.1", "localhost") and not ui.password:
        raise ConfigError(
            f"ui.host ist '{ui.host}' (im Netz erreichbar), aber UI_PASSWORD ist leer. "
            "Entweder host auf 127.0.0.1 setzen oder ein Passwort vergeben."
        )

    chat_id_raw = os.getenv("TELEGRAM_CHAT_ID", "").strip()
    try:
        chat_id = int(chat_id_raw) if chat_id_raw else 0
    except ValueError as exc:
        raise ConfigError(f"TELEGRAM_CHAT_ID ist keine Zahl: {chat_id_raw!r}") from exc

    telegram = TelegramConfig(
        enabled=bool(_get(raw, "telegram.enabled", True)),
        token=os.getenv("TELEGRAM_BOT_TOKEN", "").strip(),
        chat_id=chat_id,
        notify_new_message=bool(_get(raw, "telegram.notify_new_message", True)),
        notify_errors=bool(_get(raw, "telegram.notify_errors", True)),
    )

    logging_cfg = LoggingConfig(
        level=str(_get(raw, "logging.level", "INFO")).upper(),
        file=resolve(_get(raw, "logging.file", "logs/marktbot.log")),
        log_message_bodies=bool(_get(raw, "logging.log_message_bodies", False)),
    )

    return Config(
        root=root_path,
        credentials=Credentials(
            username=os.getenv("MARKT_USERNAME", "").strip(),
            password=os.getenv("MARKT_PASSWORD", ""),
        ),
        browser=browser,
        humanize=humanize,
        schedule=schedule,
        ai=ai,
        persona=persona,
        replies=replies,
        assistant=assistant,
        safety=safety,
        ads=ads,
        ui=ui,
        telegram=telegram,
        logging=logging_cfg,
        data_dir=root_path / "data",
    )
