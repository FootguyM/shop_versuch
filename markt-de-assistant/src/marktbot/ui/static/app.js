'use strict';

let status_ = {};
let selectedThread = null;

// --------------------------------------------------------------------------
// Hilfsfunktionen
// --------------------------------------------------------------------------

async function api(path, options = {}) {
  const response = await fetch(path, {
    headers: { 'Content-Type': 'application/json' },
    ...options,
  });
  if (response.status === 401) {
    showLogin();
    throw new Error('Nicht angemeldet');
  }
  const data = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(data.message || `HTTP ${response.status}`);
  return data;
}

function esc(value) {
  return String(value ?? '').replace(/[&<>"']/g, (c) => (
    { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]
  ));
}

function toast(message, kind = '') {
  const element = document.getElementById('toast');
  element.textContent = message;
  element.className = `toast ${kind}`;
  setTimeout(() => element.classList.add('hidden'), 4500);
}

function relTime(iso) {
  if (!iso) return '–';
  const delta = (Date.now() - new Date(iso).getTime()) / 1000;
  if (delta < 60) return 'gerade eben';
  if (delta < 3600) return `vor ${Math.floor(delta / 60)} min`;
  if (delta < 86400) return `vor ${Math.floor(delta / 3600)} h`;
  return new Date(iso).toLocaleDateString('de-DE', { day: '2-digit', month: '2-digit' });
}

// --------------------------------------------------------------------------
// Anmeldung
// --------------------------------------------------------------------------

function showLogin() {
  document.getElementById('login').classList.remove('hidden');
  document.getElementById('app').classList.add('hidden');
}

function showApp() {
  document.getElementById('login').classList.add('hidden');
  document.getElementById('app').classList.remove('hidden');
}

async function doLogin(event) {
  event.preventDefault();
  const errorBox = document.getElementById('login-error');
  errorBox.textContent = '';
  try {
    await api('/api/login', {
      method: 'POST',
      body: JSON.stringify({ password: document.getElementById('pw').value }),
    });
    showApp();
    refreshAll();
  } catch (error) {
    errorBox.textContent = error.message;
  }
}

// --------------------------------------------------------------------------
// Status
// --------------------------------------------------------------------------

async function loadStatus() {
  status_ = await api('/api/status');

  const running = status_.running && !status_.paused;
  document.getElementById('mode-line').textContent =
    `${status_.require_approval ? 'Freigabe-Modus' : 'Vollautomatik'} · KI: ${status_.ai_backend}`;

  const pauseBtn = document.getElementById('btn-pause');
  pauseBtn.textContent = status_.paused ? 'Fortsetzen' : 'Pause';
  pauseBtn.className = status_.paused ? 'btn primary' : 'btn';

  const cell = (label, value, cls = '') =>
    `<div class="stat"><div class="label">${label}</div><div class="value ${cls}">${value}</div></div>`;

  document.getElementById('stats').innerHTML = [
    cell('Automatik', running ? 'läuft' : (status_.paused ? 'pausiert' : 'gestoppt'),
         running ? 'ok' : 'warn'),
    cell('Angemeldet', status_.logged_in ? 'ja' : 'nein', status_.logged_in ? 'ok' : 'bad'),
    cell('KI', status_.ai_ready ? 'bereit' : 'lädt …', status_.ai_ready ? 'ok' : 'warn'),
    cell('Offene Entwürfe', status_.pending_drafts),
    cell('Antworten heute', `${status_.replies_today} / ${status_.limit_day}`,
         status_.replies_today >= status_.limit_day ? 'warn' : ''),
    cell('Nächster Abruf',
         status_.quiet_hours ? 'Ruhezeit' : relTime(status_.next_poll_at).replace('vor', 'in')),
  ].join('');

  document.getElementById('badge-drafts').textContent = status_.pending_drafts;

  const banner = document.getElementById('banner');
  if (status_.last_error) {
    banner.textContent = `Letzter Fehler: ${status_.last_error}`;
    banner.classList.remove('hidden');
  } else {
    banner.classList.add('hidden');
  }
}

async function control(action) {
  const button = document.getElementById('btn-poll');
  button.disabled = true;
  try {
    const result = await api(`/api/control/${action}`, { method: 'POST' });
    if (result.message) toast(result.message, 'ok');
    await refreshAll();
  } catch (error) {
    toast(error.message, 'bad');
  } finally {
    button.disabled = false;
  }
}

async function togglePause() {
  await control(status_.paused ? 'resume' : 'pause');
}

// --------------------------------------------------------------------------
// Entwürfe
// --------------------------------------------------------------------------

async function loadDrafts() {
  const drafts = await api('/api/drafts');
  const container = document.getElementById('drafts-list');

  if (!drafts.length) {
    container.innerHTML = '<p class="muted">Keine offenen Entwürfe.</p>';
    return;
  }

  container.innerHTML = drafts.map((draft) => `
    <div class="card" id="draft-${draft.id}">
      <div class="card-head">
        <strong>${esc(draft.partner_name || draft.thread_id)}</strong>
        <span class="meta">#${draft.id} · ${esc(draft.model_name)} · ${relTime(draft.created_at)}</span>
      </div>
      <textarea id="draft-text-${draft.id}">${esc(draft.text)}</textarea>
      <div class="card-actions">
        <button class="btn primary" onclick="sendDraft(${draft.id})">Senden</button>
        <button class="btn danger" onclick="rejectDraft(${draft.id})">Verwerfen</button>
        <button class="btn small" onclick="openThread('${esc(draft.thread_id)}')">Verlauf ansehen</button>
      </div>
    </div>
  `).join('');
}

async function sendDraft(id) {
  const text = document.getElementById(`draft-text-${id}`).value;
  try {
    const result = await api(`/api/drafts/${id}/send`, {
      method: 'POST',
      body: JSON.stringify({ text }),
    });
    toast(result.message, result.ok ? 'ok' : 'bad');
    await Promise.all([loadDrafts(), loadStatus()]);
  } catch (error) {
    toast(error.message, 'bad');
  }
}

async function rejectDraft(id) {
  try {
    const result = await api(`/api/drafts/${id}/reject`, { method: 'POST' });
    toast(result.message, 'ok');
    await Promise.all([loadDrafts(), loadStatus()]);
  } catch (error) {
    toast(error.message, 'bad');
  }
}

// --------------------------------------------------------------------------
// Postfach
// --------------------------------------------------------------------------

async function loadThreads() {
  const threads = await api('/api/threads');
  const container = document.getElementById('threads-list');

  if (!threads.length) {
    container.innerHTML = '<p class="muted">Noch nichts abgerufen.</p>';
    return;
  }

  container.innerHTML = threads.map((thread) => {
    const dot = thread.escalated ? 'blocked' : (thread.unread ? 'unread' : '');
    return `
      <div class="thread ${thread.thread_id === selectedThread ? 'selected' : ''}"
           onclick="openThread('${esc(thread.thread_id)}')">
        <div class="name"><span class="dot ${dot}"></span>${esc(thread.partner_name || thread.thread_id)}</div>
        <div class="sub">${esc(thread.ad_title || '–')} · ${relTime(thread.last_message_at)}</div>
        ${thread.escalated ? `<div class="sub" style="color:var(--danger)">${esc(thread.escalation_reason)}</div>` : ''}
      </div>`;
  }).join('');
}

async function openThread(threadId) {
  selectedThread = threadId;
  switchTab('inbox');
  await loadThreads();

  const detail = document.getElementById('thread-detail');
  detail.innerHTML = '<p class="muted center">Lade …</p>';

  try {
    const thread = await api(`/api/threads/${encodeURIComponent(threadId)}`);
    const messages = thread.messages.map((message) => `
      <div class="msg ${message.direction}">
        <div class="bubble">${esc(message.body)}</div>
      </div>`).join('');

    detail.innerHTML = `
      <div class="card-head">
        <strong>${esc(thread.partner_name || threadId)}</strong>
        <span class="meta">${thread.url ? `<a href="${esc(thread.url)}" target="_blank" rel="noopener">auf markt.de</a>` : ''}</span>
      </div>
      ${messages || '<p class="muted">Kein Verlauf gespeichert.</p>'}
      <textarea id="manual-text" placeholder="Antwort schreiben …"></textarea>
      <div class="card-actions">
        <button class="btn primary" onclick="sendManual('${esc(threadId)}')">Senden</button>
        <button class="btn" onclick="regenerate('${esc(threadId)}')">KI-Entwurf erzeugen</button>
      </div>`;
    detail.scrollTop = detail.scrollHeight;
  } catch (error) {
    detail.innerHTML = `<p class="error">${esc(error.message)}</p>`;
  }
}

async function sendManual(threadId) {
  const text = document.getElementById('manual-text').value.trim();
  if (!text) return;
  try {
    const result = await api(`/api/threads/${encodeURIComponent(threadId)}/reply`, {
      method: 'POST',
      body: JSON.stringify({ text }),
    });
    toast(result.message, result.ok ? 'ok' : 'bad');
    if (result.ok) await openThread(threadId);
  } catch (error) {
    toast(error.message, 'bad');
  }
}

async function regenerate(threadId) {
  toast('Erzeuge Entwurf …');
  try {
    const result = await api(`/api/threads/${encodeURIComponent(threadId)}/draft`, { method: 'POST' });
    if (result.ok) {
      toast('Entwurf erzeugt.', 'ok');
      switchTab('drafts');
      await Promise.all([loadDrafts(), loadStatus()]);
    } else {
      toast(result.message, 'bad');
    }
  } catch (error) {
    toast(error.message, 'bad');
  }
}

// --------------------------------------------------------------------------
// Anzeigen
// --------------------------------------------------------------------------

async function loadAds(refresh = false) {
  const container = document.getElementById('ads-list');
  if (refresh) container.innerHTML = '<p class="muted">Lade von markt.de …</p>';

  try {
    const ads = await api(`/api/ads?refresh=${refresh ? 'true' : 'false'}`);
    container.innerHTML = ads.length ? ads.map((ad) => `
      <div class="card">
        <div class="card-head">
          <strong>${esc(ad.title)}</strong>
          <span class="meta">${esc(ad.status)} · ${ad.views} Aufrufe${
            ad.age_days != null ? ` · ${Math.round(ad.age_days)} Tage` : ''}</span>
        </div>
        <div class="card-actions">
          <button class="btn" onclick="adAction('${esc(ad.ad_id)}','renew')">Hochschieben</button>
          <button class="btn" onclick="adAction('${esc(ad.ad_id)}','pause')">Pausieren</button>
          <button class="btn danger" onclick="confirmDelete('${esc(ad.ad_id)}','${esc(ad.title)}')">Löschen</button>
          ${ad.url ? `<a class="btn" href="${esc(ad.url)}" target="_blank" rel="noopener">Öffnen</a>` : ''}
        </div>
      </div>`).join('') : '<p class="muted">Keine Anzeigen. "Von markt.de neu laden" holt sie.</p>';
  } catch (error) {
    container.innerHTML = `<p class="error">${esc(error.message)}</p>`;
  }
}

function confirmDelete(adId, title) {
  if (confirm(`Anzeige "${title}" wirklich löschen? Das lässt sich nicht rückgängig machen.`)) {
    adAction(adId, 'delete');
  }
}

async function adAction(adId, action) {
  try {
    const result = await api(`/api/ads/${encodeURIComponent(adId)}/${action}`, { method: 'POST' });
    toast(result.message, result.ok ? 'ok' : 'bad');
    await loadAds(false);
  } catch (error) {
    toast(error.message, 'bad');
  }
}

async function loadTemplates() {
  const container = document.getElementById('templates-list');
  try {
    const templates = await api('/api/ad-templates');
    container.innerHTML = templates.length ? templates.map((template) => `
      <div class="card">
        <div class="card-head">
          <strong>${esc(template.title)}</strong>
          <span class="meta">${esc(template.name)} · ${template.images.length} Bild(er)</span>
        </div>
        <p class="muted" style="white-space:pre-wrap;font-size:.88rem">${esc(template.description.slice(0, 300))}</p>
        <div class="card-actions">
          <button class="btn primary" onclick="createAd('${esc(template.name)}')">Anzeige aufgeben</button>
        </div>
      </div>`).join('')
      : '<p class="muted">Keine Vorlagen. Lege eine YAML-Datei in <code>ads/</code> an – <code>ads/beispiel.yaml</code> zeigt das Format.</p>';
  } catch (error) {
    container.innerHTML = `<p class="error">${esc(error.message)}</p>`;
  }
}

async function createAd(name) {
  if (!confirm(`Anzeige aus Vorlage "${name}" jetzt auf markt.de aufgeben?`)) return;
  toast('Gebe Anzeige auf, das dauert etwas …');
  try {
    const result = await api('/api/ads/create', {
      method: 'POST',
      body: JSON.stringify({ template: name }),
    });
    toast(result.message, result.ok ? 'ok' : 'bad');
    await loadAds(false);
  } catch (error) {
    toast(error.message, 'bad');
  }
}

// --------------------------------------------------------------------------
// Protokoll
// --------------------------------------------------------------------------

async function loadLog() {
  const rows = await api('/api/log');
  document.getElementById('log-body').innerHTML = rows.map((row) => `
    <tr>
      <td class="time">${new Date(row.created_at).toLocaleString('de-DE')}</td>
      <td class="kind"><span class="pill ${row.ok ? 'ok' : 'bad'}">${esc(row.kind)}</span></td>
      <td>${esc(row.detail || row.ref)}</td>
    </tr>`).join('') || '<tr><td class="muted">Noch keine Aktionen.</td></tr>';
}

// --------------------------------------------------------------------------
// Tabs & Start
// --------------------------------------------------------------------------

function switchTab(name) {
  document.querySelectorAll('.tab').forEach((tab) =>
    tab.classList.toggle('active', tab.dataset.tab === name));
  document.querySelectorAll('.panel').forEach((panel) =>
    panel.classList.toggle('active', panel.id === `tab-${name}`));

  if (name === 'ads') { loadAds(false); loadTemplates(); }
  if (name === 'log') loadLog();
  if (name === 'inbox') loadThreads();
}

document.querySelectorAll('.tab').forEach((tab) =>
  tab.addEventListener('click', () => switchTab(tab.dataset.tab)));

async function refreshAll() {
  await Promise.allSettled([loadStatus(), loadDrafts(), loadThreads()]);
}

(async function init() {
  try {
    const auth = await api('/api/auth');
    if (auth.required && !auth.authenticated) { showLogin(); return; }
  } catch {
    showLogin();
    return;
  }
  showApp();
  await refreshAll();
  setInterval(() => { loadStatus().catch(() => {}); }, 10000);
  setInterval(() => { loadDrafts().catch(() => {}); }, 20000);
})();
