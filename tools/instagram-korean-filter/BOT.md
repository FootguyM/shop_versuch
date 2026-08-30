# Telegram-Bot: Follower mit koreanischen Profilnamen finden

Der Bot geht die Followerliste eines Instagram-Accounts durch, prüft bei jedem
Profil den **Profilnamen** auf koreanische Zeichen und schickt dir die Treffer
per Telegram — Etappe für Etappe, am Ende noch einmal als komplette Liste plus
CSV-Datei.

Er läuft bei **GitHub Actions** — nicht auf deinem Rechner und nicht über den
Shop. Du brauchst dafür nur dein Handy: Telegram öffnen, `/scan accountname`
schreiben, warten. Die Followerliste holt er voreingestellt über einen fertigen
Scraper bei **Apify**, du brauchst also kein eigenes Instagram-Konto — dafür
kostet dort jedes Ergebnis ein paar Zehntelcent (Schritt 2). Wahlweise geht es
auch über ein eigenes Instagram-Cookie, dann kostenlos.

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
2. **Voreingestellt läuft es über Apify** — einen fertigen Scraper-Dienst. Du
   brauchst dann kein eigenes Instagram-Konto, zahlst aber pro Ergebnis
   (Größenordnung 2,50 $ je 1000 Follower, siehe Schritt 2). Der Bot nennt dir
   vor jedem Scan die geschätzten Kosten und begrenzt sich ohne ausdrückliche
   Zahl auf 1000 Follower.
3. **Der Weg über ein eigenes Instagram-Konto** ist kostenlos, dafür kann
   Instagram bremsen oder einen Sicherheits-Check verlangen — Anfragen aus
   einem Rechenzentrum fallen stärker auf als von zu Hause. Nimm dafür nicht
   deinen wichtigsten Account. Läuft das Cookie ab, meldet sich der Bot; dein
   Fortschritt bleibt erhalten.

---

## Einrichtung (einmalig, ca. 10 Minuten)

### 1. Telegram-Bot anlegen

In Telegram **@BotFather** anschreiben → `/newbot` → Namen und Benutzernamen
vergeben. Am Ende bekommst du ein Token der Form
`123456789:AAH...`. Das ist dein `TELEGRAM_BOT_TOKEN`.

### 2. Quelle wählen

Followerlisten gibt Instagram nur an eingeloggte Besucher heraus. Es gibt
deshalb zwei Wege — der Bot kann beide.

**Voreingestellt: Apify (kein eigener Instagram-Login).** Bei
[apify.com](https://apify.com) anmelden, dann **Settings → Integrations → API
token** kopieren. Der Bot startet dort einen fertigen Scraper, wartet, bis
Ergebnisse eintrudeln, und liest sie ein. Um den Instagram-Login kümmert sich
der Anbieter.

Was du dazu wissen musst:

* **Es kostet pro Ergebnis.** Voreingestellt ist der Actor
  `scraping_solutions/instagram-scraper-followers-following-no-cookies` für
  rund **2,50 $ pro 1000 Ergebnisse**. Apifys Gratis-Rahmen sind 5 $ Guthaben
  im Monat, also etwa 2000 Follower. Eine Liste mit 50.000 Followern kostet
  entsprechend rund 125 $. Der Bot nennt dir beim Start die geschätzten Kosten.
* **Deshalb bekommt jeder Scan eine Obergrenze.** Ohne ausdrückliche Zahl im
  Befehl nimmt der Bot 1000 (`APIFY_DEFAULT_LIMIT`). `/scan name 5000` hebt sie
  für diesen Scan an.
* **Anderen Actor nehmen:** Variable `APIFY_ACTOR` setzen, bei abweichenden
  Eingabefeldern zusätzlich `APIFY_INPUT` (JSON mit den Platzhaltern
  `{{username}}` und `{{limit}}`). Die Ausgabefelder erkennt der Bot selbst —
  er akzeptiert `username`/`userName`/`handle` und
  `fullName`/`full_name`/`name`.
* **Achtung, Richtung:** Ein Actor mit „following" im Namen liefert oft die
  Accounts, denen jemand *folgt* — nicht die Follower. Das ist die
  Gegenrichtung. Beim voreingestellten Actor steuert das Feld `resultsType`,
  das in `APIFY_INPUT` auf `followers` steht.

**Alternative: eigenes Instagram-Konto.** Kostet nichts, dafür trägt dein Konto
das Risiko (Drosselung, Sicherheits-Check). Nimm dafür besser nicht deinen
Hauptaccount. Ein frisch angelegtes Konto fällt besonders schnell auf, wenn es
sofort tausende Profile abruft — lass es ein paar Tage normal stehen und starte
dann klein mit `/scan name 200 instagram`. Ein neues Konto sieht die
Followerliste eines **privaten** Profils außerdem erst, wenn es ihm folgen darf.

*Cookie auslesen:* am Computer mit diesem Konto bei instagram.com einloggen →
F12 → Tab **Application** (Firefox: **Speicher**) → **Cookies** →
`https://www.instagram.com` → den Wert von **`sessionid`** kopieren. Das ist
dein `IG_SESSIONID`.

### 3. Zugangsdaten bei GitHub hinterlegen

Im Repository: **Settings → Secrets and variables → Actions → New repository
secret**:

| Name | Wert | nötig für |
| --- | --- | --- |
| `TELEGRAM_BOT_TOKEN` | das Token vom BotFather | immer |
| `APIFY_TOKEN` | dein Apify-API-Token | Quelle Apify |
| `IG_SESSIONID` | der Cookie-Wert aus Schritt 2 | Quelle Instagram |

Secrets sind auch bei einem öffentlichen Repository nicht einsehbar.

Optional, im selben Bereich unter dem Reiter **Variables**:

| Name | Wofür |
| --- | --- |
| `TELEGRAM_ALLOWED_USERNAME` | Telegram-Benutzername, der den Bot bedienen darf. Voreingestellt `vvalora` — nur du kannst ihm Befehle geben. |
| `BOT_SOURCE` | `apify` (Vorgabe) oder `instagram` |
| `APIFY_ACTOR`, `APIFY_INPUT`, `APIFY_DEFAULT_LIMIT`, `APIFY_PRICE_PER_1000` | siehe Schritt 2 |

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
| `/scan vikavalora 500 instagram` | dieser eine Scan über das eigene Cookie statt über Apify |
| `/status` | Zwischenstand: wie viele Profile geprüft, wie viele Treffer |
| `/stop` | hält den Scan an (Stand bleibt gespeichert) |
| `/weiter` | macht dort weiter, wo es aufgehört hat |
| `/liste` | schickt die komplette Trefferliste noch einmal, inkl. CSV-Datei |
| `/hilfe` | Übersicht aller Befehle |

**Wie schnell geht das?** Über **Apify** bestimmt der Scraper das Tempo: Der Bot
stößt den Lauf an, liest ein paar Minuten lang mit und holt den Rest bei den
nächsten Etappen nach — je nach Größe der Liste innerhalb von ein bis wenigen
Stunden. Über das **eigene Cookie** arbeitet er selbst: 45 Minuten je Etappe,
rund 11.000 Profile, eine Liste mit 50.000 Einträgen also in etwa fünf Stunden.

In beiden Fällen gilt: Immer wenn 1000 weitere Profile geprüft sind, kommen die
neu gefundenen Treffer; am Ende die vollständige Liste plus CSV-Datei.

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

**„Apify-Guthaben aufgebraucht" / „Apify lehnt das Token ab".** Im Apify-Konto
nachsehen. Der Bot hält an und behält deinen Stand; nach dem Aufladen bzw. dem
Erneuern des Secrets geht es mit `/weiter` da weiter, wo er war.

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
| `APIFY_WAIT_SECONDS` | `150` | wie lange eine Etappe auf neue Apify-Daten wartet, bevor sie endet (längeres Warten kostet nur GitHub-Minuten — der Scraper läuft bei Apify weiter) |
| `APIFY_BLOCK_SIZE` | `500` | wie viele Ergebnisse pro Abruf aus dem Apify-Datensatz gelesen werden |

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
