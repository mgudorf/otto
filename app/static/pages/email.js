// Email: LEFT = search, chips, the action bar, rows by day · MIDDLE = the reader, or the mailbox status when nothing is selected.
// The bar acts on the selected message, or on every message matching the filter when none is; MIDDLE never touches the mailbox.
import { html, T, mono13, Row, GroupHeader, Chips, Search, Button, Empty, Icon, fmtInt, stamp, dayLabel, clock } from '../rows.js';
import { get, post } from '../api.js';

let styled = false;

// Rules for the sanitized body, added to the document once. The server sends bare tags: no attribute, link, image, style or script.
function ensureStyles() {
  if (styled) return;
  styled = true;
  const style = document.createElement('style');
  style.textContent = [
    '.mail{line-height:1.6;overflow-wrap:break-word}',  // not word-break: that lets a table squeeze a text column to one letter per line
    '.mail p{margin:0 0 10px}',
    '.mail h1,.mail h2{font-size:17px;font-weight:600;margin:14px 0 6px}.mail h3,.mail h4,.mail h5,.mail h6{font-size:15px;font-weight:600;margin:12px 0 6px}',
    '.mail ul,.mail ol{margin:0 0 10px;padding-left:22px}.mail li{margin:2px 0}',
    '.mail blockquote{margin:0 0 10px;padding-left:12px;border-left:2px solid rgba(230,231,234,.14);color:#8b8f98}',
    ".mail pre,.mail code,.mail tt,.mail kbd,.mail samp{font-family:'JetBrains Mono',ui-monospace,monospace;font-size:13px}",
    '.mail pre{background:#1a1c21;padding:10px 12px;border-radius:6px;margin:0 0 10px;white-space:pre-wrap}',
    '.mail table{border-collapse:collapse;max-width:100%}.mail td,.mail th{padding:1px 4px;vertical-align:top;text-align:left}.mail th{font-weight:600}',
    '.mail hr{border:0;border-top:1px solid rgba(230,231,234,.08);margin:12px 0}',
    // The raw URL is all there for selection and copy; the display clamps it to two lines so a tracking link never swamps the text around it.
    ".mail .url{display:-webkit-inline-box;-webkit-box-orient:vertical;-webkit-line-clamp:2;overflow:hidden;max-width:100%;vertical-align:top;font-family:'JetBrains Mono',ui-monospace,monospace;font-size:12px;color:#8b8f98;word-break:break-all}",
    ".mail .url::before{content:'‹'}.mail .url::after{content:'›'}",
    '.mail .img{font-size:13px;color:#5f636c}',
  ].join('');
  document.head.appendChild(style);
}

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
    <${Actions} app=${app} data=${data} mod=${mod} />
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

// The action bar, stuck to the top of LEFT while the list scrolls: the selected message's actions, or the bulk actions over the filter.
function Actions({ app, data, mod }) {
  const { sel, item, query } = app.state;
  const l = data.left;
  const bar = { position: 'sticky', top: 0, zIndex: 1, display: 'flex', alignItems: 'center', flexWrap: 'wrap', gap: 8, padding: '6px 12px', background: T.panel };
  const label = { flex: '1 1 auto', minWidth: 0, ...mono13, color: T.dim, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' };
  if (sel) {
    const act = async (a) => {
      if (a.href) { window.open(a.href, '_blank'); return; }
      if (a.confirm && !window.confirm(a.confirm)) return;
      await post(`/api/email/action/${a.verb}`, { ids: [sel.id] });
      if (a.verb === 'archive' || a.verb === 'trash') app.select(null); else app.loadItem(sel);
      app.refresh();
    };
    const actions = item && !item.error ? item.actions || [] : [];
    return html`<div style=${bar}>
      <span style=${label}>1 selected</span>
      ${actions.map((a) => html`<${Button} key=${a.verb} label=${a.label} primary=${a.primary} hue=${mod.hue} onClick=${() => act(a)} />`)}
    </div>`;
  }
  const n = fmtInt(l.total);
  const bulk = async (verb, confirmText) => {
    if (!l.total) return;
    if (confirmText && !window.confirm(confirmText)) return;
    await post(`/api/email/action/${verb}`, { filter: { query, chip: l.chip } });
    app.refresh();
  };
  return html`<div style=${bar}>
    <span style=${{ ...label, color: l.total ? T.muted : T.dim }}>${n} matching${query ? ` “${query}”` : ''} · ${l.chip}</span>
    <${Button} label="Mark read" onClick=${() => bulk('read')} />
    <${Button} label="Archive" primary=${true} hue=${mod.hue} onClick=${() => bulk('archive', `Archive ${n} messages?`)} />
    <${Button} label="Trash" onClick=${() => bulk('trash', `Trash ${n} messages?`)} />
  </div>`;
}

export function Middle({ app, data, mod, fmt }) {
  if (app.state.sel) return html`<${Reader} app=${app} item=${app.state.item} mod=${mod} fmt=${fmt} />`;
  const b = data.blank;
  return html`<div style=${{ ...mono13, color: T.dim }}>${fmtInt(b.inbox)} in inbox · ${fmtInt(b.unread)} unread · ${fmtInt(b.flagged)} flagged · ${fmtInt(b.priority)} priority · synced ${b.last_sync ? stamp(b.last_sync, fmt) : 'never'}</div>`;
}

// The message itself: headers, then its sanitized html when it has one, else its text. No mailbox action lives here.
function Reader({ app, item, mod, fmt }) {
  if (!item) return html`<div style=${{ ...mono13, color: T.dim }}>loading…</div>`;
  if (item.error) return html`<div style=${{ ...mono13, color: '#cf7b7b' }}>${item.error}</div>`;
  ensureStyles();
  const body = { borderTop: `1px solid ${T.hair}`, paddingTop: 12 };
  return html`<div style=${{ display: 'flex', flexDirection: 'column', gap: 12, maxWidth: '72ch', margin: '0 auto' }}>
    <div style=${{ display: 'flex', alignItems: 'center', gap: 12 }}>
      <span style=${{ display: 'grid', placeItems: 'center', width: 16, height: 16, color: mod.hue }}><${Icon} svg=${mod.icon} /></span>
      <span style=${{ ...mono13, color: T.muted }}>${item.kind} · ${dayLabel(item.created_at)} ${clock(item.created_at, fmt)}</span>
      <span style=${{ marginLeft: 'auto' }}><${Button} label="Send to session" onClick=${() => app.sendToSession(`About the selected item (email ${item.id}): ${String(item.text).slice(0, 300)}\n\n`)} /></span>
      <span class="bright-hover" onClick=${() => app.select(null)} style=${{ cursor: 'pointer', color: T.dim, padding: '0 4px', lineHeight: 1 }}>×</span>
    </div>
    <div style=${{ fontSize: 17, fontWeight: 600, lineHeight: 1.3 }}>${item.subject}</div>
    <div style=${{ ...mono13, color: T.muted, wordBreak: 'break-word' }}>${`${item.from_name} <${item.from_addr}> → ${item.to_addr}`}
      ${item.priority && html`<div style=${{ color: item.priority === 'high' ? mod.hue : T.dim, marginTop: 4 }}>${item.priority} · ${item.reason}</div>`}
      ${item.attachments.length > 0 && html`<div style=${{ color: T.dim, marginTop: 4 }}>attachments, not shown: ${item.attachments.join(', ')}</div>`}
    </div>
    ${item.html
      ? html`<div class="mail" style=${body} dangerouslySetInnerHTML=${{ __html: item.html }} />`
      : html`<div style=${{ ...body, lineHeight: 1.6, whiteSpace: 'pre-wrap', wordBreak: 'break-word' }}>${item.body}</div>`}
  </div>`;
}
