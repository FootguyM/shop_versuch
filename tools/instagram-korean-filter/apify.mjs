// Zugriff auf Apify: dort laufen fertige Scraper ("Actors"), die die
// Followerliste holen, ohne dass wir selbst bei Instagram eingeloggt sind.
//
// Angesprochen wird die normale REST-API mit einem API-Token -- nicht der
// MCP-Server. MCP funktioniert nur in einem Chat-Programm, das ihn startet;
// der Bot laeuft unbeaufsichtigt bei GitHub und braucht deshalb HTTP.
//
// Ablauf: Lauf starten -> Apify sammelt ein -> wir lesen den Datensatz
// haeppchenweise aus. Weil Apify die Ergebnisse schon waehrend des Laufs
// ablegt, koennen wir sie einlesen, bevor er fertig ist.

const BASE = 'https://api.apify.com/v2';

export class ApifyError extends Error {
  constructor(message, { status, hint } = {}) {
    super(message);
    this.name = 'ApifyError';
    this.status = status;
    this.hint = hint;
  }
}

/** In der API steht eine Tilde statt des Schraegstrichs: user~actor */
export function actorPfad(actor) {
  return String(actor).trim().replace('/', '~');
}

/**
 * Baut die Eingabe fuer den Actor aus einer Vorlage.
 * Platzhalter: {{username}} und {{limit}} -- {{limit}} wird zur Zahl.
 */
export function baueEingabe(vorlage, { username, limit }) {
  const ersetzt = String(vorlage)
    .replaceAll('"{{limit}}"', String(limit))
    .replaceAll('{{limit}}', String(limit))
    .replaceAll('{{username}}', username);
  try {
    return JSON.parse(ersetzt);
  } catch (fehler) {
    throw new ApifyError(`APIFY_INPUT ist kein gueltiges JSON: ${fehler.message}`, {
      hint: `Ergebnis nach dem Einsetzen: ${ersetzt.slice(0, 200)}`,
    });
  }
}

/**
 * Holt Benutzername und Profilname aus einem Datensatz-Eintrag. Jeder Actor
 * benennt seine Felder etwas anders, deshalb werden die ueblichen Varianten
 * der Reihe nach probiert.
 */
export function leseProfil(eintrag) {
  if (!eintrag || typeof eintrag !== 'object') return null;
  const feld = (...namen) => {
    for (const name of namen) {
      const wert = eintrag[name];
      if (typeof wert === 'string' && wert.trim()) return wert.trim();
    }
    return '';
  };
  const username = feld('username', 'userName', 'user_name', 'handle', 'ownerUsername', 'instaId');
  if (!username) return null;
  return {
    username,
    full_name: feld('fullName', 'full_name', 'name', 'displayName', 'title', 'profileName'),
  };
}

export function createApify(token, { onNotice = () => {} } = {}) {
  if (!token) {
    throw new ApifyError('Kein Apify-Token vorhanden (APIFY_TOKEN).', {
      status: 401,
      hint: 'Token unter apify.com -> Settings -> Integrations anlegen und als Secret hinterlegen.',
    });
  }

  async function anfrage(pfad, { method = 'GET', body, query = {} } = {}) {
    const url = new URL(`${BASE}${pfad}`);
    for (const [name, wert] of Object.entries(query)) {
      if (wert !== undefined && wert !== null) url.searchParams.set(name, String(wert));
    }
    const response = await fetch(url, {
      method,
      headers: {
        Authorization: `Bearer ${token}`,
        ...(body ? { 'Content-Type': 'application/json' } : {}),
      },
      body: body ? JSON.stringify(body) : undefined,
    });

    if (response.status === 401 || response.status === 403) {
      throw new ApifyError('Apify lehnt das Token ab.', {
        status: response.status,
        hint: 'APIFY_TOKEN pruefen bzw. erneuern.',
      });
    }
    if (response.status === 402) {
      throw new ApifyError('Apify-Guthaben aufgebraucht.', {
        status: 402,
        hint: 'Im Apify-Konto nachsehen -- der Gratis-Rahmen reicht nur fuer wenige tausend Ergebnisse.',
      });
    }
    if (response.status === 404) {
      throw new ApifyError('Von Apify nicht gefunden (falscher Actor-Name?).', { status: 404 });
    }
    if (!response.ok) {
      const text = await response.text().catch(() => '');
      throw new ApifyError(`Apify antwortet mit ${response.status}: ${text.slice(0, 200)}`, {
        status: response.status,
      });
    }
    return response;
  }

  /** Startet einen Lauf und liefert Lauf- und Datensatz-Kennung. */
  async function startRun(actor, input) {
    onNotice(`Starte Apify-Actor ${actor} ...`);
    const response = await anfrage(`/acts/${actorPfad(actor)}/runs`, { method: 'POST', body: input });
    const daten = (await response.json())?.data;
    if (!daten?.id) throw new ApifyError('Apify hat keinen Lauf zurueckgemeldet.');
    return { runId: daten.id, datasetId: daten.defaultDatasetId, status: daten.status };
  }

  /** Fragt den Stand eines Laufs ab. */
  async function getRun(runId) {
    const daten = (await (await anfrage(`/actor-runs/${runId}`)).json())?.data;
    return {
      status: daten?.status ?? 'UNKNOWN',
      datasetId: daten?.defaultDatasetId ?? null,
      itemCount: daten?.stats?.itemCount ?? null,
    };
  }

  /** Liest ein Stueck des Datensatzes ab Position `offset`. */
  async function datasetItems(datasetId, { offset = 0, limit = 500 } = {}) {
    const response = await anfrage(`/datasets/${datasetId}/items`, {
      query: { offset, limit, clean: 'true', format: 'json' },
    });
    const gesamt = Number(response.headers.get('x-apify-pagination-total'));
    const items = await response.json();
    return {
      items: Array.isArray(items) ? items : [],
      gesamt: Number.isFinite(gesamt) ? gesamt : null,
    };
  }

  async function abortRun(runId) {
    try {
      await anfrage(`/actor-runs/${runId}/abort`, { method: 'POST' });
    } catch (fehler) {
      onNotice(`Lauf liess sich nicht abbrechen: ${fehler.message}`);
    }
  }

  return { startRun, getRun, datasetItems, abortRun };
}
