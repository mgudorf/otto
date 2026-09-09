// Email: LEFT = chips + rows by day · MIDDLE blank = mailbox status and bulk actions on the current filter.
import { html, T, mono13, Row, GroupHeader, Chips, Search, Button, Empty, fmtInt, stamp } from '../rows.js';
import { get, post } from '../api.js';
import { Inspector } from '../shell.js';

export async function load(app) {
  const { query, chip, more } = app.state;
  const q = new URLSearchParams({ query, chip, page: String(more) });
  const [left, blank] = await Promise.all([get(`/api/email/left?${q}`), get('/api/email/blank')]);
  return { left, blank };
}

export function meta(app) {
  const b = app.state.data && app.state.data.blank;
  return b ? `${fmtInt(b.unread)} unread` : '';
}

export function Left({ app, data, mod, fmt }) {
  const sel = app.state.sel;
  const rerun = (patch) => app.setState(patch, () => app.refresh());
  return html`<div style=${{ display: 'flex', flexDirection: 'column', gap: 20 }}>
    <${Search} value=${app.state.query} hue=${mod.hue} onInput=${(v) => rerun({ query: v, more: 0 })} />
    <${Chips} chips=${data.left.chips} active=${data.left.chip} hue=${mod.hue} onPick=${(c) => rerun({ chip: c, more: 0 })} />
    ${data.left.groups.length === 0 && html`<${Empty} text=${app.state.query ? 'no matches' : 'nothing in the inbox yet'} />`}
    ${data.left.groups.map((g) => html`<div key=${g.label} style=${{ display: 'flex', flexDirection: 'column', gap: 2 }}>
      <${GroupHeader} label=${g.label} count=${g.count} />
      ${g.rows.map((r) => html`<${Row} key=${r.id} row=${r} hue=${mod.hue} fmt=${fmt} selected=${!!sel && String(sel.id) === String(r.id)} onSelect=${() => app.select({ module: 'email', id: r.id })} />`)}
    </div>`)}
    <div style=${{ display: 'flex', alignItems: 'center', gap: 16, height: 32, padding: '0 12px', ...mono13, color: T.dim }}>${data.left.showing}
      ${data.left.more && html`<span class="ring" onClick=${() => rerun({ more: app.state.more + 1 })} style=${{ cursor: 'pointer', color: T.muted, padding: '3px 8px', borderRadius: 6 }}>more</span>`}
    </div>
  </div>`;
}

export function Middle({ app, data, mod, fmt }) {
  const hue = mod.hue;
  if (app.state.sel) {
    const item = app.state.item;
    const act = async (a) => {
      if (a.href) { window.open(a.href, '_blank'); return; }
      if (a.confirm && !window.confirm(a.confirm)) return;
      await post(`/api/email/action/${a.verb}`, { ids: [item.id] });
      if (a.verb === 'archive' || a.verb === 'trash') app.select(null); else app.loadItem(app.state.sel);
      app.refresh();
    };
    const line = item && !item.error
      ? html`<div style=${{ ...mono13, color: T.muted, wordBreak: 'break-word' }}>${`${item.from_name} <${item.from_addr}> → ${item.to_addr}`}
          ${item.priority && html`<div style=${{ color: item.priority === 'high' ? hue : T.dim, marginTop: 4 }}>${item.priority} · ${item.reason}</div>`}</div>`
      : null;
    return html`<${Inspector} app=${app} item=${item} mod=${mod} fmt=${fmt} onAction=${act}>${line}<//>`;
  }
  const b = data.blank, l = data.left;
  const filter = { query: app.state.query, chip: l.chip };
  const bulk = async (verb, confirmText) => {
    if (!l.total) return;
    if (confirmText && !window.confirm(confirmText)) return;
    await post(`/api/email/action/${verb}`, { filter });
    app.refresh();
  };
  const n = fmtInt(l.total);
  return html`<div style=${{ display: 'flex', flexDirection: 'column', gap: 16 }}>
    <div style=${{ ...mono13, color: T.dim }}>${fmtInt(b.inbox)} in inbox · ${fmtInt(b.unread)} unread · ${fmtInt(b.flagged)} flagged · ${fmtInt(b.priority)} priority · synced ${b.last_sync ? stamp(b.last_sync, fmt) : 'never'}</div>
    <div style=${{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
      <span style=${{ flex: 1, minWidth: 0, color: l.total ? T.text : T.dim }}>${n} matching${app.state.query ? ` “${app.state.query}”` : ''} · ${l.chip}</span>
      <${Button} label="Mark read" onClick=${() => bulk('read')} />
      <${Button} label="Archive" primary=${true} hue=${hue} onClick=${() => bulk('archive', `Archive ${n} messages?`)} />
      <${Button} label="Trash" onClick=${() => bulk('trash', `Trash ${n} messages?`)} />
    </div>
  </div>`;
}
