# Reelroom — Video-Shop

Ein schlanker Video-Shop: Katalog auf der Startseite, Kauf per manueller
PayPal-Überweisung, Versand von Hand. Gebaut mit Next.js, startklar für
Vercel.

Alle Inhalte (Titel, Bilder, Preise, Texte) sind Platzhalter zum Austauschen.

---

## 1. Lokal ausprobieren

Voraussetzung: [Node.js](https://nodejs.org) 18 oder neuer.

```bash
npm install
npm run dev
```

Danach [http://localhost:3000](http://localhost:3000) öffnen. Die Seite läuft
sofort mit den 6 Beispiel-Videos — auch ganz ohne Datenbank (siehe Abschnitt 4).

> Der erste Start braucht eine Internetverbindung, weil dabei die
> Google-Schriftarten geladen werden.

---

## 2. Vor dem Launch anpassen

**PayPal-Empfänger ändern** (aktuell `paypal.me/vikavalora`):
→ `lib/data.js`, Zeile mit `export const PAYPAL_HANDLE = "vikavalora";`
Einfach den Namen austauschen — er wird überall automatisch übernommen.

**Admin-Zugang festlegen:**
→ Umgebungsvariable `ADMIN_TOKEN` setzen (siehe `.env.example`). Das ist dein
geheimer Schlüssel, z.B. `x7Kp9mQ2vL4tR8nW`. Dein Admin-Bereich ist danach
erreichbar unter:

```
https://deine-domain.de/admin/x7Kp9mQ2vL4tR8nW
```

Diesen Link wie ein Passwort behandeln und nicht öffentlich teilen — wer ihn
kennt, kann Videos verwalten.

**Beispiel-Videos ersetzen:** Am einfachsten direkt im Admin-Bereich
(bearbeiten/löschen/hinzufügen, siehe Abschnitt 5). Alternativ die
Ausgangsliste in `lib/data.js` unter `SEED_VIDEOS` anpassen.

**Farben, Schriften, Texte:** Alle Design-Tokens (Farben, Schriften) stehen
gesammelt in `app/globals.css` im `@theme`-Block. Die Texte auf der Startseite
stehen in `app/page.js`, Kopf-/Fußzeile in `components/Header.js` und
`components/Footer.js`.

---

## 3. Deployment auf Vercel

1. Dieses Projekt in ein GitHub-Repository laden (oder den Ordner direkt per
   [Vercel CLI](https://vercel.com/docs/cli) mit `vercel` hochladen).
2. Auf [vercel.com](https://vercel.com) → **Add New → Project** → das
   Repository auswählen → **Deploy** (Next.js wird automatisch erkannt, es
   ist keine Konfiguration nötig).
3. Nach dem ersten Deploy: **Project → Settings → Environment Variables** →
   `ADMIN_TOKEN` mit deinem geheimen Wert eintragen → erneut deployen
   (Deployments → „Redeploy").

Damit läuft der Shop bereits — Änderungen im Admin-Bereich werden aber erst
mit einer angebundenen Datenbank dauerhaft gespeichert (nächster Punkt).

---

## 4. Datenbank einrichten (für dauerhafte Änderungen)

Ohne Datenbank merkt sich der Server nichts zuverlässig zwischen Aufrufen —
das Projekt läuft dann nur mit den Beispieldaten, und Änderungen im
Admin-Bereich können jederzeit wieder verschwinden. Für einen echten Shop
also unbedingt einrichten (kostenlos, ca. 2 Minuten):

1. Im Vercel-Projekt: Tab **Storage** → **Create Database** bzw.
   **Marketplace Database Integrations** → **Upstash for Redis** auswählen.
2. Datenbank erstellen und mit diesem Projekt verbinden. Vercel trägt die
   nötigen Umgebungsvariablen automatisch ein.
3. Projekt neu deployen (Deployments → „Redeploy"), damit die Variablen
   greifen.

Ab jetzt bleiben alle Videos und eingehenden Bestellungen dauerhaft
gespeichert.

---

## 5. Admin-Bereich benutzen

1. `https://deine-domain.de/admin/DEIN-TOKEN` öffnen.
2. **Tab „Videos"**: neue Videos hinzufügen (Titel, Beschreibung, Preis,
   Bild-URL) oder vorhandene bearbeiten/löschen.
   - Für Thumbnails reicht ein direkter Bildlink (z.B. hochgeladen bei einem
     Bilder-Hoster deiner Wahl).
3. **Tab „Bestellungen"**: Hier landet jede Anfrage, sobald jemand auf einer
   Videoseite seine Email oder seinen Telegram-Namen einträgt — inklusive
   Video, Preis und Zeitpunkt. Nach Zahlungsprüfung per „Als erledigt
   markieren" abhaken, damit du den Überblick behältst.
4. Über „Abmelden" oben rechts wird der Zugang für dieses Gerät beendet.

---

## 6. Wie der Kaufablauf funktioniert

1. Besucher:in klickt auf ein Video → sieht Beschreibung, exakten Preis und
   einen Button, der PayPal.me mit dem Betrag direkt vorausgefüllt öffnet.
2. Sie/er trägt Email-Adresse oder Telegram-Nutzernamen ein und bestätigt,
   dass die Zahlung gesendet wurde.
3. Die Anfrage erscheint im Admin-Bereich unter „Bestellungen". Nach Prüfung
   des PayPal-Zahlungseingangs schickst du das Video manuell an die
   angegebene Adresse — ein deutlicher Hinweis auf der Seite bereitet
   Käufer:innen darauf vor, dass das etwas dauern kann.

---

## Projektstruktur (kurzer Überblick)

```
app/
  page.js                 → Startseite mit Katalog
  video/[id]/page.js       → Kauf-/Detailseite eines Videos
  admin/[token]/route.js    → geheimer Admin-Login-Link
  admin/dashboard/page.js    → Admin-Oberfläche
  api/videos/               → Video-Daten (lesen/schreiben)
  api/orders/                → Bestellungen (anlegen/lesen/Status ändern)
components/                  → wiederverwendbare UI-Bausteine
lib/data.js                  → Beispieldaten, Preis-Formatierung, PayPal-Link
lib/redis.js                 → Datenbank-Anbindung (Upstash Redis)
lib/auth.js                  → Admin-Login-Logik
```

## Hinweis zur Sicherheit

Der Admin-Zugang basiert auf einem einzigen geheimen Link/Token — das ist für
einen kleinen, persönlich betriebenen Shop ausreichend, aber kein
Hochsicherheits-System. Wähle ein langes, zufälliges Token, teile es mit
niemandem, und ändere es (neuer `ADMIN_TOKEN`-Wert + Redeploy), falls du
vermutest, dass es jemand anderes kennt.
