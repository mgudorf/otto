// Email: the inbox as one dense list — a dot, the star, the sender, the subject with its tags, the time, and
// Archive, Tag and Trash where the pointer is. A chip narrows the whole mailbox, so changing one reloads the list.
import { S, h, icon, I, chk, titleCell, stampCell, acts, tagAct, byDay, newest, dayLabel, dateLine, tagLine, confirmPop, toast, refresh, select } from '../core.js';
import { get, post, q } from '../api.js';


const CHIP = { Unread: (i) => i.unread, Flagged: (i) => i.starred, Priority: (i) => i.priority === 'high' };
let want = null;          // the chip the list in hand, or the one still on the way, was asked for
const marked = new Set(); // messages this window has already marked read by opening them

// A press on a row is what opens a message; the keyboard walks the list, and walking past a message must not write
// to Gmail. Only a release on the row the press started on names that row, the pane that draws it spends the name,
// and the click ending the gesture takes back whatever the pane did not — so nothing stays armed for a keystroke.
let down = null, pressed = null;
const rowId = (t) => {
  const row = t && t.closest && t.closest('#list .row[data-id]');
  return row && !t.closest('.acts, .chk') ? row.dataset.id : null;
};
document.addEventListener('pointerdown', (e) => { down = rowId(e.target); pressed = null; }, true);
document.addEventListener('pointerup', (e) => { pressed = down !== null && rowId(e.target) === down ? down : null; down = null; }, true);
document.addEventListener('pointercancel', () => { down = pressed = null; }, true);
document.addEventListener('click', () => { pressed = null; });

const setting = (k, fallback) => (S.shell && S.shell.settings && S.shell.settings[k] !== undefined ? S.shell.settings[k] : fallback);
// core keeps its clock to itself, so the pane spells the hour the way the row's stamp beside it does.
const clock = (s) => {
  const hm = String(s).slice(11, 16);
  if (setting('ui.time_format', '24h') !== '12h' || hm.length < 5) return hm;
  const hr = Number(hm.slice(0, 2));
  return `${((hr + 11) % 12) + 1}:${hm.slice(3)} ${hr < 12 ? 'am' : 'pm'}`;
};

// A verb the daemon owns: run it, take the list again, and close the pane if what it stood on is gone.
async function act(verb, target) {
  const body = target === undefined ? {} : Array.isArray(target) ? { ids: target.map((i) => i.id) } : { id: target.id };
  try { await post(`/api/email/action/${verb}`, body); } catch (e) { toast(e.message); return; }
  if (Array.isArray(target)) S.picked.clear();
  await refresh();
  const here = (S.data && S.data.items) || [];
  if (S.sel !== null && !here.some((i) => String(i.id) === String(S.sel))) select(null);
}

// Opening a message is what marks it read, when the knob says so. It never closes the pane it just opened,
// even when reading the message drops it out of the open chip.
function readOnOpen(item, data) {
  if (!data.readOnOpen || !item.unread || marked.has(item.id)) return;
  marked.add(item.id);
  post('/api/email/action/read', { id: item.id }).then(refresh).catch((e) => toast(e.message));
}

// The verbs the daemon offers this message, and nothing else: the primary one in the hue, a confirming one in red.
function actionBtn(item, a) {
  if (a.href) return h('button', { title: a.label, class: 'ico btn', onclick: () => window.open(a.href, '_blank', 'noopener') }, icon(I.external));
  const run = () => act(a.verb, item);
  const cls = `btn${a.primary ? ' primary' : a.confirm || a.removes ? ' danger' : ''}`;
  return h('button', { class: cls, onclick: (e) => (a.confirm ? confirmPop(e.currentTarget, a.confirm, run) : run()) }, a.label);
}

export default {
  cols: '18px 8px 14px 184px minmax(0,1fr) 70px',
  colsSplit: '18px 8px 14px 0px minmax(0,1fr) 64px',
  chips: ['All', 'Unread', 'Flagged', 'Priority'],

  // The list belongs to the chip it was asked for, so a chip changed while the request was out asks again rather
  // than leaving the wrong mailbox on screen.
  async load() {
    let chip, d;
    do {
      chip = want = S.chip.email || 'All';
      d = await get(q('/api/email/left', { chip }));
    } while (chip !== (S.chip.email || 'All'));
    return { items: d.groups.flatMap((g) => g.rows), readOnOpen: !!d.read_on_open };
  },

  // The daemon narrows the whole mailbox, so a chip it has not served yet asks for its own list.
  filter(list, chip) {
    if (chip !== want) { want = chip; refresh(); }
    return CHIP[chip] ? list.filter(CHIP[chip]) : list;
  },

  groups: (list) => byDay([...list].sort(newest)),

  cells: (i) => [
    chk(i),
    h('span', { class: 'st' }),
    icon(I.star, `star ic${i.starred ? ' on' : ''}`),
    h('span', { class: 'c', style: i.unread ? 'color:var(--ink);font-weight:500' : null }, S.sel ? '' : i.from),
    titleCell(i, S.sel ? `${i.from}, ${i.title}` : undefined),
    stampCell(i, true),
    acts(i, [
      ['Archive', () => act('archive', i), I.archive],
      tagAct(i),
      ['Trash', (e) => confirmPop(e.currentTarget, 'Trash this message?', () => act('trash', i)), I.trash],
    ]),
  ],
  rowClass: (i) => (i.unread ? 'unread' : 'dim'),

  tools: () => [h('button', { class: 'btn quiet', onclick: () => act('sync') }, 'Sync now')],

  bulk: (picked) => [
    h('button', { title: 'Archive', class: 'ico btn', onclick: () => act('archive', picked) }, icon(I.archive)),
    h('button', { title: 'Trash', class: 'ico btn danger', onclick: (e) => confirmPop(e.currentTarget, `Trash ${picked.length} messages?`, () => act('trash', picked)) }, icon(I.trash)),
  ],

  detail(i, data) {
    const opened = pressed !== null && String(pressed) === String(i.id);
    pressed = null;
    if (opened) readOnOpen(i, data);
    const attached = i.attachments || [];
    // A field the message does not carry is not drawn: a row core has not loaded yet is a bare id.
    const kv = [
      i.from ? [h('dt', null, 'From'), h('dd', null, i.from)] : null,
      i.priority ? [h('dt', null, 'Priority'), h('dd', null, h('span', { class: `prio ${i.priority}` }, i.priority, i.reason ? `, ${i.reason}` : ''))] : null,
      attached.length ? [h('dt', null, 'Attached'), h('dd', null, icon(I.clip, 'ic'), ' ', attached.join(', '))] : null,
    ].filter(Boolean);
    return [
      h('h2', null, i.title),
      i.when ? dateLine([dayLabel(i.when), clock(i.when)].filter(Boolean).join(' ')) : null,
      tagLine(i),
      kv.length ? h('dl', { class: 'kv' }, ...kv) : null,
      i.html ? h('div', { class: 'prose mail', html: i.html }) : i.body ? h('div', { class: 'prose' }, i.body) : null,
      (i.actions || []).length ? h('div', { class: 'actions' }, ...i.actions.map((a) => actionBtn(i, a))) : null,
    ];
  },
};
