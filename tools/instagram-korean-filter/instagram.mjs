// Minimaler Zugriff auf die Web-Schnittstelle von Instagram.
//
// Instagram bietet keine offizielle API fuer Followerlisten an. Genutzt wird
// daher dieselbe interne Schnittstelle, die auch die Webseite im Browser
// verwendet -- mit der Session des eigenen, eingeloggten Accounts.
// Entsprechend gilt: sparsam abfragen (siehe --delay), sonst drosselt oder
// sperrt Instagram die Anfragen.

import { setTimeout as sleep } from 'node:timers/promises';

const BASE = 'https://www.instagram.com';
const APP_ID = '936619743392459'; // oeffentliche App-ID des Web-Clients
const USER_AGENT =
  'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 ' +
  '(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36';

export class InstagramError extends Error {
  constructor(message, { status, hint } = {}) {
    super(message);
    this.name = 'InstagramError';
    this.status = status;
    this.hint = hint;
  }
}

/**
 * @param {string} sessionId Wert des `sessionid`-Cookies eines eingeloggten Accounts.
 */
export function createClient(sessionId, { delay = 1500, onNotice = () => {} } = {}) {
  if (!sessionId) {
    throw new InstagramError('Kein sessionid-Cookie uebergeben.', {
      hint: 'Umgebungsvariable IG_SESSIONID setzen (siehe README).',
    });
  }

  const headers = {
    'User-Agent': USER_AGENT,
    'X-IG-App-ID': APP_ID,
    'X-Requested-With': 'XMLHttpRequest',
    Accept: '*/*',
    'Accept-Language': 'en-US,en;q=0.9',
    Referer: `${BASE}/`,
    Cookie: `sessionid=${sessionId}`,
  };

  /** Holt eine JSON-Antwort und wiederholt bei Drosselung mit wachsender Pause. */
  async function getJson(url, { retries = 4 } = {}) {
    let wait = Math.max(delay, 2000);
    for (let versuch = 0; ; versuch++) {
      let response;
      try {
        response = await fetch(url, { headers, redirect: 'manual' });
      } catch (cause) {
        if (versuch >= retries) {
          throw new InstagramError(`Netzwerkfehler bei ${url}: ${cause.message}`);
        }
        onNotice(`Netzwerkfehler, neuer Versuch in ${Math.round(wait / 1000)}s ...`);
        await sleep(wait);
        wait *= 2;
        continue;
      }

      if (response.status === 401 || response.status === 403) {
        throw new InstagramError('Instagram lehnt die Anfrage ab (nicht eingeloggt?).', {
          status: response.status,
          hint: 'IG_SESSIONID ist abgelaufen oder falsch -- Cookie neu auslesen.',
        });
      }
      if (response.status === 302 || response.status === 301) {
        throw new InstagramError('Instagram leitet auf die Login-Seite um.', {
          status: response.status,
          hint: 'IG_SESSIONID ist abgelaufen oder falsch -- Cookie neu auslesen.',
        });
      }
      if (response.status === 404) {
        throw new InstagramError('Nicht gefunden (Account existiert nicht?).', { status: 404 });
      }
      if (response.status === 429 || response.status >= 500) {
        if (versuch >= retries) {
          throw new InstagramError(
            `Instagram antwortet weiterhin mit Status ${response.status}.`,
            {
              status: response.status,
              hint: 'Zu viele Anfragen. Spaeter erneut versuchen oder --delay erhoehen.',
            },
          );
        }
        onNotice(`Status ${response.status} -- Pause von ${Math.round(wait / 1000)}s ...`);
        await sleep(wait);
        wait *= 2;
        continue;
      }

      const text = await response.text();
      let data;
      try {
        data = JSON.parse(text);
      } catch {
        throw new InstagramError(
          `Unerwartete Antwort von Instagram (Status ${response.status}, kein JSON).`,
          {
            status: response.status,
            hint: 'Meist ein Zeichen dafuer, dass die Session ungueltig ist.',
          },
        );
      }
      if (!response.ok) {
        throw new InstagramError(
          data?.message ? `Instagram: ${data.message}` : `Fehler ${response.status} von Instagram.`,
          { status: response.status },
        );
      }
      return data;
    }
  }

  /** Profilinfos zu einem Benutzernamen (u.a. numerische ID). */
  async function fetchProfile(username) {
    const url = `${BASE}/api/v1/users/web_profile_info/?username=${encodeURIComponent(username)}`;
    const data = await getJson(url);
    const user = data?.data?.user;
    if (!user) {
      throw new InstagramError(`Account "${username}" nicht gefunden.`, { status: 404 });
    }
    return {
      id: user.id,
      username: user.username,
      full_name: user.full_name ?? '',
      is_private: Boolean(user.is_private),
      is_verified: Boolean(user.is_verified),
      followed_by_viewer: Boolean(user.followed_by_viewer),
      follower_count: user.edge_followed_by?.count ?? null,
    };
  }

  /**
   * Laeuft die Followerliste seitenweise durch und liefert einzelne Accounts.
   *
   * @param {string} userId numerische Account-ID
   * @param {{ pageSize?: number, limit?: number|null, onPage?: (n: number, total: number) => void }} opts
   */
  async function* iterateFollowers(userId, { pageSize = 50, limit = null, onPage } = {}) {
    let cursor = null;
    let seen = 0;
    let page = 0;

    while (true) {
      const params = new URLSearchParams({
        count: String(pageSize),
        search_surface: 'follow_list_page',
      });
      if (cursor) params.set('max_id', String(cursor));

      const data = await getJson(`${BASE}/api/v1/friendships/${userId}/followers/?${params}`);
      const users = Array.isArray(data?.users) ? data.users : [];
      page += 1;

      for (const user of users) {
        yield {
          id: user.pk ?? user.id ?? '',
          username: user.username ?? '',
          full_name: user.full_name ?? '',
          is_private: Boolean(user.is_private),
          is_verified: Boolean(user.is_verified),
        };
        seen += 1;
        if (limit !== null && seen >= limit) return;
      }

      if (onPage) onPage(page, seen);

      cursor = data?.next_max_id ?? null;
      if (!cursor || users.length === 0) return;
      await sleep(delay);
    }
  }

  return { fetchProfile, iterateFollowers };
}
