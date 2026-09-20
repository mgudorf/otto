// Second Brain: capture and recall. A task carries a box that completes it, anything else its kind's mark;
// the suggestions the nightly run proposes sit on their own plate above the days.
import { S, $, h, I, icon, hue, modOf, chk, titleCell, stampCell, acts, tagAct, byDay, newest,
  dateLine, tagLine, segEl, confirmPop, dayLabel, select, refresh, renderMain, toast } from '../core.js';
import { get, post, q } from '../api.js';

const MOD = 'second_brain';
const MARK = { link: I.link, quote: I.quote, note: I.note, fact: I.note };
let kind = 'Note';                                   // what the capture box writes; every opening starts on Note
let deep = 0, asked = '';                            // which page of the table is in hand, and the text it was asked with
const more = () => { deep += 1; refresh(); };
// A suggestion is not in the table the daemon searches, so the page holds it to the same words.
const hits = (i, text) => !text || `${i.title || ''} ${(i.tags || []).join(' ')}`.toLowerCase().includes(text.toLowerCase());

const act = (verb, body) => post(`/api/${MOD}/action/${verb}`, body);
// Every write is the daemon's; the page reloads from it rather than changing a row in place.
async function run(verb, body, after) {
  try { await act(verb, body); } catch (e) { toast(e.message); return; }
  if (after) after();
  await refresh();
}
// A row that has left the list takes its tick and the pane with it: nothing stays selected that is no longer there.
const drop = (i) => { S.picked.delete(String(i.id)); if (String(S.sel) === String(i.id)) select(null); };
const flip = (i) => run(i.done ? 'reopen' : 'done', { id: i.id });
// One write per task: a failure is said once and the rest still go, and only what completed is let go of.
async function doneAll(on) {
  let failed = null;
  for (const t of on.filter((i) => i.kind === 'task' && !i.done)) {
    try { await act('done', { id: t.id }); S.picked.delete(String(t.id)); } catch (e) { failed = e.message; }
  }
  if (failed) toast(failed);
  await refresh();
}

// ---- capture ------------------------------------------------------------------------------------
// A link is a link because it starts with one; the segment is the only thing that says task.
async function save() {
  const box = $('#captureBox'), tagBox = $('#captureTags');
  const text = box ? box.value.trim() : '';
  if (!text) return;
  const tags = ((tagBox && tagBox.value.match(/[\w-]+/g)) || []).map((t) => t.toLowerCase());
  const k = kind === 'Task' ? 'task' : /^https?:\/\//i.test(text) ? 'link' : 'note';
  await run('capture', { kind: k, text, tags }, () => { S.capture = false; });
}
function openCapture() {
  S.capture = !S.capture;
  if (S.capture) kind = 'Note';
  renderMain();
  const box = $('#captureBox');
  if (S.capture && box) box.focus();
}
function captureBox() {
  const close = () => { S.capture = false; renderMain(); };
  const seg = segEl(['Note', 'Task'], kind, (k) => { kind = k; for (const b of seg.children) b.classList.toggle('on', b.textContent === k); });
  const keys = (e) => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); save(); } if (e.key === 'Escape') close(); };
  return h('div', { class: `capture${S.capture ? ' open' : ''}` },
    h('textarea', { id: 'captureBox', onkeydown: keys }),
    h('div', { class: 'crow' }, seg,
      h('input', { id: 'captureTags', placeholder: '#', autocomplete: 'off', spellcheck: 'false', onkeydown: keys }),
      h('button', { class: 'btn primary', onclick: save }, 'Save')));
}

// ---- the daemon's verbs -------------------------------------------------------------------------
// What can be done with a row, and the question a destructive one asks, are the daemon's answer. Rows and the
// pane both carry that list, so a button on a row and the same button in the pane ask the same thing.
const actionOf = (i, verb) => (i.actions || []).find((a) => a.verb === verb);
const fire = (i, a) => (e) => {
  if (a.href) { window.open(a.href, '_blank', 'noopener'); return; }
  const write = () => run(a.verb, { id: i.id }, () => { if (a.removes) drop(i); });
  if (a.confirm) confirmPop(e.currentTarget, a.confirm, write); else write();
};
const rowAct = (i, verb, svg) => { const a = actionOf(i, verb); return a ? [a.label, fire(i, a), svg] : null; };
// Red is for what destroys, which is what the daemon asks about first; a link opens under its own symbol.
function actionEls(i) {
  return h('div', { class: 'actions' }, ...(i.actions || []).map((a) => (a.href
    ? h('button', { title: a.label, class: `ico btn${a.primary ? ' primary' : ''}`, onclick: fire(i, a) }, icon(I.external))
    : h('button', { class: `btn${a.primary ? ' primary' : a.confirm ? ' danger' : ''}`, onclick: fire(i, a) }, a.label))));
}

// ---- rows ---------------------------------------------------------------------------------------
const itemCells = (i) => [
  chk(i),
  i.kind === 'task'
    ? h('span', { class: 'box', style: `--c:${hue(MOD)}`, onclick: (e) => { e.stopPropagation(); flip(i); } })
    : icon(MARK[i.kind] || I.note),
  titleCell(i, undefined, { hideFixed: true }),
  stampCell(i, true),
  acts(i, i.kind === 'task'
    ? [rowAct(i, i.done ? 'reopen' : 'done'), tagAct(i)]
    : [tagAct(i), rowAct(i, 'forget', I.trash)]),
];
// A suggestion is not one of the owner's items: the daemon marks it untaggable, so the tick, ctrl-click, x, t and
// the bulk bar all pass it by, and the cell follows that one flag rather than restating it.
const suggestionCells = (i) => [
  chk(i),
  icon(modOf(MOD).icon),
  titleCell(i, undefined, { hideFixed: true }),
  stampCell(i, true),
  acts(i, [rowAct(i, 'accept'), rowAct(i, 'dismiss')]),
];

// ---- detail -------------------------------------------------------------------------------------
const when = (i) => `${dayLabel(i.when)} ${String(i.when).slice(11, 16)}`.trim();
const stampOf = (i) => (i.when ? dateLine(when(i)) : null);

export default {
  cols: '18px 14px minmax(0,1fr) 70px',
  chips: ['All', 'Tasks', 'Notes', 'Links'],
  serverQuery: true,   // second_brain_fts searches every captured item, so the typed text goes to the daemon
  // New words are a new recall: the list goes back to the first page of what they match.
  async load({ q: typed }) {
    const text = typed || '';
    if (text !== asked) { deep = 0; asked = text; }
    const [left, blank] = await Promise.all([
      get(q(`/api/${MOD}/left`, { query: text, page: deep })),
      get(`/api/${MOD}/blank`)]);
    const items = (left.groups || []).flatMap((g) => g.rows || []);
    return { items: [...(blank.suggestions || []).filter((s) => hits(s, text)), ...items], more: !!left.more };
  },
  filter: (list, chip) => (chip === 'Tasks' ? list.filter((i) => i.kind === 'task')
    : chip === 'Notes' ? list.filter((i) => ['note', 'quote', 'fact'].includes(i.kind))
      : chip === 'Links' ? list.filter((i) => i.kind === 'link') : list),
  groups: (list) => {
    const open = list.filter((i) => i.kind === 'suggestion').sort(newest);
    const rest = list.filter((i) => i.kind !== 'suggestion').sort(newest);
    return [...(open.length ? [{ label: '', rows: open }] : []), ...byDay(rest)];
  },
  cells: (i) => (i.kind === 'suggestion' ? suggestionCells(i) : itemCells(i)),
  rowClass: (i) => (i.done ? 'done dim' : ''),
  tools: (d) => [
    d.more ? h('button', { class: 'btn quiet', onclick: more }, 'More') : null,
    h('button', { title: 'Capture', class: 'ico btn primary', onclick: openCapture }, icon(I.plus)),
  ],
  above: () => captureBox(),
  bulk: (on) => (on.some((i) => i.kind === 'task' && !i.done)
    ? [h('button', { title: 'Done', class: 'ico btn', onclick: () => doneAll(on) }, icon(I.check))]
    : []),
  // An item's text is its title, and the owner's notes run to paragraphs: the first line is the heading and the rest
  // is prose, so a long note reads as a note instead of as one long heading.
  detail: (i) => {
    const text = String(i.title || ''), cut = text.indexOf('\n');
    const head = cut === -1 ? (text.length > 120 ? `${text.slice(0, 120).trimEnd()}…` : text) : text.slice(0, cut);
    const rest = cut === -1 ? (text.length > 120 ? text : '') : text.slice(cut + 1).trim();
    return [h('h2', null, head), stampOf(i), i.kind === 'suggestion' ? null : tagLine(i),
      rest ? h('div', { class: 'prose' }, rest) : null, actionEls(i)];
  },
};
