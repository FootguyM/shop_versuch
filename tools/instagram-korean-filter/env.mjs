// Einlesen einer einfachen Konfigurationsdatei (bot.env), damit Token und
// Cookie nicht in der Kommandozeile oder im Systemd-Dienst stehen muessen.
//
// Format: NAME=wert, eine Zeile je Eintrag, # leitet einen Kommentar ein.
// Bereits gesetzte Umgebungsvariablen haben Vorrang.

import { readFileSync } from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

export function ladeEnvDatei(pfad) {
  const kandidaten = pfad
    ? [pfad]
    : [
        path.join(path.dirname(fileURLToPath(import.meta.url)), 'bot.env'),
        path.resolve('bot.env'),
      ];

  for (const datei of kandidaten) {
    let text;
    try {
      text = readFileSync(datei, 'utf8');
    } catch {
      continue;
    }
    for (const zeile of text.split(/\r?\n/)) {
      const inhalt = zeile.trim();
      if (!inhalt || inhalt.startsWith('#')) continue;
      const trenner = inhalt.indexOf('=');
      if (trenner < 1) continue;
      const name = inhalt.slice(0, trenner).trim();
      let wert = inhalt.slice(trenner + 1).trim();
      if (
        (wert.startsWith('"') && wert.endsWith('"')) ||
        (wert.startsWith("'") && wert.endsWith("'"))
      ) {
        wert = wert.slice(1, -1);
      }
      if (process.env[name] === undefined) process.env[name] = wert;
    }
    return datei;
  }
  return null;
}
