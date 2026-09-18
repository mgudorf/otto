// Second Brain: LEFT = search, All · Tasks, rows by day · MIDDLE blank = the capture box and open suggestions.
// A capture is a note, a link when it starts with a URL, or a task when the chip is on; the kind is never written out.
import { html, T, meta13, Row, GroupHeader, Chips, Search, Button, Empty, More, TextArea, submitOnEnter, Enter, input } from '../rows.js';
import { get, post } from '../api.js';
import { Inspector } from '../shell.js';

export async function load(app) {
  const { query, chip, more } = app.state;
  const q = new URLSearchParams({ query, chip, page: String(more) });
  const [left, blank] = await Promise.all([get(`/api/second_brain/left?${q}`), get('/api/second_brain/blank')]);
  return { left, blank };
}

export function Left({ app, data, mod }) {
  const sel = app.state.sel;
  const rerun = (patch) => app.setState(patch, () => app.refresh());
  return html`<div style=${{ display: 'flex', flexDirection: 'column', gap: 20 }}>
    <${Search} value=${app.state.query} hue=${mod.hue} onInput=${(v) => rerun({ query: v, more: 0 })} />
    <${Chips} chips=${data.left.chips} active=${data.left.chip} hue=${mod.hue} onPick=${(c) => rerun({ chip: c, more: 0 })} />
    ${data.left.groups.length === 0 && html`<${Empty} text=${app.state.query ? 'no matches' : 'nothing captured yet'} />`}
    ${data.left.groups.map((g) => html`<div key=${g.label} style=${{ display: 'flex', flexDirection: 'column', gap: 4 }}>
      <${GroupHeader} label=${g.label} />
      ${g.rows.map((r) => html`<${Row} key=${r.id} row=${r} hue=${mod.hue} selected=${!!sel && String(sel.id) === String(r.id)} onSelect=${() => app.select({ module: 'second_brain', id: r.id })} />`)}
    </div>`)}
    ${data.left.more && html`<${More} onClick=${() => rerun({ more: app.state.more + 1 })} />`}
  </div>`;
}

const capture = { task: false, text: '', tags: '' };
let tagDraft = '';

export function Middle({ app, data, mod, fmt }) {
  const hue = mod.hue;
  if (app.state.sel) {
    const item = app.state.item;
    const act = async (a) => {
      if (a.href) { window.open(a.href, '_blank'); return; }
      if (a.confirm && !window.confirm(a.confirm)) return;
      await post(`/api/second_brain/action/${a.verb}`, { id: item.id });
      if (a.removes) app.select(null); else app.loadItem(app.state.sel);
      app.refresh();
    };
    const tags = item && !item.error ? html`<div style=${{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap', ...meta13, color: T.muted }}>
      ${(item.tags || []).map((t) => html`<span key=${t} class="ring" title="remove" onClick=${async () => { await post('/api/second_brain/action/untag', { id: item.id, tag: t }); app.loadItem(app.state.sel); }} style=${{ padding: '2px 8px', borderRadius: 6, cursor: 'pointer', boxShadow: 'inset 0 0 0 1px rgba(230,231,234,.1)' }}>${t}</span>`)}
      <input placeholder="+ tag" value=${tagDraft} onInput=${(e) => { tagDraft = e.target.value; }}
        onKeyDown=${async (e) => { if (e.key === 'Enter' && e.target.value.trim()) { const v = e.target.value.trim(); tagDraft = ''; e.target.value = ''; await post('/api/second_brain/action/tag', { id: item.id, tags: [v] }); app.loadItem(app.state.sel); app.refresh(); } }}
        style=${input(hue, { width: 96, height: 26, background: T.raised })} />
    </div>` : null;
    return html`<${Inspector} app=${app} item=${item} mod=${mod} fmt=${fmt} onAction=${act}>${tags}<//>`;
  }
  const b = data.blank;
  const save = async () => {
    const text = capture.text.trim();
    if (!text) return;
    const kind = capture.task ? 'task' : /^https?:\/\//i.test(text) ? 'link' : 'note';
    await post('/api/second_brain/action/capture', { kind, text, tags: capture.tags.split(',').map((t) => t.trim()).filter(Boolean) });
    capture.text = ''; capture.tags = ''; capture.task = false;
    app.refresh();
  };
  return html`<div style=${{ display: 'flex', flexDirection: 'column', gap: 16 }}>
    <${TextArea} value=${capture.text} onInput=${(e) => { capture.text = e.target.value; }} onKeyDown=${submitOnEnter(save)} hue=${hue} style=${{ background: T.panel }} />
    <div style=${{ display: 'flex', alignItems: 'center', gap: 8 }}>
      <span class="ring" onClick=${() => { capture.task = !capture.task; app.forceUpdate(); }} style=${{ padding: '3px 9px', borderRadius: 6, fontSize: 13, cursor: 'pointer', background: capture.task ? hue : 'transparent', color: capture.task ? T.ground : T.muted }}>task</span>
      <input placeholder="tags" value=${capture.tags} onInput=${(e) => { capture.tags = e.target.value; }} onKeyDown=${(e) => { if (e.key === 'Enter') save(); }} style=${input(hue, { flex: 1 })} />
      <${Enter} onClick=${save} />
    </div>
    ${b.suggestions.length > 0 && html`<div style=${{ display: 'flex', flexDirection: 'column', gap: 4, marginTop: 16 }}>
      <${GroupHeader} label="suggested" />
      ${b.suggestions.map((s) => html`<div key=${s.id} style=${{ display: 'flex', alignItems: 'center', gap: 12, minHeight: 36, padding: '6px 12px', borderRadius: 6, background: T.panel }}>
        <span style=${{ flex: 1, minWidth: 0 }}>${s.text}</span>
        <${Button} label="Accept" hue=${hue} onClick=${async () => { await post('/api/second_brain/action/accept', { id: s.id }); app.refresh(); }} />
        <${Button} label="Dismiss" onClick=${async () => { await post('/api/second_brain/action/dismiss', { id: s.id }); app.refresh(); }} />
      </div>`)}
    </div>`}
  </div>`;
}
