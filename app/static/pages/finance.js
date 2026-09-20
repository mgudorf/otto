// Finance: the ledger. One card per kind, the amount on the right, the four totals on the strip.
import { S, $, h, icon, I, hue, money, dayLabel, chk, titleCell, acts, tagAct, tagLine, card, frow, segEl, confirmPop, closePops, toast, refresh, select, renderMain } from '../core.js';
import { get, post, q } from '../api.js';

// The kinds, their order and the word each one goes by are the daemon's; the page keeps no second copy.
const kinds = () => (S.data && S.data.kinds) || [];
const cadences = () => (S.data && S.data.cadences) || [];
const labelOf = (k) => ((S.data && S.data.labels) || {})[k] || k;
const kindOf = (label) => kinds().find((k) => labelOf(k) === label) || null;

const cap1 = (s) => String(s).charAt(0).toUpperCase() + String(s).slice(1);
const plain = (cents) => (Number(cents) / 100).toFixed(2);   // what the amount box holds and the daemon parses back
const todayISO = () => { const d = new Date(); return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`; };
const past = (i) => !!i.due && i.due < todayISO() && !i.ended;
// Ended entries sit last, then the soonest date first, then the undated.
const byDate = (a, b) => (a.ended ? 1 : b.ended ? -1 : (a.due || 'z') < (b.due || 'z') ? -1 : 1);

// A date as the app writes it to the one the daemon stores; '' clears it, null means it is not a date yet.
function isoOf(text) {
  const t = String(text || '').trim();
  if (!t) return '';
  const m = t.match(/^(\d{1,2})-(\d{1,2})-(\d{4})$/);
  return m ? `${m[3]}-${m[1].padStart(2, '0')}-${m[2].padStart(2, '0')}` : null;
}

// One box over the button that asked for it, built like the shell's own confirm.
function askPop(anchor, value, onok) {
  closePops();
  anchor.setAttribute('data-tagbtn', '1');   // the click that opened this must not also close it
  const take = () => { closePops(); onok(inp.value); };
  const inp = h('input', { value, spellcheck: 'false', onkeydown: (e) => { if (e.key === 'Enter') take(); if (e.key === 'Escape') closePops(); } });
  const pop = h('div', { class: 'pop pin-pop', id: 'tagPop' }, inp, h('button', { class: 'btn primary', onclick: take }, icon(I.check)));
  document.body.append(pop);
  const r = anchor.getBoundingClientRect();
  pop.style.left = `${Math.max(8, Math.min(r.left, innerWidth - 310))}px`;
  pop.style.top = `${r.bottom + 6}px`;
  inp.focus();
  inp.select();
}

// Every write is one of the module's actions; the page then reloads what the daemon holds.
async function run(verb, item, body) {
  try { await post(`/api/finance/action/${verb}`, { id: item.id, ...body }); } catch (e) { toast(e.message); return; }
  S.item = null;
  await refresh();
}

// A blank box or an amount that will not parse comes back as the daemon's own message, as the capture box's does.
const amountBox = (anchor, item) => askPop(anchor, plain(item.amount), (v) => run('update', item, { amount: v.trim() }));
const dateBox = (anchor, item) => askPop(anchor, item.due_on ? dayLabel(item.due_on) : '', (v) => {
  const on = isoOf(v);
  if (on === null) { toast('MM-DD-YYYY'); return; }
  run('due', item, { due_on: on });
});

// The pane offers what the daemon says it offers: the amount and the date open a box, anything that removes asks first.
function actionBtn(a, item) {
  const cls = a.primary ? 'btn primary' : a.confirm || a.removes ? 'btn danger' : 'btn';
  const fire = (e) => {
    const b = e.currentTarget;
    if (a.href) { window.open(a.href, '_blank', 'noopener'); return; }
    if (a.verb === 'update') { amountBox(b, item); return; }
    if (a.verb === 'due') { dateBox(b, item); return; }
    if (a.confirm || a.removes) { confirmPop(b, a.confirm || `${a.label}?`, () => { if (a.removes) select(null); run(a.verb, item, {}); }); return; }
    run(a.verb, item, {});
  };
  return h('button', { class: cls, onclick: fire }, a.label);
}

// ---- capture ------------------------------------------------------------------------------------
// The box opens empty every time: a draft never outlives the box that held it.
const newEntry = () => ({ kind: kinds()[0] || '', name: '', amount: '', cadence: cadences()[0] || '', due: '', note: '' });
let entry = newEntry();

function openCapture() {
  S.capture = !S.capture;
  if (S.capture) entry = newEntry();
  renderMain();
  if (S.capture) setTimeout(() => { const el = $('#capName'); if (el) el.focus(); }, 0);
}

async function save() {
  const body = { kind: entry.kind, name: entry.name.trim(), amount: entry.amount.trim() };
  if (entry.kind === 'recurring' || entry.kind === 'budget') body.cadence = entry.cadence;
  if (entry.kind === 'recurring') {
    const on = isoOf(entry.due);
    if (on === null) { toast('MM-DD-YYYY'); return; }
    body.due_on = on;
  }
  if (entry.note.trim()) body.note = entry.note.trim();
  // A missing name or an amount that is not a number comes back as the daemon's own message, the way Settings' fields do.
  try { await post('/api/finance/action/capture', body); } catch (e) { toast(e.message); return; }
  entry = newEntry();
  S.capture = false;
  await refresh();
}

const onKey = (e) => { if (e.key === 'Enter') save(); if (e.key === 'Escape') { S.capture = false; entry = newEntry(); renderMain(); } };
const BOX = 'height:28px;padding:0 8px;border:1px solid var(--line-strong);border-radius:6px;background:var(--surface)';
const field = (key, attrs) => h('input', { value: entry[key], spellcheck: 'false', oninput: (e) => { entry[key] = e.target.value; }, onkeydown: onKey, ...attrs });

// A new entry is a small form, each field named on its left by the shell's own form row, as Settings names its own.
// Nothing here tells the owner what to type; the name of the field is what the field is.
function captureBox(d) {
  const priced = entry.kind === 'recurring' || entry.kind === 'budget';
  return h('div', { class: `capture${S.capture ? ' open' : ''}` },
    h('div', { class: 'form' },
      frow('Kind', segEl((d.kinds || []).map(cap1), cap1(entry.kind), (o) => { entry.kind = o.toLowerCase(); renderMain(); })),
      frow('Name', field('name', { id: 'capName', style: `${BOX};flex:1 1 220px;min-width:0` })),
      frow('Amount', field('amount', { class: 'num', style: `${BOX};flex:0 0 116px;text-align:right` })),
      priced ? frow('Cadence', segEl((d.cadences || []).map(cap1), cap1(entry.cadence), (o) => { entry.cadence = o.toLowerCase(); renderMain(); })) : null,
      entry.kind === 'recurring' ? frow('Date', field('due', { class: 'num', style: `${BOX};flex:0 0 140px;text-align:right` })) : null,
      frow('Note', field('note', { style: `${BOX};flex:1 1 260px;min-width:0` }))),
    h('div', { class: 'crow' }, h('span', { style: 'flex:1' }), h('button', { class: 'btn primary', onclick: save }, icon(I.check))));
}

// ---- the page -----------------------------------------------------------------------------------
const page = {
  cols: '18px minmax(0,1fr) 92px 148px 156px',
  colsSplit: '18px minmax(0,1fr) 0px 0px 150px',
  chips: ['All'],   // the kinds join them once the daemon has named them
  serverQuery: true,   // the daemon reads an entry's note, which a row never carries, so the typed text goes to it
  // The ledger is small: the daemon answers with every entry the words reach, so nothing is held back.
  async load({ q: typed }) {
    const [left, blank] = await Promise.all([
      get(q('/api/finance/left', { query: typed || '' })),
      get('/api/finance/blank')]);
    page.chips = ['All', ...(blank.kinds || []).map((k) => (blank.labels || {})[k] || k)];
    return { items: (left.groups || []).flatMap((g) => g.rows), ...blank };
  },
  filter: (list, chip) => { const k = kindOf(chip); return k ? list.filter((i) => i.kind === k) : list; },
  groups: (list) => kinds().map((k) => ({ label: labelOf(k), rows: list.filter((i) => i.kind === k).sort(byDate) })).filter((g) => g.rows.length),
  cells: (i) => [chk(i), titleCell(i, undefined, { hideFixed: true }), h('span', { class: 'c' }, i.cadence || ''),
    h('span', { class: 'c num', style: past(i) ? 'color:var(--danger)' : null }, i.ended ? dayLabel(i.ended) : i.due ? dayLabel(i.due) : ''),
    h('span', { class: 'r strong num' }, money(i.amount)),
    acts(i, [['Update', (e) => amountBox(e.currentTarget, i)], tagAct(i)])],
  rowClass: (i) => (i.ended ? 'done dim' : ''),
  tools: () => [h('button', { title: 'New entry', class: 'ico btn primary', onclick: openCapture }, icon(I.plus))],
  above: (d) => captureBox(d),
  summary: (d) => h('div', { class: 'stat-strip' }, ...[[d.totals.accounts, 'accounts'], [d.totals.holdings, 'holdings'], [d.totals.monthly_recurring, 'recurring per month'], [d.totals.monthly_budget, 'budget per month']]
    .map(([c, l]) => h('div', { class: 'stat money', style: `--c:${hue('finance')}` }, h('span', { class: 'v' }, money(c)), h('span', { class: 'l' }, l)))),
  detail: (i) => [
    h('h2', null, i.title),
    h('div', { class: 'amount num' }, money(i.amount)),
    i.ended || i.due ? h('div', { class: 'stamp num', style: past(i) ? 'color:var(--danger)' : null }, dayLabel(i.ended || i.due)) : null,
    tagLine(i),
    i.cadence ? h('dl', { class: 'kv' }, h('dt', null, 'Cadence'), h('dd', null, i.cadence)) : null,
    i.note ? h('div', { class: 'prose' }, i.note) : null,
    i.history && i.history.length ? h('div', { class: 'related' }, card('', 0, i.history.map((p) => h('div', { class: 'row', style: '--cols: minmax(0,1fr) 124px' },
      h('span', { class: 'c num', style: 'color:var(--ink)' }, money(p.amount)), h('span', { class: 'r num' }, dayLabel(p.ts)))))) : null,
    i.actions ? h('div', { class: 'actions' }, ...i.actions.map((a) => actionBtn(a, i))) : null,
  ],
};

export default page;
