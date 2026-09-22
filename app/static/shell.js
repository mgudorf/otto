// Shell: the zones and the keyboard, the command palette, the key list, the layout setting, history, the grips, and boot.
import { S, ITEMS, ORDER, $, h, put, icon, I, toast, modOf, hue, allTags, itemText, visible, listRows, select, currentItem, itemOf, renderAll, renderFeed, renderTop, renderPanel,
  addToken, clearTokens, setMode, remember, restore, doVerb, DESTRUCTIVE, flipPick, pickedItems, openTagPop, closePops, setEdit, bindOmni, setLook, dark, tokenText,
  askAgent, openDrawer, toggleChat, toggleView, togglePoint, applyLayout, saveLayout, call, parts, registerShell, isFixed, loadShell, load } from './core.js';
import { post, inflight } from './api.js';

// ---- sections: the brain, the feed, the page, the drawer; h l step between them, j k move inside one, ↵ acts on the place ------
const ZONES = () => (S.view === 'inspect' ? (currentItem() ? ['feed', 'page', 'drawer'] : ['feed', 'drawer']) : ['graph', 'feed', 'drawer']);
const tabEls = () => [...document.querySelectorAll('.chat .tabs .tab')];
export function paintZones() {
  const brainBox = $('#brain'); if (brainBox) brainBox.classList.toggle('kb', S.zone === 'graph');
  tabEls().forEach((t, i) => t.classList.toggle('kb', S.zone === 'drawer' && i === S.tabCursor));
  const plate = $('#chat .plate'); if (plate) plate.classList.toggle('kb', S.zone === 'drawer');
  const page = $('#page .plate'); if (page) page.classList.toggle('kb', S.zone === 'page');
  document.querySelectorAll('#feed .card').forEach((c) => c.classList.toggle('kb', S.zone === 'feed' && (c.classList.contains('mod') || !!c.querySelector('.row.sel'))));
  listRows().forEach((r, i) => r.classList.toggle('kb', S.zone === 'feed' && i === S.cursor));   // where the keyboard stands, apart from what is open
}
export function enterZone(z) {
  if (z === 'page' && !currentItem()) z = 'feed';
  if (z === 'graph' && S.view !== 'brain') { S.view = 'brain'; renderAll(); }
  if (z === 'page' && S.view !== 'inspect') { S.view = 'inspect'; renderAll(); }
  S.zone = z;
  const active = document.activeElement; if (active && active !== document.body) active.blur();
  if (z === 'graph') { if (S.gcursor < 0) S.gcursor = 0; }
  else if (z === 'feed') { if (S.cursor < 0 && listRows().length) S.cursor = 0; }
  else if (z === 'page') { const p = $('#page .plate'); if (p) p.focus({ preventScroll: true }); }
  else if (z === 'drawer') { openDrawer(); S.tabCursor = Math.max(0, tabEls().findIndex((t) => t.classList.contains('on'))); }
  paintZones(); call(parts().brain, 'sync');
}
function zoneStep(d) { const zs = ZONES(); enterZone(zs[Math.max(0, Math.min(zs.length - 1, Math.max(0, zs.indexOf(S.zone || 'feed')) + d))]); }
// j and k move the keyboard's place only; Enter or a click opens what it stands on.
function moveRow(d) {
  const rows = listRows(); if (!rows.length) return;
  S.cursor = Math.max(0, Math.min(rows.length - 1, (S.cursor < 0 ? (d > 0 ? -1 : rows.length) : S.cursor) + d));
  paintZones();
  rows[S.cursor].scrollIntoView({ block: 'nearest' });
}
// The drawer's places, top to bottom: the + tab, each session's tab, then the composer, which takes the keyboard when reached.
const composerAt = () => tabEls().length;
function moveDrawer(d) {
  S.tabCursor = Math.max(0, Math.min(composerAt(), (S.tabCursor || 0) + d));
  if (S.tabCursor === composerAt()) call(parts().drawer, 'focus'); else { const a = document.activeElement; if (a && a !== document.body) a.blur(); }
  paintZones();
}
export function atComposer() { openDrawer(); S.zone = 'drawer'; S.tabCursor = composerAt(); paintZones(); }
export function leaveComposer() { S.zone = 'drawer'; S.tabCursor = composerAt(); moveDrawer(-1); }
const cursorItem = () => { const r = S.zone === 'feed' ? listRows()[S.cursor] : null; return (r ? itemOf(r.dataset.id) : null) || currentItem(); };
const deleteVerb = (i) => (i.verbs || []).map(([v]) => v).find((v) => ['delete', 'forget', 'trash', 'dismiss'].includes(v));

// ---- keys --------------------------------------------------------------------------------------------------------
function bindKeys() {
  document.addEventListener('keydown', (e) => {
    const inField = ['INPUT', 'TEXTAREA'].includes(e.target.tagName);
    if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'k') { e.preventDefault(); openPalette(); return; }
    if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'j') { e.preventDefault(); toggleChat(); if (S.chat === 'open') { askAgent(); atComposer(); } return; }
    if ((e.ctrlKey || e.metaKey) && e.shiftKey && e.code === 'Space') { e.preventDefault(); clearTokens(); return; }
    if ((e.ctrlKey || e.metaKey) && e.code === 'Space') { e.preventDefault(); $('#omniInput').focus(); return; }
    if (e.altKey && (e.key === 'ArrowLeft' || e.key === 'ArrowRight')) { e.preventDefault(); try { history.go(e.key === 'ArrowLeft' ? -1 : 1); } catch { /* sandboxed */ } return; }
    if (e.key === 'Escape') {
      if (S.point) { togglePoint(false); return; }
      if (!$('#paletteScrim').hidden) { closePalette(); return; }
      if (!$('#helpScrim').hidden) { $('#helpScrim').hidden = true; return; }
      if ($('#tagPop')) { closePops(); return; }
      if (inField) { e.target.blur(); return; }
      if (S.edit !== null) { S.edit = null; renderAll(); return; }
      if (S.open !== null) { select(null); if (S.zone === 'page') S.zone = 'feed'; return; }
      if (S.picked.size) { S.picked.clear(); renderFeed(); return; }
      if (S.tokens.length || S.q) { clearTokens(); return; }
      return;
    }
    const plain = !inField && !e.ctrlKey && !e.metaKey && !e.altKey;
    if (plain && S.zone === 'drawer') {
      if (e.key === 'j' || e.key === 'ArrowDown') { e.preventDefault(); moveDrawer(1); return; }
      if (e.key === 'k' || e.key === 'ArrowUp') { e.preventDefault(); moveDrawer(-1); return; }
      // The strip's first tab is the +; a session's index is one less than its tab's.
      if (e.key === 'Enter') { e.preventDefault(); if (S.tabCursor <= 0) { call(parts().drawer, 'newChat'); atComposer(); } else if (S.tabCursor < composerAt()) call(parts().drawer, 'pickTab', S.tabCursor - 1); return; }
      if (e.key === 'F2') { e.preventDefault(); if (S.tabCursor > 0 && S.tabCursor < composerAt()) call(parts().drawer, 'renameTab', S.tabCursor - 1); return; }
      if (e.key === 'Delete') { e.preventDefault(); if (S.tabCursor > 0 && S.tabCursor < composerAt()) call(parts().drawer, 'closeChat', S.tabCursor - 1); else if (S.tabCursor === composerAt()) call(parts().drawer, 'closeChat'); S.tabCursor = Math.max(0, Math.min(S.tabCursor, composerAt())); paintZones(); return; }
    }
    if (plain && (e.key === 'h' || e.key === 'l' || e.key === 'ArrowLeft' || e.key === 'ArrowRight')) { e.preventDefault(); zoneStep(e.key === 'l' || e.key === 'ArrowRight' ? 1 : -1); return; }
    if (!plain) return;
    const k = e.key;
    if (S.zone === 'graph') {
      if (k === 'j' || k === 'ArrowDown') { e.preventDefault(); call(parts().brain, 'step', 1); return; }
      if (k === 'k' || k === 'ArrowUp') { e.preventDefault(); call(parts().brain, 'step', -1); return; }
      if (k === 'Enter') { e.preventDefault(); call(parts().brain, 'pick'); return; }
      if (k === 'm') { e.preventDefault(); call(parts().brain, 'togglePin'); return; }
    }
    if (S.zone === 'page' && (k === 'j' || k === 'k' || k === 'ArrowDown' || k === 'ArrowUp')) { e.preventDefault(); const p = $('#page'); if (p) p.scrollBy({ top: k === 'j' || k === 'ArrowDown' ? 80 : -80 }); return; }
    if (/^[1-9]$/.test(k)) { e.preventDefault(); call(parts().brain, 'pinKey', Number(k)); return; }
    if (k === 'o') { e.preventDefault(); togglePoint(); }
    else if (k === '/') { e.preventDefault(); openPalette(); }
    else if (k === '?') { e.preventDefault(); openHelp(); }
    else if (k === 'c') { e.preventDefault(); openDrawer(); call(parts().drawer, 'newChat'); atComposer(); }
    else if (k === 'C') { e.preventDefault(); openDrawer(); call(parts().drawer, 'reopenChat'); }
    else if (k === '[') { e.preventDefault(); toggleView(); if (S.zone === 'graph' && S.view !== 'brain') S.zone = 'feed'; if (S.zone === 'page' && S.view !== 'inspect') S.zone = 'feed'; paintZones(); }
    else if (k === ']') { e.preventDefault(); toggleChat(); }
    else if (k === 'p') { e.preventDefault(); setMode('Priority'); }
    else if (k === 'r') { e.preventDefault(); setMode('Recent'); }
    else if (k === 'j' || k === 'ArrowDown') { e.preventDefault(); S.zone = 'feed'; moveRow(1); paintZones(); }
    else if (k === 'k' || k === 'ArrowUp') { e.preventDefault(); S.zone = 'feed'; moveRow(-1); paintZones(); }
    else if (k === 'Enter') { e.preventDefault(); const r = listRows()[S.cursor]; if (r) { const at = S.cursor; select(r.dataset.id); S.cursor = at; paintZones(); } }
    else if (k === 'x') { e.preventDefault(); const i = cursorItem(); if (i && i.taggable !== false) flipPick(i.id); }
    else if (k === 't') { e.preventDefault(); const i = cursorItem(); const on = S.picked.size ? pickedItems() : i ? [i] : []; if (on.length) openTagPop($(`#feed .row[data-id="${on[0].id}"]`) || $('#feed'), on); }
    else if (k === 'a') { e.preventDefault(); askAgent(); atComposer(); }
    else if (k === 'e') { e.preventDefault(); const i = cursorItem(); if (i && (i.verbs || []).some(([v]) => v === 'edit')) setEdit(i.id); else toast('Nothing to edit here'); }
    else if (k === 'n') { e.preventDefault(); S.pointRef = null; if (S.open !== null) select(null); askAgent(''); atComposer(); }
    else if (k === 'Delete') { e.preventDefault(); const i = cursorItem(); const v = i && deleteVerb(i); if (v) doVerb(i, v); }
  });
  document.addEventListener('click', (e) => { if (!e.target.closest('#tagPop') && !e.target.closest('[data-tagbtn]')) closePops(); });
  document.addEventListener('mousedown', (e) => {
    const t = e.target.closest('.chat .tab');
    const z = e.target.closest('#brain') ? 'graph' : e.target.closest('#chat') ? 'drawer' : e.target.closest('#page') ? 'page' : e.target.closest('#feed') ? 'feed' : null;
    if (t) S.tabCursor = tabEls().indexOf(t); else if (e.target.closest('#composer')) S.tabCursor = composerAt();
    if (z) { const was = S.zone; S.zone = z; paintZones(); if (was !== z) call(parts().brain, 'sync'); }
  });
}

// ---- the palette: the open item's verbs first, then the frame's actions, one agent's skills, the facets, tags and items ---------
let palCursor = 0;
const SKILLS = () => (S.shell ? S.shell.modules.filter((m) => m.agent).flatMap((m) => (m.agent.skills || []).map((k) => [k, m.name])) : []);
function paletteRows(q) {
  q = q.toLowerCase();
  const cur = currentItem();
  const verbs = cur ? (cur.verbs || []).filter(([, l]) => !q || l.toLowerCase().includes(q)).map(([v, l]) => ({ group: 'Actions', label: l, svg: modOf(cur.module).icon, c: hue(cur.module), danger: DESTRUCTIVE.has(v), run: () => doVerb(cur, v) })) : [];
  const skills = SKILLS().filter(([s]) => !q || `/${s}`.includes(q)).map(([s, m]) => ({ group: 'Skills', label: `/${s}`, c: hue(m), svg: I.chat, run: () => askAgent(`/${s} `) }));
  if (q.startsWith('/')) return skills;
  const pins = S.tokens.filter((t) => t.kind === 'tag' && !isFixed(t.value)).map((t) => [S.pins.includes(t.value) ? `Unpin #${t.value} from the brain` : `Pin #${t.value} to the brain`, () => call(parts().brain, 'togglePin', t.value)]);
  const acts = [
    ...pins, ['Point at anything', () => togglePoint(true)], ['Ask about it', askAgent],
    ['New chat', () => { openDrawer(); call(parts().drawer, 'newChat'); }], ['Close the chat', () => call(parts().drawer, 'closeChat')],
    ['Priority', () => setMode('Priority')], ['Recent', () => setMode('Recent')],
    ['Settings', openLayoutPop], ['Brain or inspect', () => toggleView()], ['Toggle agent drawer', toggleChat], ['Toggle theme', () => setLook(dark() ? 'rainbow' : 'dark')], ['Keyboard shortcuts', openHelp],
  ].filter(([l]) => !q || l.toLowerCase().includes(q)).map(([label, run]) => ({ group: 'Actions', label, svg: label === 'Settings' ? I.layout : I.cmd, run }));
  const gotos = ORDER.filter((m) => m !== 'otto').map(modOf).filter((m) => !q || m.title.toLowerCase().includes(q))
    .map((m) => ({ group: 'Go to', label: m.title, c: m.hue, svg: m.icon, sub: `@${m.title.toLowerCase()}`, run: () => addToken('mod', m.id) }));
  const tags = allTags().filter((t) => !q || t.tag.includes(q.replace('#', ''))).slice(0, 6).map((t) => ({ group: '', label: `#${t.tag}`, svg: I.tag, run: () => addToken('tag', t.tag) }));
  const items = q.length > 1 ? ITEMS.filter((i) => itemText(i).includes(q)).slice(0, 8).map((i) => ({ group: '', label: i.title, c: hue(i.module), svg: modOf(i.module).icon, run: () => { if (S.mode === 'Priority' && !i.waits) setMode('Recent'); select(i.id); } })) : [];
  return [...verbs, ...acts.slice(0, q ? 8 : 4), ...skills.slice(0, q ? 8 : 3), ...gotos, ...tags, ...items];
}
export function openPalette(q) { const sc = $('#paletteScrim'); sc.hidden = false; palCursor = 0; const inp = $('#palInput'); inp.value = q || ''; inp.focus(); renderPalette(); }
function closePalette() { $('#paletteScrim').hidden = true; }
function renderPalette() {
  const list = $('#palList');
  list.replaceChildren();
  let group = null;
  paletteRows($('#palInput').value.trim()).forEach((r, i) => {
    if (r.group !== group) { group = r.group; if (group) list.append(h('div', { class: 'ph' }, group)); }
    list.append(h('div', { class: `pi${i === palCursor ? ' on' : ''}${r.danger ? ' danger' : ''}`, style: r.c ? `--c:${r.c}` : null, onmouseenter: () => { palCursor = i; renderPalette(); }, onclick: () => { closePalette(); r.run(); } }, icon(r.svg), h('span', null, r.label), r.sub ? h('span', { class: 'sub' }, r.sub) : null));
  });
  const on = $('.pi.on', list); if (on) on.scrollIntoView({ block: 'nearest' });
}

// ---- the one place keys are listed --------------------------------------------------------------------------------
// One shortcut per line, one plain name each. Delete still asks first; the name is just the name.
const KEYS = [
  ['Previous Section', 'h'], ['Next Section', 'l'], ['Move Down', 'j'], ['Move Up', 'k'],
  ['Previous Section', '←'], ['Next Section', '→'], ['Move Down', '↓'], ['Move Up', '↑'],
  ['Open Item', '↵'], ['Close', 'Esc'], ['Select Row', 'x'], ['Tag', 't'], ['Pin Tag', 'm'], ['Pinned Tag', '1–9'], ['Edit', 'e'], ['Delete', 'Del'],
  ['Ask Otto', 'a'], ['New Entry', 'n'], ['Priority', 'p'], ['Recent', 'r'],
  ['Display Mode Toggle', '['], ['Agent Panel Toggle', ']'], ['Command Palette', '/'], ['Point Mode', 'o'],
  ['Search', 'Ctrl+Space'], ['Clear Search', 'Ctrl+Shift+Space'], ['Next Suggestion', '↓'], ['Previous Suggestion', '↑'], ['Pick Suggestion', '↵'],
  ['New Session', 'c'], ['Reopen Session', 'C'], ['Select Session', '↵'], ['Rename Session', 'F2'], ['Close Session', 'Del'],
  ['Send', '↵'], ['New Line', 'Shift+↵'], ['Back', 'Alt+←'], ['Forward', 'Alt+→'], ['Shortcuts', '?'],
];
export function openHelp() {
  put($('#helpBox'), h('h3', null, 'Keyboard, everywhere'), h('div', { class: 'grid' }, ...KEYS.map(([l, k]) => h('div', null, l, h('span', null, h('kbd', null, k))))));
  $('#helpScrim').hidden = false;
}

// ---- settings: the shares Brain mode and Inspect mode give each part, and the brain's turn; the app's Settings page will hold these
function openLayoutPop() {
  closePops();
  const L = S.layout;
  const field = (label, key, min, max) => {
    const inp = h('input', { type: 'number', min: String(min), max: String(max), value: String(L[key]), 'aria-label': label, onkeydown: (e) => e.stopPropagation(), oninput: () => { const v = Number(inp.value); if (v >= min && v <= max) { L[key] = v; applyLayout(); saveLayout(); } } });
    return h('div', { class: 'frow' }, h('span', null, label), inp);
  };
  const pop = h('div', { class: 'pop layout', id: 'tagPop' },
    h('div', { class: 'ph' }, 'Layout'), field('Cards', 'feed', 15, 60), field('Drawer', 'drawer', 10, 40),
    h('div', { class: 'ph' }, 'Brain'), field('Minutes per turn', 'turn', 0, 600));
  document.body.append(pop);
  const r = $('#palBtn').getBoundingClientRect(); pop.style.left = `${Math.max(8, Math.min(r.left - 240, innerWidth - 310))}px`; pop.style.top = `${r.bottom + 6}px`;
  $('input', pop).focus();
}

// ---- the program menu, under the name in the header: the paths to Settings and the app's own chores ---------------------------
function openAppMenu() {
  closePops();
  const brand = $('#brand');
  const row = (label, svg, run) => h('div', { class: 'pi', onclick: () => { closePops(); run(); } }, icon(svg), h('span', null, label));
  const pop = h('div', { class: 'pop menu', id: 'tagPop', role: 'menu' },
    row('Settings', I.layout, openLayoutPop),
    row('Activity', modOf('system').icon, () => addToken('tag', 'routine')),
    h('div', { class: 'rule' }),
    row('Back up now', I.check, () => post('/api/data/backup').then((r) => toast(`Backed up, ${Math.round(r.size_bytes / 1e6)} MB`)).catch((e) => toast(e.message))),
    row('Export', I.up, () => post('/api/data/export').then((r) => toast(`Exported to ${r.path}`)).catch((e) => toast(e.message))),
    h('div', { class: 'rule' }),
    row('Keyboard shortcuts', I.cmd, openHelp),
    row(dark() ? 'Rainbow' : 'Dark', dark() ? I.sun : I.moon, () => setLook(dark() ? 'rainbow' : 'dark')),
    row('About Otto', I.target, () => toast(`Otto, one page. Revision ${(S.shell || {}).rev || '?'}.`)));
  document.body.append(pop);
  const r = brand.getBoundingClientRect(); pop.style.left = `${Math.max(8, r.left)}px`; pop.style.top = `${r.bottom + 6}px`;
  brand.setAttribute('aria-expanded', 'true');
  const watch = new MutationObserver(() => { if (!pop.isConnected) { brand.setAttribute('aria-expanded', 'false'); watch.disconnect(); } });
  watch.observe(document.body, { childList: true });
}

// ---- grips: the drawer's width in px; the brain's share of the width, in whichever mode is on ---------------------------------
function drag(e, onMove) {
  if (e.button !== 0) return;
  e.preventDefault();
  const app = $('.app');
  const move = (ev) => onMove(ev);
  const up = () => { document.removeEventListener('mousemove', move); document.removeEventListener('mouseup', up); app.classList.remove('dragging'); document.body.style.cursor = ''; saveLayout(); };
  app.classList.add('dragging'); document.body.style.cursor = 'col-resize';
  document.addEventListener('mousemove', move); document.addEventListener('mouseup', up);
}
function chatDrag(e) {
  drag(e, (ev) => { const pct = Math.round(Math.max(10, Math.min(40, (innerWidth - ev.clientX) / innerWidth * 100))); S.layout.drawer = pct; applyLayout(); });
}
// The bar between the big panel and the cards sets the cards' share, whichever side the big panel is on.
function navDrag(e) { drag(e, (ev) => { const pct = ev.clientX / innerWidth * 100; S.layout.feed = Math.round(Math.max(15, Math.min(60, 100 - pct - (S.chat === 'open' ? S.layout.drawer : 0)))); applyLayout(); }); }
function pageDrag(e) { drag(e, (ev) => { S.layout.feed = Math.round(Math.max(15, Math.min(60, ev.clientX / innerWidth * 100))); applyLayout(); }); }
registerShell({ chatDrag, navDrag, pageDrag, paintZones });

// ---- boot ---------------------------------------------------------------------------------------------------------------
// Nothing is drawn until the daemon has said what the facets are: the feed groups by them and the brain is built on them.
export async function boot() {
  try {
    if (localStorage.getItem('otto-look') === 'dark') document.documentElement.dataset.look = 'dark';
    const L = JSON.parse(localStorage.getItem('otto-layout') || 'null');
    if (L && ['feed', 'drawer'].every((k) => typeof L[k] === 'number')) S.layout = { turn: 20, feed: L.feed, drawer: L.drawer, ...(typeof L.turn === 'number' ? { turn: L.turn } : {}) };
    const P = JSON.parse(localStorage.getItem('otto-pins') || 'null');
    if (Array.isArray(P)) S.pins = P.filter((t) => typeof t === 'string');
  } catch { /* private window */ }
  $('#themeBtn').addEventListener('click', () => setLook(dark() ? 'rainbow' : 'dark'));
  $('#chatBtn').addEventListener('click', toggleChat);
  $('#navBtn').addEventListener('click', () => toggleView());
  $('#palBtn').addEventListener('click', () => openPalette());
  $('#helpBtn').addEventListener('click', openHelp);
  $('#pointBtn').addEventListener('click', () => togglePoint());
  $('#navGrip').addEventListener('mousedown', navDrag);
  $('#brand').addEventListener('click', () => { if ($('#tagPop.menu')) closePops(); else openAppMenu(); });
  $('#chat').addEventListener('click', (e) => { if (!e.target.closest('button, a, input, textarea, .grip')) call(parts().drawer, 'focus'); });
  $('#paletteScrim').addEventListener('mousedown', (e) => { if (e.target === e.currentTarget) closePalette(); });
  $('#helpScrim').addEventListener('mousedown', (e) => { if (e.target === e.currentTarget) e.currentTarget.hidden = true; });
  $('#palInput').addEventListener('input', () => { palCursor = 0; renderPalette(); });
  $('#palInput').addEventListener('keydown', (e) => {
    e.stopPropagation();
    const list = paletteRows(e.target.value.trim());
    if (e.key === 'ArrowDown') { e.preventDefault(); palCursor = Math.min(list.length - 1, palCursor + 1); renderPalette(); }
    if (e.key === 'ArrowUp') { e.preventDefault(); palCursor = Math.max(0, palCursor - 1); renderPalette(); }
    if (e.key === 'Escape') closePalette();
    if (e.key === 'Enter') { const r = list[palCursor]; closePalette(); if (r) r.run(); }
  });
  window.addEventListener('popstate', (e) => restore(e.state));
  bindOmni(); bindKeys();
  inflight.listeners.add((n) => { const d = $('#pulseDot'); if (d) d.classList.toggle('busy', n > 0); });
  // A link can open on an item or a tag: ?open=<id>, ?tag=<tag>.
  try { const q = new URLSearchParams(location.search); if (q.get('tag')) S.tokens.push({ kind: 'tag', value: q.get('tag') }); if (q.get('open')) { S.open = q.get('open'); S.view = 'inspect'; } } catch { /* no location */ }
  try { await loadShell(); } catch (e) { toast(`The daemon did not answer: ${e.message}`); }
  renderAll();
  paintZones();
  remember(false);
  call(parts().brain, 'start', $('#brain'));
  await load();
  call(parts().drawer, 'start');
  const every = Number((S.shell && S.shell.settings && S.shell.settings['ui.refresh_seconds']) || 30);
  setInterval(() => { if (!typing()) load(); }, Math.max(5, every) * 1000);
}
// A refresh redraws everything, so it waits while something is being typed into.
const typing = () => { const a = document.activeElement; return !!a && (a.tagName === 'INPUT' || a.tagName === 'TEXTAREA'); };
