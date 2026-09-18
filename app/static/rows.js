// Shared tokens and small components. Every number here comes from the artboard.
import { h } from './vendor/preact.mjs';
import htm from './vendor/htm.mjs';

export const html = htm.bind(h);

export const T = {
  ground: '#101114', panel: '#1a1c21', box: '#1e2126', raised: '#23262c',
  text: '#e6e7ea', muted: '#8b8f98', dim: '#5f636c',
  hair: 'rgba(230,231,234,.08)', ring: 'inset 0 0 0 1px rgba(230,231,234,.14)',
  mono: "'JetBrains Mono', ui-monospace, monospace",   // code only; everything else is Inter
};
export const meta13 = { fontSize: 13 };
export const nums = { fontVariantNumeric: 'tabular-nums' };
export const code13 = { fontFamily: T.mono, fontSize: 13 };
const pad2 = (n) => String(n).padStart(2, '0');

// MM-DD-YYYY of an ISO timestamp, today's when none.
export function dayLabel(iso) {
  const d = iso ? new Date(iso) : new Date();
  return `${pad2(d.getMonth() + 1)}-${pad2(d.getDate())}-${d.getFullYear()}`;
}

// MM-DD-YYYY of a plain date the server keeps as YYYY-MM-DD; a trailing time is dropped.
export function dateLabel(ymd) {
  if (!ymd) return '';
  const [y, m, d] = ymd.slice(0, 10).split('-');
  return `${m}-${d}-${y}`;
}

export function clock(iso, fmt) {
  const d = new Date(iso);
  if (fmt === '12h') return d.toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' });
  return `${pad2(d.getHours())}:${pad2(d.getMinutes())}`;
}

// Same day: time. Otherwise MM-DD-YYYY.
export function stamp(iso, fmt) {
  if (!iso) return '';
  const d = new Date(iso);
  return d.toDateString() === new Date().toDateString() ? clock(iso, fmt) : dayLabel(iso);
}

export function Icon({ svg, size = 16, color = 'currentColor', sw = 1.6 }) {
  return html`<svg width=${size} height=${size} viewBox="0 0 20 20" fill="none" stroke=${color} stroke-width=${sw}
    dangerouslySetInnerHTML=${{ __html: svg || '' }} />`;
}

// Group header on a module page: the day, or a name; nothing when the group has none.
export function GroupHeader({ label }) {
  if (!label) return null;
  return html`<div style=${{ display: 'flex', alignItems: 'center', height: 28, padding: '0 12px', ...meta13, ...nums, color: T.muted }}>${label}</div>`;
}

// Group header on Home: hue-colored module name with its icon.
export function ModuleHeader({ label, hue, icon, onClick }) {
  return html`<div onClick=${onClick} style=${{ display: 'flex', alignItems: 'center', gap: 8, height: 28, padding: '0 12px', color: hue, fontWeight: 500, cursor: onClick ? 'pointer' : 'default' }}>
    <${Icon} svg=${icon} />${label}</div>`;
}

// Every list row is a box on its panel: raised while it is new, flat and muted once read or done, a hue bar when selected.
export function rowStyle({ selected, hue, dim, height = 36 }) {
  return {
    display: 'flex', alignItems: 'center', gap: 12, height, padding: '0 12px', borderRadius: 6, cursor: 'pointer',
    background: selected ? T.raised : dim ? 'transparent' : T.box,
    boxShadow: selected ? `inset 2px 0 0 ${hue}` : `inset 0 0 0 1px ${T.hair}`,
    color: dim ? T.muted : T.text,
  };
}

// One line per row: the text, then `stampText` when the row carries one. Leading slot: a progress bar or a task mark.
export function Row({ row, selected, onSelect, hue, height = 36 }) {
  const lead = row.leading || {};
  let leading = null;
  if (lead.pct !== undefined) leading = html`<span style=${{ width: 40, height: 2, flex: 'none', background: 'rgba(230,231,234,.1)', position: 'relative', overflow: 'hidden', borderRadius: 1 }}>
      <span style=${{ position: 'absolute', left: 0, top: 0, bottom: 0, background: hue, width: `${lead.pct}%` }} /></span>`;
  else if (lead.task) leading = html`<span style=${{ width: 10, height: 10, flex: 'none', borderRadius: 2, boxShadow: `inset 0 0 0 1.5px ${row.done ? T.dim : hue}` }} />`;
  const dim = row.unread === false || !!row.done;
  return html`<div class="row" onClick=${(e) => onSelect(e)} style=${rowStyle({ selected, hue, dim, height })}>
    ${leading}
    <span style=${{ flex: '1 1 auto', minWidth: 0, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis', color: row.live ? hue : 'inherit', fontWeight: row.unread ? 500 : 400, textDecoration: row.done ? 'line-through' : 'none' }}>${row.text}</span>
    ${row.stampText !== undefined && html`<span style=${{ flex: 'none', ...meta13, ...nums, color: T.dim }}>${row.stampText}</span>`}
  </div>`;
}

export function Chips({ chips, active, hue, onPick }) {
  return html`<div style=${{ display: 'flex', alignItems: 'center', gap: 8, padding: '0 12px', flexWrap: 'wrap' }}>
    ${chips.map((c) => html`<span key=${c} class="ring" onClick=${() => onPick(c)} style=${{ padding: '3px 9px', borderRadius: 6, fontSize: 13, cursor: 'pointer', background: c === active ? hue : 'transparent', color: c === active ? T.ground : T.muted }}>${c}</span>`)}
  </div>`;
}

export function Search({ value, onInput, hue }) {
  return html`<input value=${value} onInput=${(e) => onInput(e.target.value)} placeholder="Search"
    style=${{ width: '100%', height: 36, marginBottom: 16, padding: '0 12px', border: 0, borderRadius: 6, background: T.raised, color: T.text, fontSize: 15, '--hue': hue }} />`;
}

// Every composer and capture box. Grows with its text from three lines to half the viewport, then scrolls
// (the browser's own content sizing, as the notebook's cells). `style` overrides the surface; `taRef` gets the element.
export function TextArea({ value, onInput, onKeyDown, placeholder, hue, disabled, taRef, style }) {
  return html`<textarea ref=${taRef} value=${value} rows="3" placeholder=${placeholder || ''} disabled=${disabled} spellcheck="false"
    onInput=${onInput} onKeyDown=${onKeyDown}
    style=${{ display: 'block', width: '100%', minHeight: 88, maxHeight: '50vh', overflow: 'auto', resize: 'none', fieldSizing: 'content', padding: '10px 12px', border: 0, borderRadius: 6, background: T.raised, color: T.text, fontSize: 15, lineHeight: 1.5, '--hue': hue, ...style }} />`;
}

// Enter submits a composer; Shift+Enter breaks the line.
export const submitOnEnter = (fn) => (e) => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); fn(); } };

export function Button({ label, primary, hue, onClick, right }) {
  const base = { padding: '5px 10px', borderRadius: 6, fontSize: 13, cursor: 'pointer', marginLeft: right ? 'auto' : 0 };
  if (primary) return html`<span onClick=${onClick} style=${{ ...base, background: hue, color: T.ground, fontWeight: 500 }}>${label}</span>`;
  return html`<span class="ring" onClick=${onClick} style=${{ ...base, color: T.muted }}>${label}</span>`;
}

// A 28px icon control: the header's settings and feedback, a composer's attach.
export function IconButton({ svg, title, on, onClick, size = 17 }) {
  return html`<span class="ring" title=${title} onClick=${onClick} style=${{ display: 'grid', placeItems: 'center', width: 28, height: 28, borderRadius: 6, cursor: 'pointer', flex: 'none', color: on ? T.text : T.muted, background: on ? T.raised : 'transparent' }}>
    <${Icon} svg=${svg} size=${size} /></span>`;
}

// The one control for anything new; raised while the new thing is what is open.
export function Plus({ onClick, title, active }) {
  return html`<span class="ring" title=${title || 'new'} onClick=${onClick} style=${{ display: 'grid', placeItems: 'center', width: 28, height: 28, borderRadius: 6, cursor: 'pointer', fontSize: 18, lineHeight: 1, flex: 'none', color: active ? T.text : T.muted, background: active ? T.raised : 'transparent' }}>+</span>`;
}

// The send key, the same on every composer.
export function Enter({ onClick, busy }) {
  return html`<span title="send" onClick=${onClick} style=${{ marginLeft: 'auto', padding: '3px 10px', borderRadius: 6, cursor: 'pointer', flex: 'none', ...meta13, color: busy ? T.dim : T.text, boxShadow: T.ring }}>↵</span>`;
}

// A pulsing hue dot: a turn is running.
export function Busy({ hue }) {
  return html`<span style=${{ width: 6, height: 6, borderRadius: 3, flex: 'none', background: hue, animation: 'otto-pulse 1.2s ease-in-out infinite' }} />`;
}

export function Toggle({ on, onFlip }) {
  return html`<span onClick=${onFlip} style=${{ marginLeft: 'auto', width: 28, height: 16, borderRadius: 8, position: 'relative', transition: 'background 120ms', cursor: 'pointer', background: on ? T.text : 'rgba(230,231,234,.14)' }}>
    <span style=${{ position: 'absolute', top: 2, width: 12, height: 12, borderRadius: 6, transition: 'left 120ms', background: on ? T.ground : T.muted, left: on ? 14 : 2 }} /></span>`;
}

export function Empty({ text }) {
  return html`<div style=${{ ...meta13, color: T.dim, padding: '0 12px', height: 32, display: 'flex', alignItems: 'center' }}>${text}</div>`;
}

// The one link under a cut list.
export function More({ onClick }) {
  return html`<div style=${{ display: 'flex', alignItems: 'center', height: 32, padding: '0 12px' }}>
    <span class="ring" onClick=${onClick} style=${{ cursor: 'pointer', color: T.muted, padding: '3px 8px', borderRadius: 6, ...meta13 }}>more</span></div>`;
}

// A one-line text box on the ground (the panel surface); `extra` overrides.
export function input(hue, extra = {}) {
  return { height: 30, padding: '0 10px', border: 0, borderRadius: 6, background: T.panel, color: T.text, fontSize: 13, '--hue': hue, ...extra };
}

// Dates are typed as MM-DD-YYYY: digits only, the dashes placed as they come, the rest of the format dim until it is filled.
const MASK = 'MM-DD-YYYY';

export function maskDate(raw) {
  const d = raw.replace(/\D/g, '').slice(0, 8);
  return d.length > 4 ? `${d.slice(0, 2)}-${d.slice(2, 4)}-${d.slice(4)}` : d.length > 2 ? `${d.slice(0, 2)}-${d.slice(2)}` : d;
}

// YYYY-MM-DD for the server; '' when blank; null while the date is still being typed.
export function isoDate(shown) {
  if (!shown) return '';
  const m = /^(\d\d)-(\d\d)-(\d{4})$/.exec(shown);
  return m ? `${m[3]}-${m[1]}-${m[2]}` : null;
}

export function DateInput({ value, onInput, onEnter, hue, surface = T.panel, width = 116 }) {
  const font = { ...meta13, ...nums, fontFamily: 'inherit' };
  return html`<span style=${{ position: 'relative', display: 'inline-block', width, height: 30, borderRadius: 6, background: surface, flex: 'none' }}>
    <span aria-hidden="true" style=${{ position: 'absolute', inset: 0, padding: '0 10px', lineHeight: '30px', whiteSpace: 'pre', pointerEvents: 'none', ...font }}>
      <span style=${{ color: 'transparent' }}>${value}</span><span style=${{ color: T.dim }}>${MASK.slice(value.length)}</span></span>
    <input value=${value} onInput=${(e) => onInput(maskDate(e.target.value))} onKeyDown=${(e) => { if (e.key === 'Enter' && onEnter) onEnter(); }}
      style=${{ position: 'relative', width: '100%', height: 30, padding: '0 10px', border: 0, borderRadius: 6, background: 'transparent', color: T.text, ...font, '--hue': hue }} />
  </span>`;
}

export function fmtInt(n) {
  return typeof n === 'number' ? n.toLocaleString() : String(n);
}

export function bytes(n) {
  if (n < 1024) return `${n} B`;
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(0)} KB`;
  if (n < 1024 ** 3) return `${(n / 1024 ** 2).toFixed(1)} MB`;
  return `${(n / 1024 ** 3).toFixed(2)} GB`;
}

export function interval(sec) {
  if (sec % 86400 === 0) return `${sec / 86400} d`;
  if (sec % 3600 === 0) return `${sec / 3600} h`;
  if (sec % 60 === 0) return `${sec / 60} min`;
  return `${sec} s`;
}
