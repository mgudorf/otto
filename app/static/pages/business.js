// Business: LEFT = chips + rows by day · MIDDLE blank = capture box and open leads.
import { html, T, mono13, Row, GroupHeader, Chips, Search, Button, Empty, fmtInt } from '../rows.js';
import { get, post } from '../api.js';
import { Inspector } from '../shell.js';

export async function load(app) {
  const { query, chip, more } = app.state;
  const q = new URLSearchParams({ query, chip, page: String(more) });
  const [left, blank] = await Promise.all([get(`/api/business/left?${q}`), get('/api/business/blank')]);
  return { left, blank };
}

export function meta(app) {
  const b = app.state.data && app.state.data.blank;
  if (!b) return '';
  const total = Object.values(b.counts).reduce((a, n) => a + n, 0);
  return b.leads.length ? `${fmtInt(total)} · ${b.leads.length} to review` : fmtInt(total);
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
      ${g.rows.map((r) => html`<${Row} key=${r.id} row=${r} hue=${mod.hue} fmt=${fmt} selected=${!!sel && String(sel.id) === String(r.id)} onSelect=${() => app.select({ module: 'business', id: r.id })} />`)}
    </div>`)}
    <div style=${{ display: 'flex', alignItems: 'center', gap: 16, height: 32, padding: '0 12px', ...mono13, color: T.dim }}>${data.left.showing}
      ${data.left.more && html`<span class="ring" onClick=${() => rerun({ more: app.state.more + 1 })} style=${{ cursor: 'pointer', color: T.muted, padding: '3px 8px', borderRadius: 6 }}>more</span>`}
    </div>
  </div>`;
}

class Capture {
  constructor() { this.kind = 'plan'; this.text = ''; this.ref = ''; }
}
const capture = new Capture();

export function Middle({ app, data, mod, fmt }) {
  const hue = mod.hue;
  const decide = async (id, verb) => { await post(`/api/business/action/${verb}`, { id }); app.refresh(); };
  if (app.state.sel) {
    const item = app.state.item;
    const act = async (a) => {
      if (a.href) { window.open(a.href, '_blank'); return; }
      if (a.confirm && !window.confirm(a.confirm)) return;
      await post(`/api/business/action/${a.verb}`, { id: item.id });
      if (a.removes) app.select(null); else app.loadItem(app.state.sel);
      app.refresh();
    };
    const detail = item && !item.error ? html`<div style=${{ display: 'flex', flexDirection: 'column', gap: 6 }}>
      ${item.why && html`<span style=${{ lineHeight: 1.6 }}>${item.why}</span>`}
      ${item.ref && html`<span style=${{ ...mono13, color: T.muted, wordBreak: 'break-all' }}>${item.ref}</span>`}
      ${item.kind === 'lead' && html`<span style=${{ ...mono13, color: T.dim }}>${item.status}</span>`}
    </div>` : null;
    return html`<${Inspector} app=${app} item=${item} mod=${mod} fmt=${fmt} onAction=${act}>${detail}<//>`;
  }
  const b = data.blank;
  const save = async () => {
    const text = capture.text.trim();
    if (!text) return;
    await post('/api/business/action/capture', { kind: capture.kind, text, ref: capture.ref.trim() });
    capture.text = ''; capture.ref = '';
    app.refresh();
  };
  return html`<div style=${{ display: 'flex', flexDirection: 'column', gap: 16 }}>
    <div style=${{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
      ${b.kinds.map((k) => html`<span key=${k} class="ring" onClick=${() => { capture.kind = k; app.forceUpdate(); }} style=${{ padding: '3px 9px', borderRadius: 6, fontSize: 13, cursor: 'pointer', background: capture.kind === k ? hue : 'transparent', color: capture.kind === k ? T.ground : T.muted }}>${k}</span>`)}
      <span style=${{ marginLeft: 'auto', ...mono13, color: T.dim }}>${Object.entries(b.counts).map(([k, n]) => `${n} ${k}`).join(' · ') || 'empty'}</span>
    </div>
    <textarea value=${capture.text} placeholder=${{ plan: 'What you are pursuing, in your own words…', person: 'Who, and why they matter…', event: 'What, where, when…' }[capture.kind]} spellcheck="false"
      onInput=${(e) => { capture.text = e.target.value; }}
      onKeyDown=${(e) => { if (e.key === 'Enter' && (e.ctrlKey || e.metaKey)) { e.preventDefault(); save(); } }}
      style=${{ width: '100%', minHeight: 112, resize: 'vertical', padding: '12px 14px', border: 0, borderRadius: 6, background: T.panel, color: T.text, fontSize: 15, lineHeight: 1.6, '--hue': hue }} />
    <div style=${{ display: 'flex', alignItems: 'center', gap: 8 }}>
      <${Button} label="Save" primary=${true} hue=${hue} onClick=${save} />
      <input placeholder="link, optional" value=${capture.ref} onInput=${(e) => { capture.ref = e.target.value; }}
        style=${{ flex: 1, height: 30, padding: '0 10px', border: 0, borderRadius: 6, background: T.panel, color: T.text, fontSize: 13, '--hue': hue }} />
      <span style=${{ ...mono13, color: T.dim }}>ctrl+enter</span>
    </div>
    ${b.leads.length > 0 && html`<div style=${{ display: 'flex', flexDirection: 'column', gap: 2, marginTop: 16 }}>
      <${GroupHeader} label="leads to review" count=${b.leads.length} />
      ${b.leads.map((l) => html`<div key=${l.id} style=${{ display: 'flex', alignItems: 'center', gap: 12, minHeight: 36, padding: '6px 12px', borderRadius: 6 }}>
        <div style=${{ flex: 1, minWidth: 0, display: 'flex', flexDirection: 'column', gap: 2 }}>
          <span onClick=${() => app.select({ module: 'business', id: l.id })} style=${{ cursor: 'pointer' }}>${l.text}</span>
          ${l.why && html`<span style=${{ fontSize: 13, color: T.muted }}>${l.why}</span>`}
        </div>
        <${Button} label="Accept" hue=${hue} onClick=${() => decide(l.id, 'accept')} />
        <${Button} label="Dismiss" onClick=${() => decide(l.id, 'dismiss')} />
      </div>`)}
    </div>`}
  </div>`;
}
