"""Offenlegung, dass hier eine KI schreibt.

Der Systemprompt weist das Modell an, sich als Assistenzprogramm zu erkennen zu
geben. Darauf allein darf man sich aber nicht verlassen: ein 3B- oder 7B-Modell
faellt bei hartnaeckigem Nachfragen ("komm schon, du bist doch echt, oder?")
zuverlaessig aus der Rolle und behauptet, ein Mensch zu sein. Genau in dem
Moment kippt der autonome Betrieb von "hilfreich" zu "Taeuschung".

Deshalb sitzt hier eine zweite, deterministische Schicht:

  1. Die erste Antwort in einer Konversation traegt immer die Kennzeichnung -
     eingefuegt von Code, nicht vom Modell.
  2. Fragt jemand direkt nach ("bist du ein Bot?"), wird geprueft, ob die
     erzeugte Antwort das klar bejaht. Tut sie es nicht, wird die Kennzeichnung
     vorangestellt.
  3. Behauptet das Modell, ein Mensch zu sein, wird die Aussage entfernt und
     durch die Kennzeichnung ersetzt.

Punkt 3 ist der Grund, warum das eine eigene Datei ist und nicht drei Zeilen
im Prompt.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass

log = logging.getLogger(__name__)


# --------------------------------------------------------------------------
# Erkennung: fragt das Gegenueber nach der Natur des Chatpartners?
# --------------------------------------------------------------------------

IDENTITY_QUESTION = [
    re.compile(p, re.IGNORECASE)
    for p in [
        # "bist du ein bot / echt / eine ki / ein mensch / real / automatisch"
        r"\bbist\s+du\s+(denn\s+|wirklich\s+|echt\s+|auch\s+)?"
        r"(ein(e)?\s+)?(bot|ki\b|k\.i\.|computer|programm|automat|roboter|chatbot|mensch|echt|real|fake)",
        # "schreibt hier ein mensch / eine maschine"
        r"\b(schreibt|antwortet|redet)\s+(hier\s+)?(ein|eine|da)\s+"
        r"(mensch|bot|ki\b|maschine|programm|computer)",
        # "ist das ein bot?" / "ist das hier automatisch?"
        r"\bist\s+(das|hier|die\s+antwort)(\s+hier|\s+alles)?\s+(ein(e)?\s+)?"
        r"(bot|ki\b|k\.i\.|automat\w*|computer|programm|echt|fake|mensch)",
        # "rede ich mit einem bot?"
        r"\b(rede|schreibe|spreche|chatte)\s+ich\s+(hier\s+)?mit\s+(einem|einer)\s+"
        r"(bot|ki\b|mensch|programm|computer|maschine)",
        # "bist du künstliche intelligenz"
        r"\bk[uü]nstliche[rn]?\s+intelligenz\b",
        # kurz und haeufig: "bot?" / "ki?" / "echt?" als ganze Nachricht
        r"^\s*(bot|ki|k\.i\.|echt|fake|real|mensch)\s*\?+\s*$",
        # "du bist doch ein bot"
        r"\bdu\s+bist\s+(doch\s+|wohl\s+|bestimmt\s+|sicher\s+)?(ein(e)?\s+)?"
        r"(bot|ki\b|programm|computer|automat)",
    ]
]

# --------------------------------------------------------------------------
# Erkennung: gibt sich der Text selbst als KI zu erkennen?
# Bewusst streng - ein falsch negatives Ergebnis fuehrt nur dazu, dass die
# Kennzeichnung zusaetzlich vorangestellt wird. Das ist der harmlose Fehler.
# --------------------------------------------------------------------------

SELF_DISCLOSURE = [
    re.compile(p, re.IGNORECASE)
    for p in [
        r"\b(ich\s+bin|hier\s+schreibt|das\s+(ist|schreibt)|ich\s+w[aä]re)\b[^.!?]{0,60}?"
        r"\b(ki|k\.i\.|k[uü]nstliche[rn]?\s+intelligenz|bot|chatbot|programm|software|"
        r"assistent\w*|assistenz\w*|automat\w*|computer|maschine)\b",
        r"\bkein\s+mensch\b",
        r"\bnicht\s+(pers[oö]nlich|selbst)\s+am\s+(handy|rechner|computer)\b",
        r"\bautomatische?\s+(antwort|nachricht)\b",
    ]
]

# --------------------------------------------------------------------------
# Erkennung: behauptet der Text, ein Mensch zu sein? Das muss raus.
# --------------------------------------------------------------------------

FALSE_HUMAN_CLAIM = [
    re.compile(p, re.IGNORECASE)
    for p in [
        r"\bich\s+bin\s+(doch\s+|wirklich\s+|natuerlich\s+|nat[uü]rlich\s+|schon\s+|ganz\s+)?"
        r"(ein\s+)?(echte[rn]?\s+)?(mensch|real|echt|kein\s+bot|keine\s+ki)\b",
        r"\bich\s+bin\s+kein\s+(bot|programm|computer|roboter|automat)\b",
        r"\bkeine\s+(ki|maschine)\b[^.!?]{0,20}\bich\b",
        r"\bnat[uü]rlich\s+bin\s+ich\s+(echt|real|ein\s+mensch)\b",
        r"\bich\s+bin\s+aus\s+fleisch\s+und\s+blut\b",
    ]
]


def asks_about_identity(text: str) -> bool:
    """Fragt die Nachricht danach, ob hier ein Mensch oder ein Programm schreibt?"""
    return any(pattern.search(text) for pattern in IDENTITY_QUESTION)


def contains_disclosure(text: str) -> bool:
    """Gibt sich der Text selbst als Programm zu erkennen?"""
    return any(pattern.search(text) for pattern in SELF_DISCLOSURE)


def claims_to_be_human(text: str) -> bool:
    """Behauptet der Text, ein Mensch zu sein?"""
    return any(pattern.search(text) for pattern in FALSE_HUMAN_CLAIM)


# --------------------------------------------------------------------------


@dataclass(slots=True)
class DisclosureResult:
    text: str
    changed: bool = False
    reason: str = ""


class DisclosureEngine:
    """Sorgt dafuer, dass jede autonome Antwort ehrlich ueber ihre Herkunft ist."""

    def __init__(
        self,
        identification: str,
        signature: str = "",
        identify_on_first_reply: bool = True,
    ) -> None:
        self.identification = identification.strip()
        self.signature = signature.strip()
        self.identify_on_first_reply = identify_on_first_reply

    # -- Hauptweg -----------------------------------------------------------

    def apply(
        self,
        text: str,
        *,
        incoming: str = "",
        is_first_reply: bool = False,
    ) -> DisclosureResult:
        """Antworttext so nachbearbeiten, dass die Offenlegung garantiert ist."""
        working = text.strip()
        reasons: list[str] = []

        # 1. Falschbehauptung entfernen. Das hat Vorrang vor allem anderen.
        if claims_to_be_human(working):
            working = self._strip_human_claims(working)
            reasons.append("Behauptung, ein Mensch zu sein, entfernt")
            log.warning(
                "Modell hat sich als Mensch ausgegeben - Aussage wurde ersetzt."
            )

        # 2. Direkte Frage nach der Identitaet muss klar beantwortet werden.
        asked = bool(incoming) and asks_about_identity(incoming)
        if asked and not contains_disclosure(working):
            working = self._prepend(working, self.identification)
            reasons.append("Antwort auf direkte Identitaetsfrage klargestellt")

        # 3. Erste Antwort im Gespraech traegt immer die Kennzeichnung.
        elif (
            is_first_reply
            and self.identify_on_first_reply
            and not contains_disclosure(working)
        ):
            working = self._prepend(working, self.identification)
            reasons.append("Kennzeichnung in der ersten Antwort ergaenzt")

        # 4. Kurze Signatur an allen uebrigen Antworten.
        elif self.signature and self.signature not in working:
            working = f"{working}\n{self.signature}"
            reasons.append("Signatur angehaengt")

        working = working.strip()
        return DisclosureResult(
            text=working,
            changed=working != text.strip(),
            reason="; ".join(reasons),
        )

    def verify(self, text: str) -> tuple[bool, str]:
        """Letzte Kontrolle vor dem Senden.

        Wird im Orchestrator direkt vor dem Absenden aufgerufen, damit auch von
        Hand bearbeitete Texte nicht als Mensch auftreten koennen.
        """
        if claims_to_be_human(text):
            return False, "Der Text behauptet, ein Mensch zu sein."
        return True, ""

    def deflection(self, topic: str, operator_name: str) -> str:
        """Feste Antwort fuer Themen, zu denen die KI nichts sagen soll.

        Bewusst kein Modelltext: Bei Preisen, Adressen und Kontaktdaten ist eine
        erfundene Antwort deutlich schaedlicher als eine langweilige.
        """
        who = operator_name or "die Person hinter dem Profil"
        return (
            f"{self.identification} "
            f"Zu dem Thema ({topic.lower()}) kann ich dir nichts sagen - "
            f"das entscheidet {who} selbst. Ich habe deine Nachricht weitergegeben, "
            f"{who} meldet sich dazu persoenlich bei dir."
        )

    # -- Intern -------------------------------------------------------------

    @staticmethod
    def _prepend(text: str, identification: str) -> str:
        if not identification:
            return text
        if not text:
            return identification
        return f"{identification} {text}"

    @staticmethod
    def _strip_human_claims(text: str) -> str:
        """Saetze mit Menschbehauptung herausnehmen.

        Es wird satzweise gearbeitet, damit der Rest der Antwort erhalten
        bleibt - meistens steckt die Behauptung in einem Nebensatz und der Rest
        ist voellig in Ordnung.
        """
        sentences = re.split(r"(?<=[.!?])\s+", text)
        kept = [s for s in sentences if not claims_to_be_human(s)]
        return " ".join(kept).strip()
