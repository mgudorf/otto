// The query editor: a table or a saved query opens on the page as SQL that runs where it is shown. The draft and the last
// result live here, keyed by item, so a redraw never loses them. A statement SQLite refuses on the read-only connection is
// confirmed first and then goes through `write`, which backs the store up before it runs.
import { $, h, put, toast, confirmPop, closePops, place, load, registerSql } from './core.js';
import { post } from './api.js';

const drafts = new Map();   // item id -> { text, result }
let box = null;
const seed = (i) => (i.type === 'query' ? i.sql || '' : `SELECT * FROM "${i.title}"`);
function state(i) {
  const k = String(i.id);
  if (!drafts.has(k)) drafts.set(k, { text: seed(i), result: null });
  return drafts.get(k);
}
const fail = (d, e) => { d.result = { kind: 'error', error: e }; };

// ---- what the buttons do ------------------------------------------------------------------------------------------
async function run(i) {
  const d = state(i), sql = d.text.trim();
  if (!sql) return;
  try {
    const r = await post('/api/database/action/run', { sql });
    if (r.needs_confirm) { confirmPop($('.sqlbar .run', box), 'This writes to the store. Run it?', () => write(i)); return; }
    if (r.error) fail(d, r.error); else d.result = { kind: 'rows', ...r };
  } catch (e) { fail(d, e.message); }
  draw(i);
}
async function write(i) {
  const d = state(i);
  try {
    const r = await post('/api/database/action/write', { sql: d.text.trim() });
    if (r.error) fail(d, r.error); else d.result = { kind: 'wrote', ...r };
  } catch (e) { fail(d, e.message); }
  draw(i);
  load();   // row counts, or the tables themselves, may have moved
}
async function explain(i) {
  const d = state(i), sql = d.text.trim();
  if (!sql) return;
  try {
    const r = await post('/api/database/action/explain', { sql });
    if (r.error) fail(d, r.error); else d.result = { kind: 'plan', lines: r.lines };
  } catch (e) { fail(d, e.message); }
  draw(i);
}
// A saved query keeps its name; a table's SQL asks for one.
function save(i, at) {
  const sql = state(i).text.trim();
  if (!sql) return;
  const keep = async (name) => {
    try { await post('/api/database/action/save', { name, sql }); } catch (e) { toast(e.message); return; }
    toast(`Saved ${name}`);
    await load();
  };
  if (i.type === 'query') { keep(i.title); return; }
  closePops();
  const inp = h('input', { autocomplete: 'off', spellcheck: 'false', 'aria-label': 'Name' });
  inp.addEventListener('keydown', (e) => {
    e.stopPropagation();
    if (e.key === 'Escape') closePops();
    if (e.key === 'Enter' && inp.value.trim()) { const name = inp.value.trim(); closePops(); keep(name); }
  });
  place(h('div', { class: 'pop', id: 'tagPop' }, inp), at);
  inp.focus();
}

// ---- drawing -------------------------------------------------------------------------------------------------------
function resultEls(r) {
  if (!r) return [];
  if (r.kind === 'error') return [h('div', { class: 'err' }, r.error)];
  if (r.kind === 'plan') return [h('pre', null, (r.lines || []).join('\n'))];
  if (r.kind === 'wrote') return [h('div', { class: 'stamp num' }, `${Number(r.changes || 0).toLocaleString()} rows changed, backup ${r.backup}`)];
  const n = Number(r.total || 0), note = `${n.toLocaleString()} rows${r.truncated ? ', truncated' : ''} · ${r.ms} ms`;
  if (!(r.columns || []).length) return [h('div', { class: 'stamp num' }, r.changed ? `${r.changed.toLocaleString()} rows changed · ${r.ms} ms` : note)];
  const cell = (v) => (v === null ? h('td', { class: 'null' }, 'null') : h('td', { title: String(v) }, String(v)));
  return [h('div', { class: 'stamp num' }, note),
    h('div', { class: 'grid' }, h('table', null, h('thead', null, h('tr', null, ...r.columns.map((c) => h('th', null, c)))),
      h('tbody', null, ...r.rows.map((row) => h('tr', null, ...row.map(cell))))))];
}
function onKey(i, e) {
  e.stopPropagation();
  if (e.key === 'Escape') e.target.blur();
  if (e.key === 'Enter' && (e.ctrlKey || e.metaKey)) { e.preventDefault(); run(i); }
}
// The editor for one item. A textarea that was being typed into keeps its focus and caret through the redraw.
function editor(i) {
  const d = state(i);
  const old = $('#page .sql textarea'), held = old && document.activeElement === old ? [old.selectionStart, old.selectionEnd] : null;
  const ta = h('textarea', { spellcheck: 'false', 'aria-label': 'SQL', onkeydown: (e) => onKey(i, e), oninput: () => { d.text = ta.value; } });
  ta.value = d.text;
  box = h('div', { class: 'sql', 'data-id': i.id }, ta,
    h('div', { class: 'sqlbar' },
      h('button', { class: 'run', 'data-tagbtn': '1', onclick: () => run(i) }, 'Run'),
      h('button', { 'data-tagbtn': '1', onclick: () => explain(i) }, 'Explain'),
      h('button', { 'data-tagbtn': '1', onclick: (e) => save(i, e.currentTarget) }, 'Save')),
    h('div', { class: 'sqlout' }, ...resultEls(d.result)));
  if (held) queueMicrotask(() => { ta.focus(); ta.setSelectionRange(Math.min(held[0], ta.value.length), Math.min(held[1], ta.value.length)); });
  return box;
}
function draw(i) {
  if (!box || box.dataset.id !== String(i.id) || !box.isConnected) return;
  put($('.sqlout', box), ...resultEls(state(i).result));
}

registerSql({ editor });
