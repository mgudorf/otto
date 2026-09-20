// Database: the SQL console over otto.db. The editor sits above the list, whatever the last statement
// returned renders under it, and the list is every table with the module that owns it, then the saved queries.
// Run goes to the read-only connection; SQLite's own refusal is what asks before a write, and the write
// path backs the store up into data/backups/ before it touches anything.
import { h, $, card, titleCell, acts, hue, icon, I, toast, refresh, renderMain, select, confirmPop, closePops } from '../core.js';
import { get, post } from '../api.js';

const COLS = '136px minmax(0,1fr) 120px';
const SCOLS = '160px 90px minmax(0,1fr)';   // the schema pane: column, type, constraints
const QID = 'query:';                       // a saved query's id, so tables and queries share one list
const COLW = 'minmax(96px, max-content)';   // a result column: as wide as its widest value, never hair-thin
// The cap every result cell wears, header included: one long name or value must not size the track it sits in.
const CAP = 'max-width:420px;overflow:hidden;text-overflow:ellipsis';

// What the editor holds between renders: core rebuilds the page on every refresh and every selection.
const ed = { sql: '', name: '', result: null, mode: 'result' };

const fmt = (n) => Number(n || 0).toLocaleString();
const plural = (n, word) => `${fmt(n)} ${word}${Number(n) === 1 ? '' : 's'}`;
const runBtn = () => $('.editor .crow .btn.primary') || $('#main');

function setSql(sql, name) {
  ed.sql = sql; ed.name = name || ''; ed.result = null;
  renderMain();
}

// A read renders where it stands; a write moves the counts and can add or drop a table, so it reloads the page.
async function exec(verb) {
  const sql = ed.sql.trim();
  if (!sql) return;
  try {
    const r = await post(`/api/database/action/${verb}`, { sql });
    if (r.needs_confirm) {
      ed.result = null; renderMain();   // the last query's grid did not describe this statement
      confirmPop(runBtn(), 'This statement writes. Back up and run?', () => write(sql));
      return;
    }
    ed.result = r; ed.mode = verb === 'explain' ? 'explain' : 'result';
    renderMain();
  } catch (e) { toast(e.message); }
}

// The statement the confirm asked about, not whatever the box holds by the time it is answered.
async function write(sql) {
  try {
    const r = await post('/api/database/action/write', { sql });
    ed.result = r; ed.mode = 'write';
    if (r.backup) toast(r.backup);
    await refresh();
  } catch (e) { toast(e.message); }
}

async function act(a, item) {
  try {
    await post(`/api/database/action/${a.verb}`, { id: item.id });
    if (a.removes) select(null);
    await refresh();
  } catch (e) { toast(e.message); }
}

async function backup() {
  try { const r = await post('/api/data/backup'); toast(String(r.path).split(/[\\/]/).pop()); }
  catch (e) { toast(e.message); }
}

// A name for the statement, anchored to the button that asked; saving upserts on the name.
function namePop(anchor, value, onok) {
  closePops();
  const done = () => { const v = inp.value.trim(); closePops(); if (v) onok(v); };
  const inp = h('input', { value, spellcheck: 'false', onkeydown: (e) => { if (e.key === 'Enter') done(); if (e.key === 'Escape') closePops(); } });
  const pop = h('div', { class: 'pop pin-pop', id: 'tagPop' }, inp, h('button', { class: 'btn primary', onclick: done }, icon(I.check)));
  document.body.append(pop);
  const r = anchor.getBoundingClientRect();
  pop.style.left = `${Math.max(8, Math.min(r.left, innerWidth - 310))}px`;
  pop.style.top = `${r.bottom + 6}px`;
  inp.focus(); inp.select();
}

function save(e) {
  if (!ed.sql.trim()) return;
  namePop(e.currentTarget, ed.name, async (name) => {
    try { await post('/api/database/action/save', { name, sql: ed.sql.trim() }); ed.name = name; await refresh(); }
    catch (err) { toast(err.message); }
  });
}

// The daemon's own measure of what just ran: how much it touched and how long it took.
function line() {
  const r = ed.result;
  if (!r) return null;
  if (r.error) return h('span', { class: 'meta', style: 'color:var(--danger)' }, r.error);
  let text;
  if (ed.mode === 'write') text = `${plural(r.changes, 'row')} · ${r.ms} ms`;
  else if (ed.mode === 'explain') text = `${plural((r.lines || []).length, 'step')} · ${r.ms} ms`;
  else if ((r.columns || []).length) text = `${fmt(r.total)}${r.truncated ? '+' : ''} row${r.total === 1 ? '' : 's'} · ${r.ms} ms`;
  else text = `${r.ms} ms`;
  return h('span', { class: 'meta num' }, text);
}

// One box for the life of the page: core rebuilds the list around it, and a fresh element each time
// would throw away the caret and the height the owner dragged.
let box = null;
function field() {
  if (!box) {
    box = h('textarea', {
      spellcheck: 'false',
      oninput: (e) => { ed.sql = e.target.value; },
      onkeydown: (e) => { if (e.key === 'Enter' && (e.ctrlKey || e.metaKey)) { e.preventDefault(); exec('run'); } },
    });
  }
  if (box.value !== ed.sql) box.value = ed.sql;
  return box;
}

function editor() {
  return h('div', { class: 'editor' }, field(),
    h('div', { class: 'crow' },
      h('button', { class: 'btn primary', 'data-tagbtn': '1', onclick: () => exec('run') }, 'Run'),
      h('button', { class: 'btn', onclick: () => exec('explain') }, 'Explain'),
      h('button', { class: 'btn', 'data-tagbtn': '1', onclick: save }, 'Save'),
      line()));
}

// The result is one grid and the header and every row are subgrids of it, so the columns line up whatever
// they hold; a result wider than the pane scrolls into view instead of being cut off at the card's edge.
function resultGrid(cols, rows) {
  const cs = '--cols:subgrid;grid-column:1/-1';
  return h('div', { style: 'overflow-x:auto' },
    h('div', { style: `display:grid;grid-template-columns:repeat(${cols.length}, ${COLW});column-gap:12px;width:max-content;min-width:100%` },
      h('div', { class: 'thead', style: cs }, ...cols.map((c) => h('span', { style: CAP }, c))),
      ...rows.map((row) => h('div', { class: 'row', style: cs },
        ...row.map((v) => h('span', { class: 'c', style: `${CAP}${v === null ? ';color:var(--ink-3)' : ''}` }, v === null ? 'null' : String(v)))))));
}

function resultBody() {
  const r = ed.result;
  if (!r || r.error || ed.mode === 'write') return null;
  if (ed.mode === 'explain') return card('', 0, (r.lines || []).map((l) => h('div', { class: 'row', style: '--cols:minmax(0,1fr)' }, h('span', { class: 'c' }, l))));
  const cols = r.columns || [];
  if (!cols.length) return null;
  return card('', 0, [resultGrid(cols, r.rows || [])]);
}

const constraints = (c) => [c.pk && 'primary key', c.notnull && 'not null', c.default !== null && c.default !== undefined && `default ${c.default}`].filter(Boolean).join(' · ');

// The pane's buttons are the ones the daemon offers: primary wears the hue, anything that removes asks first.
function actionRow(item) {
  const list = item.actions || [];
  if (!list.length) return null;
  return h('div', { class: 'actions' }, ...list.map((a) => {
    const danger = !!(a.confirm || a.removes);
    return h('button', {
      class: `btn${a.primary ? ' primary' : danger ? ' danger' : ''}`, 'data-tagbtn': danger ? '1' : null,
      onclick: (e) => {
        if (a.href) { location.href = a.href; return; }   // the CSV leaves as a download, not a page
        if (danger) confirmPop(e.currentTarget, a.confirm || `${a.label}?`, () => act(a, item));
        else act(a, item);
      },
    }, a.label);
  }));
}

function tablePane(item) {
  const cols = item.columns || [];
  return [h('h2', { style: 'font-size:19px;font-family:var(--mono)' }, item.title),
    ...cols.map((c) => h('div', { class: 'row', style: `--cols:${SCOLS};padding:0` },
      h('span', { class: 'mono' }, c.name), h('span', { class: 'c' }, c.type || ''), h('span', { class: 'c' }, constraints(c)))),
    actionRow(item)];
}

function queryPane(item) {
  return [h('h2', null, item.title),
    h('div', { class: 'prose', style: 'font-family:var(--mono);font-size:15.5px' }, item.sql || ''),
    actionRow(item)];
}

export default {
  cols: COLS,
  chips: ['All'],
  async load() {
    const left = await get('/api/database/left');
    return {
      items: [
        // A table is the store's own shape, not an item the owner keeps: nothing here can carry a tag.
        ...left.modules.flatMap((m) => m.tables.map((t) => ({
          id: t.name, module: 'database', kind: 'table', title: t.name, owner: t.module, count: t.rows, tags: [], fixed: [], taggable: false,
        }))),
        ...(left.saved || []).map((q) => ({
          id: `${QID}${q.id}`, module: 'database', kind: 'query', title: q.name, when: q.updated_at, sql: q.sql, tags: [], fixed: [],
        })),
      ],
    };
  },
  filter: (list) => list,
  groups: (list) => [
    { label: '', rows: list.filter((i) => i.kind === 'table') },
    { label: 'Saved', rows: list.filter((i) => i.kind === 'query') },
  ].filter((g) => g.rows.length),
  cells: (i) => (i.kind === 'query'
    ? [h('span', { class: 'c' }), titleCell(i), h('span', { class: 'r num' }), acts(i, [['Load', () => setSql(i.sql, i.title)]])]
    : [h('span', { class: 'c', style: `color:${i.owner === 'app' ? 'var(--ink-2)' : hue(i.owner)}` }, i.owner),
      h('span', { class: 't' }, h('span', { class: 'title mono' }, i.title)),
      h('span', { class: 'r num' }, plural(i.count, 'row'))]),
  above: () => [editor(), resultBody()],
  tools: () => [h('button', { class: 'btn', onclick: backup }, 'Back up now')],
  detail: (item) => (item.kind === 'query' ? queryPane(item) : tablePane(item)),
};
