// Point mode: aim at any element, or highlight text, then say what Claude should do with it.
// Core owns the button, the `o` key and the mode's state; the aiming, the popup and what its buttons do are here.
// The drawer is reached through core, never imported: either part runs without the other.
import { S, h, $, icon, I, modOf, toast, refresh, renderChat, currentAgent, pageTitle, togglePoint, askAgent, sendToAgent, registerPoint } from './core.js';
import { post } from './api.js';

const POINTABLE = '.row[data-id], .dbody h2, .dbody .kv, .dbody .prose p, .dbody .prose, .cell, .stat, .nav-item, .toolbar, .turn, .chead, .omni, .related, .thead, .group, .capture, .editor';
const QUOTE_CHARS = 220, SELECTION_CHARS = 300;
let aimed = null;

// Core has already flipped the mode and the button; this is what the mode looks like: a crosshair over the page.
function toggle(on) {
  document.body.classList.toggle('pointing', on);
  if (!on) { closePointPop(); if (aimed) { aimed.classList.remove('aim'); aimed = null; } }
}

// The row the daemon loaded, by id: the open item, then this page's data, then the row as it was rendered.
function findItem(id, el) {
  const want = String(id);
  if (S.item && String(S.item.id) === want) return S.item;
  const seen = new Set();
  const scan = (v, depth) => {
    if (!v || typeof v !== 'object' || depth > 5 || seen.has(v)) return null;
    seen.add(v);
    if (Array.isArray(v)) { for (const e of v) { const r = scan(e, depth + 1); if (r) return r; } return null; }
    if (v.id !== undefined && String(v.id) === want && (v.title !== undefined || v.module !== undefined)) return v;
    for (const k of Object.keys(v)) { const r = scan(v[k], depth + 1); if (r) return r; }
    return null;
  };
  const found = scan(S.data, 0);
  if (found || !el) return found;
  const t = $('.t .title', el) || $('.t', el) || el;          // a row the page keeps outside S.data still names itself
  return { id, module: el.dataset.module || S.page, title: t.textContent.replace(/\s+/g, ' ').trim() };
}

// What was pointed at: an item (a row, or a part of the open item) or a piece of the frame.
function refOf(el) {
  const row = el.closest('.row[data-id]');
  if (row) { const i = findItem(row.dataset.id, row); if (i) return { kind: 'item', module: i.module, id: i.id, item: i, label: `${modOf(i.module).title}, ${i.title}` }; }
  const sel = S.item || (S.sel && findItem(S.sel));
  if (el.closest('#detail') && sel) {
    const p = el.closest('.dbody .prose p, .cell, .dbody h2, .dbody .kv, .related, .dbody .prose');
    let part = 'body', quote = '';
    if (p) {
      if (p.matches('.cell')) { part = `cell ${[...p.parentNode.querySelectorAll('.cell')].indexOf(p) + 1}`; quote = p.textContent.replace(/\s+/g, ' ').trim(); }
      else if (p.matches('h2')) part = 'title';
      else if (p.matches('.kv')) part = 'fields';
      else if (p.matches('.related')) part = 'related items';
      else if (p.matches('p')) { part = `paragraph ${[...p.parentNode.querySelectorAll('p')].indexOf(p) + 1}`; quote = p.textContent.replace(/\s+/g, ' ').trim(); }
    }
    return { kind: 'item', module: sel.module, id: sel.id, item: sel, part, label: `${modOf(sel.module).title}, ${sel.title}, ${part}`, quote: quote.slice(0, QUOTE_CHARS) };
  }
  const nav = el.closest('.nav-item'); if (nav) return { kind: 'ui', label: `Navigation, ${nav.textContent.trim()}` };
  if (el.closest('.stat')) return { kind: 'ui', label: `Home number, ${el.closest('.stat').textContent.trim().replace(/\s+/g, ' ')}` };
  if (el.closest('.omni')) return { kind: 'ui', label: 'Search bar' };
  if (el.closest('.chat')) return { kind: 'ui', label: `${currentAgent().title} agent drawer` };
  if (el.closest('.toolbar')) return { kind: 'ui', label: `${pageTitle()} toolbar` };
  if (el.closest('.thead')) return { kind: 'ui', label: `${pageTitle()} column headers` };
  if (el.closest('.group')) return { kind: 'ui', label: `${pageTitle()} group, ${el.closest('.group').textContent.trim()}` };
  if (el.closest('.capture, .editor')) return { kind: 'ui', label: `${pageTitle()} editor` };
  return { kind: 'ui', label: `${pageTitle()} page` };
}

function openPointPop(ref, x, y) {
  closePointPop();
  const pop = h('div', { class: 'pointpop', id: 'pointPop' });
  pop.append(h('div', { class: 'ph' }, ref.item ? icon(modOf(ref.module).icon) : icon(I.target), h('span', { class: 't' }, ref.label)));
  if (ref.quote) pop.append(h('div', { class: 'q' }, `“${ref.quote}”`));
  pop.append(h('div', { class: 'acts' },
    h('button', { onclick: () => ask(ref) }, 'Ask'),
    ref.item ? h('button', { onclick: () => summarizeAndTag(ref) }, 'Summarize and tag') : null,
    ref.item || ref.quote ? h('button', { onclick: () => capture(ref) }, 'Capture') : null,
    h('button', { onclick: () => feedbackBox(pop, ref) }, 'Feedback')));
  document.body.append(pop);
  pop.style.left = `${Math.max(8, Math.min(x - 24, innerWidth - 336))}px`;
  pop.style.top = `${Math.max(8, Math.min(y + 10, innerHeight - pop.offsetHeight - 12))}px`;
}
function closePointPop() { const p = $('#pointPop'); if (p) p.remove(); }

// The reference becomes the composer's token; whatever is typed next carries it.
function ask(ref) {
  S.pointRef = ref;
  closePointPop(); togglePoint(false);
  renderChat(); askAgent();
}

// A real turn of the drawer's agent, on the open tab, with the reference and the quote carried as the token.
async function summarizeAndTag(ref) {
  closePointPop(); togglePoint(false);
  S.pointRef = ref;
  renderChat();
  if (await sendToAgent('Summarize this and add the tags it should carry.')) { S.pointRef = null; renderChat(); }   // the turn took the token with it
}

async function capture(ref) {
  const text = (ref.quote || (ref.item && ref.item.title) || '').trim();
  if (!text) return;
  const tags = (ref.item && ref.item.tags) || [];
  closePointPop(); togglePoint(false);
  try {
    await post('/api/second_brain/action/capture', { kind: 'note', text, tags });
    toast(tags.length ? 'Captured to Second Brain, tags carried over' : 'Captured to Second Brain');
    await refresh();
  } catch (e) { toast(e.message); }
}

// The owner's note on this exact element. The Feedback agent files it, so the kind is its call, not the client's.
function feedbackBox(pop, ref) {
  const ta = h('textarea', null);
  const btn = h('button', { class: 'btn primary' }, 'Send');
  const send = async () => {
    const text = ta.value.trim();
    if (!text || btn.disabled) return;
    btn.disabled = true;
    const item = {
      module: ref.module || null,
      id: ref.id === undefined || ref.id === null ? null : String(ref.id),
      text: [ref.label, ref.quote ? `“${ref.quote}”` : null].filter(Boolean).join(' — '),
    };
    try {
      await post('/api/feedback/action/add', { page: S.page, text, item });
      toast(`Filed on ${ref.item ? modOf(ref.module).title : pageTitle()}: ${text.slice(0, 48)}`);
      closePointPop(); togglePoint(false);
    } catch (e) { btn.disabled = false; toast(e.message); }
  };
  btn.addEventListener('click', send);
  ta.addEventListener('keydown', (e) => {
    e.stopPropagation();
    if (e.key === 'Escape') { closePointPop(); togglePoint(false); }
    else if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); send(); }
  });
  $('.acts', pop).replaceWith(h('div', { class: 'fb' }, ta, h('div', { class: 'crow' }, btn)));
  ta.focus();
}

function bindPoint() {
  document.addEventListener('mousemove', (e) => {
    if (!S.point) return;
    const el = e.target.closest && e.target.closest(POINTABLE);
    if (el !== aimed) { if (aimed) aimed.classList.remove('aim'); aimed = el; if (aimed) aimed.classList.add('aim'); }
  });
  document.addEventListener('click', (e) => {
    if (!S.point || e.target.closest('#pointPop, #pointBtn, #paletteScrim, #helpScrim')) return;
    e.preventDefault(); e.stopPropagation();
    if (getSelection().toString().trim()) return;   // a drag-select just opened the quote menu
    openPointPop(refOf(e.target), e.clientX, e.clientY);
  }, true);
  document.addEventListener('mousedown', (e) => { if ($('#pointPop') && !e.target.closest('#pointPop')) closePointPop(); });
  // In point mode, highlighting text offers the same menu with the quote; outside it, selection is just selection.
  document.addEventListener('mouseup', (e) => {
    if (!S.point || e.target.closest('#pointPop, textarea, input, .chat, .nav')) return;
    setTimeout(() => {
      const s = getSelection(), text = s && s.toString().replace(/\s+/g, ' ').trim();
      if (!text || text.length < 4 || !s.anchorNode || !$('#main').contains(s.anchorNode)) return;
      const r = s.getRangeAt(0).getBoundingClientRect();
      const ref = refOf(s.anchorNode.nodeType === 1 ? s.anchorNode : s.anchorNode.parentElement);
      ref.quote = text.slice(0, SELECTION_CHARS); ref.part = 'quoted text';
      if (ref.item) ref.label = `${modOf(ref.module).title}, ${ref.item.title}, quoted text`;
      openPointPop(ref, r.left + r.width / 2, r.bottom);
    }, 0);
  });
}

// ---- what core calls ----------------------------------------------------------------------------

bindPoint();
const POINT = { toggle };
registerPoint(POINT);
export default POINT;
