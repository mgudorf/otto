// Search: LEFT = status chips + findings by night · MIDDLE blank = topic editor and the open queue.
import { html, T, mono13, Row, GroupHeader, Chips, Search, Button, Empty, fmtInt, stamp } from '../rows.js';
import { get, post } from '../api.js';
import { Inspector } from '../shell.js';

export async function load(app) {
  const { query, chip, more } = app.state;
  const q = new URLSearchParams({ query, chip, page: String(more) });
  const [left, blank] = await Promise.all([get(`/api/web_search/left?${q}`), get('/api/web_search/blank')]);
  return { left, blank };
}

export function meta(app) {
  const b = app.state.data && app.state.data.blank;
  if (!b) return '';
  const topics = `${fmtInt(b.topics.length)} topics`;
  return b.queue.length ? `${topics} · ${b.queue.length} to review` : topics;
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
      ${g.rows.map((r) => html`<${Row} key=${r.id} row=${r} hue=${mod.hue} fmt=${fmt} selected=${!!sel && String(sel.id) === String(r.id)} onSelect=${() => app.select({ module: 'web_search', id: r.id })} />`)}
    </div>`)}
    <div style=${{ display: 'flex', alignItems: 'center', gap: 16, height: 32, padding: '0 12px', ...mono13, color: T.dim }}>${data.left.showing}
      ${data.left.more && html`<span class="ring" onClick=${() => rerun({ more: app.state.more + 1 })} style=${{ cursor: 'pointer', color: T.muted, padding: '3px 8px', borderRadius: 6 }}>more</span>`}
    </div>
  </div>`;
}

class Draft {
  constructor() { this.kind = 'money'; this.text = ''; }
}
const draft = new Draft();

export function Middle({ app, data, mod, fmt }) {
  const hue = mod.hue;
  const decide = async (id, verb) => { await post(`/api/web_search/action/${verb}`, { id }); app.refresh(); };
  if (app.state.sel) {
    const item = app.state.item;
    const act = async (a) => {
      if (a.href) { window.open(a.href, '_blank'); return; }
      await decide(item.id, a.verb);
      app.loadItem(app.state.sel);
    };
    const detail = item && !item.error ? html`<div style=${{ display: 'flex', flexDirection: 'column', gap: 6 }}>
      <span style=${{ ...mono13, color: T.muted, wordBreak: 'break-all' }}>${item.url}</span>
      <span style=${{ ...mono13, color: T.dim }}>${item.status}</span>
    </div>` : null;
    return html`<${Inspector} app=${app} item=${item} mod=${mod} fmt=${fmt} onAction=${act}>${detail}<//>`;
  }
  const b = data.blank;
  const add = async () => {
    const text = draft.text.trim();
    if (!text) return;
    await post('/api/web_search/action/topic_add', { kind: draft.kind, text });
    draft.text = '';
    app.refresh();
  };
  return html`<div style=${{ display: 'flex', flexDirection: 'column', gap: 16, maxWidth: 720 }}>
    <div style=${{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
      ${b.kinds.map((k) => html`<span key=${k} class="ring" onClick=${() => { draft.kind = k; app.forceUpdate(); }} style=${{ padding: '3px 9px', borderRadius: 6, fontSize: 13, cursor: 'pointer', background: draft.kind === k ? hue : 'transparent', color: draft.kind === k ? T.ground : T.muted }}>${k}</span>`)}
      <span style=${{ marginLeft: 'auto', ...mono13, color: T.dim }}>${b.last_run ? `last run ${stamp(b.last_run, fmt)}` : 'never run'}</span>
    </div>
    <div style=${{ display: 'flex', alignItems: 'center', gap: 8 }}>
      <input placeholder=${{ money: 'A sector, holding or law to follow…', work: 'A technique, field or career thread…', learn: 'Something you are learning…' }[draft.kind]} value=${draft.text}
        onInput=${(e) => { draft.text = e.target.value; }}
        onKeyDown=${(e) => { if (e.key === 'Enter') { e.preventDefault(); add(); } }}
        style=${{ flex: 1, height: 36, padding: '0 12px', border: 0, borderRadius: 6, background: T.panel, color: T.text, fontSize: 15, '--hue': hue }} />
      <${Button} label="Add" primary=${true} hue=${hue} onClick=${add} />
    </div>
    ${b.topics.length === 0 && html`<${Empty} text="no topics: nothing runs until you add one" />`}
    ${b.topics.length > 0 && html`<div style=${{ display: 'flex', flexDirection: 'column', gap: 2 }}>
      <${GroupHeader} label="topics" count=${b.topics.length} />
      ${b.topics.map((t) => html`<div key=${t.id} class="row" style=${{ display: 'flex', alignItems: 'center', gap: 12, height: 32, padding: '0 12px', borderRadius: 6 }}>
        <span style=${{ flex: 'none', ...mono13, color: hue, width: 40 }}>${t.kind}</span>
        <span style=${{ flex: 1, minWidth: 0, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>${t.text}</span>
        <span class="ring" title="remove" onClick=${async () => { await post('/api/web_search/action/topic_remove', { id: t.id }); app.refresh(); }} style=${{ ...mono13, color: T.dim, cursor: 'pointer', padding: '2px 8px', borderRadius: 6 }}>×</span>
      </div>`)}
    </div>`}
    ${b.queue.length > 0 && html`<div style=${{ display: 'flex', flexDirection: 'column', gap: 2, marginTop: 16 }}>
      <${GroupHeader} label="to review" count=${b.queue.length} />
      ${b.queue.map((f) => html`<div key=${f.id} style=${{ display: 'flex', alignItems: 'center', gap: 12, minHeight: 36, padding: '6px 12px', borderRadius: 6 }}>
        <div style=${{ flex: 1, minWidth: 0, display: 'flex', flexDirection: 'column', gap: 2 }}>
          <span onClick=${() => app.select({ module: 'web_search', id: f.id })} style=${{ cursor: 'pointer' }}>${f.title}</span>
          <span style=${{ fontSize: 13, color: T.muted }}>${f.summary}</span>
        </div>
        <${Button} label="Agree" hue=${hue} onClick=${() => decide(f.id, 'agree')} />
        <${Button} label="Disagree" onClick=${() => decide(f.id, 'disagree')} />
      </div>`)}
    </div>`}
  </div>`;
}
