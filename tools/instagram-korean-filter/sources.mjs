// Einlesen der Followerliste aus dem offiziellen Instagram-Datenexport
// ("Deine Informationen herunterladen", Format JSON).

import { readdir, readFile, stat } from 'node:fs/promises';
import path from 'node:path';

/** Sucht im Datenexport nach den Dateien mit der Followerliste. */
async function collectFiles(target) {
  const info = await stat(target);
  if (info.isFile()) return [target];

  const found = [];
  async function walk(dir, tiefe) {
    if (tiefe > 4) return;
    for (const entry of await readdir(dir, { withFileTypes: true })) {
      const full = path.join(dir, entry.name);
      if (entry.isDirectory()) {
        await walk(full, tiefe + 1);
      } else if (/^followers.*\.json$/i.test(entry.name)) {
        found.push(full);
      }
    }
  }
  await walk(target, 0);
  found.sort();
  return found;
}

/** Holt die Followereintraege aus den verschiedenen Export-Varianten heraus. */
function extractEntries(data) {
  // Variante 1: reine Liste (followers_1.json aus neueren Exporten)
  if (Array.isArray(data)) {
    if (data.every((item) => typeof item === 'string')) {
      return data.map((username) => ({ username, full_name: '' }));
    }
    return data.flatMap(fromRelationship);
  }
  // Variante 2: Objekt mit benanntem Schluessel (aeltere Exporte)
  if (data && typeof data === 'object') {
    for (const key of ['relationships_followers', 'relationships_following', 'followers']) {
      if (Array.isArray(data[key])) return data[key].flatMap(fromRelationship);
    }
  }
  return [];
}

function fromRelationship(item) {
  if (typeof item === 'string') return [{ username: item, full_name: '' }];
  const list = Array.isArray(item?.string_list_data) ? item.string_list_data : [];
  return list.map((entry) => ({
    username: entry.value || usernameFromUrl(entry.href) || '',
    full_name: typeof item.title === 'string' ? item.title : '',
    timestamp: entry.timestamp ?? null,
  }));
}

function usernameFromUrl(href) {
  if (typeof href !== 'string') return '';
  const match = href.match(/instagram\.com\/([^/?#]+)/i);
  return match ? match[1] : '';
}

/**
 * Liest die Followerliste aus einer Export-Datei, einem Export-Ordner oder
 * einer einfachen Textdatei mit einem Benutzernamen pro Zeile.
 *
 * @returns {Promise<{ users: Array<{username: string, full_name: string}>, files: string[] }>}
 */
export async function readExport(target) {
  const files = await collectFiles(target);
  if (files.length === 0) {
    throw new Error(`Keine Datei "followers*.json" unter ${target} gefunden.`);
  }

  const users = [];
  const gesehen = new Set();
  for (const file of files) {
    const raw = await readFile(file, 'utf8');
    let entries;
    if (/\.(txt|csv)$/i.test(file)) {
      entries = raw
        .split(/\r?\n/)
        .map((line) => line.split(',')[0].trim().replace(/^@/, ''))
        .filter(Boolean)
        .map((username) => ({ username, full_name: '' }));
    } else {
      entries = extractEntries(JSON.parse(raw));
    }
    for (const entry of entries) {
      if (!entry.username || gesehen.has(entry.username)) continue;
      gesehen.add(entry.username);
      users.push({ id: '', is_private: false, is_verified: false, ...entry });
    }
  }
  return { users, files };
}
