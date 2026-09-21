// Point mode: aim at anything, a row, a paragraph, a cell, a lobe, the search bar, the drawer, or highlight text, then say
// what Otto should do with it. The popover names exactly what was pointed at, down to which paragraph.
import { S, $, h, icon, I, toast, modOf, itemOf, currentItem, load, renderChat, askAgent, sendToAgent, togglePoint, registerPoint, call, parts } from './core.js';
import { post } from './api.js';

const POINTABLE = '.row[data-id], .dbody h2, .dbody .kv, .dbody .prose p, .dbody .prose, .cell, .part, .lobe, .turn, .omni, .related, .group, .tabs, .composer';
const QUOTE_CHARS = 220, SELECTION_CHARS = 300;
let aimed = null;

function toggle(on) {
  document.body.classList.toggle('pointing', on);
  if (!on) { closePop(); if (aimed) { aimed.classList.remove('aim'); aimed = null; } }
}
function refOf(el) {
  const row = el.closest('.row[data-id]');
  if (row) { const i = itemOf(row.dataset.id); if (i) return { kind: 'item', module: i.module, id: i.id, item: i, label: `${modOf(i.module).title}, ${i.title}` }; }
  const card = el.closest('.card.mod[data-id]');
  if (card) {
    const i = itemOf(card.dataset.id);
    const p = el.closest('.dbody .prose p, .cell, .part, .dbody h2, .dbody .kv, .related');
    let part = 'body', quote = '';
    if (p) {
      if (p.matches('.cell')) { part = `cell ${[...p.parentNode.querySelectorAll('.cell')].indexOf(p) + 1}`; quote = p.textContent.replace(/\s+/g, ' ').trim(); }
      else if (p.matches('.part')) { part = `part ${p.textContent.trim().slice(1, 2)}`; quote = p.textContent.replace(/\s+/g, ' ').trim(); }
      else if (p.matches('h2')) part = 'title';
      else if (p.matches('.kv')) part = 'fields';
      else if (p.matches('.related')) part = 'related items';
      else if (p.matches('p')) { part = `paragraph ${[...p.parentNode.querySelectorAll('p')].indexOf(p) + 1}`; quote = p.textContent.replace(/\s+/g, ' ').trim(); }
    }
    if (i) return { kind: 'item', module: i.module, id: i.id, item: i, part, label: `${modOf(i.module).title}, ${i.title}, ${part}`, quote: quote.slice(0, QUOTE_CHARS) };
  }
  const lobe = el.closest('.lobe'); if (lobe) return { kind: 'ui', label: `Brain, ${lobe.title || 'a type'}` };
  const word = el.closest('.gword'); if (word) return { kind: 'ui', label: `Brain, #${word.textContent}` };
  if (el.closest('#brain')) return { kind: 'ui', label: 'Graph' };
  if (el.closest('.omni')) return { kind: 'ui', label: 'Search bar' };
  if (el.closest('.tabs')) return { kind: 'ui', label: 'Chat tabs' };
  if (el.closest('.composer')) return { kind: 'ui', label: 'Composer' };
  if (el.closest('.turn')) return { kind: 'ui', label: 'A turn of the conversation', quote: el.closest('.turn').textContent.replace(/\s+/g, ' ').trim().slice(0, QUOTE_CHARS) };
  if (el.closest('#chat')) return { kind: 'ui', label: 'Agent drawer' };
  if (el.closest('.group')) return { kind: 'ui', label: `Feed group, ${el.closest('.group').textContent.trim()}` };
  if (el.closest('.top')) return { kind: 'ui', label: 'Header' };
  return { kind: 'ui', label: 'Feed' };
}
function openPop(ref, x, y) {
  closePop();
  const pop = h('div', { class: 'pointpop', id: 'pointPop' });
  pop.append(h('div', { class: 'ph' }, ref.item ? icon(modOf(ref.module).icon) : icon(I.target), h('span', { class: 't' }, ref.label)));
  if (ref.quote) pop.append(h('div', { class: 'q' }, `“${ref.quote}”`));
  pop.append(h('div', { class: 'acts' },
    h('button', { onclick: () => ask(ref) }, 'Ask'),
    ref.item ? h('button', { onclick: () => summarize(ref) }, 'Summarize and tag') : null,
    ref.item || ref.quote ? h('button', { onclick: () => capture(ref) }, 'Capture') : null,
    h('button', { onclick: () => feedback(pop, ref) }, 'Feedback')));
  document.body.append(pop);
  pop.style.left = `${Math.max(8, Math.min(x - 24, innerWidth - 396))}px`;
  pop.style.top = `${Math.max(8, Math.min(y + 10, innerHeight - pop.offsetHeight - 12))}px`;
}
function closePop() { const p = $('#pointPop'); if (p) p.remove(); }
function ask(ref) { S.pointRef = ref; closePop(); togglePoint(false); renderChat(); askAgent(); }
function summarize(ref) { closePop(); togglePoint(false); S.pointRef = ref; renderChat(); sendToAgent('Summarize this and add the tags it should carry.'); }
// What is pointed at becomes an entry, with the tags it already carried.
async function capture(ref) {
  const text = (ref.quote || (ref.item && ref.item.title) || '').trim();
  if (!text) return;
  const tags = (ref.item && ref.item.tags) ? ref.item.tags.slice() : [];
  closePop(); togglePoint(false);
  try { await post('/api/second_brain/action/capture', { kind: 'note', text, tags }); } catch (e) { toast(e.message); return; }
  await load();
  toast(tags.length ? 'Captured as a note, tags carried over' : 'Captured as a note');
}
function feedback(pop, ref) {
  const ta = h('textarea', { 'aria-label': 'Feedback' });
  const btn = h('button', null, 'Send');
  const send = async () => {
    const text = ta.value.trim();
    if (!text) return;
    closePop(); togglePoint(false);
    const item = ref.kind === 'item' ? { module: ref.module, id: ref.id } : null;
    try { await post('/api/feedback/action/add', { page: ref.module || 'otto', text, item }); toast(`Filed on ${ref.label}`); } catch (e) { toast(e.message); }
  };
  btn.addEventListener('click', send);
  ta.addEventListener('keydown', (e) => { e.stopPropagation(); if (e.key === 'Escape') { closePop(); togglePoint(false); } else if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); send(); } });
  $('.acts', pop).replaceWith(h('div', { class: 'fb' }, ta, h('div', { class: 'crow' }, btn)));
  ta.focus();
}
function bind() {
  document.addEventListener('mousemove', (e) => {
    if (!S.point) return;
    const el = e.target.closest && e.target.closest(POINTABLE);
    if (el !== aimed) { if (aimed) aimed.classList.remove('aim'); aimed = el; if (aimed) aimed.classList.add('aim'); }
  });
  document.addEventListener('click', (e) => {
    if (!S.point || e.target.closest('#pointPop, #pointBtn, #paletteScrim, #helpScrim')) return;
    e.preventDefault(); e.stopPropagation();
    if (getSelection().toString().trim()) return;
    openPop(refOf(e.target), e.clientX, e.clientY);
  }, true);
  document.addEventListener('mousedown', (e) => { if ($('#pointPop') && !e.target.closest('#pointPop')) closePop(); });
  document.addEventListener('mouseup', (e) => {
    if (!S.point || e.target.closest('#pointPop, textarea, input, .chat, .panel')) return;
    setTimeout(() => {
      const s = getSelection(), text = s && s.toString().replace(/\s+/g, ' ').trim();
      if (!text || text.length < 4 || !s.anchorNode || !($('#main').contains(s.anchorNode) || $('#page').contains(s.anchorNode))) return;
      const r = s.getRangeAt(0).getBoundingClientRect();
      const ref = refOf(s.anchorNode.nodeType === 1 ? s.anchorNode : s.anchorNode.parentElement);
      ref.quote = text.slice(0, SELECTION_CHARS); ref.part = 'quoted text';
      if (ref.item) ref.label = `${modOf(ref.module).title}, ${ref.item.title}, quoted text`;
      openPop(ref, r.left + r.width / 2, r.bottom);
    }, 0);
  });
}
bind();
registerPoint({ toggle });
