# Telegram-Bot: Follower mit koreanischen Profilnamen finden

Der Bot geht die Followerliste eines Instagram-Accounts durch, prüft bei jedem
Profil den **Profilnamen** auf koreanische Zeichen und schickt dir die Treffer
per Telegram — Etappe für Etappe, am Ende noch einmal als komplette Liste plus
CSV-Datei.

Er läuft **kostenlos bei GitHub** (GitHub Actions), nicht auf deinem Rechner und
nicht über den Shop. Du brauchst dafür nur dein Handy: Telegram öffnen,
`/scan accountname` schreiben, warten.

---

## Zuerst drei ehrliche Hinweise

1. **Das Repository ist öffentlich.** Der Bot legt seinen Zwischenstand — also
   auch die gefundenen Namen — im Zweig `bot-state` ab, und der ist damit für
   alle lesbar. Wenn dir das nicht recht ist: Repository auf **privat**
   umstellen (GitHub → Settings → General → ganz unten „Change repository
   visibility"). Dann sind pro Monat 2000 Action-Minuten frei — dafür in
   `.github/workflows/instagram-korean-bot.yml` die Zeile `- cron: '*/15 * * * *'`
   auf `'*/30 * * * *'` ändern, damit es reicht.
2. **Instagram mag automatische Abfragen nicht**, und Anfragen aus einem
   Rechenzentrum (wie bei GitHub) fallen stärker auf als von zu Hause. Der Bot
   arbeitet deshalb betont langsam. Trotzdem kann es passieren, dass Instagram
   bremst oder dein Login einen Sicherheits-Check verlangt. Nimm dafür besser
   nicht deinen wichtigsten Account.
3. **Das Instagram-Cookie läuft irgendwann ab.** Dann meldet sich der Bot bei
   dir und du hinterlegst ein neues (Schritt 3 unten). Dein Fortschritt bleibt
   dabei erhalten.

---

## Einrichtung (einmalig, ca. 10 Minuten)

### 1. Telegram-Bot anlegen

In Telegram **@BotFather** anschreiben → `/newbot` → Namen und Benutzernamen
vergeben. Am Ende bekommst du ein Token der Form
`123456789:AAH...`. Das ist dein `TELEGRAM_BOT_TOKEN`.

### 2. Instagram-Cookie auslesen

Am Computer bei instagram.com einloggen → F12 → Tab **Application**
(Firefox: **Speicher**) → **Cookies** → `https://www.instagram.com` → den Wert
von **`sessionid`** kopieren. Das ist dein `IG_SESSIONID`.

### 3. Beides bei GitHub hinterlegen

Im Repository: **Settings → Secrets and variables → Actions → New repository
secret**. Zwei Secrets anlegen:

| Name | Wert |
| --- | --- |
| `TELEGRAM_BOT_TOKEN` | das Token vom BotFather |
| `IG_SESSIONID` | der Cookie-Wert aus Schritt 2 |

Secrets sind auch bei einem öffentlichen Repository nicht einsehbar.

Optional, im selben Bereich unter dem Reiter **Variables**:

| Name | Wofür |
| --- | --- |
| `TELEGRAM_ALLOWED_USERNAME` | Telegram-Benutzername, der den Bot bedienen darf. Voreingestellt ist `vvalora` — nur du kannst ihm also Befehle geben. |

Falls dein Telegram-Konto **keinen** Benutzernamen hat, stattdessen das Secret
`TELEGRAM_CHAT_ID` mit deiner numerischen Chat-ID anlegen (bekommst du z.B. von
**@userinfobot**).

### 4. Actions einschalten

Im Repository auf den Reiter **Actions** → falls gefragt, Workflows aktivieren.
Danach läuft „Instagram-Korea-Bot" automatisch alle 15 Minuten.

### 5. Dem Bot einmal „Hallo" sagen

Wichtig: Ein Telegram-Bot darf dich **nicht von sich aus** anschreiben. Öffne
also einmal den Chat mit deinem Bot und schicke `/start`. Ab dann weiß er, wohin
er die Ergebnisse melden soll.

---

## Benutzung vom Handy

| Befehl | Wirkung |
| --- | --- |
| `/scan vikavalora` | startet den Scan dieser Followerliste |
| `/scan vikavalora 500` | prüft nur die ersten 500 Follower (gut zum Ausprobieren) |
| `/status` | Zwischenstand: wie viele Profile geprüft, wie viele Treffer |
| `/stop` | hält den Scan an (Stand bleibt gespeichert) |
| `/weiter` | macht dort weiter, wo es aufgehört hat |
| `/liste` | schickt die komplette Trefferliste noch einmal, inkl. CSV-Datei |
| `/hilfe` | Übersicht aller Befehle |

**Wie schnell geht das?** Der Bot prüft rund 2500 Profile pro Etappe und
startet alle 15 Minuten eine neue — also ungefähr 10.000 Profile pro Stunde.
Nach jeweils 500 geprüften Profilen bekommst du die neu gefundenen Treffer
geschickt, am Ende die vollständige Liste und eine CSV-Datei mit allen Spalten.

**Wie schnell antwortet er?** Befehle liest er beim nächsten Durchlauf, also
innerhalb von etwa 15 Minuten — nicht sofort. Wenn es schneller gehen soll:
GitHub-App oder Website → **Actions** → „Instagram-Korea-Bot" → **Run workflow**.
Dort kannst du im Feld `account` auch direkt einen Account eintragen und den
Scan starten, ganz ohne Telegram.

---

## Wenn etwas klemmt

**Der Bot meldet sich gar nicht.** Hast du ihm `/start` geschickt (Schritt 5)?
Und stimmt der Telegram-Benutzername in `TELEGRAM_ALLOWED_USERNAME`? Er
ignoriert alle anderen Absender stillschweigend — in den Logs unter *Actions*
steht dann „Nachricht von @… ignoriert".

**„Das Instagram-Cookie ist abgelaufen".** Schritt 2 wiederholen, das Secret
`IG_SESSIONID` aktualisieren (Settings → Secrets → auf den Namen klicken →
*Update*), dann im Chat `/weiter` schicken.

**„Diese Etappe ging schief".** Meist bremst Instagram gerade. Der Bot versucht
es beim nächsten Durchlauf von selbst wieder. Erst nach drei Fehlschlägen in
Folge hält er an und wartet auf dein `/weiter`. Bei hartnäckigen Problemen in
der Workflow-Datei `BOT_DELAY_MS` erhöhen (z.B. auf `30000` für 30 Sekunden
Pause zwischen den Abrufen).

**Nichts läuft mehr, obwohl alles eingerichtet ist.** GitHub schaltet geplante
Workflows ab, wenn 60 Tage lang niemand etwas am Repository gemacht hat. Unter
*Actions* lässt sich der Workflow mit einem Klick wieder aktivieren.

**Privates Profil.** Die Followerliste ist nur abrufbar, wenn der Account
öffentlich ist oder der eingeloggte Account ihm folgt. Sonst sagt der Bot das
direkt.

---

## Einstellungen (Workflow-Datei)

Alles steht in `.github/workflows/instagram-korean-bot.yml` unter `env:`:

| Variable | Standard | Bedeutung |
| --- | --- | --- |
| `BOT_DELAY_MS` | `12000` | Pause zwischen zwei Abrufen (wird leicht zufällig gestreut) |
| `BOT_PAGE_SIZE` | `50` | Profile pro Abruf |
| `BOT_RUN_BUDGET_SECONDS` | `600` | wie lange eine Etappe höchstens arbeitet |
| `BOT_STAGE_SIZE` | `500` | nach so vielen geprüften Profilen kommt eine Zwischenmeldung |
| `BOT_MAX_LIST` | `500` | so viele Treffer stehen am Ende direkt im Chat, der Rest nur in der CSV-Datei |
| `BOT_MAX_HITS` | `20000` | Obergrenze gespeicherter Treffer |

---

## Bot in ein eigenes Repository umziehen

Falls du ihn ganz vom Shop trennen möchtest: neues (privates) Repository
anlegen und dorthin kopieren:

```
tools/instagram-korean-filter/     (der ganze Ordner)
.github/workflows/instagram-korean-bot.yml
```

Sonst ändert sich nichts — Secrets im neuen Repository anlegen, fertig. Der Bot
hat keinerlei Verbindung zum Shop-Code und wird auch nicht mit ihm ausgeliefert.
