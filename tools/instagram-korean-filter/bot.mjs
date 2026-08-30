#!/usr/bin/env node
// Telegram-Bot: prueft die Followerliste eines Instagram-Accounts etappenweise
// auf koreanische Zeichen im Profilnamen und meldet die Treffer per Telegram.
//
// Gedacht als Dauerlaeufer auf einem eigenen Rechner (z.B. Raspberry Pi):
// Der Prozess horcht am Telegram-Anschluss und arbeitet die Followerliste
// Seite fuer Seite ab. Nach jeder Etappe legt er eine laengere Pause ein.
// Der Zustand liegt in einer Datei -- nach einem Neustart geht es genau dort
// weiter, wo er aufgehoert hat.
//
//   node bot.mjs           Dauerbetrieb (fuer den Systemd-Dienst)
//   node bot.mjs --once    arbeiten, bis nichts mehr zu tun ist, dann Ende

import { setTimeout as sleep } from 'node:timers/promises';
import process from 'node:process';

import { inspectFields } from './korean.mjs';
import { toCsv } from './format.mjs';
import { createClient, InstagramError } from './instagram.mjs';
import { createTelegram } from './telegram.mjs';
import { loadState, saveState, neuerAuftrag } from './state.mjs';
import { ladeEnvDatei } from './env.mjs';

// Vor der Konfiguration: Werte aus bot.env nachziehen, falls vorhanden.
const envDatei = ladeEnvDatei(process.env.BOT_ENV_FILE);

const zahl = (wert, standard) => {
  const n = Number(wert);
  return Number.isFinite(n) && n > 0 ? n : standard;
};

const KONFIG = {
  stateFile: process.env.BOT_STATE_FILE || '.botstate/state.json',
  // Pause zwischen zwei Seitenabrufen (wird leicht zufaellig gestreut).
  delay: zahl(process.env.BOT_DELAY_MS, 12000),
  pageSize: Math.min(100, zahl(process.env.BOT_PAGE_SIZE, 50)),
  // Nach so vielen geprueften Profilen ist eine Etappe voll: Treffer melden
  // und eine laengere Pause einlegen.
  stageSize: zahl(process.env.BOT_STAGE_SIZE, 500),
  etappenPause: zahl(process.env.BOT_ETAPPE_PAUSE_SECONDS, 120) * 1000,
  fehlerPause: zahl(process.env.BOT_ERROR_PAUSE_SECONDS, 120) * 1000,
  // So lange haengt eine Abfrage bei Telegram, wenn es nichts zu tun gibt.
  lauschen: Math.min(60, zahl(process.env.BOT_POLL_SECONDS, 45)),
  maxHits: zahl(process.env.BOT_MAX_HITS, 20000),
  listeImChat: zahl(process.env.BOT_MAX_LIST, 500),
  allowedUser: (process.env.TELEGRAM_ALLOWED_USERNAME ?? 'vvalora').replace(/^@/, '').toLowerCase(),
  chatIdEnv: process.env.TELEGRAM_CHAT_ID || null,
  startScan: (process.env.BOT_START_SCAN || '').trim().replace(/^@/, ''),
  einmal: process.argv.includes('--once') || process.env.BOT_ONCE === '1',
};

const HILFE = [
  'Ich durchsuche die Followerliste eines Instagram-Accounts nach Profilnamen',
  'mit koreanischen Zeichen und melde dir die Treffer Etappe fuer Etappe.',
  '',
  'Befehle:',
  '/scan <account> [anzahl]  Scan starten, z.B. /scan vikavalora',
  '/status                   Zwischenstand anzeigen',
  '/stop                     laufenden Scan anhalten',
  '/weiter                   angehaltenen Scan fortsetzen',
  '/liste                    komplette Ergebnisliste noch einmal schicken',
  '/hilfe                    diese Uebersicht',
  '',
  'Ich arbeite bewusst langsam: pro Etappe ein Stueck der Liste, dann Pause.',
  'Bei grossen Accounts dauert ein Scan deshalb mehrere Stunden -- du bekommst',
  'aber nach jeder Etappe die neuen Treffer geschickt.',
].join('\n');

const log = (text) => process.stderr.write(`${text}\n`);

/** Eine Trefferzeile fuer den Chat: "12. minjun_kim - 김민준" */
function trefferZeilen(hits, startIndex = 0) {
  return hits.map((hit, i) => {
    const name = hit.full_name ? ` - ${hit.full_name}` : '';
    return `${startIndex + i + 1}. ${hit.username}${name}`;
  });
}

function fortschritt(job) {
  const teile = [`${job.checked} Profile geprueft`];
  if (job.totalFollowers) {
    const anteil = Math.min(100, Math.round((job.checked / job.totalFollowers) * 100));
    teile[0] = `${job.checked} von ca. ${job.totalFollowers} Profilen geprueft (${anteil} %)`;
  }
  teile.push(`${job.hits.length} Treffer`);
  return teile.join(', ');
}

// --- Befehle -------------------------------------------------------------

async function kommandosVerarbeiten(tg, state, lauschen = 0) {
  let updates;
  try {
    updates = await tg.getUpdates(state.telegramOffset, { timeout: lauschen });
  } catch (fehler) {
    log(`Konnte keine Nachrichten abholen: ${fehler.message}`);
    return;
  }

  for (const update of updates) {
    state.telegramOffset = update.update_id + 1;
    const nachricht = update.message;
    const text = nachricht?.text?.trim();
    if (!text) continue;

    const absender = (nachricht.from?.username || '').toLowerCase();
    const chatId = nachricht.chat?.id;
    const erlaubt =
      (KONFIG.allowedUser && absender === KONFIG.allowedUser) ||
      (KONFIG.chatIdEnv && String(chatId) === String(KONFIG.chatIdEnv));
    if (!erlaubt) {
      log(`Nachricht von @${absender || '?'} ignoriert (nicht freigeschaltet).`);
      continue;
    }
    state.chatId = chatId;

    const [befehlRoh, ...rest] = text.split(/\s+/);
    const befehl = befehlRoh.toLowerCase().split('@')[0];
    await befehlAusfuehren(tg, state, befehl, rest, chatId);
  }
}

async function befehlAusfuehren(tg, state, befehl, rest, chatId) {
  const job = state.job;

  switch (befehl) {
    case '/start':
    case '/help':
    case '/hilfe':
      await tg.sendMessage(chatId, HILFE);
      return;

    case '/scan': {
      const account = (rest[0] || '').replace(/^@/, '').replace(/\/$/, '');
      if (!account) {
        await tg.sendMessage(chatId, 'So bitte: /scan vikavalora (optional mit Anzahl: /scan vikavalora 500)');
        return;
      }
      if (job && job.status === 'running') {
        await tg.sendMessage(
          chatId,
          `Es laeuft schon ein Scan fuer @${job.username} (${fortschritt(job)}).\nMit /stop beenden, dann neu starten.`,
        );
        return;
      }
      if (job) archivieren(state, job);

      const zahlArg = rest.slice(1).map(Number).find((n) => Number.isFinite(n) && n > 0);
      state.job = neuerAuftrag(account, zahlArg ?? null);
      await tg.sendMessage(
        chatId,
        `Alles klar, ich nehme mir @${account} vor${state.job.limit ? ` (die ersten ${state.job.limit} Follower)` : ''}.\nEs geht gleich los.`,
      );
      return;
    }

    case '/status': {
      if (!job) {
        await tg.sendMessage(chatId, 'Gerade laeuft nichts. Starte mit /scan <account>.');
        return;
      }
      const zustand = {
        running: 'laeuft',
        paused: 'angehalten (Problem, siehe unten)',
        stopped: 'von dir gestoppt',
        done: 'abgeschlossen',
      }[job.status];
      const zeilen = [
        `Account: @${job.username}`,
        `Stand: ${zustand}`,
        fortschritt(job),
        `Zuletzt aktualisiert: ${job.updatedAt.replace('T', ' ').slice(0, 16)} UTC`,
      ];
      if (job.hinweis) zeilen.push('', job.hinweis);
      if (job.status === 'stopped' || job.status === 'paused') zeilen.push('', 'Weiter geht es mit /weiter.');
      await tg.sendMessage(chatId, zeilen.join('\n'));
      return;
    }

    case '/stop':
      if (!job || job.status !== 'running') {
        await tg.sendMessage(chatId, 'Es laeuft gerade kein Scan.');
        return;
      }
      job.status = 'stopped';
      await tg.sendMessage(chatId, `Angehalten bei ${fortschritt(job)}.\nMit /weiter mache ich dort weiter, /liste zeigt die Treffer.`);
      return;

    case '/weiter':
    case '/resume':
      if (!job) {
        await tg.sendMessage(chatId, 'Es gibt keinen Scan zum Fortsetzen. Starte einen mit /scan <account>.');
        return;
      }
      if (job.status === 'done') {
        await tg.sendMessage(chatId, `Der Scan fuer @${job.username} ist schon durch. /liste zeigt die Ergebnisse.`);
        return;
      }
      job.status = 'running';
      job.fehlerInFolge = 0;
      job.hinweis = '';
      await tg.sendMessage(chatId, `Mache weiter bei @${job.username} (${fortschritt(job)}).`);
      return;

    case '/liste':
    case '/ergebnisse':
    case '/results':
      if (!job) {
        await tg.sendMessage(chatId, 'Noch keine Ergebnisse da. Starte mit /scan <account>.');
        return;
      }
      await ergebnisseSchicken(tg, chatId, job, job.status === 'done');
      return;

    default:
      await tg.sendMessage(chatId, `Den Befehl "${befehl}" kenne ich nicht.\n\n${HILFE}`);
  }
}

function archivieren(state, job) {
  state.archiv = [
    ...(state.archiv ?? []),
    {
      username: job.username,
      checked: job.checked,
      treffer: job.hits.length,
      status: job.status,
      beendet: new Date().toISOString(),
    },
  ].slice(-20);
}

// --- Ergebnisse ----------------------------------------------------------

async function ergebnisseSchicken(tg, chatId, job, abgeschlossen) {
  const kopf = [
    abgeschlossen ? `Fertig: @${job.username}` : `Zwischenstand: @${job.username}`,
    fortschritt(job),
  ].join('\n');

  if (job.hits.length === 0) {
    await tg.sendMessage(chatId, `${kopf}\n\nBisher kein Profilname mit koreanischen Zeichen dabei.`);
    return;
  }

  const gezeigt = job.hits.slice(0, KONFIG.listeImChat);
  const zeilen = [kopf, '', ...trefferZeilen(gezeigt)];
  if (job.hits.length > gezeigt.length) {
    zeilen.push('', `... und ${job.hits.length - gezeigt.length} weitere -- alle stehen in der angehaengten Datei.`);
  }
  await tg.sendMessage(chatId, zeilen.join('\n'));

  const csv = toCsv(
    job.hits.map((hit) => ({
      username: hit.username,
      full_name: hit.full_name,
      korean_chars: hit.chars,
      matched_fields: hit.felder,
      profile_url: `https://www.instagram.com/${hit.username}/`,
    })),
    ['username', 'full_name', 'korean_chars', 'matched_fields', 'profile_url'],
  );
  const datei = `koreanisch-${job.username}-${new Date().toISOString().slice(0, 10)}.csv`;
  try {
    await tg.sendDocument(chatId, datei, csv, `${job.hits.length} Treffer bei @${job.username}`);
  } catch (fehler) {
    log(`Datei konnte nicht geschickt werden: ${fehler.message}`);
  }
}

// --- Eine Etappe abarbeiten ---------------------------------------------

/** Prueft ein Profil und merkt sich einen Treffer. */
function pruefen(job, user) {
  job.checked += 1;
  const { matched, chars, fields } = inspectFields({
    full_name: user.full_name,
    username: user.username,
  });
  if (!matched || job.hits.length >= KONFIG.maxHits) return;
  job.hits.push({
    username: user.username,
    full_name: user.full_name,
    chars: chars.join(''),
    felder: fields.join('|'),
  });
}

/** Meldet zwischendurch, sobald genug Profile geprueft wurden -- aber nur mit Inhalt. */
async function vielleichtMelden(tg, chatId, job) {
  if (job.checked - job.gemeldetBei < KONFIG.stageSize) return;
  if (job.hits.length > job.gemeldet) await etappeMelden(tg, chatId, job);
  job.gemeldetBei = job.checked;
}

// Bis wann der Bot vor dem naechsten Seitenabruf pausiert. Die Wartezeit
// verbringt er lauschend bei Telegram, damit /stop trotzdem sofort ankommt.
let pauseBis = 0;

/**
 * Ein Arbeitsschritt: eine Seite der Followerliste holen und pruefen.
 * Danach setzt er die naechste Pause und kehrt zurueck -- so bleibt der Bot
 * zwischendurch immer ansprechbar.
 */
async function scanSchritt(tg, state) {
  const job = state.job;
  if (!job || job.status !== 'running') return;
  if (!state.chatId) {
    log('Kein Chat bekannt -- schreib dem Bot einmal /start, damit er antworten kann.');
    return;
  }
  const chatId = state.chatId;

  try {
    const client = createClient(process.env.IG_SESSIONID, { delay: KONFIG.delay, onNotice: log });

    // Erster Schritt eines Auftrags: Account nachschlagen.
    if (!job.userId) {
      const profil = await client.fetchProfile(job.username);
      if (profil.is_private && !profil.followed_by_viewer) {
        throw new InstagramError(
          `@${profil.username} ist privat und dein Konto folgt ihm nicht -- die Followerliste ist nicht abrufbar.`,
        );
      }
      job.userId = profil.id;
      job.username = profil.username;
      job.totalFollowers = profil.follower_count;
      job.updatedAt = new Date().toISOString();
      await tg.sendMessage(
        chatId,
        `Scan laeuft: @${profil.username}` +
          (profil.follower_count ? `, ca. ${profil.follower_count} Follower` : '') +
          '\nIch melde mich nach jeder Etappe mit den neuen Treffern.',
      );
      pauseBis = Date.now() + KONFIG.delay;
      return;
    }

    const { users, nextCursor } = await client.fetchFollowerPage(job.userId, {
      cursor: job.cursor,
      pageSize: KONFIG.pageSize,
    });

    for (const user of users) {
      if (job.limit && job.checked >= job.limit) break;
      pruefen(job, user);
    }

    job.cursor = nextCursor;
    job.fehlerInFolge = 0;
    job.updatedAt = new Date().toISOString();

    if (!nextCursor || users.length === 0 || (job.limit && job.checked >= job.limit)) {
      job.status = 'done';
      await ergebnisseSchicken(tg, chatId, job, true);
      archivieren(state, job);
      return;
    }

    if (job.checked - job.gemeldetBei >= KONFIG.stageSize) {
      // Etappe voll: melden, was neu dazugekommen ist, dann laenger pausieren.
      if (job.hits.length > job.gemeldet) await etappeMelden(tg, chatId, job);
      job.gemeldetBei = job.checked;
      pauseBis = Date.now() + KONFIG.etappenPause;
    } else {
      // Leichte Streuung -- gleichmaessige Abstaende fallen eher auf.
      pauseBis = Date.now() + Math.round(KONFIG.delay * (0.8 + Math.random() * 0.5));
    }
  } catch (fehler) {
    await fehlerMelden(tg, state, fehler);
    pauseBis = Date.now() + KONFIG.fehlerPause;
  }
}

async function etappeMelden(tg, chatId, job, pause = false) {
  const neue = job.hits.slice(job.gemeldet);
  const kopf = pause
    ? `Etappe beendet -- ${fortschritt(job)}.\nIch mache beim naechsten Durchlauf automatisch weiter.`
    : `Zwischenstand: ${fortschritt(job)}`;

  if (neue.length === 0) {
    await tg.sendMessage(chatId, `${kopf}\nKeine neuen Treffer in diesem Abschnitt.`);
    return;
  }
  const zeilen = [
    kopf,
    '',
    `Neu gefunden (${neue.length}):`,
    ...trefferZeilen(neue, job.gemeldet),
  ];
  await tg.sendMessage(chatId, zeilen.join('\n'));
  job.gemeldet = job.hits.length;
}

async function fehlerMelden(tg, state, fehler) {
  const job = state.job;
  const chatId = state.chatId;
  const abgelaufen = fehler instanceof InstagramError && [401, 403, 302].includes(fehler.status);

  if (abgelaufen) {
    job.status = 'paused';
    job.hinweis =
      'Das Instagram-Cookie (IG_SESSIONID) ist abgelaufen oder fehlt. Neu auslesen, ' +
      'in bot.env eintragen, Dienst neu starten, dann /weiter.';
    if (chatId) {
      await tg.sendMessage(
        chatId,
        `Ich komme nicht mehr an die Daten: ${fehler.message}\n\n${job.hinweis}\n\nDein Stand bleibt gespeichert: ${fortschritt(job)}`,
      );
    }
    return;
  }

  job.fehlerInFolge = (job.fehlerInFolge ?? 0) + 1;
  job.hinweis = fehler.message;
  const aufgeben = job.fehlerInFolge >= 3;
  if (aufgeben) job.status = 'paused';

  log(`Fehler in Etappe (${job.fehlerInFolge}. in Folge): ${fehler.message}`);
  if (!chatId) return;
  await tg.sendMessage(
    chatId,
    aufgeben
      ? `Drei Etappen hintereinander schiefgegangen, ich halte an.\nLetzter Fehler: ${fehler.message}\n\nStand: ${fortschritt(job)}\nWeiter mit /weiter.`
      : `Diese Etappe ging schief: ${fehler.message}\nIch versuche es beim naechsten Durchlauf wieder (Stand: ${fortschritt(job)}).`,
  );
}

// --- Ablauf --------------------------------------------------------------

async function main() {
  let tg;
  try {
    tg = createTelegram(process.env.TELEGRAM_BOT_TOKEN, { onNotice: log });
  } catch (fehler) {
    log(`Fehler: ${fehler.message}`);
    process.exitCode = 1;
    return;
  }
  if (envDatei) log(`Konfiguration aus ${envDatei} gelesen.`);

  const state = await loadState(KONFIG.stateFile);
  if (!state.chatId && KONFIG.chatIdEnv) state.chatId = KONFIG.chatIdEnv;

  // Start ueber die Kommandozeile: BOT_START_SCAN=name node bot.mjs
  if (KONFIG.startScan && state.job?.status !== 'running') {
    if (state.job) archivieren(state, state.job);
    state.job = neuerAuftrag(KONFIG.startScan);
    log(`Scan fuer @${KONFIG.startScan} gestartet.`);
  }

  // Sauber aufhoeren: bei systemctl stop / Strg+C den Stand noch sichern.
  let laufend = true;
  const beenden = (signal) => {
    if (!laufend) process.exit(130);
    laufend = false;
    log(`${signal} empfangen -- beende nach dem laufenden Schritt.`);
  };
  process.on('SIGINT', () => beenden('SIGINT'));
  process.on('SIGTERM', () => beenden('SIGTERM'));

  log(KONFIG.einmal ? 'Einmal-Durchlauf.' : 'Dauerbetrieb -- warte auf Befehle.');

  while (laufend) {
    const jobLaeuft = state.job?.status === 'running';
    const restPause = Math.max(0, pauseBis - Date.now());

    // Wartezeit nicht verschlafen, sondern bei Telegram lauschen. Kommt ein
    // Befehl, kehrt die Abfrage sofort zurueck.
    let lauschen = 0;
    if (!jobLaeuft && !KONFIG.einmal) lauschen = KONFIG.lauschen;
    else if (restPause > 0) lauschen = Math.min(KONFIG.lauschen, Math.ceil(restPause / 1000));

    try {
      const vorher = Date.now();
      await kommandosVerarbeiten(tg, state, lauschen);
      if (state.job?.status === 'running' && Date.now() >= pauseBis) {
        await scanSchritt(tg, state);
      } else if (Date.now() - vorher < 200) {
        // Die Abfrage kam sofort zurueck (weil Nachrichten anlagen oder
        // Telegram nicht wartet): kurz schlafen, statt im Kreis zu drehen.
        const rest = Math.max(0, pauseBis - Date.now());
        await sleep(Math.min(Math.max(rest, 1000), 2000));
      }
    } catch (fehler) {
      // Nichts darf den Dauerlauf beenden -- im Zweifel kurz warten.
      log(`Unerwarteter Fehler: ${fehler.stack ?? fehler.message}`);
      await sleep(KONFIG.fehlerPause);
    }

    await saveState(KONFIG.stateFile, state);

    if (KONFIG.einmal && state.job?.status !== 'running') break;
  }

  const job = state.job;
  log(job ? `Beendet. Stand: @${job.username}, ${job.status}, ${fortschritt(job)}` : 'Beendet (kein Auftrag).');
}

main();
