// Gemeinsame Ausgabe-Hilfen fuer CLI und Telegram-Bot.

/** Setzt ein CSV-Feld korrekt in Anfuehrungszeichen, wenn noetig. */
export function csvFeld(wert) {
  const text = String(wert ?? '');
  return /[",\n\r]/.test(text) ? `"${text.replace(/"/g, '""')}"` : text;
}

/**
 * Baut eine CSV-Tabelle.
 * @param {Array<object>} zeilen
 * @param {string[]} spalten Reihenfolge und zugleich Kopfzeile
 */
export function toCsv(zeilen, spalten) {
  const kopf = spalten.join(',');
  const inhalt = zeilen.map((zeile) => spalten.map((s) => csvFeld(zeile[s])).join(','));
  return [kopf, ...inhalt].join('\n') + '\n';
}
