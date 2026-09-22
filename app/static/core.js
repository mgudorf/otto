// Core: state, DOM helpers, the search bar and its tokens, the feed, the open item as a card of what it relates to and a
// page of what it says, the layouts, the verbs a facet allows, tags, and the frames the other parts fill. The brain, the
// drawer, point mode and the shell register here.
import { get, post, q, inflight } from './api.js';

// The shape of the app, answered once by the daemon: every module by name, the facets in the order the feed groups them,
// and which module owns each. They are filled in place, so every part that imported them stays in step.
export const MODS = {}, FIXED_MOD = {}, ORDER = [], FIXED_ORDER = [], ITEMS = [], CATALOG = [];

export const S = {
  mode: 'Priority', tokens: [], q: '', open: null, cursor: -1, zone: 'feed', gcursor: -1, picked: new Set(), tagsOpen: new Set(), qtoggle: new Set(), view: 'brain',
  edit: null, nav: 'open', chat: 'open', point: false, pointRef: null,
  pins: [],   // plain tags given a numbered callout of their own on the brain
  // Shares of the width. The big panel, the brain on the left or the page on the right, takes what the cards and the drawer leave.
  layout: { feed: 30, drawer: 20, turn: 20 },   // turn: minutes per revolution of the brain, 0 holds it still
};

// ---- DOM ------------------------------------------------------------------------------------------
export const $ = (s, el = document) => el.querySelector(s);
export function put(el, ...kids) { if (el) el.replaceChildren(...kids.flat(Infinity).filter((k) => k !== null && k !== undefined && k !== false)); }
export function h(tag, attrs, ...kids) {
  const el = document.createElement(tag);
  if (attrs) for (const [k, v] of Object.entries(attrs)) {
    if (v === null || v === undefined || v === false) continue;
    if (k === 'class') el.className = v;
    else if (k === 'style') el.style.cssText = v;
    else if (k.startsWith('on')) el.addEventListener(k.slice(2), v);
    else if (k === 'html') el.innerHTML = v;
    else el.setAttribute(k, v === true ? '' : v);
  }
  for (const kid of kids.flat(Infinity)) if (kid !== null && kid !== undefined && kid !== false) el.append(kid.nodeType ? kid : document.createTextNode(String(kid)));
  return el;
}
export function esc(s) { return String(s).replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c])); }
export const icon = (svg, cls = 'ic') => h('span', { class: cls, html: `<svg viewBox="0 0 20 20" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round">${svg || ''}</svg>` });
export const I = {
  search: '<circle cx="9" cy="9" r="5.5"></circle><path d="M13 13l4 4"></path>',
  chat: '<path d="M4 4h12v9H9l-4 3v-3H4Z"></path>',
  close: '<path d="M5 5l10 10M15 5L5 15"></path>',
  sun: '<circle cx="10" cy="10" r="3.5"></circle><path d="M10 2.5v2M10 15.5v2M2.5 10h2M15.5 10h2M4.7 4.7l1.4 1.4M13.9 13.9l1.4 1.4M4.7 15.3l1.4-1.4M13.9 6.1l1.4-1.4"></path>',
  moon: '<path d="M16 12.5A6.5 6.5 0 0 1 7.5 4a6.5 6.5 0 1 0 8.5 8.5Z"></path>',
  cmd: '<path d="M7 7h6v6H7z"></path><path d="M7 7H5a2 2 0 1 1 2-2v2M13 7h2a2 2 0 1 0-2-2v2M7 13H5a2 2 0 1 0 2 2v-2M13 13h2a2 2 0 1 1-2 2v-2"></path>',
  up: '<path d="M6 12l4-4 4 4"></path>', down: '<path d="M6 8l4 4 4-4"></path>', check: '<path d="M4 10l4 4 8-8"></path>',
  tag: '<path d="M3 3h6l8 8-6 6-8-8z"></path><circle cx="6.5" cy="6.5" r="1"></circle>',
  layout: '<rect x="3" y="4" width="14" height="12" rx="2"></rect><path d="M8 4v12M13 4v12"></path>',
  target: '<circle cx="4.5" cy="10" r="2.6"></circle><path d="M8.7 7v6M11.3 7v6"></path><circle cx="15.5" cy="10" r="2.6"></circle>',
};
let toastT;
export function toast(msg) { const t = $('#toast'); if (!t) return; t.textContent = msg; t.classList.add('on'); clearTimeout(toastT); toastT = setTimeout(() => t.classList.remove('on'), 2000); }

// ---- facets, types, dates, tags -----------------------------------------------------------------------
const NEUTRAL = '#8B92A1';
export const modOf = (id) => MODS[id] || { id, title: id, hue: NEUTRAL, icon: '' };
export const hue = (m) => modOf(m && typeof m === 'object' ? m.id : m).hue;   // a name, a module, or nothing yet
export const isFixed = (t) => FIXED_MOD[t] !== undefined;
export const fixedIcon = (t) => modOf(FIXED_MOD[t] || 'otto').icon;
export const markIcon = (i) => modOf(i.module).icon;
export const itemOf = (id) => ITEMS.find((i) => String(i.id) === String(id)) || null;
export const currentItem = () => (S.open === null ? null : itemOf(S.open));
const day = (d) => `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
const TODAY = day(new Date()), YESTERDAY = day(new Date(Date.now() - 864e5));
export const dayLabel = (s) => { const [y, m, d] = String(s).slice(0, 10).split('-'); return `${m}-${d}-${y}`; };
export const relDay = (s) => { const d = String(s).slice(0, 10); return d === TODAY ? 'Today' : d === YESTERDAY ? 'Yesterday' : dayLabel(d); };
// One clock for the whole page, so the owner's 12-hour setting reaches every time shown.
export const clock = (s) => {
  const hm = String(s).slice(11, 16);
  if (!S.shell || S.shell.settings['ui.time_format'] !== '12h') return hm;
  const [h, m] = hm.split(':').map(Number);
  return `${((h + 11) % 12) + 1}:${String(m).padStart(2, '0')} ${h < 12 ? 'am' : 'pm'}`;
};
export const stamp = (s) => (String(s).slice(0, 10) === TODAY ? clock(s) : dayLabel(s));
export const tagsOf = (i) => [...(i.fixed || []), ...(i.tags || [])];
// What the feed holds, topped up with every other tag the daemon knows, so the search bar offers more than one page of rows.
export function allTags() {
  const n = {};
  for (const i of ITEMS) for (const t of tagsOf(i)) n[t] = (n[t] || 0) + 1;
  for (const c of CATALOG) if (!n[c.tag]) n[c.tag] = c.count;
  return Object.entries(n).map(([tag, count]) => ({ tag, count })).sort((a, b) => b.count - a.count || a.tag.localeCompare(b.tag));
}
const tagOn = (t) => S.tokens.some((k) => k.kind === 'tag' && k.value === t);
export function tagEl(tag, { fixed, lg } = {}) {
  return h('button', { class: `tag${fixed ? ' fixed' : ''}${lg ? ' lg' : ''}${tagOn(tag) ? ' on' : ''}`, style: fixed && isFixed(tag) ? `--c:${fixedIcon(tag) && hue(FIXED_MOD[tag])}` : null, onclick: (e) => { e.stopPropagation(); addToken('tag', tag); } }, tag);
}
export function tagList(i, { max = 4, lg = false } = {}) {
  const all = [...(i.fixed || []).map((t) => ({ t, fixed: true })), ...(i.tags || []).map((t) => ({ t, fixed: false }))];
  const open = S.tagsOpen.has(i.id);
  const els = (open ? all : all.slice(0, max)).map(({ t, fixed }) => tagEl(t, { fixed, lg }));
  if (all.length > max) els.push(h('button', { class: `tag more${lg ? ' lg' : ''}`, onclick: (e) => { e.stopPropagation(); if (open) S.tagsOpen.delete(i.id); else S.tagsOpen.add(i.id); renderFeed(); } }, open ? 'less' : `+${all.length - max}`));
  return els;
}

// ---- the parts that register --------------------------------------------------------------------------
let drawer = null, pointer = null, brain = null, shell = null;
export const call = (obj, name, ...args) => (obj && typeof obj[name] === 'function' ? obj[name](...args) : undefined);
export function registerDrawer(impl) { drawer = impl; }
export function registerPoint(impl) { pointer = impl; }
export function registerBrain(impl) { brain = impl; }
export function registerShell(impl) { shell = impl; }
export const parts = () => ({ drawer, pointer, brain, shell });
export function openDrawer() { if (S.chat !== 'open') { S.chat = 'open'; renderTop(); renderChat(); } }
export function toggleChat() { S.chat = S.chat === 'open' ? 'closed' : 'open'; renderTop(); renderChat(); }
// Brain mode is the brain on the left of the cards; Inspect mode is the page on the right of them. `[` swaps them.
export function toggleView(v) { S.view = v || (S.view === 'brain' ? 'inspect' : 'brain'); renderAll(); }
export function askAgent(draft) { openDrawer(); if (draft !== undefined) call(drawer, 'setDraft', draft); call(drawer, 'focus'); }
export function sendToAgent(text) { openDrawer(); call(drawer, 'setDraft', text); return call(drawer, 'send'); }
export function togglePoint(on) {
  if (!pointer) return;
  S.point = on === undefined ? !S.point : !!on;
  const btn = $('#pointBtn'); if (btn) btn.setAttribute('aria-pressed', S.point);
  call(pointer, 'toggle', S.point);
}
export const dark = () => document.documentElement.dataset.look === 'dark';
export function setLook(t) {
  if (t === 'dark') document.documentElement.dataset.look = 'dark'; else delete document.documentElement.dataset.look;
  try { localStorage.setItem('otto-look', t); } catch { /* private window */ }
  renderAll();
}

// ---- layouts: one big panel, the brain on the left in Brain mode or the page on the right in Inspect mode, the same size ---------
export function applyLayout() {
  const L = S.layout, inspect = S.view === 'inspect', drawerShare = S.chat === 'open' ? L.drawer : 0, big = 100 - L.feed - drawerShare;
  const app = $('#app');
  app.style.gridTemplateColumns = `minmax(0, ${inspect ? 0 : big}fr) minmax(0, ${L.feed}fr) minmax(0, ${inspect ? big : 0}fr) minmax(0, ${drawerShare}fr)`;
  app.dataset.view = S.view;
}
export function savePins() { try { localStorage.setItem('otto-pins', JSON.stringify(S.pins)); } catch { /* private window */ } }
export function saveLayout() { try { localStorage.setItem('otto-layout', JSON.stringify(S.layout)); } catch { /* private window */ } }


// ---- what the daemon says -------------------------------------------------------------------------------
// The shell is the facets: every module that carries one lists rows, takes a place on the brain and heads a group in the
// feed. Modules without one (the feed's own, the graph, feedback) never appear.
export async function loadShell() {
  const sh = await get('/api/shell');
  Object.assign(MODS, { otto: { id: 'otto', title: 'Otto', hue: NEUTRAL, icon: I.target } });
  ORDER.length = 0; FIXED_ORDER.length = 0;
  for (const m of sh.modules.filter((m) => m.enabled !== false).sort((a, b) => a.order - b.order)) {
    MODS[m.name] = { id: m.name, title: m.title, hue: m.hue, icon: m.icon };
    ORDER.push(m.name);
    if (m.facet) { FIXED_ORDER.push(m.facet); FIXED_MOD[m.facet] = m.name; }
  }
  S.shell = sh;
}
// Every module's rows in one list: what waits carries `waits` and ranks Priority, everything else is Recent. Both modes
// read this one set, so narrowing never costs a round trip and the brain always sees every tag the feed holds.
const key = (r) => `${r.module}/${r.id}`;
export async function load() {
  const [recent, waiting] = await Promise.all([get(q('/api/feed', { mode: 'recent', limit: 200 })), get(q('/api/feed', { mode: 'priority' }))]);
  const by = new Map();
  for (const r of recent.items) by.set(key(r), r);
  for (const r of waiting.items) { const had = by.get(key(r)); if (had) had.waits = r.waits; else by.set(key(r), r); }
  for (const i of ITEMS) { const fresh = by.get(key(i)); if (fresh && i.full) Object.assign(fresh, i, { tags: fresh.tags, waits: fresh.waits }); }   // keep what a page already fetched
  ITEMS.splice(0, ITEMS.length, ...by.values());
  S.synced = new Date();
  try { const cat = await get('/api/tags'); CATALOG.splice(0, CATALOG.length, ...cat); } catch { /* the feed's own tags will do */ }
  renderAll();
}
// A row says what the row shows; the page needs the whole item, which only the module that owns it can answer for.
async function fill(i) {
  if (!i || i.full) return;
  try { Object.assign(i, await get(`/api/${i.module}/item/${encodeURIComponent(i.id)}`), { full: true }); renderPage(); renderFeed(); } catch { /* the row is all there is */ }
}

// ---- tokens: the search bar's grammar, which narrows the feed and lights the brain -------------------------
export const itemText = (i) => [i.title, i.snip, i.body, i.status, ...tagsOf(i)].filter(Boolean).join(' ').toLowerCase();
export function matches(i) {
  for (const t of S.tokens) {
    if (t.kind === 'tag' && !tagsOf(i).includes(t.value)) return false;
    if (t.kind === 'mod' && i.module !== t.value) return false;
    if (t.kind === 'filter') {
      const v = t.value.split(':')[1];
      if (v === 'unread' && !i.unread) return false;
      if (v === 'open' && (i.done || i.status === 'accepted' || i.status === 'dismissed')) return false;
      if (v === 'done' && !(i.done || i.pct === 100 || i.status === 'accepted')) return false;
      if (v === 'starred' && !i.starred) return false;
    }
  }
  if (S.q && !itemText(i).includes(S.q.toLowerCase())) return false;
  return true;
}
export const newest = (a, b) => ((a.when || '') < (b.when || '') ? 1 : -1);
// The feed: what waits, by urgency, or everything, newest first; both narrowed by the tokens and the typed text.
export function visible() {
  let list = ITEMS.filter(matches);
  if (S.mode === 'Priority') list = list.filter((i) => i.waits).sort((a, b) => a.waits - b.waits);
  else list = list.sort(newest);   // an undated row sorts last rather than falling out
  return list;
}
export function groupsOf(list) {
  return FIXED_ORDER.map((f) => ({ label: f, mod: FIXED_MOD[f], rows: list.filter((i) => (i.fixed || [])[0] === f) })).filter((g) => g.rows.length);
}
export function addToken(kind, value) {
  if (S.tokens.some((t) => t.kind === kind && t.value === value)) return;
  if (kind === 'mod') S.tokens = S.tokens.filter((t) => t.kind !== 'mod');
  if (kind === 'tag' && isFixed(value)) S.tokens = S.tokens.filter((t) => !(t.kind === 'tag' && isFixed(t.value)));   // one facet at a time
  S.tokens.push({ kind, value });
  S.cursor = -1;
  remember(true); renderAll();
}
export function removeToken(i) { S.tokens.splice(i, 1); remember(true); renderAll(); }
export function clearTokens() { S.tokens = []; S.q = ''; const inp = $('#omniInput'); if (inp) inp.value = ''; remember(true); renderAll(); }
export function setTokens(tokens) { S.tokens = tokens.map((t) => ({ ...t })); S.cursor = -1; remember(true); renderAll(); }
function parseToken(word) {
  if (word.startsWith('#') && word.length > 1) return { kind: 'tag', value: word.slice(1).toLowerCase() };
  if (word.startsWith('@') && word.length > 1) { const w = word.slice(1).toLowerCase(); const m = ORDER.map(modOf).find((m) => m.id.startsWith(w) || m.title.toLowerCase().startsWith(w)); return m ? { kind: 'mod', value: m.id } : null; }
  if (/^is:(unread|open|done|starred)$/.test(word)) return { kind: 'filter', value: word.toLowerCase() };
  return null;
}
export const tokenText = (t) => (t.kind === 'tag' ? `#${t.value}` : t.kind === 'mod' ? `@${modOf(t.value).title}` : t.value);
function renderTokens() {
  put($('#tokens'), ...S.tokens.map((t, i) => h('span', { class: t.kind === 'tag' ? `token tag${isFixed(t.value) ? ' fixed' : ''}` : t.kind === 'mod' ? 'token mod' : 'token', style: t.kind === 'mod' ? `--c:${hue(t.value)}` : t.kind === 'tag' && isFixed(t.value) ? `--c:${hue(FIXED_MOD[t.value])}` : null },
    t.kind === 'tag' ? t.value : tokenText(t), h('button', { title: 'Remove', onclick: () => removeToken(i) }, '×'))));
}
let omniRows = [], omniCursor = 0, omniKey = '';
function omniSuggest() {
  const inp = $('#omniInput'), pop = $('#omniPop');
  const w = inp.value.trim().split(/\s+/).pop() || '';
  let rows = [];
  if (w.startsWith('#')) rows = allTags().filter((t) => t.tag.startsWith(w.slice(1).toLowerCase())).slice(0, 8).map((t) => ({ label: `#${t.tag}`, sub: `${t.count} items`, tok: { kind: 'tag', value: t.tag } }));
  else if (w.startsWith('@')) rows = ORDER.map(modOf).filter((m) => m.title.toLowerCase().startsWith(w.slice(1).toLowerCase())).slice(0, 8).map((m) => ({ label: `@${m.title}`, sub: 'facet', c: m.hue, tok: { kind: 'mod', value: m.id } }));
  else if (w.includes(':') || w === 'is') rows = ['is:unread', 'is:open', 'is:done', 'is:starred'].filter((f) => f.startsWith(w)).map((f) => ({ label: f, sub: 'filter', tok: { kind: 'filter', value: f } }));
  omniRows = rows;
  const key = rows.map((r) => r.label).join('|');
  if (key !== omniKey) { omniKey = key; omniCursor = 0; }
  if (!rows.length) { pop.hidden = true; return; }
  const r = inp.getBoundingClientRect();
  pop.style.left = `${Math.max(8, r.left - 30)}px`; pop.style.top = `${r.bottom + 8}px`; pop.hidden = false;
  put(pop, ...rows.map((row, i) => h('div', { class: `pi${i === omniCursor ? ' on' : ''}`, onmousedown: (e) => { e.preventDefault(); omniPick(row); } },
    row.c ? h('span', { style: `width:8px;height:8px;border-radius:50%;background:${row.c}` }) : null, row.label, h('span', { class: 'sub' }, row.sub))));
}
function omniPick(row) {
  const inp = $('#omniInput');
  if (!row) return;
  inp.value = inp.value.replace(/\S+$/, ''); S.q = inp.value.trim();
  $('#omniPop').hidden = true; omniRows = []; omniKey = '';
  addToken(row.tok.kind, row.tok.value);
  inp.focus();
}
export function bindOmni() {
  const inp = $('#omniInput');
  inp.addEventListener('input', () => { S.q = inp.value.trim(); S.cursor = -1; omniSuggest(); renderFeed(); call(brain, 'sync'); });
  inp.addEventListener('keydown', (e) => {
    e.stopPropagation();
    const pop = $('#omniPop');
    if (!pop.hidden && omniRows.length) {
      if (e.key === 'ArrowDown' || e.key === 'ArrowUp') { e.preventDefault(); omniCursor = (omniCursor + (e.key === 'ArrowDown' ? 1 : omniRows.length - 1)) % omniRows.length; omniSuggest(); return; }
      if (e.key === 'Enter' || e.key === 'Tab') { e.preventDefault(); omniPick(omniRows[omniCursor]); return; }
    }
    if (e.key === 'Escape') { inp.value = ''; pop.hidden = true; clearTokens(); inp.blur(); return; }
    if (e.key === 'Backspace' && !inp.value && S.tokens.length) { removeToken(S.tokens.length - 1); return; }
    if (e.key === ' ' || e.key === 'Enter') {
      const words = inp.value.trim().split(/\s+/);
      const tok = parseToken(words[words.length - 1] || '');
      if (tok) { e.preventDefault(); words.pop(); inp.value = words.join(' ') + (words.length ? ' ' : ''); S.q = inp.value.trim(); pop.hidden = true; addToken(tok.kind, tok.value); return; }
      if (e.key === 'Enter') { pop.hidden = true; inp.blur(); }
    }
  });
  inp.addEventListener('blur', () => setTimeout(() => { $('#omniPop').hidden = true; }, 120));
  $('#omni').addEventListener('click', () => inp.focus());
}

// ---- history: tokens, the open item and the mode are one entry each ------------------------------------------
const snapshot = () => ({ tokens: S.tokens.map((t) => ({ ...t })), open: S.open, mode: S.mode });
export function remember(push) { try { if (push) history.pushState(snapshot(), ''); else history.replaceState(snapshot(), ''); } catch { /* sandboxed */ } }
export function restore(st) {
  if (!st) return;
  S.tokens = (st.tokens || []).map((t) => ({ ...t })); S.open = st.open ?? null; S.mode = st.mode || 'Priority'; S.cursor = -1;
  renderAll();
}

// ---- selection, picking, editing ------------------------------------------------------------------------------
export const listRows = () => [...document.querySelectorAll('#feed .row[data-id]')];
export function select(id, { scroll = true } = {}) {
  const same = S.open !== null && String(S.open) === String(id);
  S.open = id === null || same ? null : id;   // the view is `[`'s alone: opening or closing an item never swaps it
  S.edit = null;
  S.cursor = listRows().findIndex((r) => r.dataset.id === String(S.open));
  remember(true); renderAll();
  if (S.open !== null) fill(itemOf(S.open));
  if (scroll && S.open !== null) { const el = $(`#feed .card.mod[data-id="${S.open}"]`); if (el) el.scrollIntoView({ block: 'nearest' }); }
  const page = $('#page'); if (page) page.scrollTop = 0;
}
const pid = (i) => String(i.id);
export const pickedItems = () => ITEMS.filter((i) => S.picked.has(pid(i)));
export function flipPick(id) { const k = String(id); if (S.picked.has(k)) S.picked.delete(k); else S.picked.add(k); renderFeed(); }
export function setEdit(id) { S.edit = id; if (id !== null && S.open !== id) S.open = id; if (id !== null) S.view = 'inspect'; renderAll(); const ta = $('#page .editor textarea'); if (ta) { ta.focus(); ta.setSelectionRange(ta.value.length, ta.value.length); } }
function commitEdit(item, value) {
  const v = value.trim();
  if (v && v !== item.title) { item.title = v; doVerb(item, 'edit', null, { force: true, value: v }); }
  S.edit = null; renderAll();
}

// ---- verbs: what a facet allows on an item; a destructive one asks first ----------------------------------------------
export const DESTRUCTIVE = new Set(['trash', 'dismiss', 'forget', 'delete', 'restart', 'shutdown', 'end', 'unschedule']);
export const verbLabel = (item, verb) => ((item.verbs || []).find(([v]) => v === verb) || [verb, verb])[1];
export function removeItem(id) {
  const i = ITEMS.findIndex((x) => String(x.id) === String(id));
  if (i >= 0) ITEMS.splice(i, 1);
  S.picked.delete(String(id));
  if (S.open !== null && String(S.open) === String(id)) { S.open = null; S.edit = null; }
  renderAll();
}
export function addItem(item) { ITEMS.unshift(item); renderAll(); return item; }
let seq = 100;
export const nextId = (p) => `${p}${seq++}`;
// A verb runs on the daemon: the module that owns the item decides what it does and says what happened, which is what
// the drawer records. A few verbs never leave the browser, because they open something here rather than change anything.
const away = (i) => {
  const url = i.href || i.url;
  if (!url) { toast('Nothing to open'); return null; }
  window.open(url, '_blank', 'noopener');
  return null;
};
const HERE = {
  open: away, link: away, export: away,
  edit: (i) => { setEdit(i.id); return null; },
  answer: () => { askAgent(); return null; },
  explain: () => { sendToAgent('Explain the part I am on without giving the answer.'); return null; },
  update: () => { askAgent('update the amount to '); return null; },
  due: () => { askAgent('set the date to '); return null; },
  query: (i) => { askAgent(`query ${i.title}: `); return null; },
};
// `anchor` is where a confirmation opens; `value` is what a verb that takes one was given.
export async function doVerb(item, verb, anchor, { force = false, value } = {}) {
  if (!item) return null;
  if (verb === 'reopen' && item.type === 'conversation') { call(drawer, 'openConversation', item); return null; }   // a conversation reopens in the drawer
  if (HERE[verb]) return HERE[verb](item);
  const label = verbLabel(item, verb);
  if (DESTRUCTIVE.has(verb) && !force) {
    const at = anchor || $('#page .plate h2') || $(`#feed .row[data-id="${item.id}"]`) || $('#feed');
    confirmPop(at, `${label}?`, async () => { const said = await doVerb(item, verb, null, { force: true }); if (said) call(drawer, 'note', item, said); });
    return null;
  }
  try {
    const r = await post('/api/verb', { module: item.module, id: item.id, verb, value });
    if (r.url) window.open(r.url, '_blank', 'noopener');
    if (r.removes) removeItem(item.id);
    await load();
    if (r.said) toast(r.said);
    return r.said || null;
  } catch (e) { toast(e.message); return null; }
}

// ---- popovers: tags and confirmations --------------------------------------------------------------------------
export function closePops() { const p = $('#tagPop'); if (p) p.remove(); }
function place(pop, anchor, w = 280) {
  if (!pop.isConnected) document.body.append(pop);
  const r = anchor && anchor.getBoundingClientRect ? anchor.getBoundingClientRect() : { left: innerWidth / 2 - w / 2, top: innerHeight / 2 - 40, bottom: innerHeight / 2 - 40 };
  const hgt = pop.offsetHeight;
  let top = r.bottom + 6;
  if (top + hgt > innerHeight - 8) top = r.top - hgt - 6;   // no room below: open above the anchor
  if (top < 8) top = Math.max(8, innerHeight - hgt - 8);   // nor above: as high as it must go
  pop.style.left = `${Math.max(8, Math.min(r.left, innerWidth - w - 10))}px`;
  pop.style.top = `${top}px`;
}
export function openTagPop(anchor, items) {
  closePops();
  items = items.filter((i) => i.taggable !== false);
  if (!items.length) { toast('A suggestion carries no tags of yours'); return; }
  const pop = h('div', { class: 'pop', id: 'tagPop' });
  const inp = h('input', { autocomplete: 'off', spellcheck: 'false', 'aria-label': 'Tag' });
  const list = h('div');
  const draw = () => {
    const q = inp.value.trim().toLowerCase().replace(/^#/, '');
    const tags = allTags().map((t) => t.tag).filter((t) => !isFixed(t) && t.includes(q)).slice(0, 8);
    if (q && !tags.includes(q) && !isFixed(q)) tags.unshift(q);   // a facet's name is never offered as a new tag
    put(list, ...tags.map((t) => {
      const on = items.every((i) => tagsOf(i).includes(t));
      return h('div', { class: 'pi', onclick: () => apply(t, on) }, h('span', { class: `chk${on ? ' on' : ''}` }), t);
    }));
    place(pop, anchor);   // the list changes height as it is typed into; the box follows
  };
  const apply = (t, on) => {
    if (isFixed(t)) { toast('A facet’s name is not a tag you can give'); return; }
    for (const i of items) {
      if (on) { i.tags = i.tags.filter((x) => x !== t); post('/api/tags/remove', { module: i.module, id: i.id, tag: t }).catch((e) => toast(e.message)); }
      else if (!tagsOf(i).includes(t)) { i.tags.push(t); post('/api/tags/add', { module: i.module, id: i.id, tags: [t] }).catch((e) => toast(e.message)); }
    }
    renderAll(); draw();
  };
  inp.addEventListener('input', draw);
  inp.addEventListener('keydown', (e) => { e.stopPropagation(); if (e.key === 'Escape') closePops(); if (e.key === 'Enter') { const first = $('.pi', list); if (first) first.click(); inp.value = ''; draw(); } });
  pop.append(inp, list); draw(); inp.focus();
}
export function confirmPop(anchor, question, onyes) {
  closePops();
  if (anchor && anchor.setAttribute) anchor.setAttribute('data-tagbtn', '1');
  const yes = h('button', { class: 'yes', onclick: () => { closePops(); onyes(); } }, 'Yes');
  const pop = h('div', { class: 'pop ask', id: 'tagPop' }, h('span', null, question), yes);
  pop.addEventListener('keydown', (e) => { e.stopPropagation(); if (e.key === 'Escape') closePops(); });
  place(pop, anchor, 320); yes.focus();
}

// ---- rendering: the header, the panel, the feed, the page, the drawer's frame, the layout ------------------------------
export function renderAll() { renderTop(); renderPanel(); renderFeed(); renderPage(); renderChat(); applyLayout(); call(shell, 'paintZones'); }
export function renderTop() {
  const seg = $('#modeSeg');
  put(seg, ...['Priority', 'Recent'].map((m) => h('button', { class: m === S.mode ? 'on' : '', onclick: () => setMode(m) }, m)));
  $('#themeBtn').replaceChildren(icon(dark() ? I.sun : I.moon));
  $('#themeBtn').title = dark() ? 'Rainbow' : 'Dark';
  $('#chatBtn').setAttribute('aria-pressed', S.chat === 'open');
  const pt = $('#pulseText'); if (pt) pt.textContent = S.synced ? `synced ${String(S.synced.getHours()).padStart(2, '0')}:${String(S.synced.getMinutes()).padStart(2, '0')}` : 'starting';
  $('#navBtn').setAttribute('aria-pressed', S.view === 'brain');
  $('#app').dataset.chat = S.chat;
  const cur = currentItem();
  document.documentElement.style.setProperty('--m', cur ? hue(cur.module) : NEUTRAL);
  applyLayout();
}
export function setMode(m) { S.mode = m; S.cursor = -1; remember(true); renderAll(); }
export function renderPanel() {
  renderTokens();
  call(brain, 'sync');
}
export function renderChat() {
  const box = $('#chat'); if (!box) return;
  const cur = currentItem();
  box.style.setProperty('--c', cur ? hue(cur.module) : NEUTRAL);
  let plate = $('.plate', box);
  if (!plate) { plate = h('div', { class: 'plate' }); put(box, h('div', { class: 'grip', onmousedown: (e) => call(shell, 'chatDrag', e) }), plate); }
  call(drawer, 'render', plate, { item: cur, ref: S.pointRef });
}

// ---- the feed: rows, and under the open row a card of what the item relates to -------------------------------------------
const rightCell = (i) => {
  if (i.type === 'question') return h('span', { class: 'pbar' }, h('i', { style: `width:${i.pct || 0}%` }));
  if (i.type === 'ledger') return h('span', { class: `r strong num${i.late ? ' late' : ''}` }, i.amount || '');
  if (i.type === 'task') return h('span', { class: 'box' });
  let t = '';
  if (i.right !== undefined) t = i.right;
  else if (i.due) t = dayLabel(i.due);
  else if (i.when) t = stamp(i.when);
  return h('span', { class: `r num${i.late ? ' late' : ''}` }, t);
};
// A row is the title and one stamp: a date, an amount, or nothing. The plate it sits in carries the facet's mark; its tags wait in the summary under it.
function rowEl(i) {
  return h('div', {
    class: `row${i.unread ? ' unread' : ''}${i.dim ? ' dim' : ''}${i.done ? ' done' : ''}${S.open !== null && String(S.open) === String(i.id) ? ' sel' : ''}${S.picked.has(pid(i)) ? ' picked' : ''}`,
    style: `--c:${hue(i.module)}`, 'data-id': i.id, 'data-module': i.module,
    onclick: (e) => { if (S.point) return; if (e.ctrlKey || e.metaKey) { if (i.taggable !== false) flipPick(i.id); return; } S.zone = 'feed'; select(i.id, { scroll: false }); },
  },
    h('span', { class: 'chk', onclick: (e) => { e.stopPropagation(); if (i.taggable !== false) flipPick(i.id); } }),
    h('span', { class: 't' }, h('span', { class: 'title' }, i.title, i.snip ? h('span', { class: 'snip' }, ` · ${i.snip}`) : null)),
    rightCell(i));
}
export function renderFeed() {
  const feed = $('#feed');
  const list = visible();
  const out = [];
  if (S.picked.size) out.push(h('div', { class: 'bulk' }, `${S.picked.size} selected`));
  if (!list.length) out.push(h('div', { class: 'empty' }, S.tokens.length || S.q ? 'Nothing matches this filter.' : 'Nothing waits.'));
  if (S.open === null) revealed = null;
  for (const g of groupsOf(list)) {
    const m = modOf(g.mod), kids = [h('div', { class: 'group', style: `--c:${m.hue}` }, icon(m.icon))];
    for (const r of g.rows) { if (S.open !== null && String(r.id) === String(S.open)) kids.push(h('div', { class: 'openbox' }, rowEl(r), revealEl(r))); else kids.push(rowEl(r)); }   // the open item, row and summary, in one box
    out.push(h('div', { class: 'card mod', style: `--c:${m.hue}`, 'data-facet': g.label }, ...kids));
  }
  put(feed, ...out);
}

// ---- the open item: the card under its row says what it relates to, the page beside the feed says what it is --------------
const kvEl = (kv) => (kv && kv.length ? h('dl', { class: 'kv' }, ...kv.flatMap(([k, v]) => [h('dt', null, k), h('dd', null, v)])) : null);
const proseEl = (html, cls = 'prose') => (html ? h('div', { class: cls, html }) : null);
const stampEl = (text, late) => (text ? h('div', { class: `stamp num${late ? ' late' : ''}` }, text) : null);
function relatedEl(i) {
  const rows = (i.related || []).map(itemOf).filter(Boolean);
  if (!rows.length) return null;
  return h('div', { class: 'related' }, h('div', { class: 'card' }, ...rows.map((r) => h('div', { class: 'row', style: `--c:${hue(r.module)}`, 'data-id': r.id, 'data-module': r.module, onclick: (e) => { e.stopPropagation(); select(r.id); } },
    h('span', { class: 'mark' }, icon(markIcon(r))), h('span', { class: 't' }, h('span', { class: 'title' }, r.title)), rightCell(r)))));
}
function editorEl(i) {
  const ta = h('textarea', { id: `edit-${i.id}`, 'aria-label': 'Edit' });
  ta.value = i.title;
  ta.addEventListener('keydown', (e) => { e.stopPropagation(); if (e.key === 'Escape') { S.edit = null; renderAll(); } if (e.key === 'Enter' && (e.ctrlKey || e.metaKey)) commitEdit(i, ta.value); });
  ta.addEventListener('blur', () => { if (S.edit === i.id) commitEdit(i, ta.value); });
  return h('div', { class: 'editor' }, ta);
}
// What slides out under the open row: its tags, its summary (an agent will write these), and the items it is linked to.
let revealed = null;
function revealEl(i) {
  const first = revealed !== String(i.id);
  const body = [];
  if (tagsOf(i).length) body.push(h('div', { class: 'tagline' }, ...tagList(i, { max: 12, lg: true })));
  if (i.summary) body.push(h('div', { class: 'gist' }, i.summary));
  body.push(relatedEl(i));
  const wrap = h('div', { class: `reveal${first ? '' : ' open'}` }, h('div', { class: 'summary', 'data-id': i.id }, ...body));
  if (first) { revealed = String(i.id); requestAnimationFrame(() => requestAnimationFrame(() => wrap.classList.add('open'))); }
  return wrap;
}
export const widget = revealEl;
// The page: what the item says, in its type's shape.
export function contentEl(i) {
  const body = [];
  const editing = S.edit === i.id && ['note', 'task', 'quote', 'link', 'decision', 'ledger'].includes(i.type);
  if (i.type === 'ledger') body.push(h('div', { class: 'amount num' }, i.amount || ''));
  if (i.type === 'email') body.push(stampEl(`${dayLabel(i.when)} ${clock(i.when)}`));
  else if (i.type === 'question') { /* a question carries no date */ }
  else if (i.type === 'ledger') body.push(stampEl(i.due ? dayLabel(i.due) : '', i.late));
  else if (i.type === 'decision') body.push(stampEl(dayLabel(i.due)));
  else if (i.type === 'notebook' || i.type === 'script') body.push(stampEl(i.status));
  else if (i.type === 'table') body.push(stampEl(i.right));
  else if (i.type === 'routine') body.push(stampEl(i.late ? 'failed' : i.paused ? 'paused' : i.snip, i.late));
  else if (i.when) body.push(stampEl(dayLabel(i.when)));
  if (i.snip && ['note', 'ledger', 'task'].includes(i.type)) body.push(h('div', { class: 'from' }, i.snip));
  if (editing) body.push(editorEl(i));
  switch (i.type) {
    case 'email': body.push(kvEl(i.kv), proseEl(i.body, 'prose mail')); break;
    case 'question': {
      const key = (k) => `${i.id}/${k}`, nextPart = (i.parts || []).find((p) => p.score === null);
      const card = (k, text, dflt, right) => {
        const open = S.qtoggle.has(key(k)) ? !dflt : dflt;
        const flip = () => { if (S.qtoggle.has(key(k))) S.qtoggle.delete(key(k)); else S.qtoggle.add(key(k)); renderPage(); };
        return h('div', { class: `qcard${open ? ' open' : ''}` }, h('div', { class: 'qhead', onclick: flip }, h('span', { class: 'qh', html: text }), right, icon(I.down, 'ic chev')));
      };
      body.push(card('prompt', [...(i.defs || []), i.premise || ''].join(' '), true, null));
      for (const p of i.parts || []) body.push(card(p.n, `(${p.n}) ${p.ask}`, p === nextPart, p.score === null ? h('span', { class: 'sc none' }, p === nextPart ? 'answer in the drawer' : '') : h('span', { class: 'sc num' }, `${p.score} / 100`)));
      break;
    }
    case 'ledger': body.push(kvEl(i.kv), i.hist && i.hist.length ? h('div', { class: 'prose' }, h('div', { class: 'hist num' }, ...i.hist.flatMap(([d, a]) => [h('span', { class: 'd' }, d), h('span', null, a)]))) : null); break;
    case 'decision': body.push(kvEl(i.kv), proseEl(i.body)); break;
    case 'routine': body.push(kvEl(i.kv)); break;
    case 'article': body.push(kvEl(i.kv), proseEl(i.body)); break;
    case 'suggestion': body.push(proseEl(i.body)); break;
    case 'notebook': case 'script':
      for (const c of i.cells || []) body.push(h('div', { class: 'cell' }, h('span', { class: `g${c.run ? ' run' : ''}` }, c.g), h('div', null, h('pre', { html: c.code }), c.out ? h('div', { class: `out${c.err ? ' err' : ''}` }, c.out) : null)));
      break;
    case 'conversation': body.push(h('div', { class: 'excerpt' }, ...(i.turns || []).map(([role, text]) => h('div', { class: `turn ${role}` }, role === 'model' ? h('p', null, text) : text)))); break;
    case 'table': body.push(h('div', { class: 'cols' }, ...(i.cols || []).flatMap(([n, t, c]) => [h('span', null, n), h('span', { class: 'ty' }, t), h('span', null, c)]))); break;
    case 'query': body.push(h('div', { class: 'cell' }, h('span', { class: 'g' }, ''), h('pre', null, i.sql || ''))); break;
    default: if (!editing) body.push(i.body ? proseEl(i.body) : h('div', { class: 'prose' }, h('p', null, i.title)));
  }
  return body;
}
export function renderPage() {
  const page = $('#page'), i = currentItem();
  if (!page) return;
  if (!i) { put(page); return; }
  const m = modOf(i.module), mono = ['notebook', 'script', 'table', 'routine'].includes(i.type);
  const head = h('div', { class: 'dhead', style: `--c:${m.hue}` }, icon(markIcon(i)), h('span', { class: `dtitle${mono ? ' mono' : ''}` }, i.title, i.snip ? h('span', { class: 'snip' }, ` · ${i.snip}`) : null),
    h('span', { class: 'spacer' }), h('button', { class: 'icon-btn', title: 'Close', onclick: () => select(null) }, icon(I.close)));
  put(page, h('div', { class: 'grip', onmousedown: (e) => call(shell, 'pageDrag', e) }), h('div', { class: 'card mod plate', style: `--c:${m.hue}`, 'data-id': i.id, 'data-module': i.module, tabindex: '-1' }, head, h('div', { class: 'dbody' }, ...contentEl(i))));
}
