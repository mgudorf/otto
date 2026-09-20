// Science: the workspace as one list — notebooks, scripts, what is running now — with the picked file's cells beside it.
// A run is queued on the daemon and its outputs arrive over the module's event stream, so the pane fills while it runs.
import { S, $, h, icon, I, hue, toast, chk, titleCell, acts, tagAct, tagLine, dateLine, confirmPop, closePops, refresh, renderMain, select, stamp } from '../core.js';
import { get, post, sse } from '../api.js';
import hljs from '../vendor/highlight/core.min.js';
import python from '../vendor/highlight/python.min.js';

hljs.registerLanguage('python', python);

const EVERY = [['30m', 'every 30 m'], ['1h', 'every 1 h'], ['6h', 'every 6 h'], ['1d', 'every 1 d'], ['7d', 'every 7 d']];
const TOKEN = { keyword: 'k', literal: 'k', built_in: 'k', type: 'k', string: 's', number: 'n', comment: 'cm', meta: 'cm' };
const SCRIPT = 'script';   // the cell every script event carries

const live = {};       // cell id, or SCRIPT -> the outputs streaming in right now
const stream = { file: null, stop: null };   // the open event stream, and the file it was opened for
let shown = null;      // the file the pane stands on, and how far down it was read
let scrolled = 0;
let painting = false;

const busy = (i) => !!(i.running || i.kernel === 'busy');
const leaf = (p) => String(p).split('/').pop();

// highlight.js, recoloured into the four token classes the stylesheet knows.
function code(src) {
  const out = hljs.highlight(String(src || ''), { language: 'python' }).value;
  return out.replace(/<span class="([^"]*)">/g, (_, cls) => {
    const hit = cls.split(/\s+/).map((c) => TOKEN[c.replace('hljs-', '')]).find(Boolean);
    return hit ? `<span class="${hit}">` : '<span>';
  });
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

function cellEl(c) {
  const streaming = live[c.id];
  const on = !!c.running || streaming !== undefined;
  const outs = streaming !== undefined ? streaming : (c.outputs || []);
  const prose = c.type !== 'code';
  return h('div', { class: 'cell', style: `--c:${hue('science')}` },
    h('span', { class: `g${on ? ' run' : ''}` }, prose ? '' : on ? '[*]' : c.execution_count != null ? `[${c.execution_count}]` : '[ ]'),
    h('div', null,
      prose ? h('pre', { class: 'md' }, c.source) : h('pre', { html: code(c.source) }),
      ...outs.map(outEl)));
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

// The pane is rebuilt on every render, so a long notebook is put back where it was being read.
function detail(i) {
  tune(i.id);                                 // Home and a tag page open this pane too, so it is tuned here as well
  if (String(i.id) !== String(shown)) { shown = String(i.id); scrolled = 0; }
  else { const el = $('#detail'); if (el) scrolled = el.scrollTop; }
  const status = statusText(i);
  const actions = i.actions || [];
  const body = i.kind === 'py' && typeof i.source === 'string' ? [scriptEl(i)] : Array.isArray(i.cells) ? i.cells.map(cellEl) : [];
  requestAnimationFrame(() => { const el = $('#detail'); if (el && String(shown) === String(i.id)) el.scrollTop = scrolled; });
  return [h('h2', null, i.title), status ? dateLine(status) : null, tagLine(i),
    actions.length ? h('div', { class: 'actions', style: 'margin:0 0 14px' }, ...actions.map((a) => actionBtn(i, a))) : null,
    ...body];
}

export default {
  cols: '18px 16px minmax(0,1fr) 184px', colsSplit: '18px 16px minmax(0,1fr) 136px',
  chips: ['All', 'Notebooks', 'Scripts', 'Running'],
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
