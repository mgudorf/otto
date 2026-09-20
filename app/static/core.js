// Shell: state, DOM helpers, chrome, the omnibox, and the generic list and detail renderer.
// Pages live in pages/<module>.js and reach core through registerPages(); core never imports one.
import { get, post, inflight } from './api.js';

export const S = {
  page: 'home', sel: null, item: null, picked: new Set(), tokens: [], q: '',
  chip: {}, seg: {}, cursor: -1, zone: 'list', navCursor: null, tabCursor: 0, chatTab: {},
  quick: [], data: null, shell: null, tags: [], pulse: null, error: null, selMod: null,
  nav: 'open', chat: 'open', capture: false, point: false, pointRef: null, gpreview: null, tagsOpen: new Set(),
};

// ---- DOM --------------------------------------------------------------------------------------
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
  bookmark: '<path d="M6 3h8v14l-4-3-4 3V3Z"></path>',
  search: '<circle cx="9" cy="9" r="5.5"></circle><path d="M13 13l4 4"></path>',
  chat: '<path d="M4 4h12v9H9l-4 3v-3H4Z"></path>',
  close: '<path d="M5 5l10 10M15 5L5 15"></path>',
  sun: '<circle cx="10" cy="10" r="3.5"></circle><path d="M10 2.5v2M10 15.5v2M2.5 10h2M15.5 10h2M4.7 4.7l1.4 1.4M13.9 13.9l1.4 1.4M4.7 15.3l1.4-1.4M13.9 6.1l1.4-1.4"></path>',
  moon: '<path d="M16 12.5A6.5 6.5 0 0 1 7.5 4a6.5 6.5 0 1 0 8.5 8.5Z"></path>',
  panel: '<rect x="3" y="4" width="14" height="12" rx="2"></rect><path d="M12 4v12"></path>',
  panelL: '<rect x="3" y="4" width="14" height="12" rx="2"></rect><path d="M8 4v12"></path>',
  cmd: '<path d="M7 7h6v6H7z"></path><path d="M7 7H5a2 2 0 1 1 2-2v2M13 7h2a2 2 0 1 0-2-2v2M7 13H5a2 2 0 1 0 2 2v-2M13 13h2a2 2 0 1 1-2 2v-2"></path>',
  up: '<path d="M6 12l4-4 4 4"></path>', down: '<path d="M6 8l4 4 4-4"></path>',
  back: '<path d="M12 5l-5 5 5 5"></path>', forward: '<path d="M8 5l5 5-5 5"></path>',
  star: '<path d="M10 3l2.2 4.5 5 .7-3.6 3.5.9 4.9L10 14.3 5.5 16.6l.9-4.9L2.8 8.2l5-.7z"></path>',
  archive: '<rect x="3" y="4" width="14" height="4" rx="1"></rect><path d="M5 8v7a1 1 0 001 1h8a1 1 0 001-1V8M8 11h4"></path>',
  trash: '<path d="M4 6h12M8 6V4h4v2M6 6l1 10h6l1-10"></path>',
  tag: '<path d="M3 3h6l8 8-6 6-8-8z"></path><circle cx="6.5" cy="6.5" r="1"></circle>',
  check: '<path d="M4 10l4 4 8-8"></path>',
  plus: '<path d="M10 4v12M4 10h12"></path>',
  play: '<path d="M6 4l10 6-10 6z"></path>',
  link: '<path d="M8 12l4-4M7 7H5.5a3.5 3.5 0 0 0 0 7H7M13 13h1.5a3.5 3.5 0 0 0 0-7H13"></path>',
  file: '<path d="M5 3h7l3 3v11H5z"></path><path d="M12 3v3h3"></path>',
  nb: '<rect x="4" y="3" width="12" height="14" rx="1.5"></rect><path d="M7 7h6M7 10h6M7 13h4"></path>',
  help: '<circle cx="10" cy="10" r="7"></circle><path d="M8 8a2 2 0 1 1 3 1.7c-.7.4-1 .8-1 1.6M10 14h.01"></path>',
  clip: '<path d="M13.5 6.5l-6 6a2 2 0 002.8 2.8l6.5-6.5a3.5 3.5 0 00-5-5L5.3 10.3a5 5 0 007 7l5-5"></path>',
  quote: '<path d="M5 12V8a3 3 0 0 1 3-3M12 12V8a3 3 0 0 1 3-3"></path><rect x="4" y="11" width="4" height="4"></rect><rect x="11" y="11" width="4" height="4"></rect>',
  note: '<path d="M4 4h12v12H4z"></path><path d="M7 8h6M7 11h4"></path>',
  external: '<path d="M11 4h5v5M16 4l-7 7M14 11v5H4V6h5"></path>',
  grip: '<path d="M4 6h12M4 10h12M4 14h12"></path>',
  target: '<circle cx="4.5" cy="10" r="2.6"></circle><path d="M8.7 7v6M11.3 7v6"></path><circle cx="15.5" cy="10" r="2.6"></circle>',   // the Otto mark: point mode is Otto looking where you point
};

// ---- modules ----------------------------------------------------------------------------------
// Activity and Settings are shell pages, not daemon modules; every other entry comes from /api/shell.
const NEUTRAL = '#8b92a1';   // the wash for pages that are not one module's
const FOOT = [
  { id: 'activity', name: 'activity', title: 'Activity', hue: '#a6acb8', icon: '<path d="M3 12h4l2-6 3 10 2-6h3"></path>', page: true, agent: null, skills: [], order: 100 },
  { id: 'settings', name: 'settings', title: 'Settings', hue: '#a6acb8', icon: '<circle cx="10" cy="10" r="6.5"></circle><circle cx="10" cy="10" r="2"></circle>', page: true, agent: null, skills: [], order: 101 },
];
const shape = (m) => ({ ...m, id: m.name, agent: m.agent ? m.agent.placeholder : null, skills: m.agent ? m.agent.skills || [] : [] });
const mods = () => (S.shell ? S.shell.modules.map(shape) : []);
const rail = () => mods().filter((m) => m.page && (m.enabled || m.error));
const allMods = () => [...rail(), ...FOOT];
export function modOf(id) {
  return allMods().find((m) => m.id === id) || mods().find((m) => m.id === id) || { id, name: id, title: id, hue: NEUTRAL, icon: '', agent: null, skills: [] };
}
export const hue = (m) => (typeof m === 'string' ? modOf(m) : m).hue || NEUTRAL;
const dark = () => document.documentElement.dataset.theme === 'dark';   // the other theme, rainbow, is dark too
const settingOf = (k, fallback) => (S.shell && S.shell.settings && S.shell.settings[k] !== undefined ? S.shell.settings[k] : fallback);

// ---- formatting -------------------------------------------------------------------------------
const iso = (d) => `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
const today = () => iso(new Date());
const yesterday = () => { const d = new Date(); d.setDate(d.getDate() - 1); return iso(d); };
export function dayLabel(s) { const [y, m, d] = String(s).slice(0, 10).split('-'); return `${m}-${d}-${y}`; }
export function relDay(s) { const d = String(s).slice(0, 10); return d === today() ? 'Today' : d === yesterday() ? 'Yesterday' : dayLabel(d); }
function clock(s) {
  const t = String(s).slice(11, 16);
  if (settingOf('ui.time_format', '24h') !== '12h' || t.length < 5) return t;
  const hh = Number(t.slice(0, 2));
  return `${((hh + 11) % 12) + 1}:${t.slice(3)} ${hh < 12 ? 'am' : 'pm'}`;
}
export function stamp(s) { return String(s).slice(0, 10) === today() ? clock(s) : dayLabel(s); }
export function money(c) { return (Number(c) / 100).toLocaleString('en-US', { style: 'currency', currency: 'USD' }); }
let toastT;
export function toast(msg) { const t = $('#toast'); if (!t) return; t.textContent = msg; t.classList.add('on'); clearTimeout(toastT); toastT = setTimeout(() => t.classList.remove('on'), 1800); }

// ---- tags -------------------------------------------------------------------------------------
export const tagsOf = (i) => [...((i && i.fixed) || []), ...((i && i.tags) || [])];   // identity tags first, then the owner's
export function allTags() { return S.tags; }
export function tagEl(tag, { lg, removable, onremove, fixed } = {}) {
  const el = h('span', { class: `tag${lg ? ' lg' : ''}${fixed ? ' fixed' : ''}`, onclick: (e) => { e.stopPropagation(); addToken('tag', tag); } }, tag);
  if (removable) el.append(h('button', { class: 'x', onclick: (e) => { e.stopPropagation(); onremove && onremove(); } }, '×'));
  return el;
}
async function removeTag(item, tag, after) {
  try { await post('/api/tags/remove', { module: item.module || S.page, id: item.id, tag }); } catch (e) { toast(e.message); return; }
  if (after) after(); else refresh();
}
export function tagList(i, { max = 5, hideFixed = false, editable = false, onChange } = {}) {
  const all = [...(hideFixed ? [] : (i.fixed || [])).map((t) => ({ t, fixed: true })), ...(i.tags || []).map((t) => ({ t, fixed: false }))];
  const open = S.tagsOpen.has(i.id);
  const els = (open ? all : all.slice(0, max)).map(({ t, fixed }) => tagEl(t, { fixed, lg: editable, removable: editable && !fixed, onremove: () => removeTag(i, t, onChange) }));
  if (all.length > max) els.push(h('button', { class: 'tag more', onclick: (e) => { e.stopPropagation(); if (open) S.tagsOpen.delete(i.id); else S.tagsOpen.add(i.id); renderMain(); } }, open ? 'less' : `+${all.length - max}`));
  return els;
}
function tagsEditor(i) {
  const box = h('span', { class: 'tags' });
  put(box, ...tagList(i, { max: 5, editable: true }), h('button', { class: 'tag-add', 'data-tagbtn': '1', onclick: (e) => openTagPop(e.currentTarget, [i]) }, '+ tag'));
  return box;
}
// The picker for one row, the selection, or every picked row: a checked tag is on all of them.
export function openTagPop(anchor, items) {
  closePops();
  const pop = h('div', { class: 'pop', id: 'tagPop' });
  const r = anchor.getBoundingClientRect();
  pop.style.left = `${Math.min(r.left, innerWidth - 260)}px`; pop.style.top = `${r.bottom + 4}px`;
  const inp = h('input', { autocomplete: 'off', spellcheck: 'false' });
  const list = h('div');
  const draw = () => {
    const q = inp.value.trim().toLowerCase();
    const tags = allTags().map((t) => t.tag).filter((t) => t.includes(q)).slice(0, 8);
    if (q && !tags.includes(q)) tags.unshift(q);
    put(list, ...tags.map((t) => {
      const on = items.every((i) => tagsOf(i).includes(t));
      const locked = items.some((i) => (i.fixed || []).includes(t));
      return h('div', { class: 'pi', onclick: () => apply(t, on, locked) }, h('span', { class: `chk${on ? ' on' : ''}` }), t);
    }));
  };
  const apply = async (t, on, locked) => {
    if (locked) { toast('An identity tag stays with its item; delete the item to drop it.'); return; }
    try {
      for (const i of items) {
        if (on) await post('/api/tags/remove', { module: i.module || S.page, id: i.id, tag: t });
        else if (!tagsOf(i).includes(t)) await post('/api/tags/add', { module: i.module || S.page, id: i.id, tags: [t] });
      }
    } catch (e) { toast(e.message); return; }
    await refresh();
    const again = (S.data && (S.data.items || [])) || [];
    items = items.map((i) => again.find((x) => String(x.id) === String(i.id)) || i);
    draw();
  };
  inp.addEventListener('input', draw);
  inp.addEventListener('keydown', (e) => { if (e.key === 'Escape') closePops(); if (e.key === 'Enter') { const first = $('.pi', list); if (first) first.click(); inp.value = ''; draw(); } });
  pop.append(inp, list); document.body.append(pop); draw(); inp.focus();
}
export function closePops() { const p = $('#tagPop'); if (p) p.remove(); }

// ---- tokens -----------------------------------------------------------------------------------
const itemText = (i) => [i.title, i.from, i.snippet, i.summary, i.topic, i.search, i.kind, i.verb, i.note, ...tagsOf(i)].filter(Boolean).join(' ').toLowerCase();
export function applyTokens(list) {
  for (const t of S.tokens) {
    if (t.kind === 'tag') list = list.filter((i) => tagsOf(i).includes(t.value));
    else if (t.kind === 'mod') list = list.filter((i) => i.module === t.value);
    else if (t.kind === 'filter') {
      const [k, v] = t.value.split(':');
      if (k === 'is' && v === 'unread') list = list.filter((i) => i.unread);
      else if (k === 'is' && v === 'starred') list = list.filter((i) => i.starred);
      else if (k === 'is' && v === 'open') list = list.filter((i) => i.status === 'open' || (i.kind === 'task' && !i.done));
      else if (k === 'is' && v === 'done') list = list.filter((i) => i.done || i.status === 'completed');
      else if (k === 'kind') list = list.filter((i) => i.kind === v);
      else if (k === 'from') list = list.filter((i) => (i.from || '').toLowerCase().includes(v));
    }
  }
  const P = configOf(S.page);
  if (S.q && !(P && P.serverQuery)) { const q = S.q.toLowerCase(); list = list.filter((i) => itemText(i).includes(q)); }
  return list;
}
export function addToken(kind, value) {
  if (S.tokens.some((t) => t.kind === kind && t.value === value)) return;
  if (kind === 'mod') S.tokens = S.tokens.filter((t) => t.kind !== 'mod');
  S.tokens.push({ kind, value });
  S.cursor = -1;
  if (kind === 'mod' && !S.page.startsWith('tag:') && S.page !== 'home') { go(value, true); return; }
  if (S.page.startsWith('tag:')) { refresh(); return; }   // the tag page's rows come from the daemon, so narrowing reloads
  renderAll();
}
function removeToken(i) { S.tokens.splice(i, 1); if (S.page.startsWith('tag:')) refresh(); else renderAll(); }
function parseToken(word) {
  if (word.startsWith('#') && word.length > 1) return { kind: 'tag', value: word.slice(1).toLowerCase() };
  if (word.startsWith('@') && word.length > 1) { const w = word.slice(1).toLowerCase(); const m = allMods().find((m) => m.id.startsWith(w) || m.title.toLowerCase().startsWith(w)); return m ? { kind: 'mod', value: m.id } : null; }
  if (/^(is|kind|from):\S+$/.test(word)) return { kind: 'filter', value: word.toLowerCase() };
  return null;
}
function renderTokens() {
  put($('#tokens'), ...S.tokens.map((t, i) => {
    const cls = t.kind === 'tag' ? 'token tag' : t.kind === 'mod' ? 'token mod' : 'token';
    const label = t.kind === 'tag' ? t.value : t.kind === 'mod' ? `@${modOf(t.value).title}` : t.value;
    return h('span', { class: cls, style: t.kind === 'mod' ? `--c:${hue(t.value)}` : null }, label, h('button', { onclick: () => removeToken(i) }, '×'));
  }));
}

let omniRows = [], omniCursor = 0, omniKey = '';
function omniSuggest() {
  const inp = $('#omniInput'), pop = $('#omniPop');
  const w = inp.value.trim().split(/\s+/).pop() || '';
  let rows = [];
  if (w.startsWith('#')) rows = allTags().filter((t) => t.tag.startsWith(w.slice(1).toLowerCase())).slice(0, 8).map((t) => ({ label: `#${t.tag}`, sub: `${t.count} items`, tok: { kind: 'tag', value: t.tag } }));
  else if (w.startsWith('@')) rows = allMods().filter((m) => m.title.toLowerCase().startsWith(w.slice(1).toLowerCase())).slice(0, 8).map((m) => ({ label: `@${m.title}`, sub: 'module', c: hue(m), tok: { kind: 'mod', value: m.id } }));
  else if (w.includes(':') || w === 'is') rows = ['is:unread', 'is:starred', 'is:open', 'is:done', 'kind:task', 'kind:note', 'kind:link'].filter((f) => f.startsWith(w)).map((f) => ({ label: f, sub: 'filter', tok: { kind: 'filter', value: f } }));
  omniRows = rows;
  const key = rows.map((r) => r.label).join('|');
  if (key !== omniKey) { omniKey = key; omniCursor = 0; }
  if (!rows.length) { pop.hidden = true; return; }
  const r = inp.getBoundingClientRect();
  pop.style.left = `${r.left}px`; pop.style.top = `${r.bottom + 6}px`; pop.hidden = false;
  put(pop, ...rows.map((row, i) => h('div', { class: `pi${i === omniCursor ? ' on' : ''}`, onmousedown: (e) => { e.preventDefault(); omniPick(row); }, onmousemove: () => { if (omniCursor !== i) { omniCursor = i; omniHighlight(); } } },
    row.c ? h('span', { style: `width:8px;height:8px;border-radius:50%;background:${row.c}` }) : null, row.label, h('span', { class: 'sub', style: 'margin-left:auto' }, row.sub))));
}
function omniHighlight() { [...$('#omniPop').children].forEach((el, i) => el.classList.toggle('on', i === omniCursor)); }
// The highlighted suggestion becomes a token; the word that summoned it goes.
function omniPick(row) {
  const inp = $('#omniInput');
  if (!row) return;
  inp.value = inp.value.replace(/\S+$/, ''); S.q = inp.value.trim();
  $('#omniPop').hidden = true; omniRows = []; omniKey = '';
  addToken(row.tok.kind, row.tok.value);
  inp.focus();
}
let qTimer = null;
function bindOmni() {
  const inp = $('#omniInput');
  inp.addEventListener('input', () => {
    S.q = inp.value.trim(); S.cursor = -1; omniSuggest(); renderMain();
    // A page that searches its whole table is asked again, a moment after the typing stops rather than on every letter.
    const P = configOf(S.page);
    if (P && P.serverQuery) { clearTimeout(qTimer); qTimer = setTimeout(() => { if (S.q === inp.value.trim()) refresh(); }, 300); }
  });
  inp.addEventListener('keydown', (e) => {
    const pop = $('#omniPop');
    if (!pop.hidden && omniRows.length) {
      if (e.key === 'ArrowDown' || e.key === 'ArrowUp') { e.preventDefault(); omniCursor = (omniCursor + (e.key === 'ArrowDown' ? 1 : omniRows.length - 1)) % omniRows.length; omniHighlight(); return; }
      if (e.key === 'Enter' || e.key === 'Tab') { e.preventDefault(); omniPick(omniRows[omniCursor]); return; }
    }
    if (e.key === 'Escape') { inp.value = ''; S.q = ''; S.tokens = []; inp.blur(); pop.hidden = true; clearTimeout(qTimer); const P = configOf(S.page); if (S.page.startsWith('tag:') || (P && P.serverQuery)) refresh(); else renderAll(); return; }
    if (e.key === 'Backspace' && !inp.value && S.tokens.length) { S.tokens.pop(); if (S.page.startsWith('tag:')) refresh(); else renderAll(); return; }
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

// ---- history ----------------------------------------------------------------------------------
// Every page change is a history entry, so the mouse back and forward buttons walk pages; a selection
// is folded into the entry it belongs to, so stepping back lands on the page with its pane still open.
const snapshot = () => ({ page: S.page, tokens: S.tokens.map((t) => ({ ...t })), sel: S.sel, selMod: S.selMod, gpreview: S.gpreview });
function remember() { try { history.replaceState(snapshot(), '', `#/${S.page}`); } catch { /* a file:// window has no history */ } }
export function go(page, keepTokens, silent) {
  if (!keepTokens) S.tokens = S.tokens.filter((t) => t.kind !== 'mod');
  S.page = page; S.sel = null; S.item = null; S.data = null; S.picked.clear(); S.cursor = -1; S.capture = false; S.gpreview = null;
  if (!silent) try { history.pushState(snapshot(), '', `#/${page}`); } catch { /* as above */ }
  renderAll();
  refresh();
}
const known = (p) => !!p && (!!PAGES[p] || FOOT.some((f) => f.id === p) || p.startsWith('tag:'));
function restore(st) {
  const page = (st && st.page) || (location.hash.match(/^#\/(.+)$/) || [])[1];
  if (!known(page)) return;
  S.tokens = ((st && st.tokens) || []).map((t) => ({ ...t }));
  go(page, true, true);
  S.sel = (st && st.sel) || null; S.selMod = (st && st.selMod) || null; S.gpreview = (st && st.gpreview) || null;
  if (S.sel) loadItem();
}
const histGo = (d) => { try { history.go(d); } catch { /* as above */ } };
window.addEventListener('popstate', (e) => restore(e.state));

// ---- quick access -----------------------------------------------------------------------------
// A snapshot of the page and the tokens in the search bar. Added from the bar or the palette, removed from the rail.
const tokenText = (t) => (t.kind === 'tag' ? `#${t.value}` : t.kind === 'mod' ? `@${modOf(t.value).title}` : t.value);
const sameTokens = (a, b) => a.length === b.length && a.every((t, i) => t.kind === b[i].kind && t.value === b[i].value);
const tagEntry = (q) => q.page.startsWith('tag:') && q.tokens.length === 1 && q.tokens[0].kind === 'tag' && q.tokens[0].value === q.page.slice(4);
function saveQuick() { try { localStorage.setItem('otto-next-quick', JSON.stringify(S.quick)); } catch { /* private window */ } }
const pinTitle = () => { const page = S.page, tokens = S.tokens.filter((t) => t.kind !== 'mod'); return [page.startsWith('tag:') ? page.slice(4) : modOf(page).title, ...tokens.filter((t) => !(t.kind === 'tag' && page === `tag:${t.value}`)).map(tokenText)].join(' '); };
function pinView(title) {
  const page = S.page, tokens = S.tokens.filter((t) => t.kind !== 'mod').map((t) => ({ ...t }));
  if (S.quick.some((q) => q.page === page && sameTokens(q.tokens, tokens))) { toast('Already in Quick access'); return; }
  const entry = { title: (title || '').trim() || pinTitle(), page, tokens };
  S.quick.push(entry); saveQuick(); renderNav(); toast(`Added to Quick access: ${entry.title}`);
}
function openPinPop() {
  closePops();
  if (S.page === 'home' && !S.tokens.some((t) => t.kind !== 'mod')) { toast('Nothing to add yet'); return; }
  const inp = h('input', { value: pinTitle(), onkeydown: (e) => { if (e.key === 'Enter') { pinView(inp.value); closePops(); } if (e.key === 'Escape') closePops(); } });
  const pop = h('div', { class: 'pop pin-pop', id: 'tagPop' }, inp, h('button', { class: 'btn primary', onclick: () => { pinView(inp.value); closePops(); } }, 'Add'));
  document.body.append(pop);
  const r = $('#pinBtn').getBoundingClientRect(); pop.style.left = `${Math.max(8, Math.min(r.right - 300, innerWidth - 310))}px`; pop.style.top = `${r.bottom + 6}px`;
  inp.focus(); inp.select();
}

// ---- chrome -----------------------------------------------------------------------------------
export function renderTop() {
  $('#themeBtn').replaceChildren(icon(dark() ? I.sun : I.moon));
  $('#themeBtn').title = dark() ? 'Rainbow' : 'Dark';
  $('#chatBtn').setAttribute('aria-pressed', S.chat === 'open');
  $('#navBtn').setAttribute('aria-pressed', S.nav === 'open');
  $('#app').dataset.nav = S.nav; $('#app').dataset.chat = S.chat;
  renderTokens();
  renderPulse();
}
// The daemon's own line: when its clock last ran, what is running now, and any fetch that failed. With nothing to
// report it says nothing; the dot beats only while work is actually in flight.
function renderPulse() {
  const dot = $('#pulseDot'), text = $('#pulseText');
  if (!dot || !text) return;
  const running = (S.pulse && S.pulse.running) || 0;
  const bits = [];
  if (S.pulse && S.pulse.synced) bits.push(`synced ${stamp(S.pulse.synced)}`);
  if (running) bits.push(`${running} job${running > 1 ? 's' : ''} running`);
  dot.classList.toggle('busy', !!(running || inflight.n));
  dot.style.cssText = S.error ? 'background:var(--danger);box-shadow:none' : '';
  text.style.cssText = S.error ? 'color:var(--danger)' : '';
  text.textContent = S.error || bits.join(', ');
}
export function renderNav() {
  // A module that failed to load sits in the rail, dimmed and unreachable, with the failure on hover.
  const item = (m) => h('div', { class: `nav-item${S.page === m.id ? ' active' : ''}`, style: `--c:${hue(m)}${m.error ? ';opacity:.5;cursor:not-allowed' : ''}`, title: m.error || null, onclick: () => { if (!m.error) go(m.id); } }, icon(m.icon), h('span', null, m.title));
  put($('#nav'),
    ...rail().map(item),
    S.quick.length ? h('div', { class: 'rule' }) : null,
    h('div', { class: 'views' }, ...S.quick.map((q) => h('div', { class: `nav-item${S.page === q.page && sameTokens(q.tokens, S.tokens.filter((t) => t.kind !== 'mod')) ? ' active' : ''}`, onclick: () => { S.tokens = q.tokens.map((t) => ({ ...t })); go(q.page, true); } },
      h('span', { class: 'hash' }, tagEntry(q) ? '#' : '»'), h('span', null, tagEntry(q) ? q.title.replace(/^#/, '') : q.title),
      h('button', { class: 'unpin', onclick: (e) => { e.stopPropagation(); S.quick = S.quick.filter((x) => x !== q); saveQuick(); renderNav(); } }, '×')))),
    h('div', { class: 'foot' }, ...FOOT.map(item)),
  );
  paintNav();
}
function setTheme(t) {
  if (t === 'dark') document.documentElement.dataset.theme = 'dark'; else delete document.documentElement.dataset.theme;
  try { localStorage.setItem('otto-next-theme', t); } catch { /* private window */ }
  renderAll();
}
const toggleTheme = () => setTheme(dark() ? 'rainbow' : 'dark');
const toggleChat = () => { S.chat = S.chat === 'open' ? 'closed' : 'open'; renderTop(); renderChat(); };
const toggleNav = () => { S.nav = S.nav === 'open' ? 'closed' : 'open'; renderTop(); };

// ---- the agent drawer and point mode ------------------------------------------------------------
// Both are separate files that register themselves as they load; without one the shell still runs, with that part empty.
// The drawer answers render, sync, focus, setDraft, send, newChat, pickTab, renameTab, closeChat and reopenChat; point answers toggle.
let drawer = null, pointer = null;
const call = (obj, name, ...args) => (obj && typeof obj[name] === 'function' ? obj[name](...args) : undefined);
export function registerDrawer(impl) { drawer = impl; }
export function registerPoint(impl) { pointer = impl; }
export function currentAgent() { const m = S.page.startsWith('tag:') ? modOf('graph') : modOf(S.page); return m.agent ? m : modOf('home'); }
export function pageTitle() { return S.page.startsWith('tag:') ? `#${S.page.slice(4)}` : modOf(S.page).title; }
// The frame of the drawer is core's: the plate, the module's hue, the gutter. What is drawn inside the plate is the drawer's.
export function renderChat() {
  const box = $('#chat'); if (!box) return;
  const m = currentAgent();
  box.style.setProperty('--c', hue(m));
  let plate = $('.plate', box);
  if (!plate) { plate = h('div', { class: 'plate' }); put(box, h('div', { class: 'grip', onmousedown: startChatDrag }), plate); }
  call(drawer, 'render', plate, { module: m, sel: selection(), ref: S.pointRef });
  paintTabs();
}
// The composer takes the keyboard, a skill from the palette, or a whole turn the point popup started.
export function askAgent() { openDrawer(); call(drawer, 'focus'); }
export function sendToAgent(text) { openDrawer(); call(drawer, 'setDraft', text); return call(drawer, 'send'); }
// The button and the `o` key are the frame's; the aiming and the popup are point.js's.
export function togglePoint(on) {
  if (!pointer) return;
  S.point = on === undefined ? !S.point : !!on;
  const btn = $('#pointBtn'); if (btn) btn.setAttribute('aria-pressed', S.point);
  call(pointer, 'toggle', S.point);
}

// ---- grips ---------------------------------------------------------------------------------------
// A grip is a strip over a gutter; dragging it sets a width variable on the root, which the closed and narrow states still override.
function grip(onMove) {
  return (e) => {
    if (e.button !== 0) return;
    e.preventDefault();
    const app = $('.app'), move = (ev) => onMove(ev.clientX);
    const up = () => { document.removeEventListener('mousemove', move); document.removeEventListener('mouseup', up); app.classList.remove('dragging'); document.body.style.cursor = ''; };
    app.classList.add('dragging'); document.body.style.cursor = 'col-resize';
    document.addEventListener('mousemove', move); document.addEventListener('mouseup', up);
  };
}
function setWidth(name, px) { document.documentElement.style.setProperty(name, `${px}px`); try { localStorage.setItem(`otto-next${name}`, String(px)); } catch { /* private window */ } }
// The drawer is a column of the grid at every width: it never grows past the page, which keeps room for its plates.
export function chatMax() { const nav = $('#nav').getBoundingClientRect().width, need = $('#main .content.split') ? (innerWidth <= 1280 ? 660 : 840) : 520; return Math.max(280, innerWidth - nav - need); }
export function clampChat() { const w = parseFloat(getComputedStyle(document.documentElement).getPropertyValue('--chatw')) || 400, m = chatMax(); if (w > m) document.documentElement.style.setProperty('--chatw', `${m}px`); }
window.addEventListener('resize', clampChat);
const startChatDrag = grip((x) => setWidth('--chatw', Math.round(Math.max(280, Math.min(chatMax(), innerWidth - x)))));
const startSplitDrag = grip((x) => { const c = $('#main .content.split'); if (!c) return; const r = c.getBoundingClientRect(); setWidth('--listw', Math.round(Math.max(240, Math.min(r.width - 476, x - r.left)))); });

// ---- rows and plates ------------------------------------------------------------------------------
const pid = (i) => String(i && i.id !== undefined ? i.id : i);   // one spelling of a row's id, so a picked set never holds both 5 and "5"
export const taggable = (i) => i && i.taggable !== false;
const flip = (id) => { S.picked.has(id) ? S.picked.delete(id) : S.picked.add(id); renderMain(); };
export function chk(item) { if (!taggable(item)) return h('span'); return h('span', { class: 'chk', onclick: (e) => { e.stopPropagation(); flip(pid(item)); } }); }
export function titleCell(item, extra, opts = {}) {
  const tags = tagList(item, { max: 5, hideFixed: opts.hideFixed });
  return h('span', { class: `t${tags.length ? ' with-tags' : ''}` }, h('span', { class: 'title' }, extra !== undefined ? extra : item.title), tags.length ? h('span', { class: 'tags-inline' }, ...tags) : null);
}
// The right-hand stamp: a date the row is bound to, or the time of day for something that arrived today; else nothing.
export function stampCell(i, time) {
  let t = '';
  if (i.happens) t = dayLabel(i.happens) + (i.happens.length > 10 ? ` ${clock(i.happens)}` : '');
  else if (i.due && !i.ended) t = dayLabel(i.due);
  else if (i.followUp) t = dayLabel(i.followUp);
  else if (time && i.when && String(i.when).slice(0, 10) === today()) t = clock(i.when);
  return h('span', { class: 'r num' }, t);
}
export function acts(item, list) {
  return h('span', { class: 'acts' }, ...list.filter(Boolean).map(([label, fn, isIcon]) => h('button', { class: isIcon ? 'icon' : null, title: isIcon ? label : null, 'data-tagbtn': label === 'Tag' ? '1' : null, onclick: (e) => { e.stopPropagation(); fn(e); } }, isIcon ? icon(isIcon) : label)));
}
export const tagAct = (item) => ['Tag', (e) => openTagPop(e.currentTarget, S.picked.size ? picked() : [item]), I.tag];
export function markCell(mod) { return h('span', { class: 'mark', style: `--c:${hue(mod)}` }, icon(modOf(mod).icon)); }
export function byDay(list) {
  const groups = [];
  for (const it of list) { const l = relDay(it.when); let g = groups.find((x) => x.label === l); if (!g) { g = { label: l, rows: [] }; groups.push(g); } g.rows.push(it); }
  return groups;
}
export const newest = (a, b) => (a.when < b.when ? 1 : -1);
// One group of rows on its own plate; the header names the group, with the module's icon when it is one.
export function card(label, count, rows, mod) {
  const m = typeof mod === 'string' ? modOf(mod) : mod;
  return h('div', { class: `card${m ? ' mod' : ''}`, style: m ? `--c:${hue(m)}` : null }, label ? h('div', { class: 'group' }, m ? icon(m.icon) : null, label) : null, ...rows);
}
export function rowEl(i, P, cols) {
  return h('div', {
    class: `row ${P.rowClass ? P.rowClass(i) : ''}${isSel(i) ? ' sel' : ''}${S.picked.has(pid(i)) ? ' picked' : ''}`, style: `--cols:${cols || P.cols}`, 'data-id': i.id,
    onclick: (e) => { if (e.ctrlKey || e.metaKey) { if (taggable(i)) flip(pid(i)); return; } select(i.id, i.module); },
  }, ...P.cells(i));
}
export function detailHead(sel) {
  const m = modOf(sel.module || S.page);
  return h('div', { class: 'dhead', style: `--c:${hue(m)}` }, h('span', { class: 'crumb' }, icon(m.icon), m.title), h('span', { class: 'spacer' }),
    h('button', { class: 'icon-btn', onclick: () => select(null) }, icon(I.close)));
}
export const dateLine = (t) => h('div', { class: 'stamp num' }, t);
export const tagLine = (i) => h('div', { class: 'tagline' }, tagsEditor(i));
// A titled part reads as one paragraph: its name in bold, a colon, then the text.
export const titled = (t, html) => (html.startsWith('<p>') ? `<p><strong>${esc(t)}:</strong> ${html.slice(3)}` : `<p><strong>${esc(t)}:</strong></p>${html}`);
export function segEl(options, on, onpick) {
  return h('span', { class: 'seg' }, ...options.map((o) => h('button', { class: o === on ? 'on' : null, onclick: onpick ? () => onpick(o) : null }, o)));
}
const nameOf = (list, v) => (list.find(([id]) => id === v) || list[0] || [v, v])[1];
// A value that opens its choices below it; the list closes the way the tag popup does.
export function pick(list, value, onpick) {
  const b = h('button', { class: 'btn pick', 'data-tagbtn': '1' }, nameOf(list, value), icon(I.down));
  b.onclick = (e) => {
    e.stopPropagation(); closePops();
    const pop = h('div', { class: 'pop', id: 'tagPop' }, ...list.map(([id, name]) => h('div', { class: 'pi', onclick: () => { closePops(); onpick(id); renderMain(); } }, h('span', { class: `chk${id === value ? ' on' : ''}` }), name)));
    document.body.append(pop);
    const r = b.getBoundingClientRect(); pop.style.left = `${Math.min(r.left, innerWidth - 260)}px`; pop.style.top = `${r.bottom + 4}px`;
  };
  return b;
}
export const sw = (on, onflip) => h('span', { class: `switch${on ? ' on' : ''}`, onclick: (e) => { e.currentTarget.classList.toggle('on'); if (onflip) onflip(e.currentTarget.classList.contains('on')); } });
export const frow = (l, v) => h('div', { class: 'frow' }, l, h('span', { class: 'v' }, v));
// Destructive actions ask here, anchored to the button that would do it.
export function confirmPop(anchor, question, onyes) {
  closePops();
  anchor.setAttribute('data-tagbtn', '1');   // the click that opened this must not also close it
  const pop = h('div', { class: 'pop pin-pop', id: 'tagPop' }, h('span', { style: 'flex:1;min-width:0' }, question),
    h('button', { class: 'btn danger', onclick: () => { closePops(); onyes(); } }, icon(I.check)));
  document.body.append(pop);
  const r = anchor.getBoundingClientRect(); pop.style.left = `${Math.max(8, Math.min(r.left, innerWidth - 310))}px`; pop.style.top = `${r.bottom + 6}px`;
}

// ---- pages ----------------------------------------------------------------------------------------
const PAGES = {};
export function registerPages(map) { Object.assign(PAGES, map); }
// The cross-module tag page is the generic renderer fed by /api/items; no module owns it.
const TAG_PAGE = {
  cols: '18px minmax(0,1fr) 164px',
  chips: ['All'],
  async load() {
    const tags = [S.page.slice(4), ...S.tokens.filter((t) => t.kind === 'tag' && t.value !== S.page.slice(4)).map((t) => t.value)];
    const d = await get(`/api/items?tags=${encodeURIComponent(tags.join(','))}`);
    return { items: d.items || [] };
  },
  filter: (l) => l,
  groups: (list) => rail().map((m) => ({ label: m.title, mod: m, rows: list.filter((i) => i.module === m.id) })).filter((g) => g.rows.length),
  cells: (i) => [chk(i), titleCell(i), stampCell(i), acts(i, [tagAct(i)])],
  detail: (i, d) => (PAGES[i.module] && PAGES[i.module].detail ? PAGES[i.module].detail(i, d) : null),
};
const configOf = (page) => (page.startsWith('tag:') ? TAG_PAGE : PAGES[page] || null);
const rows = () => (S.data && S.data.items) || [];
const picked = () => rows().filter((i) => S.picked.has(pid(i)));
const isSel = (i) => String(i.id) === String(S.sel) && (!S.selMod || !i.module || i.module === S.selMod);
function selection() {
  if (S.sel === null || S.sel === undefined) return null;
  if (S.item && isSel(S.item)) return S.item;
  return rows().find(isSel) || { id: S.sel, module: S.selMod || undefined };
}

// ---- data -------------------------------------------------------------------------------------------
let bootRev = null, timer = null, every = 0;
async function loadShell() {
  try {
    const shell = await get('/api/shell');
    if (bootRev && shell.rev !== bootRev) { location.reload(); return null; }   // the daemon restarted on new code: this window runs the old pages
    bootRev = shell.rev;
    S.shell = shell; S.error = null;
    const ms = Math.max(5, Number(settingOf('ui.refresh_seconds', 30))) * 1000;
    if (ms !== every) { every = ms; clearInterval(timer); timer = setInterval(() => refresh(true), ms); }
    return shell;
  } catch (e) {
    S.error = `daemon unreachable: ${e.message}`;
    return null;
  }
}
async function loadPulse() {
  try {
    const [health, tasks] = await Promise.all([get('/health'), get('/api/tasks')]);   // health is the daemon's own route, outside /api
    const last = tasks.map((t) => t.last_run).filter(Boolean).sort().pop() || null;
    S.pulse = { synced: last, running: (health.running || []).length };
  } catch { S.pulse = null; }
}
async function loadTags() { try { S.tags = (await get('/api/tags')).map((t) => ({ ...t, mods: t.modules || t.mods || [] })); } catch { /* the header already carries the failure */ } }
// The open row, fetched whole. The row itself says which module owns it, so an id two modules share is not ambiguous.
async function loadItem() {
  const row = rows().find(isSel);
  if (!row) return;                                  // a tile or a row the page made itself: everything is already here
  if (row.local) { S.item = row; renderMain(); return; }
  const id = row.id, mod = row.module || S.page;
  try {
    const item = await get(`/api/${mod}/item/${encodeURIComponent(id)}`);
    if (isSel({ ...item, id, module: mod })) { S.item = { module: mod, ...item }; renderMain(); }
  } catch (e) { S.error = e.message; renderTop(); }
}
// Opens or closes the pane. The row is shown at once and the heavy fields land when the daemon answers.
export function select(id, module) {
  const same = String(S.sel) === String(id) && (module || null) === S.selMod;
  if (id === null || same) { S.sel = null; S.selMod = null; S.item = null; }
  else { S.sel = id; S.selMod = module || null; S.item = null; loadItem(); }
  S.cursor = listRows().findIndex((r) => r.dataset.id === String(S.sel));
  renderMain(); renderChat(); remember();
}
// Reloads the open page and re-renders. On the timer it waits while something in the page is being typed into.
export async function refresh(fromTimer) {
  const page = S.page;
  const P = configOf(page);
  await Promise.all([loadShell(), loadPulse(), loadTags()]);
  if (P && P.load) {
    try { const data = await P.load({ q: S.q, tokens: S.tokens.map((t) => ({ ...t })) }); if (S.page === page) { S.data = data; S.error = null; } }
    catch (e) { S.error = e.message; }
  } else if (S.page === page && !S.data) S.data = {};
  if (fromTimer && typing()) { renderTop(); return; }
  renderMain(); renderChat(); renderTop();
  call(drawer, 'sync');   // a turn a page action started lands in the newest tab, and the strip's labels catch up
  if (S.sel !== null && !S.item) loadItem();
}
const typing = () => { const a = document.activeElement; return !!a && ['INPUT', 'TEXTAREA'].includes(a.tagName) && !!a.closest('#main'); };

// ---- main ------------------------------------------------------------------------------------------
export function renderAll() { renderTop(); renderNav(); renderMain(); renderChat(); }
// A page builds one toolbar: its title first, then any summary, then a spacer, then its controls. The shell seats the
// title left of the search bar and the controls right of it; what remains is the summary, the first row of main.
export function renderMain() {
  renderMainPage();
  const bar = $('#main .toolbar'), title = $('#pageTitle'), tools = $('#pageTools');
  title.replaceChildren(); tools.replaceChildren();
  if (bar) {
    const h1 = bar.querySelector(':scope > h1');
    if (h1) title.append(h1);
    const sp = bar.querySelector(':scope > .spacer');
    if (sp) { let n = sp.nextSibling; while (n) { const next = n.nextSibling; tools.append(n); n = next; } sp.remove(); }
    if (!bar.childNodes.length) bar.remove();
  }
  const c = $('#main .content.split');
  if (c) c.append(h('div', { class: 'grip', onmousedown: startSplitDrag }));
  clampChat();
}
export function renderMainPage() {
  const main = $('#main'), page = S.page;
  document.documentElement.style.setProperty('--m', ['home', 'settings', 'activity'].includes(page) || page.startsWith('tag:') ? NEUTRAL : hue(page));   // the rainbow theme's wash
  const P = configOf(page);
  const m = modOf(page);
  if (!P) { put(main, h('div', { class: 'toolbar' }, h('h1', { style: `--c:${hue(m)}` }, icon(m.icon), m.title))); return; }
  const data = S.data;
  const chip = S.chip[page] || (P.chips || ['All'])[0];
  const seg = S.seg[page] || (P.seg ? P.seg[0] : null);
  const toolbar = h('div', { class: 'toolbar' },
    page.startsWith('tag:') ? tagHead(page.slice(4)) : h('h1', { style: `--c:${hue(m)}` }, icon(m.icon), m.title),
    data && P.summary ? P.summary(data) : null,
    h('span', { class: 'spacer' }),
    P.seg ? segEl(P.seg, seg, (s) => { S.seg[page] = s; renderMain(); }) : null,
    P.chips && P.chips.length > 1 ? segEl(P.chips, chip, (c) => { S.chip[page] = c; S.cursor = -1; renderMain(); }) : null,
    ...(data && P.tools ? P.tools(data) : []));
  if (!data) { put(main, toolbar, h('div', { class: 'content' }, h('div', { class: 'list', id: 'list' }))); return; }

  let list = applyTokens(rows());
  list = P.filter ? P.filter(list, chip) : list;
  const sel = selection();
  const cols = sel && P.detail && P.colsSplit ? P.colsSplit : P.cols;
  const listEl = h('div', { class: 'list', id: 'list' }, P.above ? P.above(data) : null);
  if (P.alt && seg && P.seg && seg !== P.seg[0]) listEl.append(P.alt(data));
  else {
    if (!list.length) listEl.append(h('div', { class: 'empty' }, S.tokens.length || S.q ? 'Nothing matches this filter.' : 'Nothing here yet.'));
    for (const g of (P.groups ? P.groups(list) : [{ label: '', rows: list }])) listEl.append(card(g.label, g.rows.length, g.rows.map((i) => rowEl(i, P, cols)), g.mod));
  }
  const detailEl = h('div', { class: 'detail', id: 'detail' });
  if (sel && P.detail) { const body = P.detail(sel, data); if (body) detailEl.append(detailHead(sel), h('div', { class: 'dbody' }, ...[body].flat(Infinity).filter(Boolean))); }
  put(main, toolbar, bulkBar(P), h('div', { class: `content${detailEl.childNodes.length ? ' split' : ''}` }, listEl, detailEl));
}
// The tag page's title: the tag, and the tags its items most often carry as well.
function tagHead(tag) {
  const near = {};
  for (const i of rows()) for (const o of tagsOf(i)) if (o !== tag) near[o] = (near[o] || 0) + 1;
  return [h('h1', { style: '--c:var(--ink-2)' }, `#${tag}`),
    Object.keys(near).length ? h('span', { class: 'rel' }, 'Often with', ...Object.entries(near).sort((a, b) => b[1] - a[1]).slice(0, 4).map(([n]) => tagEl(n))) : null];
}
function bulkBar(P) {
  if (!S.picked.size) return null;
  const on = picked();
  return h('div', { class: 'bulk' }, h('strong', null, `${S.picked.size} selected`),
    h('button', { title: 'Tag', class: 'ico btn', 'data-tagbtn': '1', onclick: (e) => openTagPop(e.currentTarget, on) }, icon(I.tag)),
    ...(P.bulk ? P.bulk(on) : []),
    h('button', { class: 'btn quiet', onclick: () => { S.picked.clear(); renderMain(); } }, 'Clear'));
}

// ---- zones and keyboard ------------------------------------------------------------------------------
// Four zones, left to right: the rail, the list, the open page, the agent. Left and right step between them;
// up, down and Enter act inside one. Where the keyboard stands is shown by a lift, never a ring.
const ZONES = ['nav', 'list', 'detail', 'tabs', 'chat'];
const navItems = () => [...document.querySelectorAll('.nav .nav-item')];
export const tabEls = () => [...document.querySelectorAll('.chat .tabs .tab')];
function paintNav() { navItems().forEach((it, i) => it.classList.toggle('kb', S.zone === 'nav' && i === S.navCursor)); paintTabs(); }
// The tabs are the drawer's, the keyboard's place among them is core's: the drawer calls this after a redraw of its own.
export function paintTabs() { tabEls().forEach((t, i) => t.classList.toggle('kb', S.zone === 'tabs' && i === S.tabCursor)); }
export function listRows() { return [...document.querySelectorAll('#list .row[data-id]')]; }
function tabStep(d) {
  const next = (S.tabCursor ?? 0) + d;
  if (next < 0) { enterZone(S.sel ? 'detail' : 'list'); return; }
  if (next >= tabEls().length) { enterZone('chat'); return; }
  S.tabCursor = next; paintTabs();
}
export function enterZone(z) {
  S.zone = z;
  const active = document.activeElement; if (active && active !== document.body && z !== 'chat') active.blur();
  if (z === 'nav') { if (S.navCursor == null) S.navCursor = 0; }
  else if (z === 'list') { const r = listRows(); if (r.length && S.cursor < 0) move(r, 1); }
  else if (z === 'detail') { const d = $('#detail'); const f = d && d.querySelector('.dbody textarea, .dbody input, .dbody button'); if (f) f.focus(); else if (d) { d.tabIndex = -1; d.focus(); } }
  else if (z === 'tabs') { openDrawer(); S.tabCursor = Math.max(0, tabEls().findIndex((t) => t.classList.contains('on'))); }   // the open tab, as the drawer drew it
  else if (z === 'chat') { openDrawer(); call(drawer, 'focus'); }
  paintNav();
}
function zoneStep(d) {
  const target = ZONES[Math.max(0, Math.min(ZONES.length - 1, ZONES.indexOf(S.zone || 'list') + d))];
  if (target === 'detail' && S.sel === null) { const r = listRows(); if (!r.length) return; S.cursor = Math.max(0, S.cursor); select(r[S.cursor].dataset.id); }
  enterZone(target);
}
function openDrawer() { if (S.chat !== 'open') { S.chat = 'open'; renderTop(); renderChat(); } }
function move(list, d) {
  if (!list.length) return;
  S.cursor = Math.max(0, Math.min(list.length - 1, (S.cursor < 0 ? (d > 0 ? -1 : list.length) : S.cursor) + d));
  select(list[S.cursor].dataset.id);
  const again = listRows()[S.cursor]; if (again) again.scrollIntoView({ block: 'nearest' });
}
// The frame's shortcuts are everywhere; a page's own come from its `keys` and are listed only under ?.
const pageKeys = () => { const P = configOf(S.page); return (P && P.keys) || []; };
function bindKeys() {
  document.addEventListener('keydown', (e) => {
    const inField = ['INPUT', 'TEXTAREA'].includes(e.target.tagName);
    if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'k') { e.preventDefault(); openPalette(); return; }
    if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'j') { e.preventDefault(); toggleChat(); if (S.chat === 'open') askAgent(); return; }
    if ((e.ctrlKey || e.metaKey) && e.shiftKey && e.code === 'Space') { e.preventDefault(); S.tokens = []; if (S.page.startsWith('tag:')) refresh(); else renderAll(); return; }
    if ((e.ctrlKey || e.metaKey) && e.code === 'Space') { e.preventDefault(); $('#omniInput').focus(); return; }
    if (e.altKey && (e.key === 'ArrowLeft' || e.key === 'ArrowRight')) { e.preventDefault(); histGo(e.key === 'ArrowLeft' ? -1 : 1); return; }
    if (e.key === 'Escape') {
      if (S.point) { togglePoint(false); return; }
      if (!$('#paletteScrim').hidden) { closePalette(); return; }
      if (!$('#helpScrim').hidden) { $('#helpScrim').hidden = true; return; }
      if ($('#tagPop')) { closePops(); return; }
      if (inField) { e.target.blur(); return; }
      if (S.page === 'graph' && (S.gpreview || S.tokens.some((t) => t.kind === 'tag'))) { if (S.gpreview) { S.gpreview = null; renderMain(); } else { S.tokens = S.tokens.filter((t) => t.kind !== 'tag'); renderAll(); } return; }
      if (S.sel !== null) { select(null); return; }
      if (S.picked.size) { S.picked.clear(); renderMain(); return; }
      return;
    }
    const plain = !inField && !e.ctrlKey && !e.metaKey && !e.altKey;
    if (plain && S.zone === 'tabs') {
      if (e.key === 'ArrowRight' || e.key === 'ArrowLeft') { e.preventDefault(); tabStep(e.key === 'ArrowRight' ? 1 : -1); return; }
      if (e.key === 'Enter') { e.preventDefault(); if (S.tabCursor >= tabEls().length - 1) { call(drawer, 'newChat'); S.zone = 'chat'; } else call(drawer, 'pickTab', S.tabCursor); return; }
      if (e.key === 'F2') { e.preventDefault(); call(drawer, 'renameTab', S.tabCursor); return; }
      if (e.key === 'Delete') { e.preventDefault(); call(drawer, 'closeChat', S.tabCursor); S.tabCursor = Math.max(0, Math.min(S.tabCursor, tabEls().length - 1)); paintTabs(); return; }
    }
    if (plain && (e.key === 'ArrowLeft' || e.key === 'ArrowRight')) { e.preventDefault(); zoneStep(e.key === 'ArrowRight' ? 1 : -1); return; }
    if (plain && S.zone === 'nav') {
      const items = navItems();
      if (e.key === 'ArrowDown' || e.key === 'j') { e.preventDefault(); S.navCursor = Math.min(items.length - 1, (S.navCursor ?? -1) + 1); paintNav(); return; }
      if (e.key === 'ArrowUp' || e.key === 'k') { e.preventDefault(); S.navCursor = Math.max(0, (S.navCursor ?? 1) - 1); paintNav(); return; }
      if (e.key === 'Enter') { e.preventDefault(); const it = items[S.navCursor ?? 0]; if (it) { it.click(); enterZone('list'); } return; }
    }
    if (!plain) return;
    const list = listRows(), k = e.key;
    if (k === 'o') { e.preventDefault(); togglePoint(); }
    else if (k === '/') { e.preventDefault(); openPalette(); }
    else if (k === '?') { e.preventDefault(); openHelp(); }
    else if (k === 'c') { e.preventDefault(); openDrawer(); call(drawer, 'newChat'); }
    else if (k === 'C') { e.preventDefault(); openDrawer(); call(drawer, 'reopenChat'); }
    else if (k === 'Delete') { e.preventDefault(); if (S.chat === 'open') call(drawer, 'closeChat'); }
    else if (k === '[') { e.preventDefault(); toggleNav(); }
    else if (k === ']') { e.preventDefault(); toggleChat(); }
    else if (k === 'j' || k === 'ArrowDown') { e.preventDefault(); move(list, 1); }
    else if (k === 'k' || k === 'ArrowUp') { e.preventDefault(); move(list, -1); }
    else if (k === 'Enter') { const r = list[S.cursor]; if (r) { if (String(S.sel) === r.dataset.id) zoneStep(1); else select(r.dataset.id); } }
    else if (k === 'x') { e.preventDefault(); const r = list[S.cursor]; const i = r && rows().find((x) => pid(x) === r.dataset.id); if (r && (!i || taggable(i))) flip(r.dataset.id); }
    else if (k === 't') { e.preventDefault(); const r = list[S.cursor] || (S.sel !== null && $(`.row[data-id="${S.sel}"]`)); const on = (S.picked.size ? picked() : rows().filter((i) => pid(i) === (r && r.dataset.id))).filter(taggable); if (r && on.length) openTagPop(r, on); }
    else if (k === 'a') { e.preventDefault(); askAgent(); }
    else {
      const hit = pageKeys().find(([, key]) => key === k);
      if (hit) { e.preventDefault(); hit[2](selection(), S.data); }
    }
  });
  document.addEventListener('click', (e) => { if (!e.target.closest('#tagPop') && !e.target.closest('[data-tagbtn]')) closePops(); });
}

// ---- palette and help ---------------------------------------------------------------------------------
let palCursor = 0;
function paletteRows(q) {
  q = q.toLowerCase();
  const ag = currentAgent();
  const skills = (ag.skills || []).filter((s) => !q || `/${s}`.includes(q)).map((s) => ({ group: 'Skills', label: `/${s}`, c: hue(ag), svg: I.chat, run: () => useSkill(s) }));
  if (q.startsWith('/')) return skills;
  const acts = [
    ['Point at anything', () => togglePoint(true)],
    ['Add to Quick access', openPinPop],
    ['Ask the agent about the selection', askAgent],
    ['New chat', () => { openDrawer(); call(drawer, 'newChat'); }],
    ['Close the chat', () => call(drawer, 'closeChat')],
    ['Back a page', () => histGo(-1)],
    ['Toggle agent drawer', toggleChat], ['Toggle navigation', toggleNav], ['Toggle theme', toggleTheme], ['Keyboard shortcuts', openHelp],
    ...pageKeys().map(([label, , fn]) => [label, () => fn(selection(), S.data)]),
  ].filter(([l]) => !q || l.toLowerCase().includes(q)).map(([label, run]) => ({ group: 'Actions', label, svg: I.cmd, run }));
  const gotos = allMods().filter((m) => !m.error && (!q || m.title.toLowerCase().includes(q))).map((m) => ({ group: 'Go to', label: m.title, c: hue(m), svg: m.icon, run: () => go(m.id) }));
  const tags = allTags().filter((t) => !q || t.tag.includes(q.replace('#', ''))).slice(0, 6).map((t) => ({ group: '', label: `#${t.tag}`, svg: I.tag, run: () => go(`tag:${t.tag}`) }));
  const items = q.length > 1 ? rows().filter((i) => itemText(i).includes(q)).slice(0, 8).map((i) => ({ group: '', label: i.title, c: hue(i.module || S.page), svg: modOf(i.module || S.page).icon, run: () => select(i.id) })) : [];
  return [...acts.slice(0, q ? 8 : 4), ...skills.slice(0, q ? 8 : 3), ...gotos, ...tags, ...items];
}
// A skill lands in the composer as the drawer's draft, so a redraw keeps it.
function useSkill(s) { openDrawer(); call(drawer, 'setDraft', `/${s} `); }
// `q` opens the palette already narrowed: the drawer passes '/' when the composer's first character is one.
export function openPalette(q) { const sc = $('#paletteScrim'); sc.hidden = false; palCursor = 0; const inp = $('#palInput'); inp.value = q || ''; inp.focus(); renderPalette(); }
function closePalette() { $('#paletteScrim').hidden = true; }
function renderPalette() {
  const list = $('#palList');
  list.replaceChildren();
  let group = null;
  paletteRows($('#palInput').value.trim()).forEach((r, i) => {
    if (r.group !== group) { group = r.group; if (group) list.append(h('div', { class: 'ph' }, group)); }
    list.append(h('div', { class: `pi${i === palCursor ? ' on' : ''}`, style: r.c ? `--c:${r.c}` : null, onmouseenter: () => { palCursor = i; renderPalette(); }, onclick: () => { closePalette(); r.run(); } }, icon(r.svg), h('span', null, r.label)));
  });
  const on = $('.pi.on', list); if (on) on.scrollIntoView({ block: 'nearest' });
}
// The one place keys are listed.
const KEYS_GLOBAL = [['Rail, list, page, chats, agent', '← →'], ['A chat: pick, rename, close', '↵ F2 Del'], ['Command palette', '/'], ['Search', 'Ctrl+Space'], ['Pick a suggestion', '↑ ↓ ↵'], ['Clear the search', 'Ctrl+Shift+Space'], ['Point at anything', 'o'], ['Next, previous row', 'j k'], ['Open, close', '↵ esc'], ['Select a row', 'x'], ['Tag the row', 't'], ['Ask about it', 'a'], ['New chat, reopen last', 'c C'], ['Close the chat', 'Del'], ['Back, forward', 'Alt+← Alt+→'], ['Navigation rail', '['], ['Agent drawer', ']'], ['This list', '?']];
function openHelp() {
  const grid = (rows) => h('div', { class: 'grid' }, ...rows.map(([l, k]) => h('div', null, l, h('span', null, ...k.split(' ').map((x) => h('kbd', null, x))))));
  const pk = pageKeys().map(([label, key]) => [label, key]);
  put($('#helpBox'), h('h3', null, 'Keyboard, everywhere'), grid(KEYS_GLOBAL), pk.length ? [h('h3', { style: 'margin-top:18px' }, `On ${pageTitle()}`), grid(pk)] : null);
  $('#helpScrim').hidden = false;
}

// ---- boot --------------------------------------------------------------------------------------------
export async function boot() {
  try { for (const n of ['--chatw', '--listw']) { const v = localStorage.getItem(`otto-next${n}`); if (v) document.documentElement.style.setProperty(n, `${v}px`); } } catch { /* private window */ }
  try { const q = JSON.parse(localStorage.getItem('otto-next-quick') || 'null'); if (Array.isArray(q) && q.every((x) => x && x.page && Array.isArray(x.tokens))) S.quick = q; } catch { /* as above */ }
  try {
    if (localStorage.getItem('otto-next-theme') === 'dark') document.documentElement.dataset.theme = 'dark';
    const p = JSON.parse(localStorage.getItem('otto-next-pins') || 'null');   // the name Quick access had before
    if (Array.isArray(p)) { for (const t of p) if (!S.quick.some((q) => tagEntry(q) && q.tokens[0].value === t)) S.quick.push({ title: t, page: `tag:${t}`, tokens: [{ kind: 'tag', value: t }] }); localStorage.removeItem('otto-next-pins'); saveQuick(); }
  } catch { /* as above */ }
  clampChat();
  $('#pinBtn').replaceChildren(icon(I.bookmark));
  $('#pinBtn').addEventListener('click', openPinPop);
  $('#themeBtn').addEventListener('click', toggleTheme);
  $('#chatBtn').addEventListener('click', toggleChat);
  $('#navBtn').addEventListener('click', toggleNav);
  $('#palBtn').addEventListener('click', () => openPalette());   // the click event must not land in the palette's box
  $('#helpBtn').addEventListener('click', openHelp);
  $('#pointBtn').addEventListener('click', () => togglePoint());
  $('#chat').addEventListener('click', (e) => { if (!e.target.closest('button, a, input, textarea, .grip')) call(drawer, 'focus'); });
  $('#paletteScrim').addEventListener('mousedown', (e) => { if (e.target === e.currentTarget) closePalette(); });
  $('#helpScrim').addEventListener('mousedown', (e) => { if (e.target === e.currentTarget) e.currentTarget.hidden = true; });
  $('#palInput').addEventListener('input', () => { palCursor = 0; renderPalette(); });
  $('#palInput').addEventListener('keydown', (e) => {
    const list = paletteRows(e.target.value.trim());
    if (e.key === 'ArrowDown') { e.preventDefault(); palCursor = Math.min(list.length - 1, palCursor + 1); renderPalette(); }
    if (e.key === 'ArrowUp') { e.preventDefault(); palCursor = Math.max(0, palCursor - 1); renderPalette(); }
    if (e.key === 'Enter') { if (!e.target.value.trim() && palCursor === 0) { closePalette(); return; } const r = list[palCursor]; if (r) { closePalette(); r.run(); } }
  });
  document.addEventListener('mousedown', (e) => {
    const t = e.target.closest('.chat .tab');
    const z = e.target.closest('#nav') ? 'nav' : t ? 'tabs' : e.target.closest('#chat') ? 'chat' : e.target.closest('#detail') ? 'detail' : e.target.closest('#list') ? 'list' : null;
    if (t) S.tabCursor = tabEls().indexOf(t);
    if (z) { S.zone = z; paintNav(); }
  });
  inflight.listeners.add(() => renderPulse());
  bindOmni(); bindKeys();
  let shell = await loadShell();
  while (!shell) { renderTop(); await new Promise((r) => setTimeout(r, 5000)); shell = await loadShell(); }   // no daemon, no content: the header says so and the window keeps asking
  const hash = (location.hash.match(/^#\/(.+)$/) || [])[1];
  S.page = known(hash) ? hash : settingOf('ui.start_page', 'home');
  renderAll();
  remember();
  await refresh();
}
