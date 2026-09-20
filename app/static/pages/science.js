// Science: the workspace as one list — notebooks, scripts, what is running now — with the picked file's cells beside it.
// A run is queued on the daemon and its outputs arrive over the module's event stream, so the pane fills while it runs.
// A notebook's cells are its editor: command and edit modes, the JupyterLab keys, every change written straight to the file.
import { S, $, h, icon, I, hue, toast, chk, titleCell, acts, tagAct, tagLine, dateLine, confirmPop, closePops, refresh, renderMain, select, stamp } from '../core.js';
import { get, post, sse } from '../api.js';
import hljs from '../vendor/highlight/core.min.js';
import python from '../vendor/highlight/python.min.js';

hljs.registerLanguage('python', python);

const EVERY = [['30m', 'every 30 m'], ['1h', 'every 1 h'], ['6h', 'every 6 h'], ['1d', 'every 1 d'], ['7d', 'every 7 d']];
const TOKEN = { keyword: 'k', literal: 'k', built_in: 'k', type: 'k', string: 's', number: 'n', comment: 'cm', meta: 'cm' };
const SCRIPT = 'script';   // the cell every script event carries
const CHORD_MS = 1000;     // JupyterLab's window for the second key of d,d · i,i · 0,0
const INDENT = '    ';
const trimNl = (s) => s.replace(/^\n+/, '').replace(/\n+$/, '');   // Lab trims both halves of a split

// The cell's editor, sized and coloured as the cell's own code block, so opening one for typing moves nothing.
const CSS = `#cells { outline: none; }
.cell textarea { display: block; width: 100%; margin: 0; padding: 8px 12px; border-radius: 6px; background: var(--bg); border: 1px solid var(--line); font-family: var(--mono); font-size: 16px; line-height: 1.55; resize: none; overflow: hidden; }
.cell textarea:focus { border-color: var(--ink); }
.cell.on pre, .cell.on textarea { box-shadow: inset 2px 0 0 var(--c); }
.cell.in pre, .cell.in textarea { box-shadow: inset 2px 0 0 var(--line-strong); }`;

const live = {};       // cell id, or SCRIPT -> the outputs streaming in right now
const stream = { file: null, stop: null };   // the open event stream, and the file it was opened for
let shown = null;      // the file the pane stands on, and how far down it was read
let scrolled = 0;
let painting = false;

// The editor, for the notebook the pane stands on: where the keyboard is, what is typed but not yet written, and the
// history z walks. `take` says the next draw takes the focus back, because every draw replaces the cells it was in,
// and `drawing` is that replacement in progress: the browser blurs the editor it tears down, which is not the owner
// leaving the cell.
const ed = {
  file: null, mode: 'command', head: 0, anchor: 0,
  draft: null, written: null, saving: null, clip: [], past: [], future: [], pending: null, caret: null, take: false, drawing: false,
};

const busy = (i) => !!(i.running || i.kernel === 'busy');
const leaf = (p) => String(p).split('/').pop();

// highlight.js, recoloured into the four token classes the stylesheet knows. A keystroke redraws every cell, so what
// a source highlighted to is kept until the pane has moved on to another file.
const painted = new Map();
function code(src) {
  const s = String(src || '');
  let out = painted.get(s);
  if (out === undefined) {
    out = hljs.highlight(s, { language: 'python' }).value.replace(/<span class="([^"]*)">/g, (_, cls) => {
      const hit = cls.split(/\s+/).map((c) => TOKEN[c.replace('hljs-', '')]).find(Boolean);
      return hit ? `<span class="${hit}">` : '<span>';
    });
    if (painted.size > 400) painted.clear();
    painted.set(s, out);
  }
  return out;
}

// ---- the daemon ---------------------------------------------------------------------------------
function paint() {
  if (painting) return;                       // a run can push many chunks a second; one repaint per frame is enough
  painting = true;
  requestAnimationFrame(() => { painting = false; if (stream.file !== null && String(S.sel) === stream.file) renderMain(); });
}

// The stream follows the pane: opened on the file it stands on, closed when that changes or goes.
function tune(id) {
  const file = id === null || id === undefined ? null : String(id);
  if (stream.file === file) return;
  if (stream.stop) stream.stop();
  for (const k of Object.keys(live)) delete live[k];
  stream.file = file;
  stream.stop = null;
  if (file) { stream.stop = sse('/api/science/events', onEvent); watch(); }
}

// Nothing tells a page it was left, so the pane's going is read off #main, whose children every render replaces:
// a render where the open row is no longer this file ends the stream, on Science's own page or on Home's.
let watching = false;
function watch() {
  const main = $('#main');
  if (watching || !main) return;
  watching = true;
  new MutationObserver(() => { if (stream.file !== null && String(S.sel) !== stream.file) tune(null); }).observe(main, { childList: true });
}

function onEvent(ev) {
  if (stream.file === null || String(ev.path) !== stream.file) return;
  if (ev.event === 'started') live[ev.cell] = [];
  else if (ev.event === 'output') live[ev.cell] = [...(live[ev.cell] || []), ev.output];
  else { delete live[ev.cell]; reload(stream.file); return; }   // done or failed: the file now holds the outputs
  paint();
}

async function reload(id) {
  try {
    const it = await get(`/api/science/item/${encodeURIComponent(id)}`);
    if (String(S.sel) === String(id)) { S.item = it; paint(); }
  } catch (e) { toast(e.message); }
}

// `note` is for a verb the daemon only queues: the file's row says nothing until the job is picked up.
async function act(verb, id, body, note) {
  try { await post(`/api/science/action/${verb}`, { id, ...body }); } catch (e) { toast(e.message); return; }
  if (note) toast(note);
  await refresh();
  if (String(S.sel) === String(id)) reload(id);
}

// `name.py` is a script, `name.ipynb` a notebook, anything else a folder, at that path under the root.
function newPop(anchor) {
  closePops();
  const inp = h('input', { autocomplete: 'off', spellcheck: 'false' });
  const add = async () => {
    const name = inp.value.trim().replace(/\/+$/, '');
    if (!name) return;
    closePops();
    const kind = name.endsWith('.py') ? 'py' : name.endsWith('.ipynb') ? 'ipynb' : 'folder';
    let made;
    try { made = await post('/api/science/action/new', { path: name, kind }); } catch (e) { toast(e.message); return; }
    await refresh();
    if (made && made.kind !== 'folder') select(made.id);
  };
  inp.addEventListener('keydown', (e) => { if (e.key === 'Enter') add(); if (e.key === 'Escape') closePops(); });
  const pop = h('div', { class: 'pop pin-pop', id: 'tagPop' }, inp, h('button', { class: 'btn primary', onclick: add }, 'Add'));
  document.body.append(pop);
  const r = anchor.getBoundingClientRect();
  pop.style.left = `${Math.max(8, Math.min(r.right - 300, innerWidth - 310))}px`;
  pop.style.top = `${r.bottom + 6}px`;
  inp.focus();
}

function everyPop(anchor, id) {
  closePops();
  const pop = h('div', { class: 'pop', id: 'tagPop' }, ...EVERY.map(([value, label]) => h('div', { class: 'pi', onclick: () => { closePops(); act('schedule', id, { every: value }); } }, label)));
  document.body.append(pop);
  const r = anchor.getBoundingClientRect();
  pop.style.left = `${Math.min(r.left, innerWidth - 290)}px`;
  pop.style.top = `${r.bottom + 4}px`;
}

// ---- the editor ---------------------------------------------------------------------------------
// The file on disk is the document: a cell leaves the keyboard and its text is written, a structural change writes the
// whole list. Nothing here holds a save button, and nothing is kept that the daemon has not been told about.
const cellsOf = () => (S.item && Array.isArray(S.item.cells) ? S.item.cells : []);
const clamp = (i) => Math.max(0, Math.min(i, cellsOf().length - 1));
const head = () => clamp(ed.head);
const srcOf = (c, i) => (ed.draft && ed.draft.index === i ? ed.draft.source : c.source);
function span() { const a = clamp(ed.anchor), b = head(); return [Math.min(a, b), Math.max(a, b)]; }

// The cell list as the owner sees it: the file's cells with what is being typed over the top.
const current = () => cellsOf().map((c, i) => ({ id: c.id, type: c.type, source: srcOf(c, i) }));

// Whatever was typed into the notebook the pane is leaving still reaches its file, even when nothing blurred the cell.
function flush(id) {
  if (!ed.file || ed.file === String(id) || !ed.draft || ed.draft === ed.written) return;
  edit('set_cell', { index: ed.draft.index, source: ed.draft.source });
  ed.draft = null;
}

// True while the pane stands on the same notebook; another file starts the editor over.
function same(item) {
  const id = String(item.id);
  if (ed.file === id) return true;
  Object.assign(ed, { file: id, mode: 'command', head: 0, anchor: 0, draft: null, written: null, saving: null, past: [], future: [], pending: null, caret: null, take: false });
  painted.clear();
  return false;
}

async function edit(verb, body) {
  try { await post(`/api/science/action/${verb}`, { id: ed.file, ...body }); return true; }
  catch (e) { toast(e.message); return false; }
}

// The file as the daemon now holds it, without a draw: the caller says when the pane is redrawn.
async function pull() {
  const id = ed.file;
  try { const it = await get(`/api/science/item/${encodeURIComponent(id)}`); if (String(S.sel) === String(id)) S.item = it; }
  catch (e) { toast(e.message); }
}

// Make `at` the active cell and draw. Edit mode hands the caret to that cell's editor, command mode to the list.
function place(at, mode = 'command', caret, anchor) {
  ed.head = clamp(at);
  ed.anchor = anchor === undefined || anchor === null ? ed.head : clamp(anchor);
  ed.mode = mode;
  ed.caret = mode === 'edit' ? (caret === undefined ? 0 : caret) : null;
  if (mode === 'edit') { const c = cellsOf()[ed.head]; ed.draft = c ? { index: ed.head, source: c.source } : null; }
  ed.take = true;
  renderMain();
}

// Write the cell being typed in, if its text changed. Every structural change waits on this.
function commit() {
  const d = ed.draft;
  const cell = d && cellsOf()[d.index];
  if (!d || !cell || d.source === cell.source) { ed.draft = null; return ed.saving; }
  ed.written = d;
  ed.saving = (async () => {
    if (await edit('set_cell', { index: d.index, source: d.source })) await pull();
    if (ed.draft === d) ed.draft = null;
    renderMain();
  })();
  return ed.saving;
}
const settle = () => (ed.draft ? commit() : ed.saving);

// Out of the cell and back to the list. A blur draws nothing, so the click that caused it still lands where it was aimed.
function leave(draw) {
  ed.mode = 'command';
  ed.caret = null;
  const p = commit();
  if (draw) { ed.take = true; renderMain(); }
  return p;
}

function enter(at, caret) {
  if (ed.mode === 'edit' && head() === clamp(at)) return;
  commit();
  place(at, 'edit', caret);
}

async function write(cells, at, mode, caret, anchor) {
  if (!(await edit('set_cells', { cells }))) return;
  await pull();
  place(at, mode, caret, anchor);
}

// One structural change: `fn` gets the cells as they stand and returns {cells, head, anchor?}, or null for nothing to
// do. Both sides are kept, so z walks back through them.
async function op(fn, mode = 'command', caret) {
  await ed.saving;
  const a = current(), ha = head();
  const r = fn(a.map((c) => ({ ...c })));
  if (!r) return;
  ed.draft = null;
  ed.future = [];
  const entry = { a, ha, b: null, hb: r.head };
  ed.past.push(entry);
  await write(r.cells, r.head, mode, caret, r.anchor);
  entry.b = current();
}

// Cells of `from`, but a cell typed in since the change keeps its text: z undoes the cell operation, not the typing.
function restore(from, to) {
  const now = new Map(current().map((c) => [c.id, c.source]));
  const then = new Map(to.map((c) => [c.id, c.source]));
  return from.map((c) => (c.id && now.has(c.id) && now.get(c.id) !== then.get(c.id) ? { ...c, source: now.get(c.id) } : c));
}

async function undo() {
  await ed.saving;
  const e = ed.past.pop();
  if (!e || !e.b) return;
  const cells = restore(e.a, e.b);
  ed.draft = null;
  ed.future.push(e);
  await write(cells, e.ha);
  e.a = current();
}

async function redo() {
  await ed.saving;
  const e = ed.future.pop();
  if (!e || !e.b) return;
  const cells = restore(e.b, e.a);
  ed.draft = null;
  ed.past.push(e);
  await write(cells, e.hb);
  e.b = current();
}

const insert = (at, type = 'code', mode = 'command') => op((cells) => { cells.splice(at, 0, { type, source: '' }); return { cells, head: at }; }, mode, 0);

function remove(cut) {
  return op((cells) => {
    const [a, b] = span();
    const gone = cells.splice(a, b - a + 1);
    if (cut) ed.clip = gone.map(({ type, source }) => ({ type, source }));
    if (!cells.length) cells.push({ type: 'code', source: '' });
    return { cells, head: Math.min(a, cells.length - 1) };
  });
}

function copy() { const [a, b] = span(); ed.clip = current().slice(a, b + 1).map(({ type, source }) => ({ type, source })); }

function paste(above) {
  if (!ed.clip.length) return;
  return op((cells) => {
    const [a, b] = span();
    const at = above ? a : b + 1;
    cells.splice(at, 0, ...ed.clip.map((c) => ({ ...c })));
    return { cells, head: at + ed.clip.length - 1 };
  });
}

function setType(type) {
  return op((cells) => {
    const [a, b] = span();
    if (cells.slice(a, b + 1).every((c) => c.type === type)) return null;
    for (let i = a; i <= b; i++) cells[i] = { ...cells[i], type };
    return { cells, head: head(), anchor: ed.anchor };
  });
}

function heading(level) {
  return op((cells) => {
    const [a, b] = span();
    for (let i = a; i <= b; i++) cells[i] = { ...cells[i], type: 'markdown', source: `${'#'.repeat(level)} ${cells[i].source.replace(/^#+\s*/, '')}` };
    return { cells, head: head(), anchor: ed.anchor };
  });
}

function split(at, caret) {
  return op((cells) => {
    const c = cells[at];
    if (!c) return null;
    // The tail keeps the id, so the outputs stay with it, as in Lab.
    cells.splice(at, 1, { type: c.type, source: trimNl(c.source.slice(0, caret)) }, { ...c, source: trimNl(c.source.slice(caret)) });
    return { cells, head: at + 1 };
  }, 'edit', 0);
}

function merge() {
  return op((cells) => {
    let [a, b] = span();
    if (a === b) b = a + 1;
    if (b >= cells.length) return null;
    const one = { type: cells[head()].type, source: cells.slice(a, b + 1).map((c) => c.source).join('\n\n') };   // a new cell: Lab drops the outputs
    cells.splice(a, b - a + 1, one);
    return { cells, head: a };
  });
}

function move(dir) {
  return op((cells) => {
    const [a, b] = span();
    if (a + dir < 0 || b + dir >= cells.length) return null;
    const block = cells.splice(a, b - a + 1);
    cells.splice(a + dir, 0, ...block);
    return { cells, head: head() + dir, anchor: clamp(ed.anchor) + dir };
  });
}

// advance: 'next' (shift+enter) · 'insert' (alt+enter) · undefined (ctrl+enter). Only code cells run; every kind advances.
async function run(idx, advance) {
  await settle();
  const cells = cellsOf();
  for (const i of idx) if (cells[i] && cells[i].type === 'code') await edit('run', { index: i });
  const last = Math.max(...idx);
  if (advance === 'insert' || (advance === 'next' && last + 1 >= cells.length)) { insert(last + 1, 'code', 'edit'); return; }
  place(advance === 'next' ? last + 1 : head(), 'command');
}

function kernel(verb) {
  const i = S.item;
  if (!i || !i.kernel) return;
  act(verb, i.id);
}

function chord(key, fire) {
  const p = ed.pending;
  ed.pending = null;
  if (p && p.key === key && Date.now() - p.at < CHORD_MS) fire();
  else ed.pending = { key, at: Date.now() };
}

// A key the notebook answers is the notebook's alone: the shell's own list keys never see it.
function onKey(e) {
  if (e.target.tagName === 'TEXTAREA') editKey(e, Number(e.target.dataset.cell));
  else commandKey(e);
}

function commandKey(e) {
  const k = e.key.length === 1 ? e.key.toLowerCase() : e.key;
  const sh = e.shiftKey, mod = e.ctrlKey || e.metaKey;
  const n = cellsOf().length, at = head(), [a, b] = span();
  const idx = []; for (let i = a; i <= b; i++) idx.push(i);
  const go = (to, extend) => place(to, 'command', null, extend ? ed.anchor : undefined);
  if (!(k.length === 1 && 'di0'.includes(k))) ed.pending = null;
  let done = true;
  if (k === 'Enter') {
    if (e.altKey) run([at], 'insert');
    else if (mod) run(idx);
    else if (sh) run(idx, 'next');
    else place(at, 'edit', 'end');
  } else if (mod && sh && (k === 'ArrowUp' || k === 'ArrowDown')) move(k === 'ArrowUp' ? -1 : 1);
  else if (mod && k === 'a') place(n - 1, 'command', null, 0);
  else if (mod && (k === 's' || k === 'm')) { /* written already · already command mode */ }
  else if (mod || e.altKey) done = false;
  else if (k === 'ArrowUp' || k === 'k') go(at - 1, sh);
  else if (k === 'ArrowDown' || k === 'j') go(at + 1, sh);
  else if (k === 'a') insert(at);
  else if (k === 'b') insert(at + 1);
  else if (k === 'x') remove(true);
  else if (k === 'c') copy();
  else if (k === 'v') paste(sh);
  else if (k === 'z') { if (sh) redo(); else undo(); }
  else if (k === 'y') setType('code');
  else if (k === 'm') { if (sh) merge(); else setType('markdown'); }
  else if (k === 'r') setType('raw');
  else if (k.length === 1 && k >= '1' && k <= '6') heading(Number(k));
  else if (k === 'd') chord('d', () => remove(false));
  else if (k === 'i') chord('i', () => kernel('interrupt'));
  else if (k === '0') chord('0', () => kernel('restart'));
  else done = false;
  if (done) { e.preventDefault(); e.stopPropagation(); }
}

function editKey(e, at) {
  const t = e.target, k = e.key.length === 1 ? e.key.toLowerCase() : e.key;
  const sh = e.shiftKey, mod = e.ctrlKey || e.metaKey, plain = !sh && !mod && !e.altKey;
  const n = cellsOf().length;
  ed.draft = { index: at, source: t.value };
  let done = true;
  if (k === 'Escape' || (mod && k === 'm')) leave(true);
  else if (k === 'Enter' && (sh || mod || e.altKey)) run([at], e.altKey ? 'insert' : sh ? 'next' : undefined);
  else if (mod && sh && (k === '-' || k === '_')) split(at, t.selectionStart);
  else if (mod && k === '/') { if ((cellsOf()[at] || {}).type === 'code') comment(t, at); }
  else if (k === 'Tab' || (mod && (k === ']' || k === '['))) indent(t, at, sh || k === '[' ? -1 : 1);
  else if (mod && k === 's') commit();
  else if (plain && k === 'ArrowUp' && at > 0 && !t.value.slice(0, t.selectionStart).includes('\n')) { commit(); place(at - 1, 'edit', 'end'); }
  else if (plain && k === 'ArrowDown' && at < n - 1 && !t.value.slice(t.selectionEnd).includes('\n')) { commit(); place(at + 1, 'edit', 0); }
  else done = false;
  if (done) { e.preventDefault(); e.stopPropagation(); }
}

function comment(t, at) {
  editLines(t, (lines) => {
    const body = lines.filter((l) => l.trim());
    if (body.length && body.every((l) => /^\s*#/.test(l))) return lines.map((l) => l.replace(/^(\s*)#\s?/, '$1'));
    const col = body.length ? Math.min(...body.map((l) => l.match(/^\s*/)[0].length)) : 0;
    return lines.map((l) => (l.trim() ? `${l.slice(0, col)}# ${l.slice(col)}` : l));
  });
  ed.draft = { index: at, source: t.value };
}

function indent(t, at, dir) {
  if (dir > 0 && t.selectionStart === t.selectionEnd) {
    if (!document.execCommand('insertText', false, INDENT)) t.setRangeText(INDENT, t.selectionStart, t.selectionEnd, 'end');
  } else editLines(t, (lines) => lines.map((l) => (dir > 0 ? INDENT + l : l.replace(/^ {1,4}/, ''))));
  ed.draft = { index: at, source: t.value };
}

// Replace the whole lines under the selection through the browser's own insert, so ctrl+z still undoes it.
function editLines(t, fn) {
  const v = t.value, s = t.selectionStart, e = t.selectionEnd;
  const from = v.lastIndexOf('\n', s - 1) + 1;
  let to = v.indexOf('\n', e > s && v[e - 1] === '\n' ? e - 1 : e);
  if (to < 0) to = v.length;
  const out = fn(v.slice(from, to).split('\n')).join('\n');
  t.setSelectionRange(from, to);
  if (!document.execCommand('insertText', false, out)) t.setRangeText(out, from, to, 'end');
  if (s === e) { const p = Math.max(from, Math.min(from + out.length, s + out.length - (to - from))); t.setSelectionRange(p, p); }
  else t.setSelectionRange(from, from + out.length);
}

// Every draw replaces the cells, so what the keyboard was holding is read off the old ones before they go...
function stash() {
  const a = document.activeElement;
  if (!a || !a.closest || !a.closest('#cells')) return;
  ed.take = true;
  if (ed.mode === 'edit' && a.tagName === 'TEXTAREA' && Number(a.dataset.cell) === head()) {
    ed.draft = { index: head(), source: a.value };
    ed.caret = [a.selectionStart, a.selectionEnd];
  }
}

// ...and put back on the new ones, with the cell being typed in fitted to its text. Edit mode always ends holding the
// keyboard, since only a deliberate act enters it and a real blur leaves it; command mode takes the focus back only if
// it had it, so a draw never steals it from the drawer.
function focusBack() {
  const box = $('#cells');
  if (!box) return;
  const t = box.querySelector('textarea');
  if (t) grow(t);
  const take = ed.take;
  ed.take = false;
  if (ed.mode === 'edit' && t) {
    if (document.activeElement !== t) {
      t.focus({ preventScroll: true });
      const c = ed.caret;
      const p = c === 'end' ? [t.value.length, t.value.length] : Array.isArray(c) ? c : [Number(c) || 0, Number(c) || 0];
      t.setSelectionRange(Math.min(p[0], t.value.length), Math.min(p[1], t.value.length));
    }
  } else if (take) box.focus({ preventScroll: true });
  if (!take) return;
  const cell = box.querySelector(`.cell[data-i="${head()}"]`);
  if (cell) cell.scrollIntoView({ block: 'nearest' });
}

const grow = (t) => { t.style.height = 'auto'; t.style.height = `${t.scrollHeight}px`; };

// The character the click landed on, so a cell opened for typing keeps the caret where the eye was.
function caretIn(pre, e) {
  const r = document.caretRangeFromPoint ? document.caretRangeFromPoint(e.clientX, e.clientY) : null;
  if (!r || !pre.contains(r.startContainer)) return 'end';
  const upto = document.createRange();
  upto.selectNodeContents(pre);
  upto.setEnd(r.startContainer, r.startOffset);
  return upto.toString().length;
}

// The code opens the cell for typing; the gutter and the margin only pick it. An output is left alone, so it can be read.
function pick(e, at) {
  if (e.target.tagName === 'TEXTAREA') return;
  if (e.target.closest('.out')) return;                     // an output is the kernel's own markup, which may hold a pre
  const pre = e.target.closest('pre');
  if (pre) { e.preventDefault(); enter(at, caretIn(pre, e)); return; }
  const box = $('#cells');
  if (box) box.focus({ preventScroll: true });
  if (ed.mode === 'edit') leave(false);
  place(at, 'command');
}

function styleOnce() { if (!$('#cellcss')) document.head.append(h('style', { id: 'cellcss', html: CSS })); }

// ---- the pane -----------------------------------------------------------------------------------
// Every button the pane offers comes from the file's own action list; a schedule picks its interval first.
function actionBtn(item, a) {
  const risky = !!(a.confirm || a.removes);
  return h('button', {
    class: `btn${a.primary ? ' primary' : ''}${risky ? ' danger' : ''}`,
    'data-tagbtn': risky || a.verb === 'schedule' ? '1' : null,
    onclick: (e) => {
      if (a.href) { window.open(a.href, '_blank', 'noopener'); return; }
      if (a.verb === 'schedule') { everyPop(e.currentTarget, item.id); return; }
      if (risky) { confirmPop(e.currentTarget, a.confirm || `${a.label}?`, () => act(a.verb, item.id)); return; }
      act(a.verb, item.id);
    },
  }, a.label);
}

function outEl(o) {
  if (o.kind === 'image') return h('div', { class: 'out' }, h('img', { src: `data:image/png;base64,${o.png}`, style: 'max-width:100%;border-radius:6px' }));
  if (o.kind === 'html') return h('div', { class: 'out', html: o.html });
  if (o.kind === 'error') return h('div', { class: 'out err' }, o.traceback || `${o.ename}: ${o.evalue}`);
  return h('div', { class: 'out' }, o.text);
}

// One cell: the run's mark, then its source — highlighted to read, an editor while it is the one being typed in —
// then whatever it last printed. Nothing under a cell moves when it is picked, so the list never shifts.
function cellEl(c, at) {
  const streaming = live[c.id];
  const on = !!c.running || streaming !== undefined;
  const outs = streaming !== undefined ? streaming : (c.outputs || []);
  const prose = c.type !== 'code';
  const src = srcOf(c, at);
  const [a, b] = span();
  const active = at === head();
  let body;
  if (active && ed.mode === 'edit') {
    body = h('textarea', {
      'data-cell': at, spellcheck: 'false', rows: String(Math.max(1, src.split('\n').length)),
      oninput: (e) => { ed.draft = { index: at, source: e.target.value }; grow(e.target); },
      onblur: (e) => { if (!ed.drawing && e.target.isConnected) leave(false); },
    });
    body.value = src;
  } else body = prose ? h('pre', { class: 'md' }, src) : h('pre', { html: code(src) });
  return h('div', { class: `cell${active ? ' on' : a <= at && at <= b ? ' in' : ''}`, 'data-i': at, style: `--c:${hue('science')}`, onmousedown: (e) => pick(e, at) },
    h('span', { class: `g${on ? ' run' : ''}` }, prose ? '' : on ? '[*]' : c.execution_count != null ? `[${c.execution_count}]` : '[ ]'),
    h('div', null, body, ...outs.map(outEl)));
}

// A script is one cell: the file, then the run streaming now or the last one's output.
function scriptEl(i) {
  const streaming = live[SCRIPT];
  const on = !!i.running || streaming !== undefined;
  const text = streaming !== undefined ? streaming.map((o) => o.text).join('') : i.last ? i.last.output : '';
  return h('div', { class: 'cell', style: `--c:${hue('science')}` },
    h('span', { class: `g${on ? ' run' : ''}` }, on ? '[*]' : ''),
    h('div', null,
      h('pre', { html: code(i.source) }),
      text ? h('div', { class: `out${!on && i.last && i.last.status === 'failed' ? ' err' : ''}` }, text) : null));
}

// The kernel, the schedule and the last run that finished — each of them what the daemon sent, nothing before a date.
function statusText(i) {
  const bits = [];
  if (i.kind === 'ipynb' && i.kernel) bits.push(i.kernel === 'busy' ? 'running' : 'kernel idle');
  if (i.schedule) bits.push(i.schedule);
  if (i.kind === 'py' && i.last) bits.push(`${stamp(i.last.started_at)}, ${i.last.exit_code != null ? `exit ${i.last.exit_code}` : i.last.status}`);
  return bits.join(', ');
}

// The pane is rebuilt on every render, so a long notebook is put back where it was being read, and the cell that had
// the keyboard takes it again.
function detail(i) {
  tune(i.id);                                 // Home and a tag page open this pane too, so it is tuned here as well
  flush(i.id);
  const nb = i.kind === 'ipynb' && Array.isArray(i.cells);
  if (nb) {
    styleOnce();
    if (same(i)) stash();
    ed.drawing = true;                        // until the new cells are in place, a blur is the old ones being torn down
    queueMicrotask(() => { ed.drawing = false; });
  }
  if (String(i.id) !== String(shown)) { shown = String(i.id); scrolled = 0; }
  else { const el = $('#detail'); if (el) scrolled = el.scrollTop; }
  const status = statusText(i);
  const actions = (i.actions || []).map((a) => actionBtn(i, a));
  if (nb) actions.push(h('button', { title: 'New cell', class: 'btn ico', onclick: () => insert(head() + 1, 'code', 'edit') }, icon(I.plus)));
  const body = i.kind === 'py' && typeof i.source === 'string' ? [scriptEl(i)]
    : nb ? [h('div', { id: 'cells', tabindex: '0', onkeydown: onKey }, ...i.cells.map(cellEl))] : [];
  // A microtask, not a frame: headless and an idle window both stall requestAnimationFrame, and where the keyboard
  // sits cannot wait for a paint. The new cells are attached by the time it runs.
  queueMicrotask(() => {
    const el = $('#detail');
    if (el && String(shown) === String(i.id)) el.scrollTop = scrolled;
    if (nb) focusBack();
  });
  return [h('h2', null, i.title), status ? dateLine(status) : null, tagLine(i),
    actions.length ? h('div', { class: 'actions', style: 'margin:0 0 14px' }, ...actions) : null,
    ...body];
}

// The keys the open notebook answers. They are bound on the cells themselves; here they are so that ? lists them and
// the palette can run the first of each without the keyboard.
const onCell = (fn) => () => { if (S.item && S.item.kind === 'ipynb' && ed.file === String(S.item.id) && cellsOf().length) fn(); };
const KEYS = [
  ['Type in the cell, back to the list', '↵ esc', onCell(() => place(head(), 'edit', 'end'))],
  ['Run it, run and step down, run and add', 'Ctrl+↵ Shift+↵ Alt+↵', onCell(() => run([head()]))],
  ['Previous, next cell', 'k j', onCell(() => place(head() - 1))],
  ['A cell above, below', 'a b', onCell(() => insert(head()))],
  ['Cut, copy, paste', 'x c v', onCell(() => remove(true))],
  ['Delete the cell', 'd,d', onCell(() => remove(false))],
  ['Undo, redo the change', 'z Shift+z', onCell(undo)],
  ['Code, markdown, raw', 'y m r', onCell(() => setType('code'))],
  ['A heading, levels one to six', '1-6', onCell(() => heading(1))],
  ['Merge with the one below, split at the caret', 'Shift+m Ctrl+Shift+-', onCell(merge)],
  ['Move the cell up, down', 'Ctrl+Shift+↑ Ctrl+Shift+↓', onCell(() => move(-1))],
  ['Every cell', 'Ctrl+a', onCell(() => place(cellsOf().length - 1, 'command', null, 0))],
  ['Indent, outdent, comment', 'Tab Shift+Tab Ctrl+/', onCell(() => { const t = $('#cells textarea'); if (t) indent(t, head(), 1); })],
  ['Interrupt, restart the kernel', 'i,i 0,0', onCell(() => kernel('interrupt'))],
  ['Write the cell now', 'Ctrl+s', onCell(commit)],
];

export default {
  cols: '18px 16px minmax(0,1fr) 184px', colsSplit: '18px 16px minmax(0,1fr) 136px',
  chips: ['All', 'Notebooks', 'Scripts', 'Running'],
  keys: KEYS,
  async load() {
    const d = await get('/api/science/left');
    return { items: (d.groups || []).flatMap((g) => g.rows) };
  },
  filter: (list, chip) => (chip === 'Notebooks' ? list.filter((i) => i.kind === 'ipynb')
    : chip === 'Scripts' ? list.filter((i) => i.kind === 'py')
      : chip === 'Running' ? list.filter(busy) : list),
  groups(list) {
    const by = new Map();
    for (const i of list) {
      const folder = i.title.includes('/') ? i.title.slice(0, i.title.lastIndexOf('/')) : '';
      if (!by.has(folder)) by.set(folder, []);
      by.get(folder).push(i);
    }
    return [...by].map(([folder, rows]) => ({ label: folder ? `${folder}/` : '', rows }));
  },
  cells: (i) => [chk(i), icon(i.kind === 'py' ? I.file : I.nb), titleCell(i, leaf(i.title), { hideFixed: true }),
    h('span', { class: 'c', style: busy(i) ? `color:${hue('science')}` : null }, busy(i) ? 'running' : i.kernel === 'idle' ? 'kernel idle' : i.schedule || ''),
    acts(i, [['Run', () => act('run', i.id, null, `Run queued: ${leaf(i.title)}`), I.play], tagAct(i)])],
  rowClass: (i) => (busy(i) ? 'unread' : ''),
  tools: () => [h('button', { title: 'New', class: 'ico btn primary', 'data-tagbtn': '1', onclick: (e) => newPop(e.currentTarget) }, icon(I.plus))],
  detail,
};
