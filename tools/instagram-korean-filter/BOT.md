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

1. **Der Zwischenstand liegt im Repository.** Der Bot legt ihn — also auch die
   gefundenen Namen — im Zweig `bot-state` ab. Bei einem **öffentlichen**
   Repository kann den jeder lesen. Der Workflow ist deshalb auf ein
   **privates** Repository eingestellt (GitHub → Settings → General → ganz
   unten „Change repository visibility"). Der Shop bei Vercel läuft mit einem
   privaten Repository unverändert weiter.

   Privat heißt: 2000 Action-Minuten pro Monat gratis, und GitHub rundet jeden
   Lauf auf volle Minuten auf. Deshalb schaut der Bot nur **stündlich** nach
   neuen Befehlen, arbeitet dann aber 45 Minuten am Stück. Das kostet rund 720
   Minuten im Monat fürs Nachschauen und lässt genug Rest für die Scans.
   Wenn du das Repository öffentlich lässt, sind die Minuten unbegrenzt — dann
   in `.github/workflows/instagram-korean-bot.yml` ruhig `- cron: '7 * * * *'`
   auf `'*/15 * * * *'` ändern, dann reagiert er viertelstündlich.
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

### 2. Instagram-Konto wählen und Cookie auslesen

Der Bot braucht ein eingeloggtes Instagram-Konto, weil Followerlisten ohne
Login nicht abrufbar sind. Nimm dafür besser **nicht** deinen Hauptaccount.

Falls du ein neues anlegst (instagram.com → Registrieren, dauert zwei Minuten):
Ein frisch erstelltes Konto fällt Instagram besonders schnell auf, wenn es
sofort tausende Profile abruft — lass es ein paar Tage normal stehen, folge
ein paar Accounts, und starte erst dann mit einem kleinen `/scan name 200`.
Und: Ein neues Konto sieht die Followerliste eines **privaten** Profils erst,
wenn es ihm folgt und die Anfrage angenommen wurde.

**Cookie auslesen:** Am Computer mit diesem Konto bei instagram.com einloggen → F12 → Tab **Application**
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

**Wie schnell geht das?** Eine Etappe dauert 45 Minuten und schafft dabei rund
11.000 Profile. Immer wenn 1000 weitere Profile geprüft sind, schickt er dir die
neu gefundenen Treffer; am Ende kommt die vollständige Liste und eine CSV-Datei
mit allen Spalten. Eine Followerliste mit 50.000 Einträgen ist also nach etwa
fünf Stunden durch.

**Wie schnell antwortet er?** Neue Befehle liest er, wenn die nächste Etappe
startet — bis zu eine Stunde später. Während ein Scan läuft, macht das wenig
aus, weil er dir die Treffer von sich aus schickt. Wenn es sofort losgehen soll:
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
| `BOT_RUN_BUDGET_SECONDS` | `2700` | wie lange eine Etappe höchstens arbeitet (45 Minuten) |
| `BOT_STAGE_SIZE` | `1000` | nach so vielen geprüften Profilen kommen die neuen Treffer |
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
