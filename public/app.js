'use strict';

const ICONS = {
  compass:'<circle cx="12" cy="12" r="9"/><path d="m16 8-2.5 5.5L8 16l2.5-5.5Z"/>',
  bookmark:'<path d="M6 4h12v17l-6-4-6 4Z"/>',
  layers:'<path d="m12 3 10 5-10 5L2 8Zm-9 9 9 5 9-5M3 16l9 5 9-5"/>',
  database:'<ellipse cx="12" cy="5" rx="8" ry="3"/><path d="M4 5v14c0 4 16 4 16 0V5M4 12c0 4 16 4 16 0"/>',
  plus:'<path d="M12 5v14M5 12h14"/>',
  sprout:'<path d="M12 21v-9M12 15C4 15 3 10 3 5c7 0 9 3 9 10Zm0-3c0-7 4-9 9-9 0 7-3 9-9 9Z"/>',
  github:'<path d="M9 19c-4 1-4-2-6-2m12 4v-4c0-1 .5-2 1-2 4-1 5-3 5-6 0-2-1-3-2-4 .3-1 .3-2 0-3-2 0-3 1-4 2a12 12 0 0 0-6 0C8 3 7 2 5 2c-.3 1-.3 2 0 3-1 1-2 2-2 4 0 3 1 5 5 6 .5 0 1 1 1 2v4"/>',
  'arrow-up-right':'<path d="M7 17 17 7M7 7h10v10"/>',
  'arrow-right':'<path d="M4 12h16m-6-6 6 6-6 6"/>',
  'arrow-left':'<path d="M20 12H4m6-6-6 6 6 6"/>',
  sparkles:'<path d="m12 3 2.5 6.5L21 12l-6.5 2.5L12 21l-2.5-6.5L3 12l6.5-2.5ZM20 2v4m-2-2h4"/>',
  heart:'<path d="M20 5c-3-3-6-1-8 1-2-2-5-4-8-1-4 5 3 10 8 15 5-5 12-10 8-15Z"/>',
  sun:'<circle cx="12" cy="12" r="4"/><path d="M12 2v2m0 16v2M2 12h2m16 0h2M5 5l1.5 1.5m11 11L19 19M5 19l1.5-1.5m11-11L19 5"/>',
  check:'<path d="m5 12 4 4L19 6"/>',
  lock:'<rect x="5" y="10" width="14" height="11" rx="2"/><path d="M8 10V6a4 4 0 0 1 8 0v4m-4 5v2"/>',
  sliders:'<path d="M4 6h6m4 0h6M4 12h10m4 0h2M4 18h2m4 0h10M10 3v6m4 0v6M6 15v6"/>',
  'chevron-down':'<path d="m6 9 6 6 6-6"/>',
  info:'<circle cx="12" cy="12" r="9"/><path d="M12 11v6m0-10v.1"/>',
  moon:'<path d="M21 13a9 9 0 1 1-10-10 7 7 0 0 0 10 10Z"/>',
  coffee:'<path d="M4 8h12v9a3 3 0 0 1-3 3H7a3 3 0 0 1-3-3Zm12 1h3a3 3 0 0 1 0 6h-3M7 2v3m4-3v3m4-3v3"/>',
  flag:'<path d="M5 21V3c5-4 9 4 14 0v10c-5 4-9-4-14 0"/>',
  users:'<circle cx="9" cy="7" r="3"/><path d="M3 21v-3a6 6 0 0 1 12 0v3m0-17a3 3 0 0 1 0 6m4 11v-3a6 6 0 0 0-3-5"/>',
  link:'<path d="m10 13 4-4m-5 6-3 3a4 4 0 0 1-6-6l4-4a4 4 0 0 1 6 0m4 0 3-3a4 4 0 0 1 6 6l-4 4a4 4 0 0 1-6 0" transform="translate(1 0) scale(.9)"/>',
  'file-text':'<path d="M14 2H5v20h14V7Zm0 0v5h5M8 12h8m-8 4h8"/>',
  shield:'<path d="m12 2 9 4v6c0 5-5 9-9 10-4-1-9-5-9-10V6Zm-4 9 3 3 5-5"/>',
  search:'<circle cx="10" cy="10" r="7"/><path d="m15 15 6 6"/>',
  download:'<path d="M12 3v12m-5-5 5 5 5-5M4 17v4h16v-4"/>',
  refresh:'<path d="M20 7a9 9 0 0 0-15-2L2 8m0-6v6h6m-4 9a9 9 0 0 0 15 2l3-3m0 6v-6h-6"/>',
  x:'<path d="m6 6 12 12M6 18 18 6"/>',
  'map-pin':'<path d="M19 9c0 6-7 12-7 12S5 15 5 9a7 7 0 1 1 14 0Z"/><circle cx="12" cy="9" r="2"/>',
  wallet:'<path d="M20 7H4V4h14v3M4 7v13h16V7m0 5h-6v4h6"/>',
  flame:'<path d="M12 2c2 7 8 7 8 13a8 8 0 0 1-16 0c0-3 2-7 4-9 0 4 1 5 2 5s3-3 2-9Z"/>',
};
const $ = id => document.getElementById(id);
const esc = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const icon = name => `<svg class="icon" viewBox="0 0 24 24" aria-hidden="true">${ICONS[name] || ICONS.info}</svg>`;
const PREFS = ['async','balance','ownership','mentorship','mission','learning'];
const FILTER_IDS = {country:'country',city:'city',work_mode:'work-mode',min_salary:'min-salary',currency:'currency',level:'level'};
const VIEWS = {discover:'Discover',saved:'Saved roles',pipeline:'How it works',sources:'Data sources'};
const defaults = () => ({query:'',filters:{country:'',city:'',work_mode:'',level:'',min_salary:0,currency:'CAD'},preferences:[],semantic_weight:0.65,page:1,page_size:12});
function readStorage(key, fallback) { try { return JSON.parse(localStorage.getItem(key)) ?? fallback; } catch { return fallback; } }
const rawSaved = readStorage('rolecraft.saved.v1', []);
const rawSearches = readStorage('rolecraft.searches.v1', []);
const state = {request:defaults(),view:'discover',status:null,last:null,token:'',controller:null,sequence:0,cache:new Map(),compared:new Set(),
  saved:new Set(Array.isArray(rawSaved) ? rawSaved.filter(x => typeof x === 'string' && /^[a-zA-Z0-9_-]{1,100}$/.test(x)).slice(0,200) : []),
  searches:Array.isArray(rawSearches) ? rawSearches.filter(x => x && typeof x.name === 'string' && x.request && typeof x.request === 'object').slice(0,10) : []};
let toastTimer;
function toast(message) { $('toast').textContent = message; $('toast').hidden = false; clearTimeout(toastTimer); toastTimer = setTimeout(() => $('toast').hidden = true, 3800); }
function persist(key, value) { try { localStorage.setItem(key, JSON.stringify(value)); return true; } catch { toast('Browser storage is unavailable. Changes will last only for this visit.'); return false; } }
function hydrateIcons(root = document) { root.querySelectorAll('[data-icon]').forEach(el => { el.innerHTML = icon(el.dataset.icon); }); }
function safeURL(value) { try { const u = new URL(value); return u.protocol === 'https:' && !u.username && !u.password ? u.href : ''; } catch { return ''; } }
function salary(job) {
  if (job.salary_min == null && job.salary_max == null) return 'Salary not disclosed';
  const amount = n => Intl.NumberFormat('en-CA',{maximumFractionDigits:0}).format(n / 1000);
  const range = job.salary_min == null ? `Up to ${amount(job.salary_max)}k` : job.salary_max == null ? `${amount(job.salary_min)}k+` : `${amount(job.salary_min)}–${amount(job.salary_max)}k`;
  return `${job.currency} ${range}`;
}
function marked(job) { return [...job.company].reduce((sum, c) => sum + c.charCodeAt(0), 0) % 6; }
function brand(job) { return `<span class="company-mark mark-${marked(job)}" aria-hidden="true">${esc(job.company.charAt(0))}</span>`; }
function cacheJobs(jobs) { jobs.forEach(j => state.cache.set(j.id,j)); }

async function api(path, payload, options = {}) {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), 55000);
  const abort = () => controller.abort();
  if (options.signal) options.signal.addEventListener('abort', abort, {once:true});
  const token = options.token ?? state.token;
  try {
    const response = await fetch(path, {method:payload === undefined ? 'GET' : 'POST',
      headers:{...(payload === undefined ? {} : {'Content-Type':'application/json'}), ...(token ? {'Authorization':`Bearer ${token}`} : {})},
      body:payload === undefined ? undefined : JSON.stringify(payload),signal:controller.signal,cache:'no-store'});
    const data = await response.json().catch(() => ({detail:'The server returned an unexpected response.'}));
    if (!response.ok) {
      const error = new Error(typeof data.detail === 'string' ? data.detail : 'Check your input and try again.');
      error.status = response.status;
      throw error;
    }
    return data;
  } finally {
    clearTimeout(timer);
    options.signal?.removeEventListener('abort', abort);
  }
}
function loadFromURL() {
  const params = new URL(location.href).searchParams;
  state.request.query = (params.get('q') || '').slice(0,600);
  for (const [name,id] of Object.entries(FILTER_IDS)) {
    const value = params.get(name);
    if (value !== null) {
      if (name === 'city') state.request.filters.city = value.slice(0,80);
      else if ([...$(id).options].some(o => o.value === value)) state.request.filters[name] = name === 'min_salary' ? Number(value) : value;
    }
  }
  state.request.preferences = [...new Set((params.get('preferences') || '').split(',').filter(p => PREFS.includes(p)))];
  if (['0','0.65','1'].includes(params.get('weight'))) state.request.semantic_weight = Number(params.get('weight'));
  state.view = Object.hasOwn(VIEWS, params.get('view')) ? params.get('view') : 'discover';
  syncForm();
}
function updateURL() {
  const url = new URL(location.href); url.search = '';
  if (state.request.query) url.searchParams.set('q',state.request.query);
  for (const [name,value] of Object.entries(state.request.filters)) if (value && (name !== 'currency' || state.request.filters.min_salary)) url.searchParams.set(name,String(value));
  if (state.request.preferences.length) url.searchParams.set('preferences',state.request.preferences.join(','));
  if (state.request.semantic_weight !== 0.65) url.searchParams.set('weight',String(state.request.semantic_weight));
  if (state.view !== 'discover') url.searchParams.set('view',state.view);
  history.replaceState(null,'',url);
}
function syncForm() {
  $('query').value = state.request.query;
  for (const [name,id] of Object.entries(FILTER_IDS)) $(id).value = String(state.request.filters[name]);
  $('retrieval-mode').value = String(state.request.semantic_weight);
  document.querySelectorAll('[data-pref]').forEach(button => button.setAttribute('aria-pressed',String(state.request.preferences.includes(button.dataset.pref))));
  const count = Object.entries(state.request.filters).filter(([key,value]) => key !== 'currency' && Boolean(value)).length;
  $('active-filter-count').textContent = count;
  $('active-filter-count').hidden = count === 0;
}
function readForm() {
  state.request.query = $('query').value.trim();
  for (const [name,id] of Object.entries(FILTER_IDS)) state.request.filters[name] = name === 'min_salary' ? Number($(id).value) : $(id).value.trim();
  state.request.semantic_weight = Number($('retrieval-mode').value);
  syncForm();
}
function setView(view, focus = true) {
  if (!Object.hasOwn(VIEWS,view)) return;
  state.view = view;
  Object.keys(VIEWS).forEach(name => $('view-'+name).hidden = name !== view);
  document.querySelectorAll('.main-nav [data-view]').forEach(b => {b.classList.toggle('active',b.dataset.view === view); if (b.dataset.view === view) b.setAttribute('aria-current','page'); else b.removeAttribute('aria-current');});
  $('breadcrumb-view').textContent = VIEWS[view];
  document.title = `${VIEWS[view]} — Rolecraft`;
  updateURL();
  if (view === 'saved') loadSaved();
  if (focus) { window.scrollTo({top:0,behavior:'instant'}); $('main').focus({preventScroll:true}); }
}
function emptyState(title, message, action = 'reset') {
  return `<div class="empty-state"><span class="empty-icon">${icon('sprout')}</span><h3>${esc(title)}</h3><p>${esc(message)}</p><button class="secondary-button" data-action="${action}">${action === 'retry' ? 'Try again' : action === 'discover' ? 'Explore roles' : 'Start a fresh search'}${icon('arrow-right')}</button></div>`;
}
function jobCard(job) {
  const saved = state.saved.has(job.id), compared = state.compared.has(job.id);
  return `<article class="job-card ${compared ? 'is-compared' : ''}" data-job="${esc(job.id)}">
    <div class="job-card-top">${brand(job)}<div class="company-meta"><div class="company-name">${esc(job.company)}</div><div class="company-sector">${esc(job.tags?.[0] || job.source)}</div></div><button class="save-button" data-save="${esc(job.id)}" aria-label="${saved ? 'Unsave' : 'Save'} ${esc(job.title)} at ${esc(job.company)}" aria-pressed="${saved}">${icon('bookmark')}</button></div>
    <h3 class="job-title"><button data-detail="${esc(job.id)}">${esc(job.title)}</button></h3>
    <div class="job-location">${icon('map-pin')}<span>${esc(job.city)}</span><span class="meta-dot">·</span><span>${esc(job.work_mode)}</span></div>
    <div class="salary">${icon('wallet')}${esc(salary(job))}${job.salary_period ? '<span class="salary-period">/ year</span>' : ''}</div>
    <div class="job-tags">${[...(job.skills || []).slice(0,2),job.level !== 'Unknown' ? job.level : 'Level unspecified'].map(t => `<span>${esc(t)}</span>`).join('')}</div>
    <div class="match-signal">${icon(job.fit === 'Strong signals' ? 'check' : 'sparkles')}${esc(job.fit || 'Saved for a closer look')}</div>
    <div class="job-card-bottom"><span class="source-badge">${icon(job.is_demo ? 'info' : 'link')}${esc(job.is_demo ? 'Illustrative role' : job.source)}</span><button class="detail-link" data-detail="${esc(job.id)}">${job.evidence ? 'See why it fits' : 'View details'}${icon('arrow-up-right')}</button></div>
    <label class="compare-label"><input type="checkbox" data-compare="${esc(job.id)}" ${compared ? 'checked' : ''}>Compare role</label>
  </article>`;
}
function renderResults() {
  if (!state.last) return;
  const data = state.last;
  $('results').innerHTML = data.jobs.length ? data.jobs.map(jobCard).join('') : emptyState('Let’s open up the possibilities.','No roles meet this combination. Try a broader query or relax a hard filter.');
  $('results').setAttribute('aria-busy','false');
  $('results-count').textContent = data.total;
  $('results-caption').textContent = `${data.eligible_count} ${data.mode === 'demo' ? 'illustrative roles' : 'roles'} meet your hard filters${state.request.query || state.request.preferences.length ? ` · ${data.total} retrieved` : ' · Start a search to find your fit'}`;
  $('pagination').hidden = data.total <= data.page_size;
  $('previous-page').disabled = data.page <= 1;
  $('next-page').disabled = !data.has_more;
  $('page-label').textContent = `Page ${data.page} of ${Math.max(1,Math.ceil(data.total/data.page_size))}`;
  $('trace-filter').textContent = `${data.eligible_count} roles meet your hard filters.`;
  $('trace-retrieval').textContent = `${data.trace.lexical_candidates} keyword + ${data.trace.semantic_candidates} vector candidates.`;
  $('trace-rank').textContent = `${data.total} results · ${data.trace.total_ms} ms end-to-end.`;
  $('pipeline-trace').textContent = JSON.stringify(data.trace,null,2);
  if (data.warnings.length) toast(data.warnings[0]);
}
async function runSearch() {
  readForm(); updateURL();
  state.controller?.abort();
  state.controller = new AbortController();
  const sequence = ++state.sequence;
  $('results').setAttribute('aria-busy','true');
  $('results').innerHTML = '<div class="skeleton" aria-hidden="true"></div>'.repeat(4);
  $('search-button').disabled = true;
  $('search-button').innerHTML = 'Finding your fit…'+icon('sparkles');
  $('connection-banner').hidden = true;
  try {
    const data = await api('/api/search',state.request,{signal:state.controller.signal});
    if (sequence !== state.sequence) return;
    state.last = data; cacheJobs(data.jobs); renderResults();
  } catch(error) {
    if (sequence !== state.sequence) return;
    const message = error.name === 'AbortError' ? 'The search timed out. Please try again.' : error.message;
    $('results').innerHTML = emptyState('Your search needs a moment.',message,'retry');
    $('results').setAttribute('aria-busy','false');
    $('results-count').textContent = '—';
    $('results-caption').textContent = 'No results were substituted.';
    $('pagination').hidden = true;
    $('connection-banner').textContent = message; $('connection-banner').hidden = false;
    if (error.status === 401 && !$('access-dialog').open) $('access-dialog').showModal();
  } finally {
    if (sequence === state.sequence) {$('search-button').disabled = false; $('search-button').innerHTML = 'Find my next role'+icon('arrow-right');}
  }
}
function renderSavedCount() { $('saved-count').textContent = state.saved.size; }
function toggleSaved(id) {
  const job = state.cache.get(id); if (!job) return;
  if (state.saved.has(id)) state.saved.delete(id); else if (state.saved.size < 200) state.saved.add(id); else {toast('Your shortlist is full. Export or remove a few roles first.'); return;}
  const stored = persist('rolecraft.saved.v1',[...state.saved]); renderSavedCount();
  document.querySelectorAll('[data-save]').forEach(b => {if (b.dataset.save === id) {b.setAttribute('aria-pressed',String(state.saved.has(id))); b.setAttribute('aria-label',`${state.saved.has(id) ? 'Unsave' : 'Save'} ${job.title} at ${job.company}`); if (b.classList.contains('secondary-button')) b.innerHTML = icon('bookmark')+(state.saved.has(id) ? 'Saved to shortlist' : 'Save this role');}});
  if (state.view === 'saved') renderSaved();
  if (stored) toast(state.saved.has(id) ? 'A good possibility, saved.' : 'Removed from your shortlist.');
}
async function loadSaved() {
  if (!state.saved.size) {renderSaved(); return;}
  $('saved-results').innerHTML = '<div class="skeleton" aria-hidden="true"></div>'.repeat(2);
  try {const data = await api('/api/jobs',{ids:[...state.saved]}); cacheJobs(data.jobs); renderSaved(data.jobs);} catch(error) {$('saved-results').innerHTML = emptyState('Your shortlist is still on this device.',error.message,'retry-saved');}
}
function renderSaved(available) {
  const jobs = available || [...state.saved].map(id => state.cache.get(id)).filter(Boolean);
  $('saved-results').innerHTML = jobs.length ? jobs.filter(j => state.saved.has(j.id)).map(jobCard).join('') : emptyState(state.saved.size ? 'Saved roles are not in this dataset.' : 'Leave room for a good possibility.',state.saved.size ? 'Your saved IDs are retained. The source may have changed, or these roles may have closed.' : 'Tap the bookmark on any role. Your shortlist will be waiting here.','discover');
}
function updateCompare() {
  $('compare-count').textContent = state.compared.size;
  $('compare-bar').hidden = state.compared.size === 0;
  $('compare-button').disabled = state.compared.size < 2;
  document.querySelectorAll('[data-compare]').forEach(el => {el.checked = state.compared.has(el.dataset.compare); el.closest('.job-card')?.classList.toggle('is-compared',el.checked);});
}
let dialogVersion = 0;
function openDialog(html, kicker = 'A CLOSER LOOK') {
  dialogVersion++;
  $('dialog-content').innerHTML = html; $('dialog-kicker').textContent = kicker;
  if (!$('detail-dialog').open) $('detail-dialog').showModal();
  $('detail-dialog').scrollTop = 0;
}
function openJob(id) {
  const job = state.cache.get(id); if (!job) {toast('This role is no longer in the current results.'); return;}
  const source = safeURL(job.source_url);
  const passages = job.evidence || [];
  openDialog(`<div class="dialog-company">${brand(job)}<strong>${esc(job.company)}</strong></div><h2 id="dialog-title" class="dialog-title">${esc(job.title)}</h2><div class="dialog-meta"><span>${esc(job.city)} · ${esc(job.country)}</span><span>${esc(job.work_mode)}</span><span>${esc(salary(job))}${job.salary_period ? ' / year' : ''}</span></div>
    ${job.is_demo ? '<div class="detail-caveat">This company and vacancy are fictional. This role exists only to demonstrate search, filtering, and explanations.</div>' : `<div class="detail-caveat">Source: ${esc(job.source)} · Last imported ${esc(new Date(job.last_seen).toLocaleDateString())}. Source claims are not independently verified. Confirm that the role is still open.</div>`}
    ${passages.length ? `<section class="detail-section"><h3>Why it surfaced</h3>${passages.map(e => `<div class="evidence-item"><strong>${icon('check')}${esc(e.label)}</strong><blockquote>“${esc(e.quote)}”</blockquote></div>`).join('')}<p class="brief-note">Exact passages from this description. Relevance signals are not a probability of qualification or an endorsement of company culture.</p></section>` : ''}
    ${job.unconfirmed_preferences?.length ? `<div class="detail-caveat">Not confirmed in the description: ${esc(job.unconfirmed_preferences.join(', '))}. Ask about these in an interview.</div>` : ''}
    <section class="detail-section"><h3>The role & the team</h3><p class="description-copy">${esc(job.description)}</p></section><section class="detail-section"><h3>Location & eligibility</h3><p class="description-copy">${esc(job.remote_scope)}</p></section>
    ${job.scores ? `<details class="detail-section"><summary>Inspect retrieval scores</summary><p class="brief-note">Raw retrieval diagnostics, not percentages. Different retriever scales are combined by rank, not added directly.</p><pre>${esc(JSON.stringify(job.scores,null,2))}</pre></details>` : ''}
    <div class="dialog-actions"><button class="secondary-button" data-save="${esc(id)}" aria-pressed="${state.saved.has(id)}">${icon('bookmark')}${state.saved.has(id) ? 'Saved to shortlist' : 'Save this role'}</button>${!job.is_demo && source ? `<a class="primary-button" href="${esc(source)}" target="_blank" rel="noopener noreferrer">View original listing${icon('arrow-up-right')}</a>` : '<button class="primary-button" disabled>Illustrative role · no application</button>'}</div>`);
}
function compareRoles() {
  const jobs = [...state.compared].map(id => state.cache.get(id)).filter(Boolean); if (jobs.length < 2) return;
  const rows = [
    ['Company',j => j.company],['Location',j => `${j.city}, ${j.country}`],['Work style',j => j.work_mode],['Annual base',salary],['Level',j => j.level],['Skills',j => j.skills.join(', ') || 'Not specified'],['Eligibility',j => j.remote_scope],['Evidence',j => j.evidence?.map(e => e.quote).join(' ') || 'Open the role to inspect its description.'],['Source',j => j.is_demo ? 'Fictional demo role' : j.source],
  ];
  openDialog(`<h2 id="dialog-title" class="dialog-title">Good fits, side by side.</h2><p class="brief-note">Compare the facts and the source evidence. Salaries are shown in their original currencies, without conversion.</p><div class="comparison-scroll"><table class="comparison-table"><thead><tr><th scope="col">The details</th>${jobs.map(j => `<th scope="col">${esc(j.title)}</th>`).join('')}</tr></thead><tbody>${rows.map(([label,fn]) => `<tr><th scope="row">${esc(label)}</th>${jobs.map(j => `<td>${esc(fn(j))}</td>`).join('')}</tr>`).join('')}</tbody></table></div>`,'YOUR SHORTLIST, IN PERSPECTIVE');
}
async function buildBrief() {
  readForm();
  openDialog('<h2 id="dialog-title" class="dialog-title">Connecting the evidence…</h2><p class="loading-message">Retrieving matching roles and checking source excerpts.</p>','YOUR EVIDENCE BRIEF');
  const version = dialogVersion;
  try {
    const data = await api('/api/brief',state.request);
    if (!$('detail-dialog').open || version !== dialogVersion) return;
    openDialog(`<h2 id="dialog-title" class="dialog-title">${esc(data.heading)}</h2><div class="card-eyebrow">${esc(data.method)}</div>${data.warning ? `<div class="detail-caveat">${esc(data.warning)}</div>` : ''}${data.cards.map((card,i) => `<article class="brief-card"><div class="card-eyebrow">0${i+1} · ${card.is_demo ? 'ILLUSTRATIVE ROLE' : 'SOURCE-BACKED EXCERPT'}</div><h3>${esc(card.title)}</h3><div class="company-name">${esc(card.company)}</div><blockquote>“${esc(card.quote)}”</blockquote><p class="brief-note">${esc(card.caveats.filter(Boolean).join(' · '))}</p>${safeURL(card.source_url) && !card.is_demo ? `<a class="text-button" href="${esc(safeURL(card.source_url))}" target="_blank" rel="noopener noreferrer">Verify at the original source${icon('arrow-up-right')}</a>` : ''}</article>`).join('')}<p class="brief-note">${esc(data.note)}</p>${!data.cards.length ? '<div class="detail-caveat">Try relaxing a filter. Hard constraints are never silently removed.</div>' : ''}`,'YOUR EVIDENCE BRIEF');
  } catch(error) { if ($('detail-dialog').open && version === dialogVersion) openDialog(`<h2 id="dialog-title" class="dialog-title">The brief isn’t ready.</h2><p class="brief-note">${esc(error.message)}</p>`); }
}
function renderSearches() {
  $('saved-search-list').innerHTML = state.searches.length ? state.searches.map((s,i) => `<div class="saved-search-item"><button data-search-index="${i}" title="${esc(s.name)}">${esc(s.name)}</button><button data-delete-search="${i}" aria-label="Delete saved search ${esc(s.name)}">${icon('x')}</button></div>`).join('') : '<p class="muted small">Keep a good search for later.</p>';
}
function saveSearch() {
  readForm();
  if (!state.request.query && !state.request.preferences.length && !Object.entries(state.request.filters).some(([key,val]) => key !== 'currency' && val)) {toast('Add a query, filter, or preference first.'); return;}
  const name = state.request.query.slice(0,50) || [state.request.filters.country,state.request.filters.work_mode,...state.request.preferences].filter(Boolean).join(' · ') || 'Filtered roles';
  const request = JSON.parse(JSON.stringify({...state.request,page:1}));
  state.searches = [{name,request},...state.searches.filter(s => JSON.stringify(s.request) !== JSON.stringify(request))].slice(0,10);
  const stored = persist('rolecraft.searches.v1',state.searches); renderSearches(); if (stored) toast('Search saved. Come back to it any time.');
}
function applySavedSearch(index) {
  const saved = state.searches[index]; if (!saved) return;
  // Do not trust persisted browser state: restore only supported values through
  // the same controlled form elements used by the URL parser.
  state.request = defaults();
  state.request.query = typeof saved.request.query === 'string' ? saved.request.query.slice(0,600) : '';
  for (const [name,id] of Object.entries(FILTER_IDS)) {
    const value = saved.request.filters?.[name];
    if (name === 'city' && typeof value === 'string') state.request.filters.city = value.slice(0,80);
    else if (name !== 'city' && [...$(id).options].some(o => o.value === String(value))) state.request.filters[name] = name === 'min_salary' ? Number(value) : value;
  }
  state.request.preferences = Array.isArray(saved.request.preferences) ? [...new Set(saved.request.preferences.filter(p => PREFS.includes(p)))] : [];
  if ([0,.65,1].includes(saved.request.semantic_weight)) state.request.semantic_weight = saved.request.semantic_weight;
  syncForm(); setView('discover'); runSearch();
}
function example(kind) {
  state.request = defaults();
  if (kind === 'calm') {state.request.query = 'Backend engineering with Python or Go, a calm team and protected focus time'; state.request.filters.country='Canada'; state.request.filters.work_mode='Remote'; state.request.preferences=['async','balance'];}
  else if (kind === 'ai') {state.request.query='AI engineering, RAG, embeddings and practical machine learning'; state.request.preferences=['ownership','learning'];}
  else {state.request.query='Meaningful work in climate, education or social impact'; state.request.preferences=['mission','balance'];}
  syncForm(); setView('discover'); runSearch();
}
function resetSearch() {state.request=defaults(); syncForm(); setView('discover'); runSearch();}
function showStatus(status) {
  state.status=status;
  const live=status.mode === 'live';
  $('mode-badge').innerHTML = '<span class="status-dot"></span>'+(live ? 'Private live workspace' : 'Demo mode');
  $('workspace-label').textContent=live ? 'Live workspace' : 'Demo workspace';
  $('workspace-description').textContent=live ? 'Private, source-backed search' : `${status.stats?.jobs || 24} illustrative roles`;
  $('honesty-note').textContent=status.notice;
  $('source-status').textContent=status.notice;
  $('postgres-status').textContent=live ? 'Configured · private access' : 'Not connected';
  $('greenhouse-status').textContent=status.sources.greenhouse ? 'Ready for authorized imports' : 'Available in live mode';
  $('firecrawl-status').textContent=status.sources.firecrawl ? 'Key configured' : 'Needs provider key';
  $('ingest-button').disabled=!live;
  if (!live) $('ingest-result').textContent='The demo is read-only. Connect the live database and server-side secrets to enable ingestion.';
  $('pipeline-engine').textContent=live ? 'PostgreSQL + pgvector workspace' : 'Local, inspectable demo';
  if (live) $('pipeline-mode-copy').textContent='Live mode uses PostgreSQL full-text search and pgvector with 1,536-dimensional OpenAI embeddings. Workspace access is required before any paid search. Optional providers are used only when configured.';
}
async function syncSource(event) {
  event.preventDefault();
  const token=$('ingest-token').value; $('ingest-token').value='';
  const payload={provider:$('ingest-provider').value,board:$('ingest-board').value.trim(),url:$('ingest-url').value.trim(),limit:5,offset:0};
  $('ingest-button').disabled=true; $('ingest-result').textContent='Importing and validating a bounded batch…';
  try {const result=await api('/api/ingest',payload,{token}); $('ingest-result').textContent=`${result.indexed} roles indexed from ${result.source}. ${result.next_offset !== null ? `More roles remain: use the CLI with --all to sync every batch (next offset ${result.next_offset}). ` : ''}${result.note}`;}
  catch(error) {$('ingest-result').textContent=error.name === 'AbortError' ? 'The request timed out. Its completion is unknown; inspect the source before retrying. Imports are idempotent.' : error.message;}
  finally {$('ingest-button').disabled=state.status?.mode !== 'live';}
}

hydrateIcons(); loadFromURL(); renderSavedCount(); renderSearches();
if (matchMedia('(max-width:600px)').matches) {$('filter-toggle').setAttribute('aria-expanded','false');$('filter-fields').hidden=true;}
$('search-form').addEventListener('submit',event => {event.preventDefault(); state.request.page=1; runSearch();});
$('query').addEventListener('keydown',event => {if (event.key === 'Enter' && (event.ctrlKey || event.metaKey)) {event.preventDefault(); state.request.page=1; runSearch();}});
let cityTimer;
Object.values(FILTER_IDS).forEach(id => $(id).addEventListener(id === 'city' ? 'input' : 'change',() => {clearTimeout(cityTimer); state.request.page=1; if (id === 'city') cityTimer=setTimeout(runSearch,400); else runSearch();}));
$('retrieval-mode').addEventListener('change',() => {state.request.page=1;runSearch();});
$('filter-toggle').addEventListener('click',() => {const expanded=$('filter-toggle').getAttribute('aria-expanded') === 'true'; $('filter-toggle').setAttribute('aria-expanded',String(!expanded)); $('filter-fields').hidden=expanded;});
$('reset-filters').addEventListener('click',() => {state.request.filters=defaults().filters;state.request.preferences=[];state.request.page=1;syncForm();runSearch();});
$('previous-page').addEventListener('click',() => {state.request.page=Math.max(1,state.request.page-1);runSearch();$('results').scrollIntoView({block:'start'});});
$('next-page').addEventListener('click',() => {state.request.page++;runSearch();$('results').scrollIntoView({block:'start'});});
$('brief-button').addEventListener('click',buildBrief); $('brief-shortcut').addEventListener('click',buildBrief);
$('save-search').addEventListener('click',saveSearch); $('save-search-inline').addEventListener('click',saveSearch);
$('compare-button').addEventListener('click',compareRoles);
$('compare-clear').addEventListener('click',() => {state.compared.clear();updateCompare();});
$('detail-dialog').addEventListener('close', () => dialogVersion++);
$('close-dialog').addEventListener('click',() => $('detail-dialog').close());
$('access-button').addEventListener('click',() => $('access-dialog').showModal());
$('close-access').addEventListener('click',() => $('access-dialog').close());
$('access-dialog').addEventListener('close',() => $('access-token').value='');
$('access-form').addEventListener('submit',event => {event.preventDefault();state.token=$('access-token').value;$('access-token').value='';$('access-dialog').close();if(state.view === 'saved') loadSaved();else runSearch();});
$('ingest-form').addEventListener('submit',syncSource);
$('ingest-provider').addEventListener('change',() => {const web=$('ingest-provider').value === 'firecrawl';$('board-label').hidden=web;$('url-label').hidden=!web;});
$('share-search').addEventListener('click',async() => {readForm();updateURL();try{await navigator.clipboard.writeText(location.href);toast('Search link copied.');}catch{openDialog(`<h2 id="dialog-title" class="dialog-title">Share a thoughtful search.</h2><p class="brief-note">Copy this link. It contains filters, not access tokens.</p><p class="description-copy">${esc(location.href)}</p>`);}});
$('clear-saved').addEventListener('click',() => {if(state.saved.size && confirm('Remove all saved roles from this browser?')) {state.saved.clear();persist('rolecraft.saved.v1',[]);renderSavedCount();renderSaved();renderResults();toast('Your shortlist is clear.');}});
$('export-saved').addEventListener('click',async() => {
  if(!state.saved.size){toast('Save a role before exporting your shortlist.');return;}
  try {const data=await api('/api/jobs',{ids:[...state.saved]});const blob=new Blob([JSON.stringify({app:'Rolecraft',version:1,exported_at:new Date().toISOString(),saved_ids:[...state.saved],jobs:data.jobs},null,2)],{type:'application/json'});const url=URL.createObjectURL(blob);const link=document.createElement('a');link.href=url;link.download='rolecraft-shortlist.json';link.click();setTimeout(() => URL.revokeObjectURL(url),1000);toast('Shortlist exported, including retained saved IDs.');}
  catch(error){toast(error.message);}
});
document.addEventListener('click',event => {
  const button=event.target.closest('button');if(!button)return;
  if(button.dataset.view){setView(button.dataset.view);return;}
  if(button.dataset.example){example(button.dataset.example);return;}
  if(button.dataset.save){toggleSaved(button.dataset.save);return;}
  if(button.dataset.detail){openJob(button.dataset.detail);return;}
  if(button.dataset.pref){const p=button.dataset.pref;state.request.preferences=state.request.preferences.includes(p)?state.request.preferences.filter(x=>x!==p):[...state.request.preferences,p];state.request.page=1;syncForm();runSearch();return;}
  if(button.dataset.searchIndex !== undefined){applySavedSearch(Number(button.dataset.searchIndex));return;}
  if(button.dataset.deleteSearch !== undefined){state.searches.splice(Number(button.dataset.deleteSearch),1);persist('rolecraft.searches.v1',state.searches);renderSearches();return;}
  if(button.dataset.action==='reset')resetSearch();
  if(button.dataset.action==='retry')runSearch();
  if(button.dataset.action==='retry-saved')loadSaved();
  if(button.dataset.action==='discover')setView('discover');
});
document.addEventListener('change',event => {const box=event.target.closest('[data-compare]');if(!box)return;const id=box.dataset.compare;if(box.checked){if(state.compared.size>=3){box.checked=false;toast('Compare up to three roles at a time.');return;}state.compared.add(id);}else state.compared.delete(id);updateCompare();});
document.addEventListener('keydown',event => {if((event.metaKey||event.ctrlKey)&&event.key.toLowerCase()==='k'&&!$('detail-dialog').open&&!$('access-dialog').open){event.preventDefault();setView('discover',false);$('query').focus();}});
window.addEventListener('popstate',() => {loadFromURL();setView(state.view,false);runSearch();});
window.addEventListener('storage',event => {if(event.key==='rolecraft.saved.v1'){const ids=readStorage('rolecraft.saved.v1',[]);state.saved=new Set(Array.isArray(ids)?ids.filter(x=>typeof x==='string'&&/^[a-zA-Z0-9_-]{1,100}$/.test(x)).slice(0,200):[]);renderSavedCount();if(state.view==='saved')loadSaved();else renderResults();}});
async function start() {
  setView(state.view,false);
  try {showStatus(await api('/api/status'));await runSearch();}
  catch(error){$('connection-banner').textContent='The workspace could not be reached. '+error.message;$('connection-banner').hidden=false;$('results').innerHTML=emptyState('Let’s reconnect.',error.message,'retry');$('results').setAttribute('aria-busy','false');}
}
start();
