// Schmale Huelle um die Telegram-Bot-API. Ohne Zusatzpakete, nur fetch.
//
// Nachrichten werden bewusst als reiner Text verschickt (kein Markdown/HTML):
// In Profilnamen stecken haeufig Sonderzeichen, die eine Formatierung sonst
// zerschiessen wuerden.

import { setTimeout as sleep } from 'node:timers/promises';

const MAX_LAENGE = 3900; // Telegram erlaubt 4096 Zeichen pro Nachricht

export class TelegramError extends Error {
  constructor(message, { status } = {}) {
    super(message);
    this.name = 'TelegramError';
    this.status = status;
  }
}

export function createTelegram(token, { onNotice = () => {} } = {}) {
  if (!token) {
    throw new TelegramError('Kein Bot-Token vorhanden (TELEGRAM_BOT_TOKEN).');
  }
  const base = `https://api.telegram.org/bot${token}`;

  async function api(method, payload, { retries = 3 } = {}) {
    for (let versuch = 0; ; versuch++) {
      let response;
      try {
        response =
          payload instanceof FormData
            ? await fetch(`${base}/${method}`, { method: 'POST', body: payload })
            : await fetch(`${base}/${method}`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(payload ?? {}),
              });
      } catch (cause) {
        if (versuch >= retries) throw new TelegramError(`Netzwerkfehler bei ${method}: ${cause.message}`);
        await sleep(2000 * 2 ** versuch);
        continue;
      }

      const data = await response.json().catch(() => null);
      if (response.ok && data?.ok) return data.result;

      // Telegram drosselt und sagt selbst, wie lange gewartet werden soll.
      const warte = data?.parameters?.retry_after;
      if ((response.status === 429 || response.status >= 500) && versuch < retries) {
        const ms = warte ? (warte + 1) * 1000 : 2000 * 2 ** versuch;
        onNotice(`Telegram bremst (${response.status}) -- warte ${Math.round(ms / 1000)}s ...`);
        await sleep(ms);
        continue;
      }
      throw new TelegramError(
        `Telegram-Fehler bei ${method}: ${data?.description ?? response.status}`,
        { status: response.status },
      );
    }
  }

  /** Zerlegt langen Text an Zeilenumbruechen in versandfertige Haeppchen. */
  function chunk(text) {
    const teile = [];
    let aktuell = '';
    for (const zeile of String(text).split('\n')) {
      const stueck = zeile.length > MAX_LAENGE ? zeile.slice(0, MAX_LAENGE) : zeile;
      if (aktuell.length + stueck.length + 1 > MAX_LAENGE) {
        if (aktuell) teile.push(aktuell);
        aktuell = stueck;
      } else {
        aktuell = aktuell ? `${aktuell}\n${stueck}` : stueck;
      }
    }
    if (aktuell) teile.push(aktuell);
    return teile.length > 0 ? teile : [''];
  }

  /** Verschickt Text und teilt ihn bei Bedarf auf mehrere Nachrichten auf. */
  async function sendMessage(chatId, text) {
    const teile = chunk(text);
    for (const [index, teil] of teile.entries()) {
      await api('sendMessage', {
        chat_id: chatId,
        text: teil,
        disable_web_page_preview: true,
      });
      if (index < teile.length - 1) await sleep(600);
    }
  }

  /** Haengt eine Datei an (z.B. die fertige Ergebnisliste als CSV). */
  async function sendDocument(chatId, filename, inhalt, caption = '') {
    const form = new FormData();
    form.set('chat_id', String(chatId));
    if (caption) form.set('caption', caption.slice(0, 1000));
    form.set('document', new Blob([inhalt], { type: 'text/csv' }), filename);
    return api('sendDocument', form);
  }

  /** Holt neue Nachrichten ab; `offset` ist die zuletzt verarbeitete ID + 1. */
  async function getUpdates(offset, { timeout = 0, limit = 50 } = {}) {
    return api('getUpdates', {
      offset: offset ?? undefined,
      timeout,
      limit,
      allowed_updates: ['message'],
    });
  }

  return { api, sendMessage, sendDocument, getUpdates, chunk };
}
