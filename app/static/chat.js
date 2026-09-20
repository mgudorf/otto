// The agent drawer: one tab per open session of the page's agent, the transcript, and a composer that carries
// whatever is being discussed as a token. Core owns the frame — the box, the grip, the width and the keyboard —
// and hands the plate over; this fills the plate and holds the sessions. Tabs, turns and streaming all come from
// /api/session/<module>, and core reaches the drawer only through the object registered at the bottom.
import { S, h, $, put, icon, I, toast, modOf, hue, go, select, refresh, renderChat, tabEls, paintTabs, enterZone, openPalette, registerDrawer } from './core.js';
import { get, post, sse } from './api.js';
import { md } from './md.js';

let cur = null;         // the drawer as it stands: {mod, sessions, sid, turns, busy, error, first}
let sel = null;         // the open item, as core last handed it over
let ref = null;         // what was pointed at, as core last handed it over
let stop = null;        // closes the open event stream
let toolIds = {};       // a streamed tool's id -> its place in the turn list
let drawnFor = null;    // the module the composer on screen belongs to
const drafts = {};      // what is half-typed, per module, so a redraw and a page change both keep it
const closed = [];      // tabs closed here, newest last

// S.chatTab is the session each module was left on, so coming back to a page opens the tab it had.

// ---- tabs ------------------------------------------------------------------------------------

// The `+` is the blank tab: nothing exists on the daemon until its first send opens a session.
function newChat() {
  if (!cur) return;
  showTab(null);
  focus();
}

function pickTab(i) {
  const s = cur && cur.sessions[i];
  if (s) showTab(s.id);
}

// Closing a tab ends the session: the agent titles and tags the conversation on its way out.
async function closeChat(at) {
  if (!cur || !cur.sessions.length) return;
  const i = at === undefined ? cur.sessions.findIndex((s) => s.id === cur.sid) : at;
  const s = cur.sessions[i];
  if (!s) return;
  try { await post(`/api/session/${cur.mod}/send`, { text: '/clear', id: s.id }); }
  catch (e) { toast(e.message); return; }
  closed.push({ mod: cur.mod, id: s.id });
  const rest = cur.sessions.filter((x) => x.id !== s.id);
  cur.sessions = rest;
  if (cur.sid === s.id) await showTab(rest.length ? rest[Math.min(i, rest.length - 1)].id : null);
  else draw();
}

let pending = null;   // a tab to open once the drawer is showing its module

async function reopenChat() {
  const last = closed.pop();
  if (!last) return;
  try { await post(`/api/session/${last.mod}/${last.id}/reopen`); }
  catch (e) { closed.push(last); toast(e.message); return; }
  // The page change is what brings the drawer to that module, and it renders on its own clock:
  // leave the tab to open as the drawer's next render of that module, rather than racing it here.
  if (!cur || cur.mod !== last.mod) { pending = { mod: last.mod, sid: last.id }; go(last.mod); return; }
  await syncTabs(last.id);
}

// F2 or a double click: the title is edited where it sits and written back to the session.
function renameTab(i) {
  const s = cur && cur.sessions[i], el = tabEls()[i], t = el && el.querySelector('.t');
  if (!s || !t) return;
  let done = false;
  const inp = h('input', { class: 'rename', value: s.label || '' });
  const finish = async (keep) => {
    if (done) return;
    done = true;
    const name = inp.value.trim();
    if (keep && name && name !== s.label) {
      try { await post(`/api/session/${cur.mod}/${s.id}/title`, { title: name }); s.label = name; }
      catch (e) { toast(e.message); }
    }
    draw();
  };
  inp.addEventListener('keydown', (e) => { e.stopPropagation(); if (e.key === 'Enter') finish(true); else if (e.key === 'Escape') finish(false); });
  inp.addEventListener('blur', () => finish(true));
  t.replaceWith(inp);
  inp.focus();
  inp.select();
}

// ---- the session behind the open tab ---------------------------------------------------------

function endStream() { if (stop) { stop(); stop = null; } toolIds = {}; }

async function showTab(sid) {
  const mod = cur.mod;
  endStream();
  cur.sid = sid;
  cur.turns = [];
  cur.busy = false;
  cur.error = null;
  S.chatTab[mod] = sid;
  draw();
  if (!sid) return;
  try {
    const s = await get(`/api/session/${mod}/${sid}`);
    if (!cur || cur.mod !== mod || cur.sid !== sid) return;
    cur.turns = s.turns;
    cur.busy = s.busy;
    draw();
    stop = sse(`/api/session/${mod}/${sid}/events`, (ev) => onEvent(mod, sid, ev));
  } catch (e) {
    if (cur && cur.mod === mod && cur.sid === sid) { cur.error = e.message; draw(); }
  }
}

// The tab strip, and which tab is open. `pick` names one; without it the open tab stays, or the newest on first sight.
async function syncTabs(pick) {
  if (!cur) return;
  const mod = cur.mod;
  let s;
  try { s = await get(`/api/session/${mod}`); }
  catch (e) { if (cur && cur.mod === mod) { cur.error = e.message; draw(); } return; }
  if (!cur || cur.mod !== mod) return;
  cur.sessions = s.sessions;
  let sid = pick === undefined ? cur.sid : pick;
  if (!sid || !s.sessions.some((x) => x.id === sid)) sid = cur.first && s.sessions.length ? s.sessions[s.sessions.length - 1].id : null;
  cur.first = false;
  if (sid === cur.sid && (sid === null || stop)) { draw(); return; }
  await showTab(sid);
}

// Turns arrive whole, as the daemon finishes them; a delta belongs to Chat's own page, not the drawer.
function onEvent(mod, sid, ev) {
  if (!cur || cur.mod !== mod || cur.sid !== sid) return;
  if (ev.role === 'delta' || ev.role === 'result') return;
  if (ev.role === 'tagged') { syncTabs(null); return; }                     // the session closed: the strip shrinks
  if (ev.role === 'idle') { cur.busy = false; draw(); refresh(); return; }  // the page the turn acted on reloads
  const turns = cur.turns.slice();
  if (ev.role === 'user' || ev.role === 'model') turns.push({ role: ev.role, text: ev.text, ts: ev.ts });
  else if (ev.role === 'tool') { toolIds[ev.id] = turns.length; turns.push({ role: 'tool', tool: ev.tool, status: ev.status, ts: ev.ts }); }
  else if (ev.role === 'tool_result') { const i = toolIds[ev.id]; if (i !== undefined && turns[i]) turns[i] = { ...turns[i], status: ev.status }; }
  else if (ev.role === 'error') turns.push({ role: 'system', text: `error: ${ev.text}`, ts: ev.ts });
  else if (ev.role === 'system') turns.push({ role: 'system', text: ev.text, ts: ev.ts });
  cur.turns = turns;
  if (ev.role === 'user') cur.busy = true;
  draw();
}

// ---- the composer ------------------------------------------------------------------------------

// What the next message is about: whatever was pointed at, else the open item.
function refOf() {
  if (ref) return ref;
  if (!sel || !sel.title) return null;
  return { module: sel.module || S.page, id: sel.id, label: `${modOf(sel.module || S.page).title}, ${sel.title}` };
}

// The reference rides into the turn as its first line, so the agent reads what the token shows.
function carry(ref, typed) {
  if (!ref) return typed;
  const head = ref.id ? `${ref.label} [${ref.module}:${ref.id}]` : ref.label;
  return `${head}${ref.quote ? `\n“${ref.quote}”` : ''}\n\n${typed}`;
}

// True when the turn reached the daemon: the point popup drops its reference on that.
async function send() {
  const c = $('#composer');
  const typed = (c ? c.value : '').trim();
  if (!typed || !cur || cur.busy) return false;
  const mod = cur.mod, sid = cur.sid;
  drafts[mod] = '';
  if (c) c.value = '';
  try {
    const r = await post(`/api/session/${mod}/send`, { text: carry(refOf(), typed), id: sid });
    if (r.session && r.session !== sid) await syncTabs(r.session);   // the blank tab became a session
    return true;
  } catch (e) {
    drafts[mod] = typed;
    if (cur && cur.mod === mod) { cur.error = e.message; draw(); }
    return false;
  }
}

function focus() {
  const c = $('#composer');
  if (c) { c.focus(); c.setSelectionRange(c.value.length, c.value.length); }
}

// A skill from the palette, or a turn the point popup started, lands in the box ready to send.
function setDraft(text) {
  if (!cur) return;
  drafts[cur.mod] = text;
  const c = $('#composer');
  if (c) c.value = text;
  focus();
}

function onKey(e) {
  if (e.key === 'ArrowLeft' && e.target.selectionStart === 0 && e.target.selectionEnd === 0) {
    e.preventDefault();
    e.target.blur();
    enterZone('tabs');
    return;
  }
  if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); if (!e.target.value.trim()) { e.target.blur(); return; } send(); }
  if (e.key === 'Escape') e.target.blur();
  if (e.key === '/' && !e.target.value) { e.preventDefault(); openPalette('/'); }
}

// ---- drawing -----------------------------------------------------------------------------------

function tabStrip() {
  const strip = h('div', { class: 'tabs' });
  cur.sessions.forEach((s, i) => strip.append(h('button', {
    class: `tab${s.id === cur.sid ? ' on' : ''}`,
    onclick: () => showTab(s.id),
    ondblclick: () => renameTab(i),
  }, h('span', { class: 't' }, s.label), h('span', { class: 'x', title: 'Close', onclick: (e) => { e.stopPropagation(); closeChat(i); } }, '×'))));
  strip.append(h('button', { class: `tab plus${cur.sid ? '' : ' on'}`, title: 'New chat', onclick: newChat }, '+'));
  return strip;
}

function lines() {
  const out = [];
  if (cur.error) out.push(h('div', { class: 'turn tool' }, cur.error));
  for (const t of cur.turns) {
    if (t.role === 'user') out.push(h('div', { class: 'turn user' }, t.text));
    else if (t.role === 'model') out.push(h('div', { class: 'turn model', html: md(t.text) }));
    else if (t.role === 'tool') out.push(h('div', { class: 'turn tool' }, t.tool, t.status ? h('span', { class: 'ok' }, t.status) : null));
    else out.push(h('div', { class: 'turn tool' }, t.text));
  }
  return out;
}

// Dropping what was pointed at goes back through core, which hands the drawer its context again.
function refToken(r) {
  const drop = () => { if (ref) { S.pointRef = null; renderChat(); } else select(null); };
  return h('span', { class: 'token ref', style: `--c:${r.module ? hue(r.module) : 'var(--ink-3)'}` },
    r.module ? icon(modOf(r.module).icon) : icon(I.target),
    h('span', { class: 't' }, r.label, r.quote ? h('span', { class: 'q' }, ` “${r.quote}”`) : null),
    h('button', { title: 'Drop reference', onclick: drop }, '×'));
}

function composer() {
  const r = refOf();
  return h('div', { class: 'composer' },
    r ? h('div', { class: 'refs' }, refToken(r)) : null,
    h('textarea', { id: 'composer', onkeydown: onKey }),
    h('button', { class: 'send', title: 'Send', onclick: send }, icon(I.up)));
}

// A redraw keeps the draft, the caret and the focus, so a streamed turn never lands on top of what is being typed.
function fill(plate) {
  if (!plate || !cur) return;
  const ta = $('#composer');
  if (ta && drawnFor) drafts[drawnFor] = ta.value;
  const held = ta && document.activeElement === ta ? [ta.selectionStart, ta.selectionEnd] : null;
  put(plate, tabStrip(), cur.sid || cur.error ? h('div', { class: 'turns' }, ...lines()) : h('div', { class: 'empty-chat' }), composer());
  const t = $('.turns', plate);
  if (t) t.scrollTop = t.scrollHeight;
  paintTabs();                      // the keyboard's place in the strip is core's to paint, on every redraw
  const c = $('#composer');
  if (c) {
    c.value = drafts[cur.mod] || '';
    if (held) { c.focus(); c.setSelectionRange(Math.min(held[0], c.value.length), Math.min(held[1], c.value.length)); }
  }
  drawnFor = cur.mod;
}

const draw = () => fill($('#chat .plate'));

// ---- what core calls ----------------------------------------------------------------------------

// Core's renderChat hands over the plate and the page's agent, selection and pointed-at reference.
function render(plate, ctx) {
  sel = ctx.sel || null;
  ref = ctx.ref || null;
  const mod = ctx.module.id;
  if (!cur || cur.mod !== mod) {
    endStream();
    const want = pending && pending.mod === mod ? pending.sid : undefined;   // a chat reopened from another page
    if (want !== undefined) pending = null;
    cur = { mod, sessions: [], sid: want ?? S.chatTab[mod] ?? null, turns: [], busy: false, error: null, first: want === undefined && S.chatTab[mod] === undefined };
    syncTabs(cur.sid);
  }
  fill(plate);
}

// The shell's clock: a turn a page action started lands in the newest tab, and the strip's labels catch up.
function sync() { if (cur) syncTabs(); }

const DRAWER = { render, sync, focus, setDraft, send, newChat, pickTab, renameTab, closeChat, reopenChat };
registerDrawer(DRAWER);
export default DRAWER;
