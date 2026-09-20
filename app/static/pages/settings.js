// Settings: a grid of tiles, Otto then every module, and the picked tile's pane beside it.
// Every value is the daemon's: /api/shell carries the live settings, the modules and Claude's choices,
// /api/data the database, and the Feedback tile's queue comes from the feedback module's own list route.
import { S, h, I, icon, hue, modOf, pick, sw, frow, segEl, dayLabel, stamp, toast, refresh, select } from '../core.js';
import { get, post, apiPut, q } from '../api.js';

const OTTO = 'otto';
const ONE_LINE = 'overflow:hidden;text-overflow:ellipsis;white-space:nowrap';

const bytes = (n) => {
  const units = ['B', 'KB', 'MB', 'GB'];
  let v = Number(n) || 0, i = 0;
  while (v >= 1024 && i < units.length - 1) { v /= 1024; i += 1; }
  return `${i ? v.toFixed(1) : v} ${units[i]}`;
};
const setting = (k, fallback) => (S.shell && S.shell.settings && S.shell.settings[k] !== undefined ? S.shell.settings[k] : fallback);
// What a module may pick, in the daemon's own words, with its "no pick of my own" first.
const choices = (list) => [['default', 'default'], ...(list || []).map((x) => [x, x])];
// A module that has made no pick of its own has nothing to say here; "default" is not a subtitle.
const agentSub = (m) => [m.model, m.effort].filter((x) => x && x !== 'default').join(', ');

async function save(patch) {
  try { await apiPut('/api/settings', patch); } catch (e) { toast(e.message); return; }
  refresh();
}
async function retry(id) {
  try { await post('/api/feedback/action/retry', { id }); } catch (e) { toast(e.message); return; }
  refresh();
}

// One tile per pane. `local` tells core the row is the whole item, so it never asks the daemon for it;
// every tile belongs to this page, so the pane's crumb reads Settings rather than the module's own name twice.
function tiles() {
  const mods = (S.shell && S.shell.modules) || [];
  return [
    { id: OTTO, module: 'settings', local: true, title: 'Otto', icon: I.target, tint: 'var(--ink-2)', sub: 'General, data, app' },
    ...mods.map((m) => ({
      id: m.name, module: 'settings', local: true, title: m.title, icon: m.icon, tint: hue(m),
      sub: m.error || (m.agent ? agentSub(m) : ''), mod: m,
    })),
  ];
}

// A module that ships no mark gets none; a failed module's error is one line here and whole in its pane.
function tileGrid(d) {
  return h('div', { class: 'tiles' }, ...(d.items || []).map((t) => h('div', {
    class: `card mod tile${String(S.sel) === String(t.id) ? ' sel' : ''}`, style: `--c:${t.tint}`, 'data-id': t.id,
    onclick: () => { if (String(S.sel) === String(t.id)) return; select(t.id); if (t.id === 'feedback') refresh(); },
  }, h('div', { class: 'tt' }, t.icon ? icon(t.icon) : null, h('span', null, t.title)),
  t.sub ? h('div', { class: 'sub', style: ONE_LINE }, t.sub) : null)));
}

// A number the route bounds; a value outside them comes back as the daemon's own message.
function numField(value, min, max, unit, onsave) {
  const inp = h('input', {
    type: 'number', min, max, class: 'num', value: value === null || value === undefined ? '' : value,
    style: 'width:78px;height:28px;padding:0 8px;border:1px solid var(--line-strong);border-radius:6px;background:var(--surface);text-align:right',
    onchange: (e) => onsave(Number(e.target.value)),
    onkeydown: (e) => { if (e.key === 'Enter') e.target.blur(); },
  });
  return unit ? [inp, h('span', { class: 'num' }, unit)] : inp;
}

function ottoPane(d) {
  const st = (S.shell && S.shell.settings) || {};
  const c = (S.shell && S.shell.claude) || {};
  const b = (S.shell && S.shell.budget) || {};
  const info = d.info || {};
  const start = st['ui.start_page'];
  const pages = [
    ...((S.shell && S.shell.modules) || []).filter((m) => m.page && m.enabled && !m.error).map((m) => [m.name, m.title]),
    ['activity', 'Activity'], ['settings', 'Settings'],
  ];
  // A start page that is hidden or gone is still the one the daemon boots on, so the row names it.
  if (start && !pages.some(([n]) => n === start)) pages.unshift([start, modOf(start).title]);
  const run = (path) => async (e) => {
    const btn = e.currentTarget;
    btn.disabled = true;
    try { await post(path); } catch (err) { toast(err.message); }
    refresh();
  };
  return [h('h2', null, 'Otto'),
    h('div', { class: 'form' },
      h('h3', null, 'General'),
      frow('Start page', pick(pages, start, (v) => save({ 'ui.start_page': v }))),
      frow('Refresh every', numField(st['ui.refresh_seconds'], 5, 3600, 's', (v) => save({ 'ui.refresh_seconds': v }))),
      frow('Time format', segEl(['24 h', '12 h'], st['ui.time_format'] === '12h' ? '12 h' : '24 h', (o) => save({ 'ui.time_format': o === '12 h' ? '12h' : '24h' }))),
      frow('Rows per page', numField(st['ui.page_size'], 10, 200, '', (v) => save({ 'ui.page_size': v }))),

      h('h3', null, 'Data'),
      info.db ? frow('Database', h('span', { class: 'mono' }, `${info.db}, ${bytes(info.size_bytes)}`)) : null,
      c.workspace ? frow('Workspace', h('span', { class: 'mono' }, c.workspace)) : null,
      b.window ? frow('Nightly window', h('span', { class: 'num' }, b.window.replace('-', ' to '))) : null,
      typeof b.max === 'number' ? frow('Nightly runs', h('span', { class: 'num' }, `${b.used} of ${b.max}, ${b.stagger_minutes} min apart`)) : null,
      info.last_backup ? frow('Last backup', h('span', { class: 'num' }, stamp(info.last_backup))) : null,
      info.last_export ? frow('Last export', h('span', { class: 'num' }, stamp(info.last_export))) : null,
      h('div', { class: 'frow', style: 'border:0' },
        h('button', { class: 'btn primary', onclick: run('/api/data/backup') }, 'Back up now'),
        h('span', { style: 'width:6px' }),
        h('button', { class: 'btn', onclick: run('/api/data/export') }, 'Export'),
        h('span', { style: 'width:6px' }),
        h('button', { class: 'btn', onclick: run('/api/data/vacuum') }, 'Vacuum')),

      h('h3', null, 'App'),
      location.host ? frow('Server', h('span', { class: 'mono' }, location.host)) : null,
      c.binary ? frow('Claude', h('span', { class: 'mono' }, c.binary)) : null,
      // The model every run falls back to, shown only when it is one: "default" leaves the choice to the CLI.
      c.model && c.model !== 'default' ? frow('Model', h('span', { class: 'mono' }, c.model)) : null,
      c.sessions_kept_days ? frow('Sessions kept', h('span', { class: 'num' }, `${c.sessions_kept_days} d`)) : null)];
}

// The module's pane. Model and effort go on every CLI run the module makes; the switches hold its page and its tasks.
function modulePane(t, d) {
  const m = t.mod;
  if (!m) return null;
  if (m.error) return [h('h2', null, m.title), h('div', { class: 'prose' }, m.error)];
  const c = (S.shell && S.shell.claude) || {};
  const key = (k) => `modules.${m.name}.${k}`;
  const knobs = [
    m.agent ? frow('Model', pick(choices(c.models), m.model, (v) => save({ [key('model')]: v }))) : null,
    m.agent ? frow('Effort', pick(choices(c.efforts), m.effort, (v) => save({ [key('effort')]: v }))) : null,
    m.page ? frow('Shown', sw(m.enabled, (on) => save({ [key('enabled')]: on }))) : null,
    m.tasks ? frow('Runs', sw(m.scheduled, (on) => save({ [key('scheduled')]: on }))) : null,
  ].filter(Boolean);
  return [h('h2', null, m.title),
    knobs.length ? h('div', { class: 'form' }, ...knobs) : null,
    m.name === 'feedback' ? feedbackQueue(d) : null];
}

// The record of what was sent from anywhere in the app: what no work session has cleared, then what one has.
function feedbackQueue(d) {
  const rows = d.feedback || [];
  if (!rows.length) return null;
  const pending = rows.filter((r) => !r.cleared_at);
  const cleared = rows.filter((r) => r.cleared_at);
  const note = (r) => frow(
    h('span', { title: r.error || r.text, style: `flex:1;min-width:0;${ONE_LINE}` }, r.summary || r.text),
    [r.kind ? h('span', null, r.kind) : null,
      r.status === 'failed' ? h('button', { class: 'btn', onclick: () => retry(r.id) }, 'Retry') : null,
      h('span', { class: 'num' }, dayLabel(r.created_at))]);
  return h('div', { class: 'form' },
    pending.length ? h('h3', null, 'Pending') : null, ...pending.map(note),
    cleared.length ? h('h3', null, 'Cleared') : null, ...cleared.map(note));
}

export default {
  cols: 'minmax(0,1fr)',
  chips: ['All'],
  // The tiles are the shell's own; a database or queue that will not answer takes its rows with it, nothing else.
  async load() {
    if (S.data === null && S.sel === null) S.sel = OTTO;   // opening the page opens Otto's pane beside the grid
    const [info, feedback] = await Promise.all([
      get('/api/data').catch(() => null),
      S.sel === 'feedback' ? get(q('/api/feedback/list', { limit: Number(setting('ui.page_size', 40)) || 40 })).catch(() => null) : null,
    ]);
    return { items: tiles(), info: info || {}, feedback: feedback || [] };
  },
  filter: () => (S.data && S.data.items) || [],   // a grid of tiles is not a list the search bar narrows
  groups: () => [],                               // the tiles are drawn above; nothing is plated under them
  cells: () => [],                                // groups() draws no rows, so core never asks for a row's cells
  above: (d) => tileGrid(d),
  detail: (item, d) => {
    const t = (d.items || []).find((x) => String(x.id) === String(item.id)) || item;   // the pane reads this load, never the one it opened on
    return t.id === OTTO ? ottoPane(d) : modulePane(t, d);
  },
};
