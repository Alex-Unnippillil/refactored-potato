'use strict';
(() => {
  const $ = (id) => document.getElementById(id);
  let token = '', timer = null, active = null, generation = 0, current = null, writing = null, editing = null;
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
    resetEditor();
    $('schedules').replaceChildren(node('p', 'No private source schedules are displayed while locked.', 'empty'));
    $('scheduler-state').textContent = 'Not checked';
    $('scheduler-help').textContent = 'Unlock to inspect scheduler configuration and worker activity.';
    $('budget-status').textContent = 'Unlock to inspect live budgets.';
    actionStatus('');
    $('checked').textContent = 'Not checked yet';
    $('worker-caption').textContent = 'Separate from web requests';
  }
  function actionStatus(text) { $('action-status').textContent = text; $('action-status').hidden = !text; }
  function controls() {
    $('queue-button').disabled = !current?.can_enqueue || !!writing;
    $('schedule-submit').disabled = !current?.can_schedule || !!writing;
    for (const button of document.querySelectorAll('[data-schedule-action]')) {
      button.disabled = !current?.can_schedule || !!writing || (button.dataset.scheduleAction === 'run' && !current?.can_enqueue);
    }
    for (const button of document.querySelectorAll('[data-cancel]')) button.disabled = !!writing;
  }
  function resetEditor() {
    editing = null; $('schedule-board').value = ''; $('schedule-board').readOnly = false;
    $('schedule-hours').value = '24'; $('schedule-submit').textContent = 'Add paused source';
    $('schedule-cancel').hidden = true; controls();
  }
  function timestamp(value, fallback) { return value ? new Date(value).toLocaleString() : fallback; }
  function renderSchedules(data) {
    const worker = data.scheduler?.worker;
    $('scheduler-state').textContent = data.mode === 'demo' ? 'Off in demo' : worker?.recent ? 'Scheduler heartbeat recent' : 'Scheduler not seen recently';
    $('scheduler-help').textContent = data.mode === 'demo'
      ? 'The demo has no scheduled sources, no worker activity, and no paid API calls. Live schedules require PostgreSQL and an opted-in worker.'
      : `Worker opt-in: IMPORT_SCHEDULER_ENABLED=true. Web-process setting: ${data.scheduler?.configured ? 'on' : 'off'}. Last scheduler heartbeat: ${timestamp(worker?.last_seen, 'not seen')}. A heartbeat is not provider-health verification.`;
    const budgets = data.budgets;
    $('budget-status').textContent = budgets
      ? `${budgets.queue_requests.remaining} / ${budgets.queue_requests.limit} new runs remaining · ${budgets.import_jobs.remaining} / ${budgets.import_jobs.limit} job attempts remaining today (UTC). Shared with manual queued imports; web and worker limits must match.`
      : 'No live import budget is simulated in the demo.';
    const rows = data.schedules || [];
    if (!rows.length) {
      $('schedules').replaceChildren(node('p', data.mode === 'demo'
        ? 'No recurring sources. Live scheduling is opt-in; the demo never fabricates source activity.'
        : 'No recurring sources yet. Add a paused source above, then resume it when your worker is configured.', 'empty'));
      return;
    }
    const focused = document.activeElement?.dataset;
    const restore = focused?.scheduleAction ? { board: focused.board, action: focused.scheduleAction } : null;
    const list = node('div', undefined, 'source-list');
    for (const source of rows) {
      const card = node('article', undefined, 'source-card'); card.dataset.source = source.board;
      const info = node('div');
      info.append(node('h3', source.board), node('p', `${source.enabled ? 'Scheduled' : 'Paused'} · every ${source.interval_hours} hours`, 'source-status'));
      info.append(node('small', source.enabled ? `Next check: ${timestamp(source.next_run_at, 'pending')}` : 'No future automatic dispatch while paused.'));
      info.append(node('small', `Last dispatch: ${source.dispatch_status.replaceAll('_', ' ')} · ${timestamp(source.last_dispatch_at, 'not attempted')}`));
      const stats = node('div');
      stats.append(node('p', `${source.searchable_roles} searchable / ${source.active_roles} active`, 'source-count'));
      if (source.active_roles > source.searchable_roles) stats.append(node('p', `${source.active_roles - source.searchable_roles} active roles are excluded by freshness or expiry.`, 'source-warning'));
      stats.append(node('small', `Last indexed record: ${timestamp(source.last_indexed_at, 'none')}`));
      stats.append(node('small', `Last retained successful import: ${timestamp(source.last_retained_success_at, 'none in history')}`));
      if (source.last_run_id) stats.append(node('small', `Last linked run: ${source.last_run_state} · ${source.last_run_processed}/${source.last_run_total || '?'} roles${source.last_run_error ? ' · '+source.last_run_error.replaceAll('_', ' ') : ''}`));
      const actions = node('div', undefined, 'source-actions');
      for (const [action, title] of [['toggle', source.enabled ? 'Pause' : 'Resume'], ['run', 'Run now'], ['edit', 'Edit interval'], ['remove', 'Remove']]) {
        const button = node('button', title, 'secondary'); button.type = 'button';
        button.dataset.scheduleAction = action; button.dataset.board = source.board;
        button.setAttribute('aria-label', `${title} ${source.board}`); actions.append(button);
      }
      card.append(info, stats, actions); list.append(card);
    }
    $('schedules').replaceChildren(list);
    controls();
    if (restore) {
      const target = Array.from(list.querySelectorAll('button')).find(b => b.dataset.board === restore.board && b.dataset.scheduleAction === restore.action);
      if (target && !target.disabled) target.focus();
      else $('schedule-board').focus();
    }
  }
  async function request(path, options = {}) {
    const controller = new AbortController();
    const abort = () => controller.abort();
    if (options.signal?.aborted) controller.abort();
    options.signal?.addEventListener('abort', abort, { once: true });
    const timeout = setTimeout(abort, 20000);
    try {
      const response = await fetch(path, { ...options, signal: controller.signal,
        headers: { 'Content-Type': 'application/json', ...(token ? { Authorization: `Bearer ${token}` } : {}), ...(options.headers || {}) }, cache: 'no-store' });
      const data = await response.json();
      if (!response.ok) { const error = new Error(typeof data.detail === 'string' ? data.detail : `Request failed (${response.status}). Check the input and refresh.`); error.status = response.status; throw error; }
      return data;
    } finally { clearTimeout(timeout); options.signal?.removeEventListener('abort', abort); }
  }
  async function mutate(path, options, success) {
    if (writing) return;
    invalidate(); const epoch = generation; const controller = new AbortController(); writing = controller; controls();
    problem(''); actionStatus('');
    try {
      const result = await request(path, { ...options, signal: controller.signal });
      if (epoch !== generation) return;
      writing = null; success(result); await refresh();
    } catch (err) {
      if (epoch !== generation) return;
      if (err.status === 401) clearData();
      problem(err.name === 'AbortError' ? 'The request timed out. Refresh before retrying; the server may already have accepted it.' : err.message);
    } finally { if (writing === controller) writing = null; if (epoch === generation) controls(); }
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
    renderSchedules(data); controls();
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
    if (active || writing) return;
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
  function invalidate() { generation++; if (active) active.abort(); if (writing) writing.abort(); active = null; writing = null; $('refresh').disabled = false; }
  $('unlock-form').addEventListener('submit', e => { e.preventDefault(); invalidate(); token = $('operator-token').value; $('operator-token').value = ''; clearData(); refresh(); });
  $('lock').addEventListener('click', () => { invalidate(); clearInterval(timer); timer = null; $('auto-refresh').checked = false; token = ''; $('operator-token').value = ''; clearData(); problem(''); $('notice').textContent = 'Access cleared. Private operation details have been removed.'; });
  $('refresh').addEventListener('click', refresh);
  $('queue-form').addEventListener('submit', e => {
    e.preventDefault(); if (!current?.can_enqueue) return;
    mutate('/api/import-runs', { method: 'POST', body: JSON.stringify({ board: $('board').value.trim() }) }, () => {
      $('board').value = ''; actionStatus('Import admitted. Check history for progress; queuing does not mean completion.');
    });
  });
  $('runs').addEventListener('click', e => {
    const button = e.target.closest('button[data-cancel]'); if (!button || button.disabled) return;
    mutate(`/api/import-runs/${encodeURIComponent(button.dataset.cancel)}`, { method: 'DELETE' }, () => actionStatus('Run cancelled. Previously committed records were preserved.'));
  });
  $('schedule-cancel').addEventListener('click', () => { resetEditor(); $('schedule-board').focus(); });
  $('schedule-form').addEventListener('submit', e => {
    e.preventDefault(); if (!current?.can_schedule) return;
    const interval_hours = Number($('schedule-hours').value);
    const edit = editing;
    const body = edit ? { interval_hours, enabled: edit.enabled, expected_revision: edit.revision }
      : { board: $('schedule-board').value.trim(), interval_hours, enabled: false };
    const path = edit ? `/api/source-schedules/${encodeURIComponent(edit.board)}` : '/api/source-schedules';
    mutate(path, { method: edit ? 'PUT' : 'POST', body: JSON.stringify(body) }, () => {
      resetEditor(); actionStatus(edit ? 'Source interval updated.' : 'Source saved paused. Resume it only after opting in the separate worker.');
    });
  });
  $('schedules').addEventListener('click', e => {
    const button = e.target.closest('button[data-schedule-action]'); if (!button || button.disabled) return;
    const source = current?.schedules.find(row => row.board === button.dataset.board); if (!source) return;
    const path = `/api/source-schedules/${encodeURIComponent(source.board)}`;
    const revision = { expected_revision: source.revision };
    switch (button.dataset.scheduleAction) {
      case 'edit':
        editing = { board: source.board, revision: source.revision, enabled: source.enabled };
        $('schedule-board').value = source.board; $('schedule-board').readOnly = true;
        $('schedule-hours').value = String(source.interval_hours); $('schedule-submit').textContent = 'Save interval';
        $('schedule-cancel').hidden = false; $('schedule-hours').focus(); break;
      case 'toggle':
        mutate(path, { method: 'PUT', body: JSON.stringify({ ...revision, interval_hours: source.interval_hours, enabled: !source.enabled }) }, () => actionStatus(source.enabled
          ? 'Schedule paused. Already admitted imports still run unless cancelled separately.'
          : 'Schedule resumed. Dispatch requires the opted-in worker and available budget.')); break;
      case 'run':
        mutate(path+'/run', { method: 'POST', body: JSON.stringify(revision) }, result => actionStatus(result.created ? 'One import queued. The schedule’s paused/enabled state was not changed.' : 'This board already has an active import; no duplicate run was created.')); break;
      case 'remove':
        if (window.confirm(`Remove the schedule for ${source.board}? Indexed jobs and already admitted imports will be preserved.`)) {
          mutate(path+`?expected_revision=${source.revision}`, { method: 'DELETE' }, () => {
            if (editing?.board === source.board) resetEditor(); actionStatus('Schedule removed. Indexed jobs and admitted imports were preserved.');
          });
        }
        break;
    }
  });
  $('auto-refresh').addEventListener('change', () => {
    clearInterval(timer); timer = null;
    if ($('auto-refresh').checked) timer = setInterval(() => { if (!document.hidden && !editing && !document.activeElement?.closest('#schedule-form')) refresh(); }, 15000);
  });
  window.addEventListener('pagehide', () => { clearInterval(timer); invalidate(); token = ''; $('operator-token').value = ''; clearData(); });
  refresh();
})();
