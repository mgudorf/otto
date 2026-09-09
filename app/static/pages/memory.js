// Memory: LEFT = chips + rows by day · MIDDLE blank = capture box and open suggestions.
import { html, T, mono13, Row, GroupHeader, Chips, Search, Button, Empty, fmtInt } from '../rows.js';
import { get, post } from '../api.js';
import { Inspector } from '../shell.js';

const KIND_HUE = '#d1a36a';

export async function load(app) {
  const { query, chip, more } = app.state;
  const q = new URLSearchParams({ query, chip, page: String(more) });
  const [left, blank] = await Promise.all([get(`/api/memory/left?${q}`), get('/api/memory/blank')]);
  return { left, blank };
}

export function meta(app) {
  const c = app.state.data && app.state.data.blank.counts;
  if (!c) return '';
  const total = Object.values(c).reduce((a, b) => a + b, 0);
  return `${fmtInt(total)}`;
}

export function Left({ app, data, mod, fmt }) {
  const sel = app.state.sel;
  const rerun = (patch) => app.setState(patch, () => app.refresh());
  return html`<div style=${{ display: 'flex', flexDirection: 'column', gap: 20 }}>
    <${Search} value=${app.state.query} hue=${mod.hue} onInput=${(v) => rerun({ query: v, more: 0 })} />
    <${Chips} chips=${data.left.chips} active=${data.left.chip} hue=${mod.hue} onPick=${(c) => rerun({ chip: c, more: 0 })} />
    ${data.left.groups.length === 0 && html`<${Empty} text=${app.state.query ? 'no matches' : 'nothing captured yet'} />`}
    ${data.left.groups.map((g) => html`<div key=${g.label} style=${{ display: 'flex', flexDirection: 'column', gap: 2 }}>
      <${GroupHeader} label=${g.label} count=${g.count} />
      ${g.rows.map((r) => html`<${Row} key=${r.id} row=${r} hue=${KIND_HUE} fmt=${fmt} selected=${!!sel && String(sel.id) === String(r.id)} onSelect=${() => app.select({ module: 'memory', id: r.id })} />`)}
    </div>`)}
    <div style=${{ display: 'flex', alignItems: 'center', gap: 16, height: 32, padding: '0 12px', ...mono13, color: T.dim }}>${data.left.showing}
      ${data.left.more && html`<span class="ring" onClick=${() => rerun({ more: app.state.more + 1 })} style=${{ cursor: 'pointer', color: T.muted, padding: '3px 8px', borderRadius: 6 }}>more</span>`}
    </div>
  </div>`;
}

class Capture {
  constructor() { this.kind = 'note'; this.text = ''; this.tags = ''; }
}
const capture = new Capture();
let tagDraft = '';

export function Middle({ app, data, mod, fmt }) {
  const hue = mod.hue;
  if (app.state.sel) {
    const item = app.state.item;
    const act = async (a) => {
      if (a.href) { window.open(a.href, '_blank'); return; }
      if (a.confirm && !window.confirm(a.confirm)) return;
      await post(`/api/memory/action/${a.verb}`, { id: item.id });
      if (a.verb === 'forget') app.select(null); else app.loadItem(app.state.sel);
      app.refresh();
    };
    const tags = item && !item.error ? html`<div style=${{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap', ...mono13, color: T.muted }}>
      ${(item.tags || []).map((t) => html`<span key=${t} class="ring" title="remove" onClick=${async () => { await post('/api/memory/action/untag', { id: item.id, tag: t }); app.loadItem(app.state.sel); }} style=${{ padding: '2px 8px', borderRadius: 6, cursor: 'pointer', boxShadow: 'inset 0 0 0 1px rgba(230,231,234,.1)' }}>${t}</span>`)}
      <input placeholder="add tag" value=${tagDraft} onInput=${(e) => { tagDraft = e.target.value; }}
        onKeyDown=${async (e) => { if (e.key === 'Enter' && e.target.value.trim()) { const v = e.target.value.trim(); tagDraft = ''; e.target.value = ''; await post('/api/memory/action/tag', { id: item.id, tags: [v] }); app.loadItem(app.state.sel); app.refresh(); } }}
        style=${{ width: 120, height: 26, padding: '0 8px', border: 0, borderRadius: 6, background: T.raised, color: T.text, fontSize: 13, '--hue': hue }} />
    </div>` : null;
    return html`<${Inspector} app=${app} item=${item} mod=${mod} fmt=${fmt} onAction=${act}>${tags}<//>`;
  }
  const b = data.blank;
  const save = async () => {
    const text = capture.text.trim();
    if (!text) return;
    await post('/api/memory/action/capture', { kind: capture.kind, text, tags: capture.tags.split(',').map((t) => t.trim()).filter(Boolean) });
    capture.text = ''; capture.tags = '';
    app.refresh();
  };
  return html`<div style=${{ display: 'flex', flexDirection: 'column', gap: 16 }}>
    <div style=${{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
      ${b.kinds.map((k) => html`<span key=${k} class="ring" onClick=${() => { capture.kind = k; app.forceUpdate(); }} style=${{ padding: '3px 9px', borderRadius: 6, fontSize: 13, cursor: 'pointer', background: capture.kind === k ? hue : 'transparent', color: capture.kind === k ? T.ground : T.muted }}>${k}</span>`)}
      <span style=${{ marginLeft: 'auto', ...mono13, color: T.dim }}>${Object.entries(b.counts).map(([k, n]) => `${n} ${k}`).join(' · ') || 'empty'}</span>
    </div>
    <textarea value=${capture.text} placeholder=${capture.kind === 'link' ? 'https://… (then a note)' : 'Capture in your own words…'} spellcheck="false"
      onInput=${(e) => { capture.text = e.target.value; }}
      onKeyDown=${(e) => { if (e.key === 'Enter' && (e.ctrlKey || e.metaKey)) { e.preventDefault(); save(); } }}
      style=${{ width: '100%', minHeight: 112, resize: 'vertical', padding: '12px 14px', border: 0, borderRadius: 6, background: T.panel, color: T.text, fontSize: 15, lineHeight: 1.6, '--hue': hue }} />
    <div style=${{ display: 'flex', alignItems: 'center', gap: 8 }}>
      <${Button} label="Save" primary=${true} hue=${hue} onClick=${save} />
      <input placeholder="tags, comma separated" value=${capture.tags} onInput=${(e) => { capture.tags = e.target.value; }}
        style=${{ flex: 1, height: 30, padding: '0 10px', border: 0, borderRadius: 6, background: T.panel, color: T.text, fontSize: 13, '--hue': hue }} />
      <span style=${{ ...mono13, color: T.dim }}>ctrl+enter</span>
    </div>
    ${b.suggestions.length > 0 && html`<div style=${{ display: 'flex', flexDirection: 'column', gap: 2, marginTop: 16 }}>
      <${GroupHeader} label="suggested" count=${b.suggestions.length} />
      ${b.suggestions.map((s) => html`<div key=${s.id} style=${{ display: 'flex', alignItems: 'center', gap: 12, minHeight: 36, padding: '6px 12px', borderRadius: 6 }}>
        <span style=${{ flex: 1, minWidth: 0 }}>${s.text}</span>
        <${Button} label="Accept" hue=${hue} onClick=${async () => { await post('/api/memory/action/suggestion', { id: s.id, status: 'accepted' }); app.refresh(); }} />
        <${Button} label="Dismiss" onClick=${async () => { await post('/api/memory/action/suggestion', { id: s.id, status: 'dismissed' }); app.refresh(); }} />
      </div>`)}
    </div>`}
  </div>`;
}
