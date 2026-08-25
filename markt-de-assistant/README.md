# markt.de Assistent

Automatisierungs-Assistent für einen markt.de-Account: liest das Postfach, erzeugt
KI-Antwortentwürfe, verwaltet Anzeigen. Steuerbar über ein lokales Web-Dashboard
am PC und über Telegram vom Handy. Läuft auf Windows (zum Testen) und auf einem
Raspberry Pi (für den Dauerbetrieb).

Die KI läuft **komplett lokal** – ein Modell von Hugging Face wird einmal
heruntergeladen und danach auf der eigenen CPU gerechnet. Es wird **kein
API-Token** gebraucht.

---

## Inhalt

- [Zwei Betriebsarten](#zwei-betriebsarten)
- [Was der Assistent macht](#was-der-assistent-macht)
- [Wie die KI-Antworten funktionieren](#wie-die-ki-antworten-funktionieren)
- [Assistenzmodus: autonom und offen als KI](#assistenzmodus-autonom-und-offen-als-ki)
- [Schnellstart Windows](#schnellstart-windows)
- [Die Oberfläche](#die-oberfläche)
- [Schnellstart Raspberry Pi](#schnellstart-raspberry-pi)
- [Konfiguration](#konfiguration)
- [Modellwahl](#modellwahl)
- [In der Cloud testen](#in-der-cloud-testen)
- [Bandbreite und Residential Proxy](#bandbreite-und-residential-proxy)
- [Telegram](#telegram)
- [Web-UI](#web-ui)
- [Anzeigen verwalten](#anzeigen-verwalten)
- [Wenn Selektoren brechen](#wenn-selektoren-brechen)
- [Residential IP und Browser-Identität](#residential-ip-und-browser-identität)
- [Sicherheitsfilter](#sicherheitsfilter)
- [Architektur](#architektur)
- [Fehlersuche](#fehlersuche)
- [Grenzen und Rechtliches](#grenzen-und-rechtliches)

---

## Zwei Betriebsarten

| | **Freigabe-Modus** (`run.py`) | **Assistenzmodus** (`run.py assistant`) |
|---|---|---|
| Antwortet | erst nach deiner Freigabe | selbstständig, ohne Rückfrage |
| Tritt auf als | du | erkennbar als Programm |
| Config | `config.yaml` | `config.assistant.yaml` |
| Heikle Themen | bleiben liegen, gehen an dich | feste Weiterleitungsformel + Meldung an dich |
| Du wirst gefragt | bei jedem Entwurf | nie – bekommst aber jede gesendete Antwort zu sehen |

Beide teilen sich Browser, Speicher, Sicherheitsfilter, Limits, Telegram und
Web-UI. Der Unterschied liegt allein im Antwortverhalten.

---

## Was der Assistent macht

| Bereich | Funktion |
|---|---|
| **Postfach** | Ruft in unregelmäßigen Abständen neue Nachrichten ab, speichert Verläufe, erzeugt Antwortentwürfe |
| **Freigabe** | Jeder Entwurf geht per Telegram oder Web-UI an dich: Senden / Ändern / Verwerfen |
| **Trockenlauf** | `--dry-run` durchläuft alles, sendet aber nichts an markt.de |
| **Bandbreite** | Bilder, Videos, Fonts und Tracker werden geblockt - wichtig bei Proxy-Abrechnung pro GB |
| **Anzeigen** | Auflisten, aus Vorlage neu aufgeben, bearbeiten, hochschieben, pausieren, löschen |
| **Sicherheit** | Filter stoppt Themen, die kein Automat beantworten darf, und eskaliert an dich |
| **Limits** | Obergrenzen pro Stunde und Tag, Mindestabstand zwischen Nachrichten, Ruhezeiten |
| **Anmeldung** | Persistentes Browser-Profil; Captcha und 2FA gehen per Screenshot an dich |
| **Oberfläche** | Desktop-Fenster für Einrichtung, Start/Stopp und Live-Protokoll |

---

## Wie die KI-Antworten funktionieren

Der Standardmodus ist **Freigabe erforderlich**. Ablauf:

```
neue Nachricht  →  Sicherheitsfilter  →  KI erzeugt Entwurf  →  Filter prüft Entwurf
                          │                                            │
                          ├─ blockiert ──→ Meldung an dich,            ├─ auffällig ──→ gestoppt
                          │                keine Antwort               │
                          └─ ok                                        └─ ok
                                                                        │
                                              Telegram/Web-UI: [Senden] [Ändern] [Verwerfen]
```

Weil du jede Nachricht vor dem Absenden liest, bist du der Absender — die KI ist
ein Schreibwerkzeug wie eine Textvorlage. Ein KI-Hinweis ist in diesem Modus
deshalb nicht nötig und standardmäßig auch nicht gesetzt (`replies.disclosure: ""`).

**Heikle Themen bekommen einen Entwurf mit Warnung.** Fragt jemand nach Preisen,
Adressen oder Kontaktdaten, entsteht trotzdem ein Vorschlag — markiert mit
`⚠️ Heikles Thema`, weil das Modell genau dort gern erfindet. Abschaltbar über
`replies.draft_sensitive_topics: false`.

**Harte Blocker erzeugen nie einen Entwurf.** Bei Minderjährigen, Nötigung oder
Betrugsmustern soll dir kein fertiger Text vorliegen, den man im Vorbeigehen
durchwinkt. Stattdessen wird der Thread markiert und du bekommst eine Meldung.

Vollautomatik lässt sich einschalten (`replies.require_approval: false`), dann
verschickt der Assistent Entwürfe direkt. Das ist eine bewusste Entscheidung mit
zwei Folgen, die man kennen sollte:

- Dein Gegenüber unterhält sich mit einem Programm, ohne es zu wissen. Über
  `replies.disclosure` lässt sich ein Hinweis anhängen (z. B. `"(automatische
  Antwort)"`), der an jede erzeugte Nachricht kommt.
- Ein Modell dieser Größe schreibt gelegentlich Unsinn. Was rausgeht, steht
  unter deinem Namen.

Unabhängig von der Einstellung wird der **erste Kontakt** immer vorgelegt
(`replies.always_approve_first_contact`), und der Sicherheitsfilter greift immer.

---

## Assistenzmodus: autonom und offen als KI

Der zweite Modus beantwortet alles selbstständig – und macht dabei kenntlich,
dass ein Programm schreibt. Das eine ist die Bedingung für das andere: ohne
`assistant.identification` startet der Modus nicht.

```bash
cp config.assistant.example.yaml config.assistant.yaml
nano config.assistant.yaml     # Namen und Kennzeichnung anpassen
python run.py assistant
```

### Offenlegung ist Code, nicht nur Prompt

Der Systemprompt weist das Modell an, sich als Assistenzprogramm zu erkennen zu
geben. **Darauf allein kann man sich nicht verlassen.** Ein 3B- oder 7B-Modell
fällt bei hartnäckigem Nachfragen aus der Rolle:

> „Komm schon, du bist doch echt, oder?“
> → *„Nein nein, ich bin wirklich ein Mensch, glaub mir.“*

Genau da kippt autonomer Betrieb von hilfreich zu Täuschung. Deshalb sitzt hinter
dem Prompt eine deterministische Schicht (`ai/disclosure.py`, 30+ Tests):

1. **Erste Antwort im Gespräch** trägt immer die Kennzeichnung – eingefügt von
   Code, nicht vom Modell.
2. **Direkte Frage erkannt** („bist du ein Bot?“, „echt?“, „rede ich mit einer
   KI?“) → die Antwort wird geprüft; klärt sie nicht auf, wird die Kennzeichnung
   vorangestellt.
3. **Menschbehauptung wird entfernt.** Sätze wie „ich bin ein Mensch“ werden
   satzweise herausgeschnitten, der unschuldige Rest der Antwort bleibt stehen.
4. **Letzte Kontrolle vor dem Senden** – auch für von Hand getippte Texte.

```yaml
assistant:
  enabled: true
  assistant_name: "Robin"
  operator_name: "Alex"
  identification: >-
    Hi, ich bin Robin, der digitale Assistent von Alex - ein Programm, kein Mensch.
  signature: "– Robin (automatischer Assistent)"
  identify_on_first_reply: true
  deflect_handover_topics: true
```

So sieht das im Betrieb aus:

```
Erstkontakt  →  "Hi, ich bin Robin, der digitale Assistent von Alex – ein
                 Programm, kein Mensch. Ja, die Anzeige ist noch aktuell."

Preisfrage   →  "Hi, ich bin Robin, … Zu dem Thema kann ich dir nichts sagen –
                 das entscheidet Alex selbst. Ich habe deine Nachricht
                 weitergegeben, Alex meldet sich persönlich bei dir."
```

### Heikle Themen: ausweichen statt schweigen

Im Freigabe-Modus blockiert der Filter bei Preisen, Adressen und Kontaktdaten
komplett. Im Assistenzmodus wäre das schlecht – der Absender bliebe ohne
Rückmeldung. Stattdessen antwortet eine **feste Formel**, kein Modelltext: bei
genau diesen Themen ist eine erfundene Antwort deutlich schädlicher als eine
langweilige. Du bekommst die Nachricht trotzdem gemeldet.

Abschaltbar mit `deflect_handover_topics: false` – dann bleiben solche
Nachrichten unbeantwortet und gehen nur an dich.

### Was gleich bleibt

**Harte Blocker gelten weiter.** Minderjährige, Nötigung, ungeschützt,
Betrugsmuster → keine automatische Antwort, Thread markiert, Meldung an dich.
Der Assistenzmodus lockert den Sicherheitsfilter an keiner Stelle.

**Rate-Limits und Ruhezeiten gelten weiter** – im autonomen Betrieb sogar
wichtiger, weil niemand mehr drüberschaut, bevor gesendet wird.

**Du siehst alles mit.** Jede automatisch gesendete Antwort kommt per Telegram
bei dir an, inklusive Notiz, was die Offenlegungsschicht geändert hat. Autonom
heißt nicht unbeobachtet.

Testen ohne Modell-Download und ohne Browser:

```bash
# in config.assistant.yaml  ai.backend: "template"
python run.py -c config.assistant.yaml ai-test "Hallo, ist das noch aktuell?"
python run.py -c config.assistant.yaml ai-test "Bist du ein Bot?"
python run.py -c config.assistant.yaml ai-test "Was kostet das denn?"
```

---

## Schnellstart Windows

Voraussetzung: [Python 3.11+](https://www.python.org/downloads/). Beim
Installieren zwei Häkchen setzen: **Add python.exe to PATH** und **tcl/tk and
IDLE** (Letzteres liefert die Oberfläche — ohne das startet nur die
Kommandozeilenversion).

Dann **`AUF-DESKTOP-INSTALLIEREN.bat` doppelklicken.** Das Skript legt den
Ordner `markt-de-assistant` auf dem Desktop an, richtet die Python-Umgebung ein,
installiert Pakete und Chromium, erstellt `config.yaml` und `.env` aus den
Vorlagen und legt eine Desktop-Verknüpfung an. Danach öffnet sich die
Oberfläche.

Ein zweiter Lauf aktualisiert nur die Programmdateien — `config.yaml`, `.env`,
das Browser-Profil und die Datenbank bleiben unangetastet.

### Von Hand

Wer lieber selbst einrichtet:

```powershell
git clone https://github.com/FootguyM/markt-de-assistant.git
cd markt-de-assistant
powershell -ExecutionPolicy Bypass -File scripts\setup_windows.ps1
```

Danach:

**1. Zugangsdaten eintragen** – `.env` im Editor öffnen:

```ini
MARKT_USERNAME=deine@email.de
MARKT_PASSWORD=dein-passwort
TELEGRAM_BOT_TOKEN=1234567890:AA...
TELEGRAM_CHAT_ID=123456789
```

**2. Ohne Modell-Download testen** – in `config.yaml` `ai.backend: "template"`
setzen, dann:

```powershell
.venv\Scripts\python.exe run.py ai-test "Hallo, bist du heute Abend frei?"
```

**3. Einmal anmelden** – öffnet ein sichtbares Browserfenster; Cookie-Banner und
eventuelles Captcha löst du hier von Hand. Das Profil landet in `profiles/` und
wird ab da wiederverwendet:

```powershell
.venv\Scripts\python.exe run.py login
```

**4. Selektoren prüfen** (siehe [unten](#wenn-selektoren-brechen)):

```powershell
.venv\Scripts\python.exe run.py doctor
```

**5. Starten:**

```powershell
.venv\Scripts\python.exe run.py
```

Web-UI: <http://127.0.0.1:8765>

---

## Die Oberfläche

Doppelklick auf die Desktop-Verknüpfung, oder im Ordner:

```bash
python gui.py
```

Ein Fenster mit drei Reitern, das ohne installierte Pakete startet — Tkinter
liegt jeder Python-Installation bei. Das ist Absicht: die Einrichtung soll aus
der Oberfläche heraus laufen können, nicht erst danach zur Verfügung stehen.

**Übersicht** — Systemcheck (Pakete, Browser, Konfiguration, Anmeldung),
Auswahl der Betriebsart, Trockenlauf-Schalter, Start/Stopp und ein Knopf zum
Web-Dashboard.

**Einrichtung** — Felder für markt.de-Zugang, Telegram und Proxy; Speichern
schreibt nach `.env`, ohne die Kommentare der Vorlage zu zerstören. Darunter die
Einrichtungsschritte als Knöpfe: Pakete installieren, Browser installieren, bei
markt.de anmelden, Selektoren prüfen, KI testen.

**Protokoll** — die Ausgabe des Bots in Echtzeit, farblich nach Fehlern,
Warnungen und Erfolgen sortiert.

Der Bot läuft dabei als eigener Prozess. Das kostet etwas Umstand bei der
Ausgabe, hat aber zwei Vorteile: ein Absturz des Bots nimmt die Oberfläche nicht
mit, und „Stoppen" ist ein sauberes Prozessende statt eines halb abgeräumten
Event-Loops.

Die eigentliche Arbeit — Entwürfe lesen und freigeben, Verläufe ansehen,
Anzeigen verwalten — passiert weiterhin im Web-Dashboard oder in Telegram. Das
Fenster ist Schaltzentrale und Einrichtung.

> Auf dem Raspberry Pi im Dauerbetrieb wird die Oberfläche nicht gebraucht —
> dort läuft `run.py headless` als systemd-Dienst, gesteuert über Telegram.

---

## Schnellstart Raspberry Pi

Voraussetzung: **Raspberry Pi OS 64 Bit**. Auf einem 32-Bit-System gibt es weder
brauchbares Chromium noch llama.cpp. Empfohlen: Pi 5 mit 8 GB.

```bash
git clone https://github.com/FootguyM/markt-de-assistant.git
cd markt-de-assistant
chmod +x scripts/setup_pi.sh
./scripts/setup_pi.sh
```

Das Skript installiert Systempakete, vergrößert die Auslagerungsdatei (sonst
bricht der llama.cpp-Build ab), baut die Python-Umgebung und trägt das
System-Chromium ein.

**Browser-Profil vom PC mitbringen.** Das ist der wichtigste Schritt: melde dich
einmal am PC an (`run.py login`) und kopiere das Profil rüber. Damit muss auf
dem Pi kein Captcha ohne Bildschirm gelöst werden.

```bash
scp -r profiles/ pi@raspberrypi:~/markt-de-assistant/
```

**Kleineres Modell eintragen** – in `config.yaml` unter `ai.llama_cpp`:

```yaml
repo_id:  "bartowski/Qwen2.5-3B-Instruct-GGUF"
filename: "Qwen2.5-3B-Instruct-Q4_K_M.gguf"
```

**Als Dienst einrichten:**

```bash
sudo cp deploy/marktbot.service /etc/systemd/system/
sudo nano /etc/systemd/system/marktbot.service   # Benutzer und Pfade prüfen
sudo systemctl daemon-reload
sudo systemctl enable --now marktbot
journalctl -u marktbot -f
```

---

## Konfiguration

Zwei Dateien, beide per `.gitignore` ausgeschlossen:

| Datei | Inhalt |
|---|---|
| `.env` | Zugangsdaten, Telegram-Token, Proxy — alles Geheime |
| `config.yaml` | Verhalten: Tempo, Limits, Persona, KI-Backend |

Beide entstehen beim Setup aus `.env.example` und `config.example.yaml`. Die
Kommentare dort erklären jede Option; hier nur die Stellschrauben, die man
wirklich anfasst:

```yaml
persona:
  display_name: "Alex"
  description: >
    Locker, freundlich, kurz angebunden. Schreibt wie in einer normalen Chat-App.
  rules:
    - "Antworte auf Deutsch, per Du."
    - "Maximal 3 kurze Saetze."
    - "Keine Preise, Adressen, Telefonnummern oder Kontodaten nennen."

replies:
  require_approval: true        # false = Vollautomatik
  disclosure: ""                # z.B. "(automatische Antwort)"

schedule:
  inbox_poll_min: 240           # zufälliges Abrufintervall in Sekunden
  inbox_poll_max: 900
  quiet_hours:
    start: "23:30"
    end: "07:30"
  limits:
    replies_per_hour: 8
    replies_per_day: 40
```

`persona.description` und `persona.rules` sind die wirksamsten Hebel für den
Tonfall – deutlich wirksamer als ein größeres Modell.

---

## Modellwahl

Das Backend `llama_cpp` lädt eine öffentliche GGUF-Datei von Hugging Face
(kein Token) und rechnet lokal. Faustregel für die Auswahl:

| Gerät | Modell | Datei | RAM | Tempo |
|---|---|---|---|---|
| PC, 16 GB+ | `bartowski/Qwen2.5-7B-Instruct-GGUF` | `…Q4_K_M.gguf` | ~6 GB | 5–15 s |
| PC, 8 GB | `bartowski/Qwen2.5-3B-Instruct-GGUF` | `…Q4_K_M.gguf` | ~3 GB | 5–20 s |
| Pi 5, 8 GB | `bartowski/Qwen2.5-3B-Instruct-GGUF` | `…Q4_K_M.gguf` | ~3 GB | 40–90 s |
| Pi 4, 4 GB | `bartowski/Llama-3.2-1B-Instruct-GGUF` | `…Q4_K_M.gguf` | ~1 GB | 30–60 s |

Qwen 2.5 schreibt brauchbares Deutsch und ist für die kurzen Antworten hier gut
geeignet. Die Antwortzeit spielt kaum eine Rolle – der Assistent wartet ohnehin
bewusst, bevor er antwortet.

Weitere Backends (`ai.backend` in `config.yaml`):

- `transformers` – volle Modellauswahl über torch, nur für den PC mit viel RAM
- `hf_inference` – Hugging Face Inference API, schnell, **braucht ein Token**
- `template` – keine KI, feste Textbausteine; zum Testen ohne GB-Download

---

## In der Cloud testen

Bevor der Pi angefasst wird, lässt sich fast alles woanders prüfen. Zwei Dinge
sind dabei sauber zu trennen: **die Software** kannst du überall testen, die
**Verbindung zu markt.de** solltest du nicht aus einem Rechenzentrum aufbauen —
eine fremde Datacenter-IP an deinem Account ist genau das Muster, das eine
Sicherheitsabfrage auslöst.

### Trockenlauf

Der Schalter dafür hängt an jedem Befehl:

```bash
python run.py --dry-run
```

Abruf, Sicherheitsfilter, KI, Rate-Limits, Telegram und Web-UI laufen exakt wie
im Echtbetrieb. Nur der letzte Schritt — das Absenden an markt.de — wird
übersprungen und stattdessen protokolliert. Telegram und Dashboard schreiben
`TROCKENLAUF` in die Statuszeile, damit kein Zweifel aufkommt.

### Wo testen

| Umgebung | Wofür | Kosten |
|---|---|---|
| **Oracle Cloud Free Tier (ARM)** | Der beste Test vor dem Pi: `aarch64`, also dieselbe Architektur. Du prüfst den llama.cpp-Build, das Modelltempo und `setup_pi.sh` unter realen Bedingungen. | kostenlos |
| **Hetzner CAX11 (ARM)** | Dasselbe, aber zuverlässig verfügbar und in Deutschland | ~4 €/Monat |
| **GitHub Codespaces** | Schnell für Web-UI, Telegram, Sicherheitsfilter und KI. x86, sagt also nichts über das Pi-Tempo aus. | 60 h/Monat frei |

Auf einer ARM-Instanz ist die Reihenfolge dieselbe wie auf dem Pi — nur dass ein
Fehlschlag nichts kostet:

```bash
./scripts/setup_pi.sh                    # baut llama.cpp, dauert 10-25 min
python run.py ai-test                    # lädt das Modell, misst das Tempo
python run.py --dry-run headless         # voller Lauf, ohne zu senden
```

### Was in der Cloud sinnvoll bleibt

Ohne markt.de-Zugriff funktionieren: `ai-test` (Persona, Tonfall,
Sicherheitsfilter), die komplette Telegram-Steuerung, das Web-UI, die
Anzeigenvorlagen und `pytest`. Das ist der Großteil dessen, was man vor dem
Produktivlauf wissen will.

Nur `login`, `doctor`, `check` und `ads` sprechen mit markt.de. Für die gilt:
entweder von zuhause laufen lassen, oder mit demselben Residential-Proxy, den
du später auch produktiv nutzt.

---

## Bandbreite und Residential Proxy

Residential-Proxys rechnen pro Gigabyte ab, und Playwright lädt standardmäßig
die komplette Seite — Bilder, Videos, Fonts, Tracker. Ein einzelner
Postfach-Aufruf kann zweistellige Megabyte kosten, obwohl der Bot nur ein paar
Zeilen Text braucht. Bei ein paar hundert Abrufen am Tag übersteigen die
Proxy-Kosten schnell die Serverkosten.

Der Filter ist deshalb **standardmäßig an**:

```yaml
browser:
  block_resources: true
  blocked_resource_types: ["image", "media", "font"]
```

Zwei bewusste Ausnahmen:

- **Stylesheets bleiben erlaubt.** Playwright entscheidet über `state="visible"`
  anhand des tatsächlichen Layouts. Ohne CSS ändert sich die Sichtbarkeit von
  Elementen, und Selektoren fangen an, sprunghaft zu versagen. Die paar Kilobyte
  sind den Ärger nicht wert.
- **Captcha-Ressourcen kommen immer durch**, egal was konfiguriert ist. Sonst
  bekämst du bei einer Sicherheitsabfrage einen Screenshot, auf dem nichts zu
  sehen ist.

Wie viel es bringt, steht in `/status` und im Dashboard („Requests geblockt"),
und beim Beenden im Log. **Screenshots zeigen die Seite dann ohne Bilder** — für
die Selektor-Diagnose reicht das, und Sicherheitsabfragen sind ja ausgenommen.

### Proxy einrichten

```ini
# .env
PROXY_SERVER=http://de.anbieter.com:10000
PROXY_USERNAME=nutzer-session-abc123-country-de
PROXY_PASSWORD=...
```

```yaml
# config.yaml
browser:
  use_proxy: true
```

**Sticky Sessions sind Pflicht.** Die meisten Anbieter rotieren die IP pro
Request — das ist für Scraping gedacht und hier ein Totalschaden: Login aus
Hamburg, Postfach aus München, Antwort aus Köln, alles in einer Minute mit
demselben Cookie. Achte auf eine Session-Haltedauer von mindestens 10 Minuten
und Geo-Targeting auf Deutschland. Ohne das ist ein Gerät bei dir zuhause die
klar bessere Lösung.

**Den Erstlogin nicht über den Proxy machen.** Melde dich lokal an und kopiere
`profiles/` auf den Server.

---

## Telegram

Bot bei [@BotFather](https://t.me/BotFather) anlegen, Token und die eigene
Chat-ID in `.env` eintragen. Die Chat-ID bekommt man z. B. über
[@userinfobot](https://t.me/userinfobot).

**Nur die eingetragene Chat-ID darf steuern.** Alles andere wird abgewiesen und
protokolliert.

| Befehl | Wirkung |
|---|---|
| `/status` | Zustand, Limits, offene Entwürfe |
| `/pruefen` | Sofort nach neuen Nachrichten sehen |
| `/postfach` | Letzte Konversationen mit IDs |
| `/entwuerfe` | Offene Entwürfe mit Freigabe-Knöpfen |
| `/antwort <id> <text>` | Selbst antworten |
| `/anzeigen` | Eigene Anzeigen auflisten |
| `/vorlagen` | Vorlagen aus `ads/` |
| `/neu <vorlage>` | Anzeige aufgeben |
| `/hoch <id>` | Anzeige hochschieben |
| `/stoppen <id>` | Anzeige pausieren |
| `/loeschen <id>` | Anzeige löschen |
| `/pause` · `/weiter` | Automatik anhalten / fortsetzen |
| `/screenshot` | Aktuelle Browseransicht als Bild |
| `/code <ziffern>` | 2FA-Code eintragen |
| `/doctor` | Selektoren prüfen |

Bei jedem Entwurf kommen drei Knöpfe: **Senden**, **Ändern** (der Bot fragt nach
neuem Text und schickt ihn dann), **Verwerfen**.

> **Token-Hinweis:** Ein Bot-Token, der einmal in einem Chat, Screenshot oder
> Commit gelandet ist, gilt als kompromittiert. Bei @BotFather mit `/revoke`
> einen neuen erzeugen und nur in `.env` ablegen.

---

## Web-UI

`python run.py` startet das Dashboard auf <http://127.0.0.1:8765>.

Vier Bereiche: **Entwürfe** (bearbeiten und senden), **Postfach** (Verläufe
lesen, selbst antworten, Entwurf neu erzeugen lassen), **Anzeigen** (verwalten
und aus Vorlagen aufgeben), **Protokoll** (alle Aktionen mit Zeitstempel).

Bewusst als Web-UI statt als Desktop-Fenster: derselbe Code läuft am PC und auf
dem Pi, und auf dem Pi muss kein GUI-Toolkit kompiliert werden.

Standardmäßig lauscht der Server nur auf `127.0.0.1`. Wer ihn im Heimnetz
erreichbar machen will, setzt `ui.host: "0.0.0.0"` **und** `UI_PASSWORD` in
`.env` – ohne Passwort verweigert der Assistent den Start. Von unterwegs besser
per SSH-Tunnel statt offen ins Internet:

```bash
ssh -L 8765:127.0.0.1:8765 pi@raspberrypi
```

---

## Anzeigen verwalten

Jede `ads/*.yaml` ist eine Vorlage; der Dateiname ohne Endung ist ihr Name:

```yaml
# ads/meine_anzeige.yaml
title: "Titel der Anzeige"
description: |
  Mehrzeiliger Anzeigentext.
  Zeilenumbrüche bleiben erhalten.
price: ""
location: "Berlin"
postal_code: "10115"
images:
  - "bilder/foto1.jpg"
```

Aufgeben mit `/neu meine_anzeige` oder per Knopf im Web-UI.

**Einschränkung, die man kennen muss:** Das Formular „Anzeige aufgeben“ ist bei
markt.de mehrstufig und hängt an der gewählten Kategorie. Der Assistent füllt
Titel, Beschreibung, Preis, PLZ und Bilder aus. Wenn ein Schritt unklar ist –
typischerweise die Kategoriewahl – bricht er ab, lässt das Formular offen stehen
und schickt dir einen Screenshot. Du klickst zu Ende. Für die üblichen Fälle
reicht es, die Kategorie einmal von Hand zu wählen.

Automatisches Hochschieben lässt sich einschalten:

```yaml
ads:
  auto_renew: true
  auto_renew_after_days: 7
```

---

## Wenn Selektoren brechen

**Das ist der Teil, der Pflege braucht – bitte einmal lesen.**

markt.de ändert sein HTML ohne Vorwarnung. Deshalb steht im Code kein einziger
fester Selektor, sondern pro Element eine Kandidatenliste (`src/marktbot/markt/selectors.py`),
die von sehr spezifisch bis zu generischen Fallbacks über ARIA-Rollen und
Textinhalt reicht. Findet der Assistent ein Element nicht, meldet er, *welches*
fehlt, und legt Screenshot plus HTML-Dump in `data/screenshots/` ab.

Prüfen, was gerade greift:

```bash
python run.py doctor                                  # Postfach
python run.py doctor https://www.markt.de/meins/anzeigen/
```

Korrigieren, ohne Code anzufassen – `selectors.example.yaml` nach
`selectors.yaml` kopieren und eintragen:

```yaml
reply_input:
  - "css=textarea.message-composer__input"
reply_submit:
  - "css=button.message-composer__send"
```

Eigene Einträge werden **vor** den eingebauten probiert; die Defaults bleiben als
Auffangnetz. Den passenden Selektor findest du in Chrome per Rechtsklick →
*Untersuchen* → im DevTools-Baum Rechtsklick → *Copy* → *Copy selector*.

---

## Residential IP und Browser-Identität

Der Assistent fährt ein **echtes, dauerhaftes Chromium-Profil** aus `profiles/`.
Cookies, LocalStorage und Login überleben Neustarts – wie bei einem Menschen, der
seinen Browser zumacht und wieder aufmacht. Ein frisches Profil bei jedem Start
wäre das auffälligste Verhalten überhaupt.

Dazu kommen deutsche Locale und Zeitzone, eine gewöhnliche Fenstergröße,
zeichenweises Tippen mit variabler Geschwindigkeit und Denkpausen,
unregelmäßige Abrufintervalle, Ruhezeiten und harte Obergrenzen.

**Zur IP:** Wenn der Pi zuhause am eigenen Anschluss hängt, *ist* das bereits eine
deutsche Privatanschluss-IP – da ist nichts weiter zu tun, und das ist der
sauberste Aufbau. Ein Proxy wird nur gebraucht, wenn der Assistent woanders läuft:

```ini
# .env
PROXY_SERVER=http://proxy.anbieter.de:8000
PROXY_USERNAME=nutzer
PROXY_PASSWORD=passwort
```

```yaml
# config.yaml
browser:
  use_proxy: true
```

**Was hier bewusst nicht drin ist:** Fingerprint-Spoofing (Patchen von
`navigator`-Eigenschaften, Canvas-Rauschen), Captcha-Solver-Dienste oder
Account-Rotation. Der Assistent verhält sich wie ein langsamer, höflicher Nutzer
mit einem echten Browser – er verschleiert nicht, was er ist. Captcha und 2FA
landen als Screenshot bei dir statt umgangen zu werden.

---

## Sicherheitsfilter

Läuft vor der KI (auf der eingehenden Nachricht) und nach der KI (auf dem
Entwurf). `src/marktbot/ai/safety.py`, abgedeckt von 40+ Tests.

**Harte Blocker** – kein Entwurf, Thread wird markiert, Meldung an dich:
Hinweise auf Minderjährige, Zwang und Nötigung, ungeschützter Verkehr,
Betrugsmuster (Gutscheine, Western Union, Krypto-Vorkasse, Überzahlungstrick).

**Übergabe an dich** – die KI hält sich raus: Preise und Geld, Adressen,
Telefonnummern und Messenger-Kontakte, Verifizierungsanfragen.

**Ausgehend gestoppt** – auch bei selbst getippten Antworten: IBAN und
Bankdaten, Telefonnummern, E-Mail-Adressen, konkrete Straßenadressen. Im
Assistenzmodus zusätzlich jede Nachricht, die behauptet, ein Mensch zu sein.

Die Muster melden bewusst lieber einmal zu viel. Eigene ergänzen:

```yaml
safety:
  extra_blocklist:
    - "\\bstammkunde\\b"
```

---

## Architektur

```
AUF-DESKTOP-INSTALLIEREN.bat   Windows: legt alles auf dem Desktop an
gui.py                    Desktop-Oberfläche (Tkinter, ohne Zusatzpakete)
run.py                    CLI: run · assistant · ui · headless · login · doctor · check · ads · ai-test
└── marktbot/
    ├── app.py            Orchestrator + Telegram + Web-UI in einem Event-Loop
    ├── config.py         config.yaml + .env → geprüftes Config-Objekt
    ├── models.py         Thread, Message, Draft, Ad, …
    ├── storage.py        SQLite: Verläufe, Entwürfe, Anzeigen, Aktionsprotokoll
    ├── browser/
    │   ├── session.py    persistentes Chromium-Profil, Proxy, Screenshots
    │   └── humanize.py   Tippgeschwindigkeit, Pausen, Scrollen
    ├── markt/
    │   ├── selectors.py  Kandidatenlisten + Fallback-Auflösung
    │   ├── auth.py       Login, Cookie-Banner, Captcha/2FA an den Menschen
    │   ├── inbox.py      Konversationen lesen, Antworten senden
    │   └── ads.py        Anzeigen auflisten, anlegen, ändern, hochschieben
    ├── ai/
    │   ├── huggingface.py  4 Backends: llama_cpp · transformers · hf_inference · template
    │   ├── prompt.py       Prompt-Bau (Persona- und Assistenzmodus), Nachbearbeitung
    │   ├── safety.py       Sicherheitsfilter: allow · handover · block
    │   ├── disclosure.py   garantierte KI-Kennzeichnung im Assistenzmodus
    │   └── responder.py    Verlauf rein, geprüfter Entwurf raus
    ├── core/
    │   ├── orchestrator.py Kern; Telegram und UI rufen nur hier hinein
    │   ├── ratelimit.py    Limits und Ruhezeiten (persistent über Neustarts)
    │   └── notifier.py     Benachrichtigungskanäle
    ├── telegrambot/bot.py  Fernsteuerung
    └── ui/
        ├── server.py       FastAPI + Web-Dashboard
        ├── desktop.py      Desktop-Fenster
        └── envfile.py      .env lesen/schreiben ohne Kommentarverlust
```

Alle Browser-Zugriffe laufen über einen gemeinsamen Lock, damit sich
Hintergrundschleife, Telegram-Kommandos und Web-UI nicht in die Quere kommen.
Rate-Limits liegen in SQLite und überleben Neustarts – sonst könnte man das
Tageslimit durch einen Neustart umgehen.

Tests:

```bash
pip install -r requirements-dev.txt
pytest -q
```

---

## Fehlersuche

| Symptom | Ursache und Abhilfe |
|---|---|
| „Element … nicht gefunden“ | Markup hat sich geändert → `run.py doctor`, `selectors.yaml` anpassen |
| Login schlägt fehl | `run.py login` mit sichtbarem Browser, Captcha von Hand lösen |
| Captcha auf dem Pi | Profil am PC anmelden und `profiles/` rüberkopieren |
| Keine Entwürfe | Wahrscheinlich Sicherheitsfilter → `/status` und Protokoll ansehen |
| Modell lädt nicht | Plattenplatz prüfen; auf dem Pi kleineres Modell eintragen |
| `llama-cpp-python` baut nicht | Swap zu klein → `scripts/setup_pi.sh` erhöht ihn auf 2 GB |
| Bot antwortet nicht in Telegram | Chat-ID in `.env` prüfen; nur die eingetragene ID darf steuern |
| `gui.py` startet nicht | Tkinter fehlt → Python neu installieren mit „tcl/tk and IDLE", auf Linux `sudo apt install python3-tk` |
| Installer findet kein Python | Beim Installieren „Add python.exe to PATH" nicht angekreuzt → Python neu installieren |
| `assistant.identification ist leer` | Assistenzmodus braucht die Kennzeichnung – ohne sie kein autonomer Betrieb |
| Assistent stellt sich zu oft vor | `identify_on_first_reply` gilt pro Konversation; bei jedem Erstkontakt ist das gewollt |
| „Nicht gesendet: Ruhezeit“ | `schedule.quiet_hours` in `config.yaml` |

Mehr Details ins Log:

```yaml
logging:
  level: "DEBUG"
```

Zugangsdaten und Token werden aus dem Log herausgefiltert, bevor es geschrieben
wird (`logging_setup.py`).

---

## Grenzen und Rechtliches

- **Automatisierung kann gegen die AGB von markt.de verstoßen.** Prüfe das selbst;
  im Zweifel droht eine Accountsperre. Die Limits und Ruhezeiten sind so gesetzt,
  dass der Assistent den Betrieb der Gegenseite nicht belastet.
- **Die Selektoren sind nicht offiziell** und werden brechen. Rechne mit
  gelegentlicher Nachpflege über `selectors.yaml`.
- **Verantwortung für das Gesendete bleibt bei dir.** Deshalb ist der
  Freigabe-Modus die Voreinstellung. Wer autonom fahren will, nimmt den
  Assistenzmodus – dort weiß das Gegenüber, womit es schreibt.
- **Kennzeichnungspflicht:** Wenn du autonom antworten lässt, ohne offenzulegen,
  dass ein Programm schreibt, bewegst du dich je nach Kontext im Bereich
  irreführender Geschäftspraktiken. Der Assistenzmodus ist auch deshalb so
  gebaut, wie er gebaut ist.
- **Personenbezogene Daten** aus den Verläufen landen in `data/marktbot.db` auf
  deinem Gerät. Nachrichteninhalte werden standardmäßig *nicht* ins Log
  geschrieben (`logging.log_message_bodies: false`).
- **Nichts verlässt dein Gerät** außer den Anfragen an markt.de und den
  Telegram-Nachrichten an dich. Die KI rechnet lokal.
