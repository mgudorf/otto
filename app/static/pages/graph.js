// Graph: the map is the page. A click picks one tag, Ctrl+click adds one, Ctrl+Shift+click removes one, and the
// pick is written to the search bar, so the map and every module's list share one selection. The pane shows what
// carries every selected tag, the tags shared with it, and any of those items previewed in place.
import { S, h, $, I, icon, modOf, allTags, tagEl, card, titleCell, stampCell, dateLine, tagLine, dayLabel, go, select, refresh, renderTop, sendToAgent } from '../core.js';
import { get, q } from '../api.js';
import { md } from '../md.js';
import { graphData, mapEl, neighbours, gsel, gset, gtokens, gclick, gnear } from '../graph.js';

const COLS = 'minmax(0,1fr) 92px 160px minmax(0,1.2fr)';
const RELATED = '18px minmax(0,1fr) 164px';
const mode = () => S.seg.graph || 'Map';
const tags = () => (S.data && S.data.tags) || [];
const key = () => gsel().join(',');
const none = () => S.sel === null || S.sel === undefined;

let asked = null, loaded = null, seenKey = null, seenSel = null;

// core opens the pane for S.sel alone, so S.sel carries what the pane is about: the selected tags, or the item being
// previewed. The tags and the pane are two views of one selection, so whichever of them moved since the last render
// wins: a row the keyboard lands on becomes the selection, and closing the pane drops the preview, then the tags.
function sync() {
  if (S.gpreview) {
    const closed = none();
    if (closed || String(S.sel) !== String(S.gpreview)) { S.gpreview = null; if (closed) S.sel = key() || null; }
  }
  if (!S.gpreview) {
    const k = key();
    if (k !== seenKey || String(S.sel) === String(seenSel)) S.sel = k || null;
    else if (none()) { S.tokens = S.tokens.filter((t) => t.kind !== 'tag'); renderTop(); }
    else if (tags().some((r) => r.id === String(S.sel))) { gtokens([String(S.sel)]); renderTop(); }
    else S.sel = k || null;
  }
  seenKey = key(); seenSel = S.sel;
  if (key() !== loaded && key() !== asked) { asked = key(); refresh(); }   // the selection moved: reload what carries it
}

const nodeRow = (n) => ({ id: n.tag, module: 'graph', title: n.tag, when: n.last_seen, fixed: [], tags: n.tags || [], count: n.count, local: true });

function cells(i) {
  const g = graphData((S.data && S.data.graph) || {});
  const t = allTags().find((x) => x.tag === i.title);
  return [h('span', { class: 't' }, tagEl(i.title)),
    h('span', { class: 'c num' }, `${i.count} item${i.count === 1 ? '' : 's'}`),
    h('span', { class: 'c' }, t ? t.mods.map((m) => modOf(m).title).join(', ') : ''),
    h('span', { class: 'tags' }, ...neighbours(i.title, g.edges).slice(0, 4).map((n) => tagEl(n.tag)))];
}

const ask = () => sendToAgent(`What connects ${gsel().map((t) => `#${t}`).join(' and ')}?`);

// What carries every selected tag, and the tags it shares with them.
function focus(d) {
  const g = graphData(d.graph), sel = gsel(), many = sel.length > 1;
  const { any, all, deg } = gnear(g);
  const fresh = loaded === key();                      // until the daemon answers for this selection, nothing is known
  const items = fresh ? d.carried || [] : [];
  const order = S.shell ? S.shell.modules.map((m) => m.name) : [];
  const mods = [...new Set(items.map((i) => i.module))].sort((a, b) => order.indexOf(a) - order.indexOf(b));
  const shared = [...(many ? all : any)].sort((a, b) => (deg[b] - deg[a]) || a.localeCompare(b));
  const rest = many ? [...any].filter((t) => !all.has(t)).sort() : [];
  const chips = (list) => h('span', { class: 'tags' }, ...list.map((t) => h('button', { class: 'tag lg', onclick: () => gset([...sel, t]) }, t)));
  const row = (o) => h('div', { class: 'row', style: `--cols:${RELATED}`, 'data-id': o.id, onclick: () => { S.gpreview = o.id; select(o.id); } }, h('span'), titleCell(o), stampCell(o));
  return [h('h2', null, sel.map((t) => `#${t}`).join(' and ')),
    h('dl', { class: 'kv' },
      h('dt', null, 'Items'), h('dd', null, items.length ? `${items.length} across ${mods.map((m) => modOf(m).title).join(', ')}` : fresh ? 'none carry all of these' : ''),
      h('dt', null, many ? 'Shared with' : 'Linked with'), h('dd', null, shared.length ? chips(shared) : 'nothing yet'),
      rest.length ? [h('dt', null, 'Near some'), h('dd', null, chips(rest))] : null),
    h('div', { class: 'actions' },
      many ? null : h('button', { class: 'btn', onclick: () => go(`tag:${sel[0]}`, true) }, 'Open as a page'),
      h('button', { class: 'icon-btn', title: 'Ask', onclick: ask }, icon(I.chat))),
    h('div', { class: 'related' }, ...mods.map((m) => card(modOf(m).title, 0, items.filter((o) => o.module === m).slice(0, 8).map(row), m)))];
}

// An item from another module, read here without leaving the map; the head above it already names where it came from.
function preview(o) {
  const text = [o.summary, o.body, o.text, o.snippet].find((v) => typeof v === 'string' && v.trim());
  return [h('h2', null, o.title), o.when ? dateLine(dayLabel(o.when)) : null, tagLine(o), text ? h('div', { class: 'prose', html: md(text) }) : null];
}

// A tag row opened from another page: the node itself, and the way back to the map.
function node(i) {
  const t = allTags().find((x) => x.tag === i.title);
  return [h('h2', null, `#${i.title}`),
    h('dl', { class: 'kv' }, h('dt', null, 'Items'), h('dd', null, String(i.count !== undefined ? i.count : t ? t.count : 0))),
    h('div', { class: 'actions' }, h('button', { class: 'btn', onclick: () => { gset([i.title]); go('graph', true); } }, 'Graph'))];
}

export default {
  cols: COLS,
  chips: ['All'],
  seg: ['Map', 'Browse'],
  async load() {
    seenKey = null; seenSel = null;                                            // fresh data: the tags say what the pane is about
    const sel = gsel(), k = sel.join(',');
    const [graph, found] = await Promise.all([
      get('/api/graph/graph'),
      sel.length ? get(q('/api/items', { tags: k })) : Promise.resolve({ items: [] }),
    ]);
    const carried = (found.items || []).filter((i) => i.module !== 'graph');   // the pane lists what carries the tags elsewhere
    const rows = (graph.nodes || []).map(nodeRow);
    loaded = k; asked = null;
    return { graph, carried, tags: rows, items: [...rows, ...carried] };
  },
  // Both views are drawn whole from the daemon's nodes; the rows path is left to say when there is nothing at all.
  filter: () => { sync(); return tags(); },
  groups: () => [],
  cells,
  above(d) {
    const on = mode() === 'Map' && (d.graph.nodes || []).length > 0;
    queueMicrotask(() => { const l = $('#list'); if (l) l.classList.toggle('map', on); });   // core owns #list; the map fills it
    return on ? mapEl(graphData(d.graph)) : null;
  },
  alt(d) {
    const text = S.q.toLowerCase(), sel = gsel();
    const rows = d.tags.filter((r) => !text || r.title.includes(text));
    if (!rows.length) return h('div', { class: 'empty' }, text ? 'Nothing matches this filter.' : 'Nothing here yet.');
    return card('', 0, rows.map((r) => h('div', { class: `row${sel.includes(r.id) ? ' sel' : ''}${S.picked.has(r.id) ? ' picked' : ''}`, style: `--cols:${COLS}`, 'data-id': r.id, onclick: (e) => gclick(r.id, e) }, ...cells(r))));
  },
  detail(sel, d) {
    if (!d || !d.graph) return node(sel);                                        // another page borrowed this pane
    if (S.gpreview && String(sel.id) === String(S.gpreview)) return preview(sel);
    return focus(d);
  },
};
