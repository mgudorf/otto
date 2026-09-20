// Chat: every conversation by the day it last moved; the pane opens one, streams its turns and sends the next into it.
import {
  S, h, put, $, icon, I, hue, chk, titleCell, stampCell, acts, tagAct, byDay, newest,
  dayLabel, dateLine, tagLine, confirmPop, toast, refresh, select, renderMain,
} from '../core.js';
import { get, post, sse } from '../api.js';
import { md } from '../md.js';

// The open conversation: its turns as they stand and the reply arriving a piece at a time.
const live = { sid: null, stop: null, turns: [], tools: {}, partial: '', busy: false, sending: false, seen: null };
const drafts = {};   // what is half-typed, per conversation, so opening another one and coming back keeps it
let box = null;      // the transcript element, so a streamed piece lands without rebuilding the page
let ta = null;       // the box on screen, so a rebuild can hand the caret to the one that replaces it
let caret = null;    // where the caret stood when that box went, until the new one has it
let focusOn = null;  // the conversation whose box takes the caret as soon as it is drawn
let beat = null;     // the clock that asks the daemon again while a conversation is open

const setting = (k, fallback) => (S.shell && S.shell.settings && S.shell.settings[k] !== undefined ? S.shell.settings[k] : fallback);

// The stream follows the selection: opened when one is picked, closed when it changes or goes.
function tune(id) {
  const sid = id === null || id === undefined ? null : String(id);
  if (live.sid === sid) return;
  if (live.stop) live.stop();
  clearInterval(beat);
  caret = null;                  // the caret belonged to the conversation being left
  Object.assign(live, { sid, stop: null, turns: [], tools: {}, partial: '', busy: false, sending: false, seen: null });
  if (sid) {
    live.stop = sse(`/api/chat/events/${encodeURIComponent(sid)}`, (ev) => onEvent(sid, ev));
    beat = setInterval(repair, Math.max(5, Number(setting('ui.refresh_seconds', 30))) * 1000);   // the shell's own clock
    watch();
  }
}

// A stream that reconnects subscribes to a fresh queue, so the frames it missed are gone for good, and one of them
// may be the `idle` that unlocks the box. The daemon's record is the truth, so it is asked for again on the clock
// for as long as a conversation is open — from Chat's page, from Home, from a tag page — and settles the box there.
async function repair() {
  const sid = live.sid, had = live.turns.length, was = live.busy;
  let open = null;
  try { open = await get(`/api/chat/item/${encodeURIComponent(sid)}`); } catch { return; }   // the next pass asks again
  if (live.sid !== sid) return;
  sync(open);
  if (live.turns.length !== had || live.busy !== was) draw();
}

// Nothing tells a page it was left, so the pane's going is read off #main, whose children every render replaces:
// a render where the open row is no longer this conversation ends the stream, on Chat's own page or on Home's.
let watching = false;
function watch() {
  const main = $('#main');
  if (watching || !main) return;
  watching = true;
  new MutationObserver(() => { if (live.sid !== null && String(S.sel) !== String(live.sid)) tune(null); }).observe(main, { childList: true });
}

// The daemon's record leads: its turns are the truth, whatever the stream added past them is kept, and its `busy`
// is what unlocks the box.
function sync(i) {
  if (!i || String(i.id) !== String(live.sid) || !Array.isArray(i.turns)) return;
  const turns = i.turns.slice();
  if (live.turns.length > turns.length) turns.push(...live.turns.slice(turns.length));
  live.turns = turns;
  live.busy = live.sending || !!i.busy;
  if (!live.busy) live.partial = '';   // nothing runs, so a piece of reply a dropped stream left behind is stale
}

function onEvent(sid, ev) {
  if (live.sid !== sid) return;
  const add = (t) => { live.turns = [...live.turns, t]; };
  if (ev.role === 'delta') live.partial += ev.text || '';
  else if (ev.role === 'user') { add({ role: 'user', text: ev.text }); live.busy = true; live.partial = ''; }
  else if (ev.role === 'model') { add({ role: 'model', text: ev.text }); live.partial = ''; }
  else if (ev.role === 'tool') { live.tools[ev.id] = live.turns.length; add({ role: 'tool', tool: ev.tool, status: ev.status }); }
  else if (ev.role === 'tool_result') {
    const at = live.tools[ev.id];
    if (at !== undefined && live.turns[at]) { const copy = live.turns.slice(); copy[at] = { ...copy[at], status: ev.status }; live.turns = copy; }
  } else if (ev.role === 'error') add({ role: 'system', text: `error: ${ev.text}` });
  else if (ev.role === 'system') add({ role: 'system', text: ev.text });
  else if (ev.role === 'tagged') { reload(); return; }                                      // the title and the tags just landed
  else if (ev.role === 'idle') { live.busy = false; live.partial = ''; draw(); reload(); return; }
  else return;                                                                              // init and result carry nothing to show
  draw();
}

function turnEl(t) {
  if (t.role === 'user') return h('div', { class: 'turn user', style: 'display:inline-block;margin-bottom:10px' }, t.text || '');
  if (t.role === 'model') return h('div', { class: 'turn model', html: md(t.text) });
  if (t.role === 'tool') return h('div', { class: 'turn tool' }, t.tool, t.status ? h('span', { class: 'ok' }, t.status) : null);
  return h('div', { class: 'turn tool' }, t.text || '');
}
function lines() {
  const out = live.turns.map(turnEl);
  if (live.partial) out.push(h('div', { class: 'turn model', html: md(live.partial) }));
  return out;
}
// A streamed piece repaints the transcript alone, so the draft and the caret below it stay where they were.
function draw() {
  if (box && box.isConnected) {
    put(box, ...lines());
    const pane = $('#detail');
    if (pane && live.busy) pane.scrollTop = pane.scrollHeight;
  } else if (S.page === 'chat') renderMain();
}
// A finished turn moves the title, the tags and the folder, so the open conversation is fetched again.
function reload() { S.item = null; refresh(); }

async function send(el) {
  const text = (el.value || '').trim();
  const sid = live.sid;
  if (!text || live.busy || !sid) return;
  el.value = '';
  drafts[sid] = '';
  live.busy = true;
  live.sending = true;      // until the daemon has the turn, its own `busy` is behind what this page knows
  try { await post('/api/chat/send', { id: sid, text }); }
  catch (e) {
    toast(e.message);
    drafts[sid] = text;
    if (live.sid === sid) { live.busy = false; el.value = text; }
  } finally { if (live.sid === sid) live.sending = false; }
  draw();
}

// A rebuild puts a new box on screen: the half-typed line and the caret in it move across to it. The new box is
// not in the page yet, so it takes the caret on the next tick, and only if it is the one that landed there.
function composer() {
  const el = h('textarea', {
    spellcheck: 'false',
    oninput: (e) => { drafts[live.sid] = e.target.value; },
    onkeydown: (e) => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); send(el); } },
  });
  el.value = drafts[live.sid] || '';
  if (ta && document.activeElement === ta) caret = [ta.selectionStart, ta.selectionEnd];
  else if (focusOn !== null && String(focusOn) === String(live.sid)) { focusOn = null; caret = [el.value.length, el.value.length]; }
  ta = el;
  if (caret) queueMicrotask(() => {
    if (!caret || !el.isConnected) return;
    el.focus();
    el.setSelectionRange(Math.min(caret[0], el.value.length), Math.min(caret[1], el.value.length));
    caret = null;
  });
  // The list's capture box, without the inset and the rule that seat it above a list.
  return h('div', { class: 'capture open', style: 'padding:0;border-bottom:0;background:none;margin-top:14px' }, el,
    h('div', { class: 'crow' }, h('button', { class: 'btn primary', title: 'Send', onclick: () => send(el) }, icon(I.up))));
}

// One action the daemon offers: a link opens, anything that asks or removes goes through the confirm.
function runAction(a, item, anchor) {
  if (a.href) { window.open(a.href, '_blank', 'noopener'); return; }
  const go = async () => {
    try { await post(`/api/chat/action/${a.verb}`, { id: item.id }); }
    catch (e) { toast(e.message); return; }
    if (a.removes) { delete drafts[item.id]; if (String(S.sel) === String(item.id)) select(null); }
    refresh();
  };
  if (a.confirm) confirmPop(anchor, a.confirm, go); else go();
}
const btnClass = (a) => `btn${a.primary ? ' primary' : a.confirm || a.removes ? ' danger' : ''}`;
function actionRow(item) {
  const list = item.actions || [];
  if (!list.length) return null;
  return h('div', { class: 'actions' }, ...list.map((a) => h('button', {
    class: btnClass(a),
    onclick: (e) => runAction(a, item, e.currentTarget),
  }, a.label)));
}
// The row offers the same verbs the daemon put on the conversation; Tag is the shell's own.
const rowActs = (i) => [tagAct(i), ...(i.actions || []).map((a) => [a.label, (e) => runAction(a, i, e.currentTarget), a.removes ? I.trash : null])];

async function newChat() {
  let made;
  try { made = await post('/api/chat/new'); }
  catch (e) { toast(e.message); return; }
  focusOn = made.id;
  await refresh();
  select(made.id);
}

// Also the pane a tag page or Home opens on a conversation, so the stream is tuned here and not only from the list.
function detail(i) {
  tune(i.id);
  if (i !== live.seen) { live.seen = i; sync(i); }   // each fetch of the conversation is a fresh object, and settles it
  const files = i.files || [];
  box = h('div', { class: 'prose', style: `white-space:normal;--c:${hue('chat')}` }, ...lines());
  return [
    h('h2', null, i.title),
    i.when ? dateLine(dayLabel(i.when)) : null,
    tagLine(i),
    files.length ? h('dl', { class: 'kv' }, h('dt', null, 'Files'), h('dd', null, ...files.map((f, n) => [
      n ? ', ' : null,
      h('a', { href: `/api/chat/file/${encodeURIComponent(i.id)}/${encodeURIComponent(f.name)}`, target: '_blank', style: 'color:var(--ink-2)' }, f.name),
    ]))) : null,
    box,
    composer(),
    actionRow(i),
  ];
}

export default {
  cols: '18px minmax(0,1fr) 70px',
  chips: ['All'],
  async load() {
    const d = await get('/api/chat/left');
    const actions = d.actions || [];
    return { items: (d.groups || []).flatMap((g) => g.rows || []).map((r) => ({ ...r, actions })) };
  },
  filter: (list) => list,
  groups: (list) => byDay(list.slice().sort(newest)),
  cells: (i) => [chk(i), titleCell(i), stampCell(i, true), acts(i, rowActs(i))],
  tools: () => [h('button', { title: 'New conversation', class: 'ico btn primary', onclick: newChat }, icon(I.plus))],
  detail,
};
