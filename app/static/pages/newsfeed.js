// Newsfeed: LEFT = chips + entries by the day they were found, open ones bright · MIDDLE blank = the searches, each killable · selected = entry or search.
import { html, T, meta13, nums, Row, rowStyle, GroupHeader, Chips, Search, Empty, More, dateLabel } from '../rows.js';
import { get, post } from '../api.js';
import { Inspector } from '../shell.js';

const RED = '#cf7b7b';

export async function load(app) {
  const { query, chip, more } = app.state;
  const q = new URLSearchParams({ query, chip, page: String(more) });
  const [left, blank] = await Promise.all([get(`/api/newsfeed/left?${q}`), get('/api/newsfeed/blank')]);
  return { left, blank };
}

export function Left({ app, data, mod }) {
  const sel = app.state.sel;
  const rerun = (patch) => app.setState(patch, () => app.refresh());
  return html`<div style=${{ display: 'flex', flexDirection: 'column', gap: 20 }}>
    <${Search} value=${app.state.query} hue=${mod.hue} onInput=${(v) => rerun({ query: v, more: 0 })} />
    <${Chips} chips=${data.left.chips} active=${data.left.chip} hue=${mod.hue} onPick=${(c) => rerun({ chip: c, more: 0 })} />
    ${data.left.groups.length === 0 && html`<${Empty} text=${app.state.query ? 'no matches' : 'nothing found yet'} />`}
    ${data.left.groups.map((g) => html`<div key=${g.label} style=${{ display: 'flex', flexDirection: 'column', gap: 4 }}>
      <${GroupHeader} label=${g.label} />
      ${g.rows.map((r) => html`<${Row} key=${r.id} row=${r} hue=${mod.hue} selected=${!!sel && String(sel.id) === String(r.id)} onSelect=${() => app.select({ module: 'newsfeed', id: r.id })} />`)}
    </div>`)}
    ${data.left.more && html`<${More} onClick=${() => rerun({ more: app.state.more + 1 })} />`}
  </div>`;
}

let tagDraft = '';

// Tag chips on an entry or a search: a click removes, Enter in the box adds. `id` is what the routes take: 12 or "s12".
function Tags({ id, tags, hue, onChange }) {
  return html`<div style=${{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap', ...meta13, color: T.muted }}>
    ${(tags || []).map((t) => html`<span key=${t} class="ring" title="remove" onClick=${async () => { await post('/api/newsfeed/action/untag', { id, tag: t }); onChange(); }} style=${{ padding: '2px 8px', borderRadius: 6, cursor: 'pointer', boxShadow: 'inset 0 0 0 1px rgba(230,231,234,.1)' }}>${t}</span>`)}
    <input placeholder="+ tag" value=${tagDraft} onInput=${(e) => { tagDraft = e.target.value; }}
      onKeyDown=${async (e) => { if (e.key === 'Enter' && e.target.value.trim()) { const v = e.target.value.trim(); tagDraft = ''; e.target.value = ''; await post('/api/newsfeed/action/tag', { id, tags: [v] }); onChange(); } }}
      style=${{ width: 96, height: 26, padding: '0 8px', border: 0, borderRadius: 6, background: T.raised, color: T.text, fontSize: 13, '--hue': hue }} />
  </div>`;
}

// The day an entry happens: "Fri 09-10-2026", plus the time when the listing gave one.
function when(starts) {
  const [day, clock] = starts.split('T');
  const d = new Date(`${day}T12:00`);
  return `${d.toDateString().slice(0, 3)} ${dateLabel(day)}${clock ? ` ${clock}` : ''}`;
}

export function Middle({ app, data, mod, fmt }) {
  const hue = mod.hue;
  if (app.state.sel) {
    const item = app.state.item;
    const act = async (a) => {
      if (a.href) { window.open(a.href, '_blank'); return; }
      if (a.confirm && !window.confirm(a.confirm)) return;
      await post(`/api/newsfeed/action/${a.verb}`, { id: item.id });
      if (a.removes) app.select(null); else app.loadItem(app.state.sel);
      app.refresh();
    };
    const reload = () => { app.loadItem(app.state.sel); app.refresh(); };
    let detail = null;
    if (item && !item.error && item.kind === 'search') {
      const bad = item.last_result && item.last_result.startsWith('bad');
      detail = html`<div style=${{ display: 'flex', flexDirection: 'column', gap: 10 }}>
        <pre style=${{ margin: 0, whiteSpace: 'pre-wrap', fontFamily: 'inherit', lineHeight: 1.6 }}>${item.prompt}</pre>
        <span style=${{ ...meta13, ...nums, color: T.dim }}>every ${item.every_days} d · ${item.cap} per run · next ${dateLabel(item.next_run)}</span>
        ${bad && html`<span style=${{ ...meta13, color: RED }}>${item.last_result}</span>`}
        <${Tags} id=${item.id} tags=${item.tags} hue=${hue} onChange=${reload} />
      </div>`;
    } else if (item && !item.error) {
      const line = [item.search, item.follow_up_at && `follow up ${dateLabel(item.follow_up_at)}`].filter(Boolean).join(' · ');
      detail = html`<div style=${{ display: 'flex', flexDirection: 'column', gap: 6 }}>
        ${item.starts_at && html`<span style=${{ ...meta13, ...nums, color: hue }}>${when(item.starts_at)}</span>`}
        ${item.summary && html`<span style=${{ lineHeight: 1.6 }}>${item.summary}</span>`}
        <span style=${{ ...meta13, color: T.muted, wordBreak: 'break-all' }}>${item.url}</span>
        ${line && html`<span style=${{ ...meta13, ...nums, color: T.dim }}>${line}</span>`}
        <${Tags} id=${item.id} tags=${item.tags} hue=${hue} onChange=${reload} />
      </div>`;
    }
    return html`<${Inspector} app=${app} item=${item} mod=${mod} fmt=${fmt} onAction=${act}>${detail}<//>`;
  }
  const b = data.blank;
  const kill = async (s) => {
    if (!window.confirm(`Kill ${s.name}? Its entries stay.`)) return;
    await post('/api/newsfeed/action/kill', { id: s.id });
    app.refresh();
  };
  return html`<div style=${{ display: 'flex', flexDirection: 'column', gap: 4 }}>
    ${b.searches.length === 0 && html`<${Empty} text="no searches yet" />`}
    ${b.searches.map((s) => {
      const bad = s.last_result && s.last_result.startsWith('bad');
      return html`<div key=${s.id} class="row" style=${{ ...rowStyle({ hue }), height: 'auto', minHeight: 44, padding: '6px 12px', cursor: 'default' }}>
        <div style=${{ flex: 1, minWidth: 0, display: 'flex', flexDirection: 'column', gap: 2 }}>
          <span onClick=${() => app.select({ module: 'newsfeed', id: s.id })} style=${{ cursor: 'pointer', display: 'flex', alignItems: 'baseline', gap: 8 }}>
            ${s.name}<span style=${{ ...meta13, ...nums, color: hue }}>${s.open ? `${s.open} open` : ''}</span></span>
          <span style=${{ ...meta13, ...nums, color: T.dim, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>${[`next ${dateLabel(s.next_run)}`, ...s.tags].join(' · ')}</span>
        </div>
        ${bad && html`<span style=${{ ...meta13, color: RED, maxWidth: 220, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }} title=${s.last_result}>${s.last_result}</span>`}
        <span class="bright-hover" title="kill" onClick=${() => kill(s)} style=${{ cursor: 'pointer', color: T.dim, padding: '0 4px', lineHeight: 1 }}>×</span>
      </div>`;
    })}
  </div>`;
}
