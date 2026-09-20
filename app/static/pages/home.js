// Home: what waits on the owner, or the newest few of every module. One card per module in rail order;
// the counts strip is the page's summary and core seats it in the header.
import { S, h, icon, modOf, hue, go, chk, titleCell, stampCell, stamp, acts, tagAct, dateLine, tagLine, confirmPop, select, refresh, toast, newest } from '../core.js';
import { get, post } from '../api.js';

const COLS = '18px minmax(0,1fr) 164px';
const RECENT_ROWS = 5;   // what Recent draws per module; /recent returns this many, and the sort cuts anything over
const mode = () => S.seg.home || 'Priority';
// A row from /left already says title and when; the item route of a module not yet ported still says text and stamp.
const words = (i) => i.title || i.text || '';
const when = (i) => i.when || i.stamp || '';

// A row opens in its own module's detail shape, borrowed from that module's page; one without a page falls back below.
const OWNER = {};
async function owners(items) {
  const want = [...new Set(items.map((i) => i.module))].filter((m) => m && m !== 'home' && !(m in OWNER));
  await Promise.all(want.map(async (m) => { try { OWNER[m] = (await import(`./${m}.js`)).default || null; } catch { OWNER[m] = null; } }));
}

// A row carries its group's `waiting` mark, so a row that waits stays apart from one that merely arrived today.
const flat = (d) => ((d && d.groups) || []).flatMap((g) => (g.rows || []).map((r) => ({ ...r, module: r.module || g.module, _waits: !!g.waiting })));
// Both modes hang off one list, so a row keeps its identity when the mode flips and a tag lands on it once.
function merge(left, fresh) {
  const out = [], seen = new Map();
  const add = (list, isNew) => {
    for (const r of list) {
      const key = `${r.module} ${r.id}`, had = seen.get(key);
      if (had) { had._new = had._new || isNew; continue; }
      const row = { ...r, _new: isNew };
      seen.set(key, row); out.push(row);
    }
  };
  add(left, false); add(fresh, true);
  return out;
}

// A verb the owning module offered on this item: a link opens, anything it wants confirmed asks first.
async function run(a, item, anchor) {
  if (a.href) { window.open(a.href, '_blank', 'noopener'); return; }
  const fire = async () => {
    try { await post(`/api/${item.module}/action/${a.verb}`, { id: item.id }); } catch (e) { toast(e.message); return; }
    if (a.removes && String(S.sel) === String(item.id)) select(null);
    await refresh();
  };
  if (a.confirm) confirmPop(anchor, a.confirm, fire); else fire();
}
const btnClass = (a) => `btn${a.primary ? ' primary' : a.confirm || a.removes ? ' danger' : ''}`;
const actionRow = (item) => ((item.actions || []).length
  ? h('div', { class: 'actions' }, ...item.actions.map((a) => h('button', { class: btnClass(a), 'data-tagbtn': a.confirm ? '1' : null, onclick: (e) => run(a, item, e.currentTarget) }, a.label)))
  : null);
const rowActs = (item) => ((item.actions || []).length ? item.actions.map((a) => [a.label, (e) => run(a, item, e.currentTarget)]) : [tagAct(item)]);

export default {
  cols: COLS,
  chips: ['All'],
  seg: ['Priority', 'Recent'],
  async load() {
    const [left, recent, numbers] = await Promise.all([get('/api/home/left'), get('/api/home/recent'), get('/api/home/numbers')]);
    const items = merge(flat(left), flat(recent));
    await owners(items);
    return { items, numbers: numbers || [] };
  },
  filter: (list) => list.filter((i) => (mode() === 'Recent' ? i._new : i._waits)),
  groups(list) {
    const order = ((S.shell && S.shell.modules) || []).map((m) => m.name);
    const ids = [...new Set(list.map((i) => i.module))].sort((a, b) => (order.indexOf(a) + 1 || 99) - (order.indexOf(b) + 1 || 99));
    const recent = mode() === 'Recent';
    return ids.map((id) => {
      const rows = list.filter((i) => i.module === id);
      return { label: modOf(id).title, mod: id, rows: recent ? [...rows].sort(newest).slice(0, RECENT_ROWS) : rows };
    });
  },
  cells: (i) => (mode() === 'Recent'
    ? [chk(i), titleCell(i), h('span', { class: 'r num' }, i.when ? stamp(i.when) : ''), acts(i, [tagAct(i)])]
    : [chk(i), titleCell(i), stampCell(i), acts(i, rowActs(i))]),
  rowClass: (i) => (i.unread === false ? 'dim' : ''),
  tools: (data) => (data.numbers.length
    ? [h('div', { class: 'stat-strip' }, ...data.numbers.map((n) => h('div', { class: 'stat', style: `--c:${hue(n.module)}`, onclick: n.page ? () => go(n.module) : null },
      icon(modOf(n.module).icon), h('span', { class: 'v' }, n.value), h('span', { class: 'l' }, n.label))))]
    : []),
  detail(item, data) {
    const P = OWNER[item.module];
    // Only the module's own answer carries the fields its pane reads; a list row alone would draw them as empty labels.
    if (S.item === item && P && P.detail) { try { const body = P.detail(item, data); if (body) return body; } catch { /* that shape reads its own page's data */ } }
    return [h('h2', null, words(item)), when(item) ? dateLine(stamp(when(item))) : null, tagLine(item), actionRow(item)];
  },
};
