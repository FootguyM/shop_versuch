#!/usr/bin/env node
// Geht die Followerliste eines Instagram-Accounts durch und filtert alle
// Accounts heraus, deren Benutzername oder Profilname koreanische Zeichen
// enthaelt.
//
// Aufruf:  node tools/instagram-korean-filter/index.mjs --help

import { writeFile } from 'node:fs/promises';
import { setTimeout as sleep } from 'node:timers/promises';
import path from 'node:path';
import process from 'node:process';

import { inspectFields } from './korean.mjs';
import { createClient, InstagramError } from './instagram.mjs';
import { readExport } from './sources.mjs';

const HILFE = `
Instagram-Follower nach koreanischen Zeichen filtern

  node tools/instagram-korean-filter/index.mjs --user <account> [Optionen]
  node tools/instagram-korean-filter/index.mjs --export <pfad>   [Optionen]

Quelle (eine von beiden noetig)
  -u, --user <name>      Account, dessen Followerliste geprueft wird. Braucht
                         die Umgebungsvariable IG_SESSIONID (siehe README).
  -e, --export <pfad>    Datei followers_1.json bzw. Ordner des offiziellen
                         Instagram-Datenexports. Ohne Netzzugriff.

Optionen
  -o, --out <datei>      Ergebnis zusaetzlich in eine Datei schreiben
                         (.csv, .json oder .txt; Format aus der Endung)
      --format <f>       Format erzwingen: csv | json | txt
      --fields <liste>   zu pruefende Felder, Standard: username,full_name
      --invert           stattdessen die Accounts OHNE koreanische Zeichen
      --limit <n>        hoechstens n Follower pruefen
      --delay <ms>       Pause zwischen den Abrufen, Standard 1500
      --page-size <n>    Follower pro Abruf, Standard 50 (max. 100)
      --resolve-names    im Export-Modus die Profilnamen nachladen (langsam,
                         braucht ebenfalls IG_SESSIONID)
  -q, --quiet            keine Fortschrittsmeldungen
  -h, --help             diese Hilfe

Beispiele
  IG_SESSIONID=... node tools/instagram-korean-filter/index.mjs -u vikavalora -o korea.csv
  node tools/instagram-korean-filter/index.mjs -e ~/instagram-export -o korea.json
`;

function parseArgs(argv) {
  const opts = {
    user: null,
    export: null,
    out: null,
    format: null,
    fields: ['username', 'full_name'],
    invert: false,
    limit: null,
    delay: 1500,
    pageSize: 50,
    resolveNames: false,
    quiet: false,
    help: false,
  };

  const zahl = (wert, name) => {
    const n = Number(wert);
    if (!Number.isFinite(n) || n <= 0) throw new Error(`--${name} braucht eine positive Zahl.`);
    return n;
  };

  for (let i = 0; i < argv.length; i++) {
    const arg = argv[i];
    const next = () => {
      const wert = argv[++i];
      if (wert === undefined) throw new Error(`Zu "${arg}" fehlt der Wert.`);
      return wert;
    };
    switch (arg) {
      case '-u': case '--user': opts.user = next().replace(/^@/, ''); break;
      case '-e': case '--export': opts.export = next(); break;
      case '-o': case '--out': opts.out = next(); break;
      case '--format': opts.format = next().toLowerCase(); break;
      case '--fields': opts.fields = next().split(',').map((f) => f.trim()).filter(Boolean); break;
      case '--invert': opts.invert = true; break;
      case '--limit': opts.limit = zahl(next(), 'limit'); break;
      case '--delay': opts.delay = zahl(next(), 'delay'); break;
      case '--page-size': opts.pageSize = Math.min(100, zahl(next(), 'page-size')); break;
      case '--resolve-names': opts.resolveNames = true; break;
      case '-q': case '--quiet': opts.quiet = true; break;
      case '-h': case '--help': opts.help = true; break;
      default:
        if (!opts.user && !arg.startsWith('-')) { opts.user = arg.replace(/^@/, ''); break; }
        throw new Error(`Unbekannte Option: ${arg}`);
    }
  }
  return opts;
}

const ERLAUBTE_FELDER = new Set(['username', 'full_name']);

function formatFuer(opts) {
  if (opts.format) return opts.format;
  if (!opts.out) return 'csv';
  const endung = path.extname(opts.out).slice(1).toLowerCase();
  return endung === 'json' || endung === 'txt' ? endung : 'csv';
}

function csvFeld(wert) {
  const text = String(wert ?? '');
  return /[",\n\r]/.test(text) ? `"${text.replace(/"/g, '""')}"` : text;
}

function serialisieren(treffer, format) {
  if (format === 'json') return `${JSON.stringify(treffer, null, 2)}\n`;
  if (format === 'txt') return treffer.map((t) => t.username).join('\n') + (treffer.length ? '\n' : '');
  const kopf = ['username', 'full_name', 'korean_chars', 'matched_fields', 'profile_url'];
  const zeilen = treffer.map((t) =>
    [t.username, t.full_name, t.korean_chars, t.matched_fields, t.profile_url].map(csvFeld).join(','),
  );
  return [kopf.join(','), ...zeilen].join('\n') + '\n';
}

async function main() {
  let opts;
  try {
    opts = parseArgs(process.argv.slice(2));
  } catch (fehler) {
    console.error(`Fehler: ${fehler.message}\n${HILFE}`);
    process.exitCode = 2;
    return;
  }

  if (opts.help || (!opts.user && !opts.export)) {
    console.log(HILFE.trim());
    process.exitCode = opts.help ? 0 : 2;
    return;
  }
  if (opts.user && opts.export) {
    console.error('Fehler: --user und --export schliessen sich gegenseitig aus.');
    process.exitCode = 2;
    return;
  }
  const unbekannt = opts.fields.filter((f) => !ERLAUBTE_FELDER.has(f));
  if (unbekannt.length > 0 || opts.fields.length === 0) {
    console.error(`Fehler: --fields kennt nur username und full_name (nicht: ${unbekannt.join(', ')}).`);
    process.exitCode = 2;
    return;
  }

  const log = opts.quiet ? () => {} : (text) => process.stderr.write(`${text}\n`);
  const treffer = [];
  let geprueft = 0;

  // Auch bei Strg+C bleibt das bis dahin Gefundene erhalten.
  let abgebrochen = false;
  process.on('SIGINT', () => {
    if (abgebrochen) process.exit(130);
    abgebrochen = true;
    log('\nAbbruch -- schreibe die bisherigen Treffer ...');
  });

  const pruefen = (user) => {
    geprueft += 1;
    const felder = Object.fromEntries(opts.fields.map((f) => [f, user[f] ?? '']));
    const { matched, fields, chars } = inspectFields(felder);
    if (matched === opts.invert) return;
    treffer.push({
      username: user.username,
      full_name: user.full_name ?? '',
      korean_chars: chars.join(''),
      matched_fields: fields.join('|'),
      profile_url: `https://www.instagram.com/${user.username}/`,
    });
  };

  try {
    if (opts.user) {
      const client = createClient(process.env.IG_SESSIONID, {
        delay: opts.delay,
        onNotice: log,
      });
      log(`Suche Account @${opts.user} ...`);
      const profil = await client.fetchProfile(opts.user);
      if (profil.is_private && !profil.followed_by_viewer) {
        throw new InstagramError(`@${profil.username} ist privat und du folgst dem Account nicht.`, {
          hint: 'Die Followerliste ist damit nicht abrufbar.',
        });
      }
      log(
        `@${profil.username} (ID ${profil.id})` +
          (profil.follower_count !== null ? `, ${profil.follower_count} Follower` : ''),
      );

      for await (const follower of client.iterateFollowers(profil.id, {
        pageSize: opts.pageSize,
        limit: opts.limit,
        onPage: (seite, gesamt) => log(`  Seite ${seite}: ${gesamt} Follower geprueft, ${treffer.length} Treffer`),
      })) {
        pruefen(follower);
        if (abgebrochen) break;
      }
    } else {
      const { users, files } = await readExport(opts.export);
      log(`${users.length} Follower aus ${files.length} Datei(en) gelesen.`);
      const hatNamen = users.some((u) => u.full_name);
      if (!opts.resolveNames && !hatNamen) {
        log(
          'Hinweis: Der Export enthaelt nur Benutzernamen, und die duerfen bei\n' +
            'Instagram keine koreanischen Zeichen enthalten. Fuer ein brauchbares\n' +
            'Ergebnis --resolve-names verwenden (laedt die Profilnamen nach).',
        );
      }

      const liste = opts.limit ? users.slice(0, opts.limit) : users;
      if (opts.resolveNames) {
        const client = createClient(process.env.IG_SESSIONID, { delay: opts.delay, onNotice: log });
        for (const [index, user] of liste.entries()) {
          if (abgebrochen) break;
          try {
            const profil = await client.fetchProfile(user.username);
            pruefen({ ...user, full_name: profil.full_name });
          } catch (fehler) {
            if (fehler instanceof InstagramError && fehler.status === 404) {
              pruefen(user); // Account existiert nicht mehr -- nur Name pruefbar
            } else {
              throw fehler;
            }
          }
          if ((index + 1) % 25 === 0) {
            log(`  ${index + 1}/${liste.length} Profile geladen, ${treffer.length} Treffer`);
          }
          if (index < liste.length - 1) await sleep(opts.delay);
        }
      } else {
        for (const user of liste) pruefen(user);
      }
    }
  } catch (fehler) {
    if (fehler instanceof InstagramError) {
      console.error(`Fehler: ${fehler.message}${fehler.hint ? `\n  ${fehler.hint}` : ''}`);
    } else {
      console.error(`Fehler: ${fehler.message}`);
    }
    process.exitCode = 1;
    if (treffer.length === 0) return;
    log('Die bis dahin gefundenen Treffer folgen trotzdem.');
  }

  const format = formatFuer(opts);
  const ausgabe = serialisieren(treffer, format);
  if (opts.out) {
    await writeFile(opts.out, ausgabe, 'utf8');
    log(`\n${treffer.length} von ${geprueft} Accounts geschrieben nach ${opts.out}`);
  } else {
    process.stdout.write(ausgabe);
    log(`\n${treffer.length} von ${geprueft} Accounts ${opts.invert ? 'ohne' : 'mit'} koreanischen Zeichen.`);
  }
}

main();
