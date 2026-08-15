"""Hugging-Face-Wrapper.

Vier Backends, eine gemeinsame Schnittstelle:

  llama_cpp    Standard. Laedt ein oeffentliches GGUF-Modell direkt von
               huggingface.co und rechnet lokal auf der CPU. KEIN API-Token.
               Das ist der Weg, der auf dem Raspberry Pi funktioniert.
  transformers Lokal via transformers/torch. Braucht viel RAM, dafuer volle
               Modellauswahl. Nur fuer den PC gedacht.
  hf_inference Hugging Face Inference API. Schnell, aber braucht ein Token.
  template     Ohne KI, reine Textbausteine. Zum Testen der Mechanik, ohne
               dass mehrere GB heruntergeladen werden.
"""

from __future__ import annotations

import logging
import random
import re
from pathlib import Path

from ..config import AIConfig
from .base import ChatTurn, GenerationError, ReplyBackend

log = logging.getLogger(__name__)


# --------------------------------------------------------------------------
# 1) llama.cpp mit GGUF von Hugging Face - der tokenfreie Standardweg
# --------------------------------------------------------------------------


class LlamaCppBackend(ReplyBackend):
    name = "llama_cpp"

    def __init__(self, config: AIConfig, model_dir: Path) -> None:
        super().__init__()
        self.config = config
        self.model_dir = Path(model_dir)
        self._llm = None
        self._model_path: Path | None = None

    def _resolve_model(self) -> Path:
        """GGUF aus dem HF-Hub holen (oeffentliches Repo, kein Token noetig)."""
        from huggingface_hub import hf_hub_download

        self.model_dir.mkdir(parents=True, exist_ok=True)
        log.info(
            "Hole Modell %s / %s (beim ersten Mal mehrere GB Download) ...",
            self.config.llama_repo_id,
            self.config.llama_filename,
        )
        path = hf_hub_download(
            repo_id=self.config.llama_repo_id,
            filename=self.config.llama_filename,
            local_dir=str(self.model_dir),
            token=self.config.hf_token or None,
        )
        return Path(path)

    def _load(self) -> None:
        try:
            from llama_cpp import Llama
        except ImportError as exc:  # pragma: no cover - Umgebungsproblem
            raise GenerationError(
                "llama-cpp-python ist nicht installiert.\n"
                "  pip install llama-cpp-python\n"
                "Auf dem Raspberry Pi kann das Kompilieren einige Minuten dauern."
            ) from exc

        self._model_path = self._resolve_model()
        threads = self.config.llama_threads or (__import__("os").cpu_count() or 4)

        log.info("Lade Modell (%s, %d Threads) ...", self._model_path.name, threads)
        self._llm = Llama(
            model_path=str(self._model_path),
            n_ctx=self.config.llama_context_size,
            n_threads=threads,
            n_gpu_layers=self.config.llama_gpu_layers,
            verbose=False,
        )
        log.info("Modell bereit.")

    def _generate(self, turns: list[ChatTurn], options: dict[str, object]) -> str:
        if self._llm is None:
            raise GenerationError("Modell ist nicht geladen.")
        generation = self.config.generation
        messages = [{"role": turn.role, "content": turn.content} for turn in turns]

        try:
            result = self._llm.create_chat_completion(
                messages=messages,
                max_tokens=int(options.get("max_new_tokens", generation.max_new_tokens)),
                temperature=float(options.get("temperature", generation.temperature)),
                top_p=float(options.get("top_p", generation.top_p)),
            )
            return result["choices"][0]["message"]["content"]
        except Exception as exc:  # noqa: BLE001
            raise GenerationError(f"llama.cpp konnte nichts erzeugen: {exc}") from exc

    async def close(self) -> None:
        self._llm = None
        await super().close()


# --------------------------------------------------------------------------
# 2) transformers - lokal, nur fuer den PC
# --------------------------------------------------------------------------


class TransformersBackend(ReplyBackend):
    name = "transformers"

    def __init__(self, config: AIConfig, model_dir: Path) -> None:
        super().__init__()
        self.config = config
        self.model_dir = Path(model_dir)
        self._pipeline = None

    def _load(self) -> None:
        try:
            import torch  # noqa: F401
            from transformers import pipeline
        except ImportError as exc:  # pragma: no cover
            raise GenerationError(
                "transformers/torch fehlen.\n  pip install transformers torch\n"
                "Auf dem Raspberry Pi lieber das Backend 'llama_cpp' nehmen."
            ) from exc

        log.info("Lade %s via transformers ...", self.config.transformers_model_id)
        self._pipeline = pipeline(
            "text-generation",
            model=self.config.transformers_model_id,
            device_map=self.config.transformers_device,
            model_kwargs={"cache_dir": str(self.model_dir)},
            token=self.config.hf_token or None,
        )
        log.info("Modell bereit.")

    def _generate(self, turns: list[ChatTurn], options: dict[str, object]) -> str:
        if self._pipeline is None:
            raise GenerationError("Pipeline ist nicht geladen.")
        generation = self.config.generation
        messages = [{"role": turn.role, "content": turn.content} for turn in turns]

        try:
            output = self._pipeline(
                messages,
                max_new_tokens=int(options.get("max_new_tokens", generation.max_new_tokens)),
                temperature=float(options.get("temperature", generation.temperature)),
                top_p=float(options.get("top_p", generation.top_p)),
                do_sample=True,
                return_full_text=False,
            )
        except Exception as exc:  # noqa: BLE001
            raise GenerationError(f"transformers konnte nichts erzeugen: {exc}") from exc

        generated = output[0]["generated_text"]
        # Je nach Version ist das ein String oder die fortgesetzte Nachrichtenliste.
        if isinstance(generated, list):
            return generated[-1]["content"]
        return str(generated)


# --------------------------------------------------------------------------
# 3) Hugging Face Inference API - braucht Token
# --------------------------------------------------------------------------


class HFInferenceBackend(ReplyBackend):
    name = "hf_inference"

    def __init__(self, config: AIConfig) -> None:
        super().__init__()
        self.config = config
        self._client = None

    def _load(self) -> None:
        if not self.config.hf_token:
            raise GenerationError(
                "Backend 'hf_inference' braucht HUGGINGFACE_TOKEN in .env. "
                "Ohne Token nimm 'llama_cpp'."
            )
        try:
            from huggingface_hub import InferenceClient
        except ImportError as exc:  # pragma: no cover
            raise GenerationError("huggingface-hub fehlt: pip install huggingface-hub") from exc

        self._client = InferenceClient(token=self.config.hf_token)
        log.info("Inference-Client bereit (Modell %s).", self.config.hf_model_id)

    def _generate(self, turns: list[ChatTurn], options: dict[str, object]) -> str:
        if self._client is None:
            raise GenerationError("Client ist nicht initialisiert.")
        generation = self.config.generation
        messages = [{"role": turn.role, "content": turn.content} for turn in turns]

        try:
            result = self._client.chat_completion(
                messages=messages,
                model=self.config.hf_model_id,
                max_tokens=int(options.get("max_new_tokens", generation.max_new_tokens)),
                temperature=float(options.get("temperature", generation.temperature)),
                top_p=float(options.get("top_p", generation.top_p)),
            )
            return result.choices[0].message.content or ""
        except Exception as exc:  # noqa: BLE001
            raise GenerationError(f"Inference API meldet einen Fehler: {exc}") from exc


# --------------------------------------------------------------------------
# 4) Textbausteine - kein Modell, kein Download
# --------------------------------------------------------------------------


class TemplateBackend(ReplyBackend):
    """Regelbasiert. Nuetzlich, um Postfach, Telegram und UI zu testen,
    bevor man mehrere GB Modell herunterlaedt."""

    name = "template"

    GREETING = re.compile(r"\b(hallo|hi|hey|guten (tag|abend|morgen)|servus|moin)\b", re.I)
    QUESTION = re.compile(r"\?")
    AVAILABILITY = re.compile(r"\b(zeit|verf[uü]gbar|wann|frei|heute|morgen)\b", re.I)

    RESPONSES = {
        "greeting": [
            "Hi! Schoen, dass du dich meldest.",
            "Hallo! Danke fuer deine Nachricht.",
            "Hey, danke fuer die Nachricht.",
        ],
        "availability": [
            "Melde mich gleich mit einem konkreten Vorschlag bei dir.",
            "Ich schaue kurz in den Kalender und sage dir Bescheid.",
        ],
        "question": [
            "Gute Frage - dazu antworte ich dir gleich in Ruhe.",
            "Das schaue ich mir an und melde mich kurz darauf.",
        ],
        "default": [
            "Danke fuer deine Nachricht, ich melde mich gleich.",
            "Alles klar, ich komme kurz darauf zurueck.",
        ],
    }

    def __init__(self, seed: int | None = None) -> None:
        super().__init__()
        self._rng = random.Random(seed)

    def _load(self) -> None:
        log.info("Template-Backend aktiv (keine KI, nur Textbausteine).")

    def _generate(self, turns: list[ChatTurn], options: dict[str, object]) -> str:
        last_user = next(
            (turn.content for turn in reversed(turns) if turn.role == "user"), ""
        )
        # Aus dem Kontextblock die letzte Gegenueber-Zeile ziehen.
        incoming = [
            line.split(":", 1)[1].strip()
            for line in last_user.splitlines()
            if line.startswith("Er/Sie:")
        ]
        text = incoming[-1] if incoming else last_user

        parts: list[str] = []
        if self.GREETING.search(text):
            parts.append(self._rng.choice(self.RESPONSES["greeting"]))
        if self.AVAILABILITY.search(text):
            parts.append(self._rng.choice(self.RESPONSES["availability"]))
        elif self.QUESTION.search(text):
            parts.append(self._rng.choice(self.RESPONSES["question"]))
        if not parts:
            parts.append(self._rng.choice(self.RESPONSES["default"]))
        return " ".join(parts)


# --------------------------------------------------------------------------
# Fabrik
# --------------------------------------------------------------------------


def create_backend(config: AIConfig, model_dir: str | Path) -> ReplyBackend:
    model_dir = Path(model_dir)
    backends = {
        "llama_cpp": lambda: LlamaCppBackend(config, model_dir),
        "transformers": lambda: TransformersBackend(config, model_dir),
        "hf_inference": lambda: HFInferenceBackend(config),
        "template": lambda: TemplateBackend(),
    }
    factory = backends.get(config.backend)
    if factory is None:
        raise GenerationError(
            f"Unbekanntes Backend '{config.backend}'. Erlaubt: {', '.join(backends)}"
        )
    log.info("KI-Backend: %s", config.backend)
    return factory()
