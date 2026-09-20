// Newsfeed: what the nightly searches brought back, by the day they found it. The second view is the searches themselves.
import { S, h, icon, I, chk, titleCell, stampCell, acts, tagAct, tagEl, card, byDay, newest, dayLabel, hue, dateLine, tagLine, confirmPop, toast, refresh, select } from '../core.js';
import { get, post } from '../api.js';

const isSearch = (id) => String(id).startsWith('s');   // a search's row id is s12, an entry's is its bare integer

// Every decision runs the module's own route and the page reloads from the daemon; nothing changes on screen alone.
async function act(verb, id, removes) {
  try { await post(`/api/newsfeed/action/${verb}`, { id }); } catch (e) { toast(e.message); return; }
  if (String(S.sel) === String(id)) { if (removes) select(null); else S.item = null; }   // its buttons follow its status
  await refresh();
}

// The one date an entry is bound to: the day it happens, else the day to come back to it, else the day it was found.
const oneDate = (i) => (i.happens ? dayLabel(i.happens) + (i.happens.length > 10 ? ` ${i.happens.slice(11)}` : '') : dayLabel(i.followUp || i.when));

// The two verbs the item route declares for an open entry. A list row is never fetched one by one, so the page holds
// them here and both the row and the pane fire the same action: one verb, one question, asked the one way.
const OPEN_ACTS = [{ verb: 'accept', label: 'Accept', primary: true }, { verb: 'dismiss', label: 'Dismiss', removes: true }];
const asks = (a) => !!(a.confirm || a.removes);   // anything that ends the entry asks first
const fire = (a, id) => {
  const run = () => act(a.verb, id, a.removes);
  return (e) => (asks(a) ? confirmPop(e.currentTarget, a.confirm || `${a.label}?`, run) : run());
};

// A button the daemon offers: primary in the hue, a link as its symbol.
function actionBtn(i, a) {
  if (a.verb === 'link') return a.href ? h('button', { class: 'btn ico', title: a.label, onclick: () => window.open(a.href, '_blank', 'noopener') }, icon(I.external)) : null;
  return h('button', { class: `btn${a.primary ? ' primary' : asks(a) ? ' danger' : ''}`, onclick: fire(a, i.id) }, a.label);
}

// The pane belongs to the list under it: a search has no row once the control shows entries, and an entry has none
// under the searches, so the view that cannot carry the open row closes it rather than acting on what is off screen.
function sync() {
  if (S.sel === null || S.sel === undefined) return;
  if (((S.seg.newsfeed || 'Entries') === 'Searches') !== isSearch(S.sel)) { S.sel = null; S.selMod = null; S.item = null; S.cursor = -1; }
}

// Killing a search is asked in one place, so the row and the pane end it the same way.
const kill = (s) => (e) => confirmPop(e.currentTarget, `Kill ${s.name}? Its entries stay.`, () => act('kill', s.id, true));

const SCOLS = 'minmax(0,1fr) 112px 100px 110px 74px';
// The standing searches: what each one looks for, how often, how much one run may bring, and the day it next runs.
function searchesView(data) {
  const list = data.searches || [];
  if (!list.length) return h('div', { class: 'empty' }, 'Nothing here yet.');
  return card('', 0, list.map((s) => h('div', { class: `row${String(S.sel) === String(s.id) ? ' sel' : ''}`, style: `--cols:${SCOLS}`, onclick: () => select(s.id) },
    h('span', { class: `t${s.tags.length ? ' with-tags' : ''}` }, h('span', { class: 'title' }, s.name),
      s.tags.length ? h('span', { class: 'tags-inline' }, ...s.tags.map((t) => tagEl(t))) : null),
    h('span', { class: 'c num' }, `every ${s.every_days} d`),
    h('span', { class: 'c num' }, `${s.cap} per run`),
    h('span', { class: 'c num' }, dayLabel(s.next_run)),
    h('span', { class: 'r num', style: s.open ? `color:${hue('newsfeed')}` : null }, s.open ? `${s.open} open` : ''),
    acts(s, [['Kill', kill(s), I.trash]]))));
}

// A search in the pane: the words it looks with, its schedule, its tags, and the button that ends it. The searches
// arrive with the page's own load, so opening one asks the daemon for nothing.
function searchView(id, data) {
  const s = ((data && data.searches) || []).find((x) => String(x.id) === String(id));
  if (!s) return null;
  return [h('h2', null, s.name),
    dateLine(`every ${s.every_days} d · ${s.cap} per run · ${dayLabel(s.next_run)}`),
    h('div', { class: 'tagline' }, h('span', { class: 'tags' }, ...s.tags.map((t) => tagEl(t, { lg: true })))),
    s.prompt ? h('div', { class: 'prose' }, s.prompt) : null,
    h('div', { class: 'actions' }, h('button', { class: 'btn danger', onclick: kill(s) }, 'Kill'))];
}

// An entry in the pane: its headline, its one date, its tags, where it came from, and the buttons the daemon offers.
function entryView(i) {
  const kv = [
    i.search ? [h('dt', null, 'Search'), h('dd', null, i.search)] : null,
    i.url ? [h('dt', null, 'Link'), h('dd', null, h('a', { href: i.url, target: '_blank', rel: 'noopener', style: 'color:var(--ink-2)' }, i.url))] : null,
  ].filter(Boolean);
  const buttons = (i.actions || []).map((a) => actionBtn(i, a)).filter(Boolean);
  return [h('h2', null, i.title), dateLine(oneDate(i)), tagLine(i),
    kv.length ? h('dl', { class: 'kv' }, ...kv) : null,
    i.summary ? h('div', { class: 'prose' }, i.summary) : null,
    buttons.length ? h('div', { class: 'actions' }, ...buttons) : null];
}

export default {
  cols: '18px 8px minmax(0,1fr) 164px', colsSplit: '18px 8px minmax(0,1fr) 150px',
  chips: ['Open', 'Accepted', 'All'],
  seg: ['Entries', 'Searches'],
  async load() {
    const [left, blank] = await Promise.all([get('/api/newsfeed/left'), get('/api/newsfeed/blank')]);
    return { items: left.groups.flatMap((g) => g.rows), searches: blank.searches || [] };
  },
  filter: (list, chip) => { sync(); return chip === 'Open' ? list.filter((i) => i.status === 'open') : chip === 'Accepted' ? list.filter((i) => i.status === 'accepted') : list; },
  groups: (list) => byDay(list.slice().sort(newest)),
  cells: (i) => [chk(i), h('span', { class: `st${i.status === 'open' ? ' open' : ''}`, style: `--c:${hue('newsfeed')}` }), titleCell(i), stampCell(i),
    acts(i, i.status === 'open' ? [...OPEN_ACTS.map((a) => [a.label, fire(a, i.id)]), tagAct(i)] : [tagAct(i)])],
  rowClass: (i) => (i.status === 'open' ? '' : 'dim'),
  alt: (data) => searchesView(data),
  detail: (i, data) => (isSearch(i.id) ? searchView(i.id, data) : entryView(i)),
};
