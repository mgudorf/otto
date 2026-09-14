// Shared tokens and small components. Every number here comes from the artboard.
import { h } from './vendor/preact.mjs';
import htm from './vendor/htm.mjs';

export const html = htm.bind(h);

export const T = {
  ground: '#101114', panel: '#1a1c21', raised: '#23262c',
  text: '#e6e7ea', muted: '#8b8f98', dim: '#5f636c',
  hair: 'rgba(230,231,234,.08)',
  mono: "'JetBrains Mono', ui-monospace, monospace",
};
export const mono13 = { fontFamily: T.mono, fontSize: 13 };
const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];

export function dayLabel(iso) {
  const d = iso ? new Date(iso) : new Date();
  return `${String(d.getDate()).padStart(2, '0')} ${MONTHS[d.getMonth()]}`;
}

export function clock(iso, fmt) {
  const d = new Date(iso);
  if (fmt === '12h') return d.toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' });
  return `${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}`;
}

// Same day: time. Otherwise: "05 Sep".
export function stamp(iso, fmt) {
  if (!iso) return '';
  const d = new Date(iso);
  return d.toDateString() === new Date().toDateString() ? clock(iso, fmt) : dayLabel(iso);
}

export function Icon({ svg, size = 16, color = 'currentColor', sw = 1.6 }) {
  return html`<svg width=${size} height=${size} viewBox="0 0 20 20" fill="none" stroke=${color} stroke-width=${sw}
    dangerouslySetInnerHTML=${{ __html: svg || '' }} />`;
}

// Group header on a module page: "05 Sep 14" in mono.
export function GroupHeader({ label, count }) {
  return html`<div style=${{ display: 'flex', alignItems: 'baseline', gap: 10, height: 28, padding: '0 12px', ...mono13, color: T.muted }}>
    ${label}<span style=${{ color: T.dim }}>${count}</span></div>`;
}

// Group header on Home: hue-colored module name with its icon and count.
export function ModuleHeader({ label, count, hue, icon, onClick }) {
  return html`<div onClick=${onClick} style=${{ display: 'flex', alignItems: 'center', gap: 8, height: 28, padding: '0 12px', color: hue, fontWeight: 500, cursor: onClick ? 'pointer' : 'default' }}>
    <${Icon} svg=${icon} />${label}<span style=${{ ...mono13, color: T.dim, fontWeight: 400 }}>${count}</span></div>`;
}

// One line per row, stamp right after the text. Leading slot: kind | dot | ext | pct.
export function Row({ row, selected, onSelect, hue, fmt, height = 36 }) {
  const lead = row.leading || {};
  let leading = null;
  if (lead.kind !== undefined) leading = html`<span style=${{ flex: 'none', ...mono13, color: hue, width: 40 }}>${lead.kind}</span>`;
  else if (lead.dot !== undefined) leading = html`<span style=${{ width: 6, height: 6, borderRadius: 3, flex: 'none', background: lead.dot || 'transparent' }} />`;
  else if (lead.ext !== undefined) leading = html`<span style=${{ flex: 'none', ...mono13, color: hue, width: 40 }}>${lead.ext}</span>`;
  else if (lead.pct !== undefined) leading = html`<span style=${{ width: 40, height: 2, flex: 'none', background: 'rgba(230,231,234,.1)', position: 'relative', overflow: 'hidden', borderRadius: 1 }}>
      <span style=${{ position: 'absolute', left: 0, top: 0, bottom: 0, background: hue, width: `${lead.pct}%` }} /></span>`;
  return html`<div class="row" onClick=${(e) => onSelect(e)} style=${{ display: 'flex', alignItems: 'center', gap: 12, height, padding: '0 12px', borderRadius: 6, cursor: 'pointer', background: selected ? T.raised : 'transparent' }}>
    ${leading}
    <span style=${{ flex: '1 1 auto', minWidth: 0, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis', color: row.done ? T.dim : T.text, textDecoration: row.done ? 'line-through' : 'none', ...(row.mono ? mono13 : {}) }}>${row.text}</span>
    <span style=${{ flex: 'none', ...mono13, color: T.dim }}>${row.stampText !== undefined ? row.stampText : stamp(row.stamp, fmt)}</span>
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
  return html`<textarea ref=${taRef} value=${value} rows="3" placeholder=${placeholder} disabled=${disabled} spellcheck="false"
    onInput=${onInput} onKeyDown=${onKeyDown}
    style=${{ display: 'block', width: '100%', minHeight: 88, maxHeight: '50vh', overflow: 'auto', resize: 'none', fieldSizing: 'content', padding: '10px 12px', border: 0, borderRadius: 6, background: T.raised, color: T.text, fontSize: 15, lineHeight: 1.5, '--hue': hue, ...style }} />`;
}

export function Button({ label, primary, hue, onClick, right }) {
  const base = { padding: '5px 10px', borderRadius: 6, fontSize: 13, cursor: 'pointer', marginLeft: right ? 'auto' : 0 };
  if (primary) return html`<span onClick=${onClick} style=${{ ...base, background: hue, color: T.ground, fontWeight: 500 }}>${label}</span>`;
  return html`<span class="ring" onClick=${onClick} style=${{ ...base, color: T.muted }}>${label}</span>`;
}

export function Toggle({ on, onFlip }) {
  return html`<span onClick=${onFlip} style=${{ marginLeft: 'auto', width: 28, height: 16, borderRadius: 8, position: 'relative', transition: 'background 120ms', cursor: 'pointer', background: on ? T.text : 'rgba(230,231,234,.14)' }}>
    <span style=${{ position: 'absolute', top: 2, width: 12, height: 12, borderRadius: 6, transition: 'left 120ms', background: on ? T.ground : T.muted, left: on ? 14 : 2 }} /></span>`;
}

export function Empty({ text }) {
  return html`<div style=${{ ...mono13, color: T.dim, padding: '0 12px', height: 32, display: 'flex', alignItems: 'center' }}>${text}</div>`;
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
