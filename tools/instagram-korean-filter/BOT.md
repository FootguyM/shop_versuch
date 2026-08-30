# Telegram-Bot: Follower mit koreanischen Profilnamen finden

Der Bot geht die Followerliste eines Instagram-Accounts durch, prüft bei jedem
Profil den **Profilnamen** auf koreanische Zeichen und schickt dir die Treffer
per Telegram — Etappe für Etappe, am Ende noch einmal als komplette Liste plus
CSV-Datei.

Er läuft als Dauerprogramm auf deinem **Raspberry Pi** (oder jedem anderen
Rechner, der durchlaufen kann). Bedient wird er vom Handy aus über Telegram.
Kosten entstehen keine: kein bezahlter Dienst, keine API-Gebühren — nur dein
Instagram-Konto und der Strom für den Pi.

---

## Zuerst zwei ehrliche Hinweise

1. **Der Pi muss laufen, während gescannt wird.** Er ist das Programm, das
   arbeitet — dein Handy schickt nur Befehle und bekommt die Ergebnisse. Ist
   der Pi aus, passiert nichts; ist er wieder an, macht der Bot dort weiter,
   wo er aufgehört hat.
2. **Instagram mag automatische Abfragen nicht.** Der Bot arbeitet deshalb
   betont langsam und in Etappen. Trotzdem kann Instagram drosseln oder einen
   Sicherheits-Check verlangen. Nimm dafür ein Zweitkonto, nicht deinen
   Hauptaccount. Von deinem heimischen Anschluss fällt es allerdings deutlich
   weniger auf als aus einem Rechenzentrum.

---

## Einrichtung auf dem Pi

Voraussetzung: **Node.js 18 oder neuer**. Prüfen mit `node --version`;
falls es fehlt: `sudo apt install nodejs npm`.

### 1. Telegram-Bot anlegen

In Telegram **@BotFather** anschreiben → `/newbot` → Namen und Benutzernamen
vergeben. Am Ende bekommst du ein Token der Form `123456789:AAH…`.

### 2. Instagram-Konto und Cookie

Followerlisten gibt Instagram nur an eingeloggte Besucher heraus — deshalb
braucht der Bot ein Konto. Nimm ein Zweitkonto. Ein frisch angelegtes fällt
besonders schnell auf, wenn es sofort tausende Profile abruft: lass es ein paar
Tage normal stehen, folge ein paar Accounts, und fang dann klein an mit
`/scan name 200`. Die Followerliste eines **privaten** Profils sieht es
außerdem erst, wenn es ihm folgen darf.

**Cookie auslesen:** am Computer mit diesem Konto bei instagram.com einloggen →
F12 → Tab **Application** (Firefox: **Speicher**) → **Cookies** →
`https://www.instagram.com` → den Wert von **`sessionid`** kopieren.

### 3. Projekt auf den Pi holen und einstellen

```bash
git clone https://github.com/FootguyM/shop_versuch.git
cd shop_versuch/tools/instagram-korean-filter
cp bot.env.example bot.env
chmod 600 bot.env
nano bot.env
```

In `bot.env` mindestens diese beiden Zeilen ausfüllen:

```
TELEGRAM_BOT_TOKEN=123456789:AAH…
IG_SESSIONID=der_kopierte_cookie_wert
```

Die Datei ist von der Versionsverwaltung ausgenommen, deine Zugangsdaten landen
also nicht auf GitHub.

### 4. Probelauf

```bash
node bot.mjs
```

Im Terminal sollte „Dauerbetrieb — warte auf Befehle" erscheinen. Jetzt in
Telegram den Chat mit deinem Bot öffnen und `/start` schicken — er antwortet mit
der Befehlsübersicht. (Ein Telegram-Bot darf dich **nicht** von sich aus
anschreiben; erst dein `/start` öffnet den Kanal.) Dann ein kleiner Test:
`/scan irgendeinaccount 100`. Beenden mit `Strg+C` — der Stand bleibt erhalten.

### 5. Als Dienst einrichten (läuft ab jetzt von selbst)

Damit der Bot nach jedem Neustart des Pi wieder hochkommt:

```bash
sudo cp deploy/instagram-korean-bot.service /etc/systemd/system/
sudo nano /etc/systemd/system/instagram-korean-bot.service   # Pfade/Benutzer prüfen
sudo systemctl daemon-reload
sudo systemctl enable --now instagram-korean-bot
```

Die Datei geht von Benutzer `pi` und dem Pfad
`/home/pi/shop_versuch/tools/instagram-korean-filter` aus — falls das bei dir
anders heißt, in den Zeilen `User=`, `WorkingDirectory=` und `ReadWritePaths=`
anpassen.

Nachsehen, was er tut:

```bash
systemctl status instagram-korean-bot
journalctl -u instagram-korean-bot -f
```

---

## Benutzung vom Handy

| Befehl | Wirkung |
| --- | --- |
| `/scan vikavalora` | startet den Scan dieser Followerliste |
| `/scan vikavalora 500` | prüft nur die ersten 500 Follower |
| `/status` | Zwischenstand: wie viele Profile geprüft, wie viele Treffer |
| `/stop` | hält den Scan an (Stand bleibt gespeichert) |
| `/weiter` | macht dort weiter, wo er aufgehört hat |
| `/liste` | schickt die komplette Trefferliste noch einmal, inkl. CSV-Datei |
| `/hilfe` | Übersicht aller Befehle |

**Wie schnell geht das?** Mit den Vorgaben prüft der Bot 50 Profile alle 12
Sekunden und legt nach je 500 Profilen zwei Minuten Pause ein — macht rund
**7500 Profile pro Stunde**. Eine Liste mit 50.000 Followern ist also in etwa
sieben Stunden durch. Nach jeder Etappe bekommst du die neu gefundenen Treffer
geschickt, am Ende die vollständige Liste und eine CSV-Datei.

Schneller geht über `BOT_DELAY_MS` und `BOT_ETAPPE_PAUSE_SECONDS` in `bot.env`
— auf eigenes Risiko, das ist genau die Schraube, an der Instagram merkt, dass
da niemand von Hand scrollt.

**Befehle wirken sofort.** Der Bot horcht dauerhaft am Telegram-Anschluss, auch
während er eine Seite abarbeitet; `/stop` greift binnen Sekunden.

---

## Wenn etwas klemmt

**Der Bot antwortet nicht.** Läuft der Dienst? `systemctl status
instagram-korean-bot`. Hast du ihm `/start` geschickt? Stimmt der Name in
`TELEGRAM_ALLOWED_USERNAME`? Fremde Absender ignoriert er wortlos — im Log
steht dann „Nachricht von @… ignoriert".

**„Das Instagram-Cookie ist abgelaufen."** Cookie neu auslesen (Schritt 2), in
`bot.env` eintragen, `sudo systemctl restart instagram-korean-bot`, dann im Chat
`/weiter`. Der Fortschritt bleibt erhalten.

**„Diese Etappe ging schief."** Meist bremst Instagram gerade. Der Bot wartet
zwei Minuten und versucht es erneut; erst nach drei Fehlschlägen in Folge hält
er an und wartet auf dein `/weiter`. Bei hartnäckigen Problemen `BOT_DELAY_MS`
erhöhen (z.B. `30000`).

**Privates Profil.** Die Followerliste ist nur abrufbar, wenn der Account
öffentlich ist oder dein Konto ihm folgt. Sonst sagt der Bot das direkt.

**Pi war aus.** Nichts verloren: Der Zwischenstand liegt in
`.botstate/state.json`. Nach dem Hochfahren startet der Dienst von selbst und
setzt den Scan fort.

---

## Einstellungen

Alles steht in `bot.env` (Vorlage: `bot.env.example`):

| Variable | Standard | Bedeutung |
| --- | --- | --- |
| `BOT_DELAY_MS` | `12000` | Pause zwischen zwei Abrufen (leicht zufällig gestreut) |
| `BOT_PAGE_SIZE` | `50` | Profile pro Abruf |
| `BOT_STAGE_SIZE` | `500` | nach so vielen Profilen: Treffer melden und länger pausieren |
| `BOT_ETAPPE_PAUSE_SECONDS` | `120` | Länge dieser Pause |
| `BOT_ERROR_PAUSE_SECONDS` | `120` | Wartezeit nach einem Fehler |
| `BOT_MAX_LIST` | `500` | so viele Treffer stehen am Ende im Chat, der Rest in der CSV |
| `BOT_MAX_HITS` | `20000` | Obergrenze gespeicherter Treffer |
| `BOT_STATE_FILE` | `.botstate/state.json` | wo der Zwischenstand liegt |

Zum Testen ohne Dauerbetrieb: `node bot.mjs --once` arbeitet, bis nichts mehr
zu tun ist, und beendet sich dann.

---

## Was auf dem Pi bleibt

Zwischenstand und Ergebnisse liegen ausschließlich auf dem Pi
(`.botstate/state.json`), die Zugangsdaten in `bot.env`. Beides ist von der
Versionsverwaltung ausgenommen — auf GitHub landet nur der Programmcode. Ob das
Repository öffentlich oder privat ist, spielt für deine Daten daher keine Rolle
mehr.
