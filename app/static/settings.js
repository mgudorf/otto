// Settings: every task by the kind of work it is, each with whether it runs on its schedule and the model and effort
// Claude is launched with for it; then the facets the feed shows, the page's own knobs, the data and the app.
// Every value but the layout's is the daemon's: /api/shell carries the settings, /api/tasks the scheduled tasks and
// /api/data the database. The layout is this browser's, kept in `otto-layout`.
import { S, $, h, put, icon, I, toast, renderAll, applyLayout, saveLayout, loadShell, load, stamp, closePops } from './core.js';
import { get, post, apiPut } from './api.js';

// The Claude runs no schedule declares, by the job name their model and effort are kept under.
const RUNS = [
  ['Conversation', [['otto.turn', 'Otto']]],
  ['Filing', [['otto.close', 'Naming conversations'], ['feedback.file', 'Filing feedback']]],
];
// What each scheduled task does; one missing here shows its job name.
const TITLES = {
  'education.generate': 'Question writing', 'email.triage': 'Email triage', 'newsfeed.run': 'Newsfeed searches', 'second_brain.suggest': 'Entry suggestions',
  'email.sync': 'Email sync', 'graph.rebuild': 'Graph rebuild', 'science.reap': 'Idle kernel shutdown', 'science.due': 'Scheduled files',
  'system.heartbeat': 'Heartbeat', 'system.prune_sessions': 'Old conversation cleanup',
};
let tasks = [], data = {}, reload = false;

const settings = () => (S.shell && S.shell.settings) || {};
export const pickOf = (task, key) => settings()[`tasks.${task}.${key}`] || 'default';
// Writes live settings; the answer is every setting, so the page reads what the daemon now holds.
export async function saveSettings(patch) {
  try { S.shell.settings = await apiPut('/api/settings', patch); } catch (e) { toast(e.message); return false; }
  renderAll();
  return true;
}
const bytes = (n) => { let v = Number(n) || 0, i = 0; while (v >= 1024 && i < 3) { v /= 1024; i += 1; } return `${i ? v.toFixed(1) : v} ${['B', 'KB', 'MB', 'GB'][i]}`; };

// ---- controls: each keeps its own state, so a change never redraws the dialog under the keyboard ----------------------
function switchEl(on, onflip) {
  const b = h('button', { class: 'sw', role: 'switch', 'aria-checked': String(!!on), onclick: async () => {
    const next = b.getAttribute('aria-checked') !== 'true';
    if (await onflip(next)) b.setAttribute('aria-checked', String(next));
  } });
  return b;
}
function choiceEl(task, key) {
  const sel = h('select', { class: 'pick', 'aria-label': key, onchange: async () => {
    if (!(await saveSettings({ [`tasks.${task}.${key}`]: sel.value }))) sel.value = pickOf(task, key);
    sel.classList.toggle('dflt', sel.value === 'default');
  } }, ...['default', ...(key === 'model' ? S.shell.claude.models : S.shell.claude.efforts)].map((v) => h('option', { value: v }, v)));
  sel.value = pickOf(task, key);
  sel.classList.toggle('dflt', sel.value === 'default');
  return sel;
}
function numEl(value, min, max, unit, onsave, live) {
  const inp = h('input', { type: 'number', min: String(min), max: String(max), value: value ?? '', onkeydown: (e) => { if (e.key === 'Enter') inp.blur(); } });
  inp.addEventListener(live ? 'input' : 'change', () => { const v = Number(inp.value); if (inp.value !== '' && v >= min && v <= max) onsave(v); else if (!live) toast(`${min} to ${max}`); });
  return h('span', { class: 'numf' }, inp, unit ? h('span', null, unit) : null);
}
function segEl(options, value, onpick) {
  const seg = h('span', { class: 'seg' }, ...options.map(([v, label]) => h('button', { class: v === value ? 'on' : '', onclick: async () => {
    if (await onpick(v)) [...seg.children].forEach((b, i) => b.classList.toggle('on', options[i][0] === v));
  } }, label)));
  return seg;
}
const row = (label, ...right) => h('div', { class: 'srow' }, h('span', { class: 'lbl' }, label), ...right);
const path = (p, right) => (p ? h('div', { class: 'srow' }, h('span', { class: 'lbl mono', title: p }, p), right || null) : null);
const group = (title, rows) => h('section', { class: 'sgroup' }, h('div', { class: 'ph' }, title), ...rows.filter(Boolean));

// ---- the tasks ------------------------------------------------------------------------------------------------------
// A task's switch is its app_tasks row's, the one its routine row's Pause and Resume throw.
async function setRuns(t, on) {
  try { Object.assign(t, await post(`/api/tasks/${encodeURIComponent(t.name)}`, { enabled: on })); } catch (e) { toast(e.message); return false; }
  load();
  return true;
}
function taskRow(name, title, sched, llm) {
  return h('div', { class: 'srow task' }, h('span', { class: 'lbl', title: name }, title),
    sched ? switchEl(sched.enabled, (on) => setRuns(sched, on)) : h('span'),
    llm ? choiceEl(name, 'model') : h('span'), llm ? choiceEl(name, 'effort') : h('span'));
}
function taskGroups() {
  const titled = (list, llm) => list.map((t) => taskRow(t.name, TITLES[t.name] || t.name, t, llm));
  const nightly = tasks.filter((t) => t.llm), upkeep = tasks.filter((t) => !t.llm);
  return [
    ...RUNS.map(([g, list]) => group(g, list.map(([name, title]) => taskRow(name, title, null, true)))),
    nightly.length ? group('Nightly', titled(nightly, true)) : null,
    upkeep.length ? group('Upkeep', titled(upkeep, false)) : null,
  ];
}

// ---- the facets, the page, the data, the app ---------------------------------------------------------------------------
// A facet switched off takes its rows off the feed and its tools off the agent; the brain is built on the facets once, so
// the page reloads when the dialog closes.
function feedGroup() {
  const mods = ((S.shell && S.shell.modules) || []).filter((m) => m.facet).sort((a, b) => a.order - b.order);
  return group('Feed', mods.map((m) => row([icon(m.icon), m.facet], switchEl(m.enabled, async (on) => {
    if (!(await saveSettings({ [`modules.${m.name}.enabled`]: on }))) return false;
    m.enabled = on; reload = true;
    return true;
  }))));
}
function generalGroup() {
  const st = settings();
  return group('General', [
    row('Refresh every', numEl(st['ui.refresh_seconds'], 5, 3600, 's', (v) => saveSettings({ 'ui.refresh_seconds': v }))),
    row('Time format', segEl([['24h', '24 h'], ['12h', '12 h']], st['ui.time_format'] === '12h' ? '12h' : '24h', (v) => saveSettings({ 'ui.time_format': v }))),
  ]);
}
function layoutGroup() {
  const L = S.layout;
  const field = (label, key, min, max, unit) => row(label, numEl(L[key], min, max, unit, (v) => { L[key] = v; applyLayout(); saveLayout(); }, true));
  return group('Layout', [field('Cards', 'feed', 15, 60, '%'), field('Drawer', 'drawer', 10, 40, '%'), field('Brain turn', 'turn', 0, 600, 'min')]);
}
function dataGroup() {
  const run = (url) => async (e) => {
    e.currentTarget.disabled = true;
    try { await post(url); data = await get('/api/data'); } catch (err) { toast(err.message); }
    draw();
  };
  const act = (label, url, when, primary) => [h('button', { class: `btn${primary ? ' primary' : ''}`, onclick: run(url) }, label), when ? h('span', { class: 'when num' }, stamp(when)) : null];
  return group('Data', [
    path(data.db, h('span', { class: 'val num' }, bytes(data.size_bytes))),
    h('div', { class: 'acts' }, act('Back up now', '/api/data/backup', data.last_backup, true), act('Export', '/api/data/export', data.last_export), act('Vacuum', '/api/data/vacuum')),
  ]);
}
function appGroup() {
  const c = (S.shell && S.shell.claude) || {}, b = (S.shell && S.shell.budget) || {};
  return group('App', [
    path(location.host), path(c.binary), path(c.workspace),
    c.model && c.model !== 'default' ? row('Model', h('span', { class: 'val' }, c.model)) : null,
    b.window ? row('Nightly', h('span', { class: 'val num' }, `${b.window.replace('-', ' to ')}, ${b.used} of ${b.max} runs, ${b.stagger_minutes} min apart`)) : null,
    c.sessions_kept_days ? row('Sessions kept', h('span', { class: 'val num' }, `${c.sessions_kept_days} d`)) : null,
  ]);
}

// ---- the dialog ------------------------------------------------------------------------------------------------------
function draw() {
  const box = $('#setBox');
  put(box, h('div', { class: 'shead' }, h('h3', null, 'Settings'), h('button', { class: 'icon-btn', title: 'Close', onclick: closeSettings }, icon(I.close))),
    h('div', { class: 'scols' }, h('div', null, ...taskGroups()), h('div', null, feedGroup(), generalGroup(), layoutGroup(), dataGroup(), appGroup())));
}
let bound = false;
export async function openSettings() {
  closePops();
  const sc = $('#setScrim');
  if (!bound) {
    bound = true;
    sc.addEventListener('mousedown', (e) => { if (e.target === sc) closeSettings(); });
    sc.addEventListener('keydown', (e) => { e.stopPropagation(); if (e.key === 'Escape') closeSettings(); });   // the page's keys stay with the page
  }
  try { [tasks, data] = await Promise.all([get('/api/tasks'), get('/api/data').catch(() => ({})), loadShell()]); } catch (e) { toast(e.message); }
  draw();
  sc.hidden = false;
  $('#setBox').focus();
}
export function closeSettings() {
  $('#setScrim').hidden = true;
  if (reload) location.reload();
}
