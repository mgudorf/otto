// Social: LEFT = chips + events by day · MIDDLE blank = the interest box, category counts and the events waiting on a yes or no.
import { html, T, mono13, Row, GroupHeader, Chips, Search, Button, Empty, fmtInt } from '../rows.js';
import { get, post } from '../api.js';
import { Inspector } from '../shell.js';

export async function load(app) {
  const { query, chip, more } = app.state;
  const q = new URLSearchParams({ query, chip: chip || 'Upcoming', page: String(more) });
  const [left, blank] = await Promise.all([get(`/api/social/left?${q}`), get('/api/social/blank')]);
  return { left, blank };
}

export function meta(app) {
  const b = app.state.data && app.state.data.blank;
  if (!b) return '';
  const upcoming = Object.values(b.counts).reduce((a, n) => a + n, 0);
  return b.events.length ? `${fmtInt(upcoming)} upcoming · ${b.events.length} to review` : `${fmtInt(upcoming)} upcoming`;
}

export function Left({ app, data, mod, fmt }) {
  const sel = app.state.sel;
  const rerun = (patch) => app.setState(patch, () => app.refresh());
  return html`<div style=${{ display: 'flex', flexDirection: 'column', gap: 20 }}>
    <${Search} value=${app.state.query} hue=${mod.hue} onInput=${(v) => rerun({ query: v, more: 0 })} />
    <${Chips} chips=${data.left.chips} active=${data.left.chip} hue=${mod.hue} onPick=${(c) => rerun({ chip: c, more: 0 })} />
    ${data.left.groups.length === 0 && html`<${Empty} text=${app.state.query ? 'no matches' : 'nothing here yet'} />`}
    ${data.left.groups.map((g) => html`<div key=${g.label} style=${{ display: 'flex', flexDirection: 'column', gap: 2 }}>
      <${GroupHeader} label=${g.label} count=${g.count} />
      ${g.rows.map((r) => html`<${Row} key=${r.id} row=${r} hue=${mod.hue} fmt=${fmt} selected=${!!sel && String(sel.id) === String(r.id)} onSelect=${() => app.select({ module: 'social', id: r.id })} />`)}
    </div>`)}
    <div style=${{ display: 'flex', alignItems: 'center', gap: 16, height: 32, padding: '0 12px', ...mono13, color: T.dim }}>${data.left.showing}
      ${data.left.more && html`<span class="ring" onClick=${() => rerun({ more: app.state.more + 1 })} style=${{ cursor: 'pointer', color: T.muted, padding: '3px 8px', borderRadius: 6 }}>more</span>`}
    </div>
  </div>`;
}

class Capture {
  constructor() { this.text = ''; this.ref = ''; }
}
const capture = new Capture();

function When({ ev }) {
  const [day, clock] = ev.starts_at.split('T');
  const d = new Date(`${day}T12:00`);
  const label = `${d.toDateString().slice(0, 3)} ${day.slice(8)}/${day.slice(5, 7)}`;
  return html`<span style=${{ ...mono13, color: T.muted, flex: 'none' }}>${clock === '00:00' ? label : `${label} ${clock}`}</span>`;
}

export function Middle({ app, data, mod, fmt }) {
  const hue = mod.hue;
  const decide = async (id, verb) => { await post(`/api/social/action/${verb}`, { id }); app.refresh(); };
  if (app.state.sel) {
    const item = app.state.item;
    const act = async (a) => {
      if (a.href) { window.open(a.href, '_blank'); return; }
      if (a.confirm && !window.confirm(a.confirm)) return;
      await post(`/api/social/action/${a.verb}`, { id: item.id });
      if (a.removes) app.select(null); else app.loadItem(app.state.sel);
      app.refresh();
    };
    const where = item && [item.venue, item.city].filter(Boolean).join(', ');
    const detail = item && !item.error ? html`<div style=${{ display: 'flex', flexDirection: 'column', gap: 6 }}>
      ${item.starts_at && html`<span style=${{ ...mono13, color: hue }}>${item.starts_at.replace('T', ' ').replace(' 00:00', ' (all day)')}</span>`}
      ${where && html`<span style=${{ color: T.muted }}>${where}</span>`}
      ${item.why && html`<span style=${{ lineHeight: 1.6 }}>${item.why}</span>`}
      ${item.ref && html`<span style=${{ ...mono13, color: T.muted, wordBreak: 'break-all' }}>${item.ref}</span>`}
      ${item.kind === 'event' && html`<span style=${{ ...mono13, color: T.dim }}>${item.category} · ${item.status}</span>`}
    </div>` : null;
    return html`<${Inspector} app=${app} item=${item} mod=${mod} fmt=${fmt} onAction=${act}>${detail}<//>`;
  }
  const b = data.blank;
  const save = async () => {
    const text = capture.text.trim();
    if (!text) return;
    await post('/api/social/action/capture', { text, ref: capture.ref.trim() });
    capture.text = ''; capture.ref = '';
    app.refresh();
  };
  const jump = (c) => app.setState({ query: c, chip: 'Upcoming', more: 0 }, () => app.refresh());
  return html`<div style=${{ display: 'flex', flexDirection: 'column', gap: 16 }}>
    <div style=${{ display: 'flex', alignItems: 'center', gap: 8, ...mono13, color: T.dim }}>
      <span>${b.cities.map((c) => c.split(',')[0]).join(' · ')}</span>
      <span style=${{ marginLeft: 'auto' }}>${b.going} going · ${b.interests} interests</span>
    </div>
    <textarea value=${capture.text} placeholder="What you want to do, learn or who you want to meet…" spellcheck="false"
      onInput=${(e) => { capture.text = e.target.value; }}
      onKeyDown=${(e) => { if (e.key === 'Enter' && (e.ctrlKey || e.metaKey)) { e.preventDefault(); save(); } }}
      style=${{ width: '100%', minHeight: 112, resize: 'vertical', padding: '12px 14px', border: 0, borderRadius: 6, background: T.panel, color: T.text, fontSize: 15, lineHeight: 1.6, '--hue': hue }} />
    <div style=${{ display: 'flex', alignItems: 'center', gap: 8 }}>
      <${Button} label="Save interest" primary=${true} hue=${hue} onClick=${save} />
      <input placeholder="link, optional" value=${capture.ref} onInput=${(e) => { capture.ref = e.target.value; }}
        style=${{ flex: 1, height: 30, padding: '0 10px', border: 0, borderRadius: 6, background: T.panel, color: T.text, fontSize: 13, '--hue': hue }} />
      <span style=${{ ...mono13, color: T.dim }}>ctrl+enter</span>
    </div>
    <div style=${{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap', padding: '0 12px' }}>
      ${b.categories.map((c) => html`<span key=${c} class="ring" onClick=${() => jump(c)} style=${{ padding: '3px 9px', borderRadius: 6, fontSize: 13, cursor: 'pointer', color: b.counts[c] ? T.muted : T.dim }}>${c} <span style=${{ ...mono13, color: b.counts[c] ? hue : T.dim }}>${b.counts[c] || 0}</span></span>`)}
    </div>
    ${b.events.length > 0 && html`<div style=${{ display: 'flex', flexDirection: 'column', gap: 2, marginTop: 16 }}>
      <${GroupHeader} label="events to review" count=${b.events.length} />
      ${b.events.map((e) => html`<div key=${e.id} style=${{ display: 'flex', alignItems: 'center', gap: 12, minHeight: 36, padding: '6px 12px', borderRadius: 6 }}>
        <${When} ev=${e} />
        <div style=${{ flex: 1, minWidth: 0, display: 'flex', flexDirection: 'column', gap: 2 }}>
          <span onClick=${() => app.select({ module: 'social', id: e.id })} style=${{ cursor: 'pointer' }}>${e.text}</span>
          ${(e.why || e.venue) && html`<span style=${{ fontSize: 13, color: T.muted }}>${[e.venue, e.city].filter(Boolean).join(', ')}${e.why ? ` — ${e.why}` : ''}</span>`}
        </div>
        <${Button} label="Going" hue=${hue} onClick=${() => decide(e.id, 'going')} />
        <${Button} label="Dismiss" onClick=${() => decide(e.id, 'dismiss')} />
      </div>`)}
    </div>`}
  </div>`;
}
