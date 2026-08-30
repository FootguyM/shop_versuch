// Zustand des Bots: laufender Auftrag, gefundene Treffer, zuletzt gelesene
// Telegram-Nachricht. Wird als eine JSON-Datei gespeichert und von der
// GitHub-Action zwischen den Etappen im Zweig "bot-state" abgelegt.

import { mkdir, readFile, writeFile } from 'node:fs/promises';
import path from 'node:path';

export const LEERER_ZUSTAND = {
  version: 1,
  telegramOffset: null, // ID der zuletzt verarbeiteten Telegram-Nachricht + 1
  chatId: null, // wird beim ersten /start gemerkt
  job: null, // aktueller Scan-Auftrag, siehe neuerAuftrag()
  archiv: [], // kurze Zusammenfassungen abgeschlossener Scans
};

export function neuerAuftrag(username, limit = null) {
  return {
    username,
    userId: null,
    cursor: null, // Position in der Followerliste -- macht das Fortsetzen moeglich
    checked: 0,
    gemeldet: 0, // wie viele Treffer bereits per Etappen-Nachricht raus sind
    gemeldetBei: 0, // Stand von `checked` bei der letzten Etappen-Meldung
    hits: [],
    limit,
    totalFollowers: null,
    status: 'running', // running | paused | stopped | done
    hinweis: '',
    fehlerInFolge: 0,
    startedAt: new Date().toISOString(),
    updatedAt: new Date().toISOString(),
  };
}

export async function loadState(datei) {
  try {
    const roh = await readFile(datei, 'utf8');
    const daten = JSON.parse(roh);
    if (daten && typeof daten === 'object') return { ...LEERER_ZUSTAND, ...daten };
  } catch (fehler) {
    if (fehler.code !== 'ENOENT') {
      process.stderr.write(`Zustandsdatei unlesbar (${fehler.message}) -- starte leer.\n`);
    }
  }
  return { ...LEERER_ZUSTAND };
}

export async function saveState(datei, state) {
  await mkdir(path.dirname(path.resolve(datei)), { recursive: true });
  await writeFile(datei, `${JSON.stringify(state, null, 2)}\n`, 'utf8');
}
