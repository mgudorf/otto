// The drawer: one agent, its conversations as tabs, a transcript, and a composer that carries what is being discussed as
// a token. Every turn belongs to the daemon: what is typed goes to one Claude session holding every module's tools, and
// the reply arrives over a stream. Ending a conversation tags it and files it under the chats facet, where it becomes a
// row like any other.
import { S, ITEMS, $, h, put, icon, I, toast, modOf, hue, select, renderChat, registerDrawer, parts, call, load } from './core.js';
import { leaveComposer, openPalette } from './shell.js';
import { get, post, sse } from './api.js';
import { md } from './md.js';

const AGENT = 'otto';   // one agent for the whole app; the daemon hands it every module's tools and every module's prompt
let sessions = [], turns = [], toolAt = {}, sid = null, busy = false, ctxItem = null, ctxRef = null, plate = null, stop = null;
const drafts = {};
const cur = () => sessions.find((s) => s.id === sid) || null;

// ---- the conversations ------------------------------------------------------------------------------------------
// `want` picks which tab to land on: an id, or null for none. Left out, the open one stays if it is still open.
async function syncTabs(want) {
  try { sessions = (await get(`/api/session/${AGENT}`)).sessions || []; } catch { sessions = []; }
  const pick = want !== undefined ? want : cur() ? sid : sessions.length ? sessions[sessions.length - 1].id : null;
  if (pick !== sid) await openSession(pick); else draw();
}
async function openSession(id) {
  if (stop) { stop(); stop = null; }
  sid = id; turns = []; toolAt = {}; busy = false;
  draw();
  if (!id) return;
  try { const d = await get(`/api/session/${AGENT}/${id}`); turns = d.turns || []; busy = !!d.busy; } catch { /* a session that is gone draws empty */ }
  stop = sse(`/api/session/${AGENT}/${id}/events`, onEvent);
  draw();
}
function newChat() { openSession(null); focus(); }
function pickTab(i) { const s = sessions[i]; if (s) openSession(s.id); }
// `/clear` is how the daemon ends a conversation: it names it, tags it and closes it, and it returns as a row under chats.
async function closeChat(at) {
  const s = at === undefined ? cur() : sessions[at];
  if (!s) return;
  try { await post(`/api/session/${AGENT}/send`, { text: '/clear', id: s.id }); } catch (e) { toast(e.message); return; }
  toast(`Closed ${s.label}; it is tagged and kept as a conversation`);
  await syncTabs(null); await load();
}
async function openConversation(item) {
  try { await post('/api/verb', { module: 'chat', id: item.id, verb: 'reopen' }); } catch (e) { toast(e.message); return; }
  await syncTabs(item.id); await load();
}
// Nothing is kept in the browser: the newest closed conversation in the feed is the one to reopen.
function reopenChat() {
  const last = ITEMS.filter((i) => (i.fixed || [])[0] === 'chats').sort((a, b) => ((a.when || '') < (b.when || '') ? 1 : -1))[0];
  if (!last) { toast('Nothing to reopen'); return; }
  openConversation(last);
}
function renameTab(i) {
  const s = sessions[i], el = tabEls()[i + 1], t = el && el.querySelector('.t');   // the strip's first tab is the +
  if (!s || !t) return;
  let done = false;
  const inp = h('input', { class: 'rename', value: s.label, 'aria-label': 'Rename' });
  const finish = (keep) => {
    if (done) return;
    done = true;
    const name = inp.value.trim();
    if (keep && name && name !== s.label) { s.label = name; post(`/api/session/${AGENT}/${s.id}/title`, { title: name }).catch((e) => toast(e.message)); }
    draw();
  };
  inp.addEventListener('keydown', (e) => { e.stopPropagation(); if (e.key === 'Enter') finish(true); else if (e.key === 'Escape') finish(false); });
  inp.addEventListener('blur', () => finish(true));
  t.replaceWith(inp); inp.focus(); inp.select();
}
const tabEls = () => [...document.querySelectorAll('.chat .tabs .tab')];

// ---- the composer ---------------------------------------------------------------------------------------------
function refOf() {
  if (ctxRef) return ctxRef;
  if (!ctxItem) return null;
  const part = ctxItem.type === 'question' ? (ctxItem.parts || []).find((p) => p.score === null) : null;
  return { kind: 'item', module: ctxItem.module, id: ctxItem.id, label: `${modOf(ctxItem.module).title}, ${ctxItem.title}${part ? `, (${part.n})` : ''}` };
}
function focus() { const c = $('#composer'); if (c) { c.focus(); c.setSelectionRange(c.value.length, c.value.length); } }
function setDraft(text) { drafts[sid || '+'] = text; const c = $('#composer'); if (c) c.value = text; focus(); }
// The turn is not drawn here: it arrives on the stream, the same way the reply does, so the transcript has one author.
async function send() {
  const c = $('#composer');
  const typed = (c ? c.value : '').trim();
  if (!typed || busy) return false;
  const ref = refOf();
  drafts[sid || '+'] = ''; if (c) c.value = '';
  busy = true; draw();
  try {
    const r = await post(`/api/session/${AGENT}/send`, { text: ref ? `${ref.label}\n\n${typed}` : typed, id: sid || undefined });
    if (r.session && r.session !== sid) await syncTabs(r.session);
  } catch (e) { busy = false; turns.push({ role: 'system', text: e.message }); draw(); return false; }
  if (ctxRef) { S.pointRef = null; ctxRef = null; }
  return true;
}
// A pane event is one line of the turn in flight. A delta is the text of a turn that still arrives whole after it, and a
// result is the run's own summary, so neither is drawn.
function onEvent(ev) {
  if (ev.role === 'delta' || ev.role === 'result') return;
  if (ev.role === 'tagged') { syncTabs(null); load(); return; }
  if (ev.role === 'idle') { busy = false; draw(); load(); return; }
  if (ev.role === 'user' || ev.role === 'model') turns.push({ role: ev.role, text: ev.text });
  else if (ev.role === 'tool') { toolAt[ev.id] = turns.length; turns.push({ role: 'tool', tool: ev.tool, status: ev.status }); }
  else if (ev.role === 'tool_result') { const i = toolAt[ev.id]; if (i !== undefined && turns[i]) turns[i] = { ...turns[i], status: ev.status }; }
  else if (ev.role === 'error') turns.push({ role: 'system', text: `error: ${ev.text}` });
  else if (ev.role === 'system') turns.push({ role: 'system', text: ev.text });
  else return;
  if (ev.role === 'user') busy = true;
  draw();
}
// A verb run from the palette or a key lands in the transcript too, so the drawer is the record of what happened.
function note(item, text) {
  turns.push({ role: 'tool', tool: `${item.module}_action`, status: 'done' }, { role: 'model', text });
  draw();
}

// ---- drawing ------------------------------------------------------------------------------------------------------
function onKey(e) {
  e.stopPropagation();
  if (e.key === 'ArrowUp' && !e.target.value.slice(0, e.target.selectionStart).includes('\n')) { e.preventDefault(); e.target.blur(); leaveComposer(); return; }
  if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); if (!e.target.value.trim()) { e.target.blur(); return; } send(); }
  if (e.key === 'Escape') e.target.blur();
  if (e.key === '/' && !e.target.value) { e.preventDefault(); openPalette('/'); }
}
// The + comes first, then the open sessions: a new chat is always the first thing in the strip.
function tabStrip() {
  const strip = h('div', { class: 'tabs' });
  strip.append(h('button', { class: `tab plus${sid ? '' : ' on'}`, title: 'New chat', onclick: newChat }, '+'));
  sessions.forEach((s, i) => strip.append(h('button', { class: `tab${s.id === sid ? ' on' : ''}`, onclick: () => openSession(s.id), ondblclick: () => renameTab(i) },
    h('span', { class: 't' }, s.label), h('span', { class: 'x', title: 'Close', onclick: (e) => { e.stopPropagation(); closeChat(i); } }, '×'))));
  return strip;
}
function lines() {
  return turns.map((t) => {
    if (t.role === 'user') return h('div', { class: 'turn user' }, t.text);
    if (t.role === 'model') return h('div', { class: 'turn model', html: md(t.text || '') });
    if (t.role === 'system') return h('div', { class: 'turn tool' }, t.text);
    return h('div', { class: `turn tool${t.status === '…' ? ' busy' : ''}` }, t.tool, t.status ? h('span', { class: 'ok' }, t.status) : null);
  });
}
function refToken(r) {
  const drop = () => { if (ctxRef) { S.pointRef = null; ctxRef = null; renderChat(); } else select(null); };
  return h('span', { class: 'token ref', style: `--c:${r.module ? hue(r.module) : 'var(--ink-3)'}` }, r.module ? icon(modOf(r.module).icon) : icon(I.target),
    h('span', { class: 't' }, r.label, r.quote ? h('span', { class: 'q' }, ` “${r.quote}”`) : null), h('button', { title: 'Drop reference', onclick: drop }, '×'));
}
function composer() {
  const r = refOf();
  return h('div', { class: 'composer' }, r ? h('div', { class: 'refs' }, refToken(r)) : null,
    h('textarea', { id: 'composer', 'aria-label': 'Message', onkeydown: onKey }),
    h('button', { class: 'send', title: 'Send', onclick: send }, icon(I.up)));
}
function draw() {
  if (!plate) return;
  const ta = $('#composer');
  const key = sid || '+';
  if (ta) drafts[drawnFor] = ta.value;
  const held = ta && document.activeElement === ta ? [ta.selectionStart, ta.selectionEnd] : null;
  put(plate, tabStrip(), sid ? h('div', { class: 'turns' }, ...lines()) : h('div', { class: 'empty-chat' }, 'Say what to file, or open an item and ask.'), composer());
  const t = $('.turns', plate); if (t) t.scrollTop = t.scrollHeight;
  const c = $('#composer');
  if (c) { c.value = drafts[key] || ''; if (held) { c.focus(); c.setSelectionRange(Math.min(held[0], c.value.length), Math.min(held[1], c.value.length)); } }
  drawnFor = key;
  call(parts().shell, 'paintZones');
}
let drawnFor = '+';

// ---- what core calls ---------------------------------------------------------------------------------------------
function render(el, ctx) { plate = el; ctxItem = ctx.item || null; ctxRef = ctx.ref || null; draw(); }
registerDrawer({ render, focus, setDraft, send, newChat, pickTab, renameTab, closeChat, reopenChat, openConversation, note, start: syncTabs });
