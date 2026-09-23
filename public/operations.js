'use strict';
(() => {
  const $ = (id) => document.getElementById(id);
  let token = '', timer = null, active = null, generation = 0, current = null;
  const terminal = new Set(['succeeded', 'failed', 'cancelled']);
  function node(tag, text, cls) { const e = document.createElement(tag); if (text !== undefined) e.textContent = text; if (cls) e.className = cls; return e; }
  function problem(text) { $('error').textContent = text; $('error').hidden = !text; }
  function clearData() {
    current = null;
    $('board').value = '';
    for (const id of ['metric-jobs', 'metric-chunks', 'metric-runs', 'metric-worker']) $(id).textContent = '—';
    $('checks').replaceChildren(node('li', 'Unlock the operator workspace to inspect readiness.'));
    $('runs').replaceChildren(node('p', 'No private import history is displayed while locked.', 'empty'));
    $('queue-button').disabled = true;
    $('checked').textContent = 'Not checked yet';
    $('worker-caption').textContent = 'Separate from web requests';
  }
  async function request(path, options = {}) {
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), 20000);
    try {
      const response = await fetch(path, { ...options, signal: options.signal || controller.signal,
        headers: { 'Content-Type': 'application/json', ...(token ? { Authorization: `Bearer ${token}` } : {}), ...(options.headers || {}) }, cache: 'no-store' });
      const data = await response.json();
      if (!response.ok) { const error = new Error(data.detail || `Request failed (${response.status}).`); error.status = response.status; throw error; }
      return data;
    } finally { clearTimeout(timeout); }
  }
  function render(data) {
    current = data;
    $('mode').textContent = data.mode === 'demo' ? 'Read-only demo' : 'Private live workspace';
    $('release').textContent = `v${data.release.version} · ${data.release.commit}`;
    $('checked').textContent = `Checked ${new Date().toLocaleTimeString()}`;
    $('notice').textContent = data.notice;
    $('metric-jobs').textContent = data.stats?.jobs ?? '—';
    $('metric-chunks').textContent = data.stats?.chunks ?? '—';
    $('metric-runs').textContent = data.runs.filter(r => !terminal.has(r.state)).length;
    $('metric-worker').textContent = data.mode === 'demo' ? 'Off' : data.worker?.recent ? 'Recent' : 'Not seen';
    $('worker-caption').textContent = data.mode === 'demo' ? 'Not started in demo mode' : data.worker?.last_seen ? `Last seen ${new Date(data.worker.last_seen).toLocaleString()}` : 'Start the separate worker process';
    $('metric-caption').textContent = data.mode === 'demo' ? 'Fictional demonstration roles' : 'Active source records';
    $('queue-button').disabled = !data.can_enqueue;
    $('queue-help').textContent = data.mode === 'demo' ? 'Demo mode is read-only. No import or paid API call will be made.' : data.can_enqueue ? 'A queued request is not a completed import. Keep a worker running to make progress.' : 'Configure separate tokens, migrations and embedding credentials first.';
    $('checks').replaceChildren(...data.checks.map(check => {
      const li = node('li'); li.append(node('span', check.ok ? '✓' : '!', `check-icon${check.ok ? '' : ' warn'}`));
      const copy = node('div'); copy.append(node('strong', check.label), node('p', check.detail)); li.append(copy); return li;
    }));
    if (!data.runs.length) {
      $('runs').replaceChildren(node('p', data.mode === 'demo' ? 'No import runs. This is the real, read-only demo state—not simulated activity.' : 'No imports yet. Queue an authorized Greenhouse board to begin.', 'empty'));
      return;
    }
    const list = node('div', undefined, 'run-list');
    for (const run of data.runs) {
      const row = node('article', undefined, 'run');
      const info = node('div'); info.append(node('strong', run.board), node('small', `Created ${new Date(run.created_at).toLocaleString()}`), node('small', `Run ${run.id.slice(0, 8)} · ${run.failures} failures`));
      const status = node('div'); status.append(node('span', `${run.state} · ${run.processed}/${run.total || '?'} roles`, 'state'));
      const progress = node('progress'); progress.max = Math.max(1, run.total); progress.value = run.processed; progress.setAttribute('aria-label', `${run.board} import progress`); status.append(progress);
      if (run.error_code) status.append(node('small', run.error_code.replaceAll('_', ' '), 'run-error'));
      row.append(info, status);
      if (!terminal.has(run.state)) { const cancel = node('button', 'Cancel', 'secondary'); cancel.type = 'button'; cancel.dataset.cancel = run.id; cancel.setAttribute('aria-label', `Cancel ${run.board} import`); row.append(cancel); }
      list.append(row);
    }
    $('runs').replaceChildren(list);
  }
  async function refresh() {
    if (active) return;
    const epoch = generation;
    const controller = new AbortController(); active = controller;
    const timeout = setTimeout(() => controller.abort(), 20000);
    $('refresh').disabled = true;
    try {
      const data = await request('/api/operations', { signal: controller.signal });
      if (epoch !== generation) return;
      problem(''); render(data);
    } catch (err) {
      if (epoch !== generation) return;
      if (err.status === 401 || err.status === 503) clearData();
      problem(err.name === 'AbortError' ? 'The status request timed out. Refresh to try again.' : err.message);
    } finally {
      clearTimeout(timeout);
      if (active === controller) { active = null; $('refresh').disabled = false; }
    }
  }
  function invalidate() { generation++; if (active) active.abort(); active = null; $('refresh').disabled = false; }
  $('unlock-form').addEventListener('submit', e => { e.preventDefault(); invalidate(); token = $('operator-token').value; $('operator-token').value = ''; clearData(); refresh(); });
  $('lock').addEventListener('click', () => { invalidate(); token = ''; $('operator-token').value = ''; clearData(); problem(''); $('notice').textContent = 'Access cleared. Private operation details have been removed.'; });
  $('refresh').addEventListener('click', refresh);
  $('queue-form').addEventListener('submit', async e => {
    e.preventDefault(); if (!current?.can_enqueue) return;
    const epoch = generation; $('queue-button').disabled = true;
    try { await request('/api/import-runs', { method: 'POST', body: JSON.stringify({ board: $('board').value.trim() }) }); if (epoch === generation) { $('board').value = ''; await refresh(); } }
    catch (err) { if (epoch === generation) problem(err.name === 'AbortError' ? 'Import request timed out. Refresh history before retrying; an active board is deduplicated.' : err.message); }
    finally { if (epoch === generation) $('queue-button').disabled = !current?.can_enqueue; }
  });
  $('runs').addEventListener('click', async e => {
    const button = e.target.closest('button[data-cancel]'); if (!button) return;
    const epoch = generation; button.disabled = true;
    try { await request(`/api/import-runs/${encodeURIComponent(button.dataset.cancel)}`, { method: 'DELETE' }); if (epoch === generation) await refresh(); }
    catch (err) { if (epoch === generation) { problem(err.message); button.disabled = false; } }
  });
  $('auto-refresh').addEventListener('change', () => {
    clearInterval(timer); timer = null;
    if ($('auto-refresh').checked) timer = setInterval(() => { if (!document.hidden) refresh(); }, 15000);
  });
  window.addEventListener('pagehide', () => { clearInterval(timer); invalidate(); token = ''; $('operator-token').value = ''; clearData(); });
  refresh();
})();
