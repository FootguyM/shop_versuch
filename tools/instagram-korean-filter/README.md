# Instagram-Follower nach koreanischen Zeichen filtern

Kleines Kommandozeilen-Werkzeug: Es geht die Followerliste eines
Instagram-Accounts durch und gibt alle Accounts aus, deren Benutzername oder
Profilname koreanische Schriftzeichen (Hangul) enthält.

Kein zusätzliches Paket nötig — es reicht **Node.js 18 oder neuer**, das für
den Shop ohnehin installiert ist. Das Werkzeug ist unabhängig vom Shop und
verändert nichts an ihm.

---

## Lieber per Telegram vom Handy?

Es gibt zusätzlich einen Telegram-Bot, der kostenlos bei GitHub läuft, die
Followerliste in Etappen abarbeitet und dir die Treffer laufend schickt.
Einrichtung und Bedienung: **[BOT.md](BOT.md)**.

Der Rest dieser Seite beschreibt das Kommandozeilen-Werkzeug für den eigenen
Rechner.

---

## Schnellstart

```bash
# Aus dem offiziellen Instagram-Datenexport (ohne Login, ohne Netzzugriff)
node tools/instagram-korean-filter/index.mjs --export ~/Downloads/instagram-export --resolve-names -o korea.csv

# Direkt über Instagram (braucht das Session-Cookie, siehe unten)
IG_SESSIONID=dein_cookie node tools/instagram-korean-filter/index.mjs --user vikavalora -o korea.csv
```

Ohne `-o` landet das Ergebnis direkt im Terminal.

---

## Die zwei Betriebsarten

### 1. `--user <account>` — Followerliste live abfragen

Instagram bietet keine offizielle Schnittstelle für Followerlisten an. Das
Werkzeug benutzt deshalb dieselbe interne Schnittstelle wie die Webseite im
Browser — dafür braucht es das Session-Cookie deines eigenen, eingeloggten
Accounts.

**Cookie auslesen** (einmalig, hält je nach Konto einige Wochen):

1. Im Browser bei instagram.com einloggen.
2. Entwicklertools öffnen (F12) → Tab **Application** (Chrome) bzw.
   **Speicher** (Firefox) → **Cookies** → `https://www.instagram.com`.
3. Den Wert von `sessionid` kopieren.

**Übergeben** — am besten als Umgebungsvariable, damit das Cookie nicht in der
Shell-Historie landet:

```bash
export IG_SESSIONID='hier_der_kopierte_wert'
node tools/instagram-korean-filter/index.mjs --user vikavalora -o korea.csv
```

Voraussetzungen: Die Followerliste muss für dich sichtbar sein — bei privaten
Accounts also nur, wenn du dem Account folgst.

### 2. `--export <pfad>` — aus dem Datenexport lesen

Instagram → Einstellungen → *Deine Informationen und Berechtigungen* →
*Deine Informationen herunterladen* → Format **JSON**. Im Export liegt die
Followerliste unter `followers_and_following/followers_1.json`.

`--export` nimmt diese Datei oder gleich den ganzen Export-Ordner (es werden
alle `followers*.json` eingelesen). Eine einfache Textdatei mit einem
Benutzernamen pro Zeile geht ebenfalls.

> **Wichtig:** Der Export enthält nur die Benutzernamen — und die dürfen bei
> Instagram ausschließlich aus `a–z`, `0–9`, `.` und `_` bestehen, also nie
> koreanische Zeichen. Koreanisch steckt praktisch immer im *Profilnamen*.
> Deshalb im Export-Modus `--resolve-names` verwenden: das lädt zu jedem
> Follower den Profilnamen nach (braucht dann ebenfalls `IG_SESSIONID` und
> dauert bei großen Listen entsprechend lange).

---

## Optionen

| Option | Bedeutung |
| --- | --- |
| `-u`, `--user <name>` | Account, dessen Followerliste geprüft wird |
| `-e`, `--export <pfad>` | Datei oder Ordner des Instagram-Datenexports |
| `-o`, `--out <datei>` | Ergebnis in eine Datei schreiben |
| `--format csv\|json\|txt` | Format erzwingen (sonst aus der Dateiendung, Standard `csv`) |
| `--fields username,full_name` | welche Felder geprüft werden (Standard: beide) |
| `--invert` | umgekehrt: alle Accounts **ohne** koreanische Zeichen |
| `--limit <n>` | höchstens n Follower prüfen (gut zum Ausprobieren) |
| `--delay <ms>` | Pause zwischen den Abrufen, Standard `1500` |
| `--page-size <n>` | Follower pro Abruf, Standard `50` (max. 100) |
| `--resolve-names` | im Export-Modus die Profilnamen nachladen |
| `-q`, `--quiet` | keine Fortschrittsmeldungen |
| `-h`, `--help` | Hilfe anzeigen |

Die CSV-Ausgabe hat die Spalten `username`, `full_name`, `korean_chars`
(die gefundenen Zeichen), `matched_fields` (wo sie standen) und `profile_url`.
`--format txt` gibt nur die Benutzernamen aus, einer pro Zeile — praktisch zum
Weiterverarbeiten.

---

## Was als „koreanisch" zählt

Erkannt werden alle Unicode-Blöcke mit Hangul: die üblichen Silben (`가`–`힣`),
einzelne Jamo, halbbreite und eingekreiste Formen (`korean.mjs`).

Bewusst **nicht** erkannt werden chinesische Han-Zeichen (Hanja). Sie kommen
genauso in japanischen und chinesischen Namen vor und wären damit kein
verlässlicher Hinweis auf einen koreanischen Account. Umgekehrt gilt: Ein
koreanischer Account, der seinen Namen lateinisch schreibt („Minjun Kim"),
lässt sich über Zeichen nicht erkennen.

---

## Grenzen und Fairness gegenüber Instagram

* Die interne Schnittstelle ist nicht dokumentiert und kann sich jederzeit
  ändern. Wenn plötzlich Fehler kommen, liegt es meist daran — oder an einem
  abgelaufenen `sessionid`.
* Instagram drosselt zu häufige Abfragen. Das Werkzeug pausiert deshalb
  standardmäßig 1,5 Sekunden zwischen den Seiten und wartet bei Status 429
  mit wachsender Pause. Bei sehr großen Followerlisten lieber `--delay`
  erhöhen und in Etappen mit `--limit` arbeiten, statt eine Sperre zu
  riskieren.
* Automatisierte Abfragen widersprechen den Nutzungsbedingungen von
  Instagram. Für die eigene Followerliste ist der Datenexport der offiziell
  vorgesehene Weg — deshalb gibt es den Export-Modus.
* Mit `Strg+C` abgebrochene Läufe schreiben die bis dahin gefundenen Treffer
  noch weg.
