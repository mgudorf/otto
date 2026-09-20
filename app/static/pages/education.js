// Education: the queue and the completed history, one bar per row; the pane is the question itself, set as a page of
// a textbook — definitions, premise, then each part with its own answer box. The tutor grades in the drawer.
import {
  S, h, hue, chk, titleCell, acts, tagAct, card, tagEl, dateLine, tagLine, titled, confirmPop, toast, refresh, select,
  newest, dayLabel, I,
} from '../core.js';
import { get, post } from '../api.js';
import { tex } from '../md.js';

const HUE = () => hue('education');
const bar = (i) => (i.status === 'completed' ? i.score || 0 : i.pct || 0);
const drafts = {};          // a half-typed answer per part, so the poll and a sibling's Submit never throw it away
const dkey = (item, p) => `${item.id}:${p.n}`;
let topics = null;          // the Topics view's rows: fetched on open and while that view is up, never behind it

// Every write goes through the module's own route; the pane reloads from the daemon rather than guessing the result.
async function run(verb, body, removed) {
  try { await post(`/api/education/action/${verb}`, body); } catch (e) { toast(e.message); return false; }
  if (removed) for (const k of Object.keys(drafts)) if (k.startsWith(`${removed}:`)) delete drafts[k];
  if (removed && String(S.sel) === String(removed)) select(null); else S.item = null;
  await refresh();
  return true;
}

// The pane's buttons are the server's: primary is the module's hue, anything that asks or removes is the red one.
function actionEl(item, a) {
  const risky = !!(a.confirm || a.removes);
  const cls = `btn${a.primary ? ' primary' : risky ? ' danger' : ''}`;
  if (a.href) return h('button', { class: cls, onclick: () => window.open(a.href, '_blank', 'noopener') }, a.label);
  const go = () => run(a.verb, { id: item.id }, a.removes ? item.id : null);
  return h('button', { class: cls, onclick: (e) => (risky ? confirmPop(e.currentTarget, a.confirm || `${a.label}?`, go) : go()) }, a.label);
}

// One part: its title and ask as a single paragraph, the answer under it, and the score it came back with.
function partEl(item, p) {
  const graded = p.score !== null && p.score !== undefined;
  const closed = item.status === 'completed';
  const k = dkey(item, p);
  const box = h('textarea', {
    class: 'answer', disabled: closed || null, 'data-part': k,
    // A draft is text the daemon has not seen. An emptied box holds none, so it stops standing in front of the answer.
    oninput: (e) => { if (e.target.value) drafts[k] = e.target.value; else delete drafts[k]; },
    onkeydown: (e) => { if (e.key === 'Enter' && (e.ctrlKey || e.metaKey)) { e.preventDefault(); send(); } },
  });
  box.value = closed ? (p.answer || '') : (drafts[k] ?? (p.answer || ''));   // no draft: what the daemon holds
  const send = async () => {
    const text = box.value.trim();
    if (!text) return;
    delete drafts[k];                                          // the daemon's copy takes over, unless it refused it
    if (!(await run('answer', { id: item.id, n: p.n, answer: text }))) drafts[k] = text;
  };
  return h('div', { class: 'related' },
    graded ? h('span', { class: 'num', style: 'float:right' }, `${p.score}/100`) : null,
    h('div', { class: 'qbody', html: titled(p.title, tex(p.text)) }),
    box,
    closed ? null : h('div', { class: 'actions', style: 'margin-top:8px' }, h('button', { class: 'btn primary', onclick: send }, graded ? 'Resubmit' : 'Submit')));
}

// Ctrl+Enter sends the box the caret sits in. The palette runs the same action with the caret nowhere, so there it
// sends the open question's first part holding an answer the daemon has not seen. With nothing to send it says so.
function submitHere() {
  const boxes = [...document.querySelectorAll('#detail .answer:not([disabled])')];
  const at = document.activeElement;
  const box = boxes.includes(at) ? at : boxes.find((b) => drafts[b.dataset.part] !== undefined);
  if (!box || !box.value.trim()) { toast(boxes.length ? 'Nothing typed to send' : 'Open a question first'); return; }
  box.parentElement.querySelector('.actions .btn.primary').click();
}

function questionView(i) {
  const head = [h('h2', null, i.title), i.when ? dateLine(dayLabel(i.when)) : null, tagLine(i)];
  if (!i.parts) return head;                                   // the row is open while the daemon answers with the body
  const buttons = i.actions || [];
  return [...head,
    h('div', { class: 'prose qbody', html: (i.definitions ? tex(i.definitions) : '') + tex(i.premise) }),
    ...i.parts.map((p) => partEl(i, p)),
    buttons.length ? h('div', { class: 'actions' }, ...buttons.map((a) => actionEl(i, a))) : null];
}

// Topics: what each one has cost so far, the name doubling as the tag its questions carry.
function topicsView(rows) {
  const cols = 'minmax(0,1fr) 120px 88px';
  return h('div', null, card('', 0, rows.map((t) => h('div', { class: 'row', style: `--cols:${cols}` },
    h('span', { class: 't' }, tagEl(String(t.name).trim().toLowerCase(), { fixed: true })),
    h('span', { class: 'c num' }, `${t.completed}/${t.asked}`),
    h('span', { class: 'r num strong' }, t.average === null || t.average === undefined ? '' : String(t.average))))));
}

async function generate() {
  let r;
  try { r = await post('/api/education/action/generate'); } catch (e) { toast(e.message); return; }
  await refresh();
  if (r && r.warning) toast(r.warning);
  if (r && r.id) select(r.id);
}

export default {
  cols: '18px 44px minmax(0,1fr) 70px', colsSplit: '18px 44px minmax(0,1fr) 64px',
  chips: ['Active', 'Completed'],
  seg: ['Questions', 'Topics'],
  keys: [['Submit the answer', 'Ctrl+↵', submitHere]],
  async load() {
    const want = topics === null || S.seg.education === 'Topics';   // /blank feeds the Topics view and nothing else
    const [left, blank] = await Promise.all([get('/api/education/left'), want ? get('/api/education/blank') : null]);
    if (blank) topics = blank.topics || [];
    return { items: (left.groups || []).flatMap((g) => g.rows), topics };
  },
  filter: (list, chip) => list.filter((i) => (chip === 'Completed' ? i.status === 'completed' : i.status === 'active')),
  groups: (list) => [{ label: '', rows: [...list].sort(newest) }],
  cells: (i) => [chk(i),
    h('span', { class: 'pbar', style: `--c:${HUE()}` }, h('i', { style: `width:${bar(i)}%` })),
    titleCell(i),
    h('span', { class: 'r num' }, i.status === 'completed' ? i.score : ''),
    acts(i, [tagAct(i), i.status === 'active' && ['Delete', (e) => confirmPop(e.currentTarget, `Delete "${i.title}"?`, () => run('delete', { id: i.id }, i.id)), I.trash]])],
  tools: () => [h('button', { class: 'btn primary', onclick: generate }, 'Generate')],
  alt: (data) => topicsView(data.topics),
  detail: (i) => questionView(i),
};
