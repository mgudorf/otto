// Education: LEFT = the due queue, then history by day · MIDDLE blank = progress per topic and an add-topic box.
import { html, T, mono13, Row, GroupHeader, Search, Button, Empty, stamp } from '../rows.js';
import { get, post } from '../api.js';
import { Inspector } from '../shell.js';

export async function load(app) {
  const { query, more } = app.state;
  const q = new URLSearchParams({ query, page: String(more) });
  const [left, blank] = await Promise.all([get(`/api/education/left?${q}`), get('/api/education/blank')]);
  return { left, blank };
}

export function meta(app) {
  const b = app.state.data && app.state.data.blank;
  return b ? `${b.due} due` : '';
}

export function Left({ app, data, mod, fmt }) {
  const sel = app.state.sel;
  const rerun = (patch) => app.setState(patch, () => app.refresh());
  return html`<div style=${{ display: 'flex', flexDirection: 'column', gap: 20 }}>
    <${Search} value=${app.state.query} hue=${mod.hue} onInput=${(v) => rerun({ query: v, more: 0 })} />
    ${data.left.groups.length === 0 && html`<${Empty} text=${app.state.query ? 'no matches' : 'no questions yet'} />`}
    ${data.left.groups.map((g) => html`<div key=${g.label} style=${{ display: 'flex', flexDirection: 'column', gap: 2 }}>
      <${GroupHeader} label=${g.label} count=${g.count} />
      ${g.rows.map((r) => html`<${Row} key=${r.id} row=${r} hue=${mod.hue} fmt=${fmt} selected=${!!sel && String(sel.id) === String(r.id)} onSelect=${() => app.select({ module: 'education', id: r.id })} />`)}
    </div>`)}
    <div style=${{ display: 'flex', alignItems: 'center', gap: 16, height: 32, padding: '0 12px', ...mono13, color: T.dim }}>${data.left.showing}
      ${data.left.more && html`<span class="ring" onClick=${() => rerun({ more: app.state.more + 1 })} style=${{ cursor: 'pointer', color: T.muted, padding: '3px 8px', borderRadius: 6 }}>more</span>`}
    </div>
  </div>`;
}

// The numbered parts under the premise, with score and note once graded, then the owner's feedback lines.
function Parts({ item }) {
  return html`<div style=${{ display: 'flex', flexDirection: 'column', gap: 12 }}>
    ${item.parts.map((p) => html`<div key=${p.n} style=${{ display: 'flex', gap: 12, lineHeight: 1.6 }}>
      <span style=${{ ...mono13, color: T.dim, flex: 'none', width: 20, paddingTop: 2 }}>${p.n}</span>
      <div style=${{ flex: 1, minWidth: 0 }}>${p.text}
        ${p.score !== null && p.score !== undefined && html`<div style=${{ ...mono13, color: T.muted }}>${p.score} / 100${p.note ? ` · ${p.note}` : ''}</div>`}
      </div>
    </div>`)}
    ${item.feedback.length > 0 && html`<div style=${{ display: 'flex', flexDirection: 'column', gap: 4, ...mono13, color: T.muted }}>
      ${item.feedback.map((f, i) => html`<span key=${i}>“${f}”</span>`)}
    </div>`}
  </div>`;
}

const draft = { name: '', description: '' };

export function Middle({ app, data, mod, fmt }) {
  const hue = mod.hue;
  if (app.state.sel) {
    const item = app.state.item;
    const ok = item && !item.error;
    const act = async (a) => {
      if (a.confirm && !window.confirm(a.confirm)) return;
      await post(`/api/education/action/${a.verb}`, { id: item.id });
      if (a.verb === 'start') app.sendToSession(`Q${item.id} part 1: `);
      app.loadItem(app.state.sel);
      app.refresh();
    };
    return html`<${Inspector} app=${app} item=${ok ? { ...item, text: `${item.title}\n\n${item.premise}` } : item} mod=${mod} fmt=${fmt} onAction=${act}>
      ${ok && html`<${Parts} item=${item} />`}
    <//>`;
  }
  const b = data.blank;
  const save = async () => {
    const name = draft.name.trim();
    if (!name) return;
    await post('/api/education/action/add_topic', { name, description: draft.description.trim() });
    draft.name = ''; draft.description = '';
    app.refresh();
  };
  const retire = async (t) => {
    if (!window.confirm(`Retire ${t.name}?`)) return;
    await post('/api/education/action/retire_topic', { id: t.id });
    app.refresh();
  };
  const cols = 'minmax(0,1fr) 28px 56px 40px 120px 64px 16px';
  const cell = { whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' };
  return html`<div style=${{ display: 'flex', flexDirection: 'column', gap: 16 }}>
    <span style=${{ ...mono13, color: T.dim }}>${b.due} due · ${b.topics.length} topics</span>
    <div style=${{ display: 'flex', flexDirection: 'column', ...mono13 }}>
      <div style=${{ display: 'grid', gridTemplateColumns: cols, gap: 12, height: 28, alignItems: 'center', padding: '0 12px', color: T.muted }}>topic<span>d</span><span>graded</span><span>avg</span><span>recent</span><span>last</span><span /></div>
      ${b.topics.length === 0 && html`<${Empty} text="no topics yet" />`}
      ${b.topics.map((t) => html`<div key=${t.id} class="trow" title=${t.description || ''} style=${{ display: 'grid', gridTemplateColumns: cols, gap: 12, height: 32, alignItems: 'center', padding: '0 12px', borderTop: `1px solid ${T.hair}`, color: T.text }}>
        <span style=${{ ...cell, fontFamily: 'Inter, system-ui, sans-serif', fontSize: 15 }}>${t.name}</span>
        <span style=${{ color: hue }}>d${t.difficulty}</span>
        <span style=${{ color: T.muted }}>${t.graded}/${t.asked}</span>
        <span>${t.average === null ? '–' : t.average}</span>
        <span style=${{ ...cell, color: T.muted }}>${t.recent.join(' ') || '–'}</span>
        <span style=${{ color: T.dim }}>${t.last_asked ? stamp(t.last_asked, fmt) : '–'}</span>
        <span class="bright-hover" title="retire" onClick=${() => retire(t)} style=${{ cursor: 'pointer', color: T.dim, textAlign: 'right' }}>×</span>
      </div>`)}
    </div>
    <div style=${{ display: 'flex', alignItems: 'center', gap: 8, marginTop: 8 }}>
      <input placeholder="new topic" value=${draft.name} onInput=${(e) => { draft.name = e.target.value; }} onKeyDown=${(e) => { if (e.key === 'Enter') save(); }}
        style=${{ width: 220, height: 30, padding: '0 10px', border: 0, borderRadius: 6, background: T.panel, color: T.text, fontSize: 15, '--hue': hue }} />
      <input placeholder="what you want from it, optional" value=${draft.description} onInput=${(e) => { draft.description = e.target.value; }} onKeyDown=${(e) => { if (e.key === 'Enter') save(); }}
        style=${{ flex: 1, height: 30, padding: '0 10px', border: 0, borderRadius: 6, background: T.panel, color: T.text, fontSize: 13, '--hue': hue }} />
      <${Button} label="Add" primary=${true} hue=${hue} onClick=${save} />
    </div>
  </div>`;
}
