// Newsfeed: LEFT = chips + entries by the day they were found · MIDDLE blank = the searches, each killable · selected = entry or search.
import { html, T, mono13, Row, GroupHeader, Chips, Search, Button, Empty, fmtInt, stamp, dayLabel } from '../rows.js';
import { get, post } from '../api.js';
import { Inspector } from '../shell.js';

export async function load(app) {
  const { query, chip, more } = app.state;
  const q = new URLSearchParams({ query, chip, page: String(more) });
  const [left, blank] = await Promise.all([get(`/api/newsfeed/left?${q}`), get('/api/newsfeed/blank')]);
  return { left, blank };
}

export function meta(app) {
  const b = app.state.data && app.state.data.blank;
  if (!b) return '';
  return b.open ? `${fmtInt(b.total)} · ${b.open} to review` : fmtInt(b.total);
}

export function Left({ app, data, mod, fmt }) {
  const sel = app.state.sel;
  const rerun = (patch) => app.setState(patch, () => app.refresh());
  return html`<div style=${{ display: 'flex', flexDirection: 'column', gap: 20 }}>
    <${Search} value=${app.state.query} hue=${mod.hue} onInput=${(v) => rerun({ query: v, more: 0 })} />
    <${Chips} chips=${data.left.chips} active=${data.left.chip} hue=${mod.hue} onPick=${(c) => rerun({ chip: c, more: 0 })} />
    ${data.left.groups.length === 0 && html`<${Empty} text=${app.state.query ? 'no matches' : 'nothing found yet'} />`}
    ${data.left.groups.map((g) => html`<div key=${g.label} style=${{ display: 'flex', flexDirection: 'column', gap: 2 }}>
      <${GroupHeader} label=${g.label} count=${g.count} />
      ${g.rows.map((r) => html`<${Row} key=${r.id} row=${r} hue=${mod.hue} fmt=${fmt} selected=${!!sel && String(sel.id) === String(r.id)} onSelect=${() => app.select({ module: 'newsfeed', id: r.id })} />`)}
    </div>`)}
    <div style=${{ display: 'flex', alignItems: 'center', gap: 16, height: 32, padding: '0 12px', ...mono13, color: T.dim }}>${data.left.showing}
      ${data.left.more && html`<span class="ring" onClick=${() => rerun({ more: app.state.more + 1 })} style=${{ cursor: 'pointer', color: T.muted, padding: '3px 8px', borderRadius: 6 }}>more</span>`}
    </div>
  </div>`;
}

let tagDraft = '';

// Tag chips on an entry or a search: a click removes, Enter in the box adds. `id` is what the routes take: 12 or "s12".
function Tags({ app, id, tags, hue, onChange }) {
  return html`<div style=${{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap', ...mono13, color: T.muted }}>
    ${(tags || []).map((t) => html`<span key=${t} class="ring" title="remove" onClick=${async () => { await post('/api/newsfeed/action/untag', { id, tag: t }); onChange(); }} style=${{ padding: '2px 8px', borderRadius: 6, cursor: 'pointer', boxShadow: 'inset 0 0 0 1px rgba(230,231,234,.1)' }}>${t}</span>`)}
    <input placeholder="add tag" value=${tagDraft} onInput=${(e) => { tagDraft = e.target.value; }}
      onKeyDown=${async (e) => { if (e.key === 'Enter' && e.target.value.trim()) { const v = e.target.value.trim(); tagDraft = ''; e.target.value = ''; await post('/api/newsfeed/action/tag', { id, tags: [v] }); onChange(); } }}
      style=${{ width: 120, height: 26, padding: '0 8px', border: 0, borderRadius: 6, background: T.raised, color: T.text, fontSize: 13, '--hue': hue }} />
  </div>`;
}

// The day an entry happens, as the rows show it: "Fri 09 Oct", plus the time when the listing gave one.
function when(starts) {
  const [day, clock] = starts.split('T');
  const d = new Date(`${day}T12:00`);
  return `${d.toDateString().slice(0, 3)} ${dayLabel(d)}${clock ? ` ${clock}` : ''}`;
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
      detail = html`<div style=${{ display: 'flex', flexDirection: 'column', gap: 10 }}>
        <pre style=${{ margin: 0, whiteSpace: 'pre-wrap', fontFamily: 'inherit', lineHeight: 1.6 }}>${item.prompt}</pre>
        <span style=${{ ...mono13, color: T.muted }}>every ${item.every_days} d · ${item.cap} per run · ${item.entries} entries · ${item.open} open</span>
        <span style=${{ ...mono13, color: T.dim }}>next ${item.next_run} · last ${item.last_run ? `${stamp(item.last_run, fmt)}: ${item.last_result || ''}` : 'never'}</span>
        <${Tags} app=${app} id=${item.id} tags=${item.tags} hue=${hue} onChange=${reload} />
      </div>`;
    } else if (item && !item.error) {
      detail = html`<div style=${{ display: 'flex', flexDirection: 'column', gap: 6 }}>
        ${item.starts_at && html`<span style=${{ ...mono13, color: hue }}>${when(item.starts_at)}</span>`}
        ${item.summary && html`<span style=${{ lineHeight: 1.6 }}>${item.summary}</span>`}
        <span style=${{ ...mono13, color: T.muted, wordBreak: 'break-all' }}>${item.url}</span>
        <span style=${{ ...mono13, color: T.dim }}>${[item.search && `from ${item.search}`, item.status, item.follow_up_at && `follow up ${item.follow_up_at}`, item.follows && `follows #${item.follows}`].filter(Boolean).join(' · ')}</span>
        <${Tags} app=${app} id=${item.id} tags=${item.tags} hue=${hue} onChange=${reload} />
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
  return html`<div style=${{ display: 'flex', flexDirection: 'column', gap: 16 }}>
    <div style=${{ display: 'flex', alignItems: 'center', gap: 8, ...mono13, color: T.dim }}>
      <span>${b.searches.length} scheduled search${b.searches.length === 1 ? '' : 'es'} · a new one is asked of the agent</span>
      <span style=${{ marginLeft: 'auto' }}>last run ${b.last_run ? stamp(b.last_run, fmt) : 'never'}</span>
    </div>
    ${b.searches.length === 0 && html`<${Empty} text="nothing scheduled; ask the agent to add a search" />`}
    <div style=${{ display: 'flex', flexDirection: 'column', gap: 2 }}>
      ${b.searches.map((s) => html`<div key=${s.id} class="row" style=${{ display: 'flex', alignItems: 'center', gap: 12, minHeight: 44, padding: '6px 12px', borderRadius: 6 }}>
        <div style=${{ flex: 1, minWidth: 0, display: 'flex', flexDirection: 'column', gap: 2 }}>
          <span onClick=${() => app.select({ module: 'newsfeed', id: s.id })} style=${{ cursor: 'pointer', display: 'flex', alignItems: 'baseline', gap: 8 }}>
            ${s.name}<span style=${{ ...mono13, color: hue }}>${s.open ? `${s.open} open` : ''}</span></span>
          <span style=${{ ...mono13, color: T.dim }}>every ${s.every_days} d · ${s.cap} per run · next ${s.next_run} · ${s.tags.length ? s.tags.join(' · ') : 'no tags'}</span>
        </div>
        <span style=${{ ...mono13, color: s.last_result && s.last_result.startsWith('bad') ? '#cf7b7b' : T.dim, maxWidth: 220, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }} title=${s.last_result || ''}>${s.last_run ? s.last_result : 'not run yet'}</span>
        <${Button} label="Kill" onClick=${() => kill(s)} />
      </div>`)}
    </div>
  </div>`;
}
