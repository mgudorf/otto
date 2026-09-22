// The drawer: one agent, its conversations as tabs, a transcript, and a composer that carries what is being discussed as
// a token. In this preview the agent is a mock: it runs a verb said about the open item, grades an answer to the open
// question, files anything typed with no item as a note or task, and otherwise gives the item's canned reading.
import { S, ITEMS, $, h, put, icon, I, toast, modOf, hue, itemOf, currentItem, select, doVerb, applyValue, addItem, nextId, allTags, tagsOf, renderFeed, renderChat, registerDrawer, parts, call, verbLabel, isFixed } from './core.js';
import { leaveComposer, openPalette } from './shell.js';
import { SESSIONS } from './data.js';

const sessions = SESSIONS.map((s) => ({ ...s, turns: s.turns.map((t) => ({ ...t })) }));
let sid = 'quiz', busy = false, ctxItem = null, ctxRef = null, plate = null;
const drafts = {}, closed = [];
const cur = () => sessions.find((s) => s.id === sid) || null;

// ---- tabs -----------------------------------------------------------------------------------------------------
function newChat() { sid = null; draw(); focus(); }
function pickTab(i) { const s = sessions[i]; if (s) { sid = s.id; draw(); } }
function closeChat(at) {
  const i = at === undefined ? sessions.findIndex((s) => s.id === sid) : at;
  const s = sessions[i]; if (!s) return;
  sessions.splice(i, 1); closed.push(s);
  if (sid === s.id) sid = sessions.length ? sessions[Math.min(i, sessions.length - 1)].id : null;
  toast(`Closed ${s.label}; it is tagged and kept as a conversation`);
  addItem({ id: nextId('c'), module: 'chat', type: 'conversation', title: s.label, when: '2026-09-20T09:42', tags: [], fixed: ['chats'], turns: s.turns.filter((t) => t.role !== 'tool').slice(0, 2).map((t) => [t.role, t.text || (t.blocks || []).map((b) => b.text).join(' ')]), verbs: [['reopen', 'Reopen'], ['delete', 'Delete']] });
  draw();
}
function reopenChat() { const s = closed.pop(); if (!s) { toast('Nothing to reopen'); return; } sessions.push(s); sid = s.id; draw(); }
function openConversation(item) {
  const s = { id: nextId('s'), label: item.title, turns: (item.turns || []).map(([role, text]) => ({ role, text })) };
  sessions.push(s); sid = s.id; draw();
}
function renameTab(i) {
  const s = sessions[i], el = tabEls()[i + 1], t = el && el.querySelector('.t');   // the strip's first tab is the +
  if (!s || !t) return;
  let done = false;
  const inp = h('input', { class: 'rename', value: s.label, 'aria-label': 'Rename' });
  const finish = (keep) => { if (done) return; done = true; const name = inp.value.trim(); if (keep && name) s.label = name; draw(); };
  inp.addEventListener('keydown', (e) => { e.stopPropagation(); if (e.key === 'Enter') finish(true); else if (e.key === 'Escape') finish(false); });
  inp.addEventListener('blur', () => finish(true));
  t.replaceWith(inp); inp.focus(); inp.select();
}
const tabEls = () => [...document.querySelectorAll('.chat .tabs .tab')];

// ---- the composer and the mock agent ------------------------------------------------------------------------------
function refOf() {
  if (ctxRef) return ctxRef;
  if (!ctxItem) return null;
  const part = ctxItem.type === 'question' ? (ctxItem.parts || []).find((p) => p.score === null) : null;
  return { kind: 'item', module: ctxItem.module, id: ctxItem.id, label: `${modOf(ctxItem.module).title}, ${ctxItem.title}${part ? `, (${part.n})` : ''}` };
}
function focus() { const c = $('#composer'); if (c) { c.focus(); c.setSelectionRange(c.value.length, c.value.length); } }
function setDraft(text) { drafts[sid || '+'] = text; const c = $('#composer'); if (c) c.value = text; focus(); }
function push(turn) { const s = cur(); if (s) s.turns.push(turn); draw(); }
function send() {
  const c = $('#composer');
  const typed = (c ? c.value : '').trim();
  if (!typed || busy) return false;
  const ref = refOf();
  if (!cur()) { const s = { id: nextId('s'), label: typed.slice(0, 26), turns: [] }; sessions.push(s); sid = s.id; }
  drafts[sid] = ''; if (c) c.value = '';
  push({ role: 'user', text: typed });
  busy = true; push({ role: 'tool', tool: 'thinking', status: '…', busy: true });
  setTimeout(() => { const s = cur(); if (s) s.turns = s.turns.filter((t) => !t.busy); busy = false; answer(typed, ref); }, 500 + Math.random() * 500);
  if (ctxRef) { S.pointRef = null; ctxRef = null; }
  return true;
}
const SYN = { delete: ['delete', 'forget', 'trash', 'dismiss'], remove: ['delete', 'forget', 'trash', 'dismiss'], 'not now': ['later'], move: ['do'], transfer: ['do'], yes: ['do', 'accept'], 'mark read': ['read'], 'mark unread': ['unread'], finish: ['done', 'complete'], run: ['run'], reopen: ['reopen'] };
function verbFor(item, lower) {
  const verbs = (item.verbs || []).map(([v]) => v);
  for (const [v, l] of item.verbs || []) if (lower.startsWith(v) || lower.startsWith(l.toLowerCase())) return v;
  for (const [word, vs] of Object.entries(SYN)) if (lower.startsWith(word)) { const v = vs.find((x) => verbs.includes(x)); if (v) return v; }
  return null;
}
function answer(text, ref) {
  const item = ref && ref.id !== undefined ? itemOf(ref.id) : null;
  const lower = text.toLowerCase();
  const m = item ? item.module : 'otto';
  if (item && /^summari[sz]e/.test(lower)) {
    if (item.taggable !== false && !item.tags.includes('reviewed') && !isFixed('reviewed')) item.tags.push('reviewed');
    renderFeed();
    push({ role: 'tool', tool: `${m}_get`, status: 'done' });
    push({ role: 'model', hue: hue(m), text: `${item.reply || item.title}${item.taggable !== false ? ' Tagged #reviewed.' : ''}` });
    return;
  }
  const verb = item ? verbFor(item, lower) : null;
  if (item && verb) {
    const set = verb === 'update' || verb === 'due' ? applyValue(item, text) : null;
    const result = set || doVerb(item, verb, null, { force: true });
    push({ role: 'tool', tool: `${m}_${verb}`, status: 'done' });
    push({ role: 'model', hue: hue(m), text: result || `${verbLabel(item, verb)}: waiting on you in the feed.` });
    return;
  }
  if (item && item.type === 'question' && !/\?$/.test(text)) {
    const part = (item.parts || []).find((p) => p.score === null);
    if (part) {
      const score = 70 + (text.length % 26);
      part.score = score;
      const scored = item.parts.filter((p) => p.score !== null).length;
      item.pct = Math.round(scored / item.parts.length * 100);
      if (scored === item.parts.length) { item.waits = null; item.done = true; }
      renderFeed(); call(parts().brain, 'sync');
      push({ role: 'tool', tool: 'education_grade', status: 'done' });
      push({ role: 'model', hue: hue('education'), blocks: [{ kind: 'grade', score: `${score} / 100`, text: score >= 85 ? 'The argument is complete and the identity is used where it matters.' : 'The shape is right. State the identity you rely on before you cancel, and say why the boundary is excluded.' }], text: scored === item.parts.length ? 'Every part is graded; the question leaves Priority and stays under Recent.' : 'Resubmit, or go on: the next part is the token below.' });
      renderChat();
      return;
    }
  }
  if (item) {
    push({ role: 'tool', tool: `${m}_get`, status: 'done' });
    push({ role: 'model', hue: hue(m), text: item.reply || `${item.title}. Say one of ${(item.verbs || []).map(([, l]) => l.toLowerCase()).join(', ')}, or ask something about it.` });
    return;
  }
  if (ref && ref.kind === 'ui') { push({ role: 'model', hue: hue('otto'), text: `That is the ${ref.label.toLowerCase()}. Say what should change and it is filed as feedback on that spot.` }); return; }
  if (/\?\s*$/.test(text)) { push({ role: 'model', hue: hue('otto'), text: 'In this preview I act on the open item, grade an answer to the open question, and file what you type as a note or a task. Open an item and ask again.' }); return; }
  const isTask = /^(todo|task)\b/i.test(text) || /\b(remind me|renew|pay|send|buy|call|book)\b/i.test(text);
  const title = text.replace(/^(note|todo|task)\s*[:\-]?\s*/i, '').trim();
  const tags = allTags().map((t) => t.tag).filter((t) => !isFixed(t) && (lower.includes(t.replace(/-/g, ' ')) || lower.includes(t))).slice(0, 3);   // never a facet's name
  const type = isTask ? 'task' : 'note';
  const it = addItem({ id: nextId('b'), module: 'second_brain', type, title, snip: 'from this chat', when: '2026-09-20T09:43', tags: type === 'task' ? ['task', ...tags] : tags, fixed: ['entry'], done: false, verbs: type === 'task' ? [['done', 'Done'], ['edit', 'Edit'], ['forget', 'Forget']] : [['edit', 'Edit'], ['forget', 'Forget']] });
  call(parts().brain, 'sync');
  push({ role: 'tool', tool: 'note_add', status: 'filed' });
  push({ role: 'model', hue: hue('second_brain'), blocks: [{ kind: 'note', item: it }], text: `Filed as a ${type}${tags.length ? `, tagged ${tags.map((t) => `#${t}`).join(' ')}` : ''}. It is under Recent now; e edits it, Del forgets it.` });
}
// A verb run from the palette or a key lands in the transcript too, so the drawer is the record of what happened.
function note(item, text) {
  if (!cur()) { const s = { id: nextId('s'), label: modOf(item.module).title, turns: [] }; sessions.push(s); sid = s.id; }
  push({ role: 'tool', tool: `${item.module}_action`, status: 'done' });
  push({ role: 'model', hue: hue(item.module), text });
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
  sessions.forEach((s, i) => strip.append(h('button', { class: `tab${s.id === sid ? ' on' : ''}`, onclick: () => { sid = s.id; draw(); }, ondblclick: () => renameTab(i) },
    h('span', { class: 't' }, s.label), h('span', { class: 'x', title: 'Close', onclick: (e) => { e.stopPropagation(); closeChat(i); } }, '×'))));
  return strip;
}
function blockEl(b) {
  if (b.kind === 'grade') return h('div', { class: 'block', style: '--c:#86AAE3' }, h('div', { class: 'sc num' }, b.score), b.text);
  if (b.kind === 'note') return h('div', { class: 'block', style: '--c:#DDB06F', onclick: () => select(b.item.id) }, h('span', { class: 'tag fixed' }, b.item.type), ` ${b.item.title}`);
  return null;
}
function lines(s) {
  return s.turns.map((t) => {
    if (t.role === 'user') return h('div', { class: 'turn user' }, t.text);
    if (t.role === 'model') return h('div', { class: 'turn model', style: t.hue ? `--c:${t.hue}` : null }, ...(t.blocks || []).map(blockEl), t.text ? h('p', null, t.text) : null);
    return h('div', { class: `turn tool${t.busy ? ' busy' : ''}` }, t.tool, t.status ? h('span', { class: 'ok' }, t.status) : null);
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
  const s = cur();
  put(plate, tabStrip(), s ? h('div', { class: 'turns' }, ...lines(s)) : h('div', { class: 'empty-chat' }, 'Say what to file, or open an item and ask.'), composer());
  const t = $('.turns', plate); if (t) t.scrollTop = t.scrollHeight;
  const c = $('#composer');
  if (c) { c.value = drafts[key] || ''; if (held) { c.focus(); c.setSelectionRange(Math.min(held[0], c.value.length), Math.min(held[1], c.value.length)); } }
  drawnFor = key;
  call(parts().shell, 'paintZones');
}
let drawnFor = '+';

// ---- what core calls ---------------------------------------------------------------------------------------------
function render(el, ctx) { plate = el; ctxItem = ctx.item || null; ctxRef = ctx.ref || null; draw(); }
registerDrawer({ render, focus, setDraft, send, newChat, pickTab, renameTab, closeChat, reopenChat, openConversation, note });
