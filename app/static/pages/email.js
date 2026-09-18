// Email: LEFT = search, chips, the action bar, rows by day · MIDDLE = the reader, or the inbox count when nothing is selected.
// The bar acts on the rows picked with ctrl and shift, else the open message, else every message matching the filter.
// It is built from the row data LEFT already carries, so it never waits on item/{id} and never changes height.
import { html, T, meta13, nums, Row, GroupHeader, Chips, Search, Button, Empty, More, Icon, fmtInt, stamp, dayLabel, clock } from '../rows.js';
import { get, post } from '../api.js';

let styled = false;

// 20x20, stroke, to match the rail. Text labels cannot fit five controls in a 220-420px track; these can.
const ICONS = {
  archive: '<rect x="3" y="4" width="14" height="4" rx="1"></rect><path d="M5 8v7a1 1 0 001 1h8a1 1 0 001-1V8M8 11h4"></path>',
  trash: '<path d="M4 6h12M8 6V4h4v2M6 6l1 10h6l1-10"></path>',
  unread: '<rect x="3" y="5" width="14" height="10" rx="2"></rect><path d="M3 7l7 5 7-5"></path>',
  star: '<path d="M10 3l2.2 4.5 5 .7-3.6 3.5.9 4.9L10 14.3 5.5 16.6l.9-4.9L2.8 8.2l5-.7z"></path>',
  sync: '<path d="M16 6a7 7 0 10.9 7M16 3v3.5h-3.5"></path>',
  clip: '<path d="M13.5 6.5l-6 6a2 2 0 002.8 2.8l6.5-6.5a3.5 3.5 0 00-5-5L5.3 10.3a5 5 0 007 7l5-5"></path>',
};

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
    // The URL lives in the title now, so a tracking link costs one glyph instead of two lines of the body.
    ".mail .url{cursor:help;color:#5f636c;font-size:11px;vertical-align:super}.mail .url::after{content:'↗'}",
    '.mail .img{font-size:13px;color:#5f636c}',
    '.bar-btn{display:grid;place-items:center;width:28px;height:28px;border-radius:6px;flex:none}',
    '.bar-btn[data-on="1"]{cursor:pointer}.bar-btn[data-on="1"]:hover{background:#23262c}',
    '.bar-btn[data-on="0"]{opacity:.28}',
  ].join('');
  document.head.appendChild(style);
}

export async function load(app) {
  const { query, chip, more } = app.state;
  const q = new URLSearchParams({ query, chip, page: String(more) });
  const [left, blank] = await Promise.all([get(`/api/email/left?${q}`), get('/api/email/blank')]);
  return { left, blank };
}

const flatten = (left) => left.groups.flatMap((g) => g.rows);

export function Left({ app, data, mod }) {
  const { sel, picked } = app.state;
  const rows = flatten(data.left);
  const rerun = (patch) => app.setState(patch, () => app.refresh());
  const set = new Set(picked);

  // Plain click opens one message; ctrl adds or removes one; shift takes everything between the anchor and here.
  const onSelect = (row, e) => {
    if (e && (e.ctrlKey || e.metaKey)) {
      // Windows convention: the row already open stays in the selection when the next one is added to it.
      const next = new Set(set.size || !sel ? set : [sel.id]);
      if (next.has(row.id)) next.delete(row.id); else next.add(row.id);
      app.setState({ picked: [...next] });
      return;
    }
    if (e && e.shiftKey) {
      const ids = rows.map((r) => r.id);
      const anchor = ids.indexOf(app.state.anchor || (sel && sel.id) || row.id);
      const here = ids.indexOf(row.id);
      const [a, b] = anchor < 0 ? [here, here] : [Math.min(anchor, here), Math.max(anchor, here)];
      app.setState({ picked: [...new Set([...set, ...ids.slice(a, b + 1)])] });
      return;
    }
    app.setState({ picked: [], anchor: row.id });
    app.select({ module: 'email', id: row.id });
    // Opening a message is what marks it read; there is no chip for it any more.
    if (row.unread && data.left.read_on_open) {
      post('/api/email/action/read', { id: row.id }).then(() => app.refresh()).catch(() => {});
    }
  };

  return html`<div style=${{ display: 'flex', flexDirection: 'column', gap: 20 }}>
    <${Search} value=${app.state.query} hue=${mod.hue} onInput=${(v) => rerun({ query: v, more: 0 })} />
    <${Chips} chips=${data.left.chips} active=${data.left.chip} hue=${mod.hue} onPick=${(c) => rerun({ chip: c, more: 0 })} />
    <${Actions} app=${app} data=${data} mod=${mod} rows=${rows} />
    ${data.left.groups.length === 0 && html`<${Empty} text=${app.state.query ? 'no matches' : 'nothing in the inbox yet'} />`}
    ${data.left.groups.map((g) => html`<div key=${g.label} style=${{ display: 'flex', flexDirection: 'column', gap: 4 }}>
      <${GroupHeader} label=${g.label} />
      ${g.rows.map((r) => html`<${Row} key=${r.id} row=${r} hue=${mod.hue}
        selected=${set.has(r.id) || (!!sel && !picked.length && String(sel.id) === String(r.id))}
        onSelect=${(e) => onSelect(r, e)} />`)}
    </div>`)}
    ${data.left.more && html`<${More} onClick=${() => rerun({ more: app.state.more + 1 })} />`}
  </div>`;
}

// One fixed row of controls, always the same five, dimmed when they do not apply. Nothing here changes height,
// so the list below never moves. The only words are `N picked` while a set is picked, and the error a refused action returns.
function Actions({ app, data, mod, rows }) {
  const { sel, picked, query, busy, err } = app.state;
  const l = data.left;
  const set = new Set(picked);
  const chosen = picked.length ? rows.filter((r) => set.has(r.id)) : sel ? rows.filter((r) => String(r.id) === String(sel.id)) : [];
  const target = picked.length ? { ids: picked } : sel ? { id: sel.id } : { filter: { query, chip: l.chip } };
  const n = picked.length || (sel ? 1 : l.total);
  const anyStarred = chosen.some((r) => r.starred);
  const bulk = !picked.length && !sel;

  const run = async (verb, confirmText) => {
    if (busy || (verb !== 'sync' && !n)) return;
    if (confirmText && !window.confirm(confirmText)) return;
    app.setState({ busy: verb, err: null });
    try {
      await post(`/api/email/action/${verb}`, verb === 'sync' ? {} : target);
      if ((verb === 'archive' || verb === 'trash') && sel && !picked.length) app.select(null);
      app.setState({ busy: null, picked: [] }, () => app.refresh());
    } catch (e) {
      app.setState({ busy: null, err: e.message });   // a refused action used to look exactly like a successful one
    }
  };

  const Ctl = ({ name, verb, title, confirm, on, hue }) => html`<span class="bar-btn" data-on=${on && !busy ? '1' : '0'}
    title=${title} onClick=${() => on && run(verb, confirm)} style=${{ color: hue || T.muted, background: hue ? 'rgba(207,123,123,.12)' : 'transparent' }}>
    <${Icon} svg=${ICONS[name]} size=${17} color="currentColor" /></span>`;

  return html`<div style=${{ position: 'sticky', top: 0, zIndex: 1, display: 'flex', flexDirection: 'column', gap: 2, padding: '6px 12px', background: T.panel }}>
    <div style=${{ display: 'flex', alignItems: 'center', gap: 4, height: 28 }}>
      <span style=${{ flex: '1 1 auto', minWidth: 0, ...meta13, ...nums, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>${picked.length ? `${fmtInt(picked.length)} picked` : ''}</span>
      <${Ctl} name="archive" verb="archive" title=${`Archive ${n}`} on=${n > 0}
        confirm=${bulk ? `Archive ${fmtInt(n)} messages?` : null} />
      <${Ctl} name="unread" verb="unread" title=${`Mark ${n} unread`} on=${n > 0} />
      <${Ctl} name="star" verb=${anyStarred ? 'unstar' : 'star'} title=${anyStarred ? `Unstar ${n}` : `Star ${n}`} on=${n > 0} />
      <${Ctl} name="trash" verb="trash" title=${`Trash ${n}`} on=${n > 0} hue=${mod.hue}
        confirm=${`Trash ${fmtInt(n)} message${n === 1 ? '' : 's'}?`} />
      <span style=${{ width: 1, height: 16, background: T.hair, margin: '0 4px', flex: 'none' }} />
      <${Ctl} name="sync" verb="sync" title="Sync now" on=${!busy} />
    </div>
    <div style=${{ ...meta13, color: mod.hue, height: 16, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>${err || ''}</div>
  </div>`;
}

export function Middle({ app, data, mod, fmt }) {
  if (app.state.sel) return html`<${Reader} app=${app} item=${app.state.item} mod=${mod} fmt=${fmt} />`;
  const b = data.blank;
  return html`<div style=${{ ...meta13, ...nums, color: T.dim }}>${fmtInt(b.inbox)} in inbox · synced ${b.last_sync ? stamp(b.last_sync, fmt) : 'never'}</div>`;
}

// The message itself: headers, then its sanitized html when it has one, else its text. No mailbox action lives here.
function Reader({ app, item, mod, fmt }) {
  if (!item) return html`<div style=${{ ...meta13, color: T.dim }}>loading…</div>`;
  if (item.error) return html`<div style=${{ ...meta13, color: '#cf7b7b' }}>${item.error}</div>`;
  ensureStyles();
  const body = { borderTop: `1px solid ${T.hair}`, paddingTop: 12 };
  const open = (item.actions || []).find((a) => a.verb === 'open');
  return html`<div style=${{ display: 'flex', flexDirection: 'column', gap: 12 }}>
    <div style=${{ display: 'flex', alignItems: 'center', gap: 12 }}>
      <span style=${{ display: 'grid', placeItems: 'center', width: 16, height: 16, color: mod.hue }}><${Icon} svg=${mod.icon} /></span>
      <span style=${{ ...meta13, ...nums, color: T.dim }}>${dayLabel(item.created_at)} ${clock(item.created_at, fmt)}</span>
      <span style=${{ marginLeft: 'auto', display: 'flex', gap: 8 }}>
        ${open && html`<${Button} label="Open in Gmail" onClick=${() => window.open(open.href, '_blank')} />`}
        <${Button} label="Send to session" onClick=${() => app.sendToSession(`About the selected item (email ${item.id}): ${String(item.text).slice(0, 300)}\n\n`)} />
      </span>
      <span class="bright-hover" onClick=${() => app.select(null)} style=${{ cursor: 'pointer', color: T.dim, padding: '0 4px', lineHeight: 1 }}>×</span>
    </div>
    <div style=${{ fontSize: 17, fontWeight: 600, lineHeight: 1.3 }}>${item.subject}</div>
    <div style=${{ ...meta13, color: T.muted, wordBreak: 'break-word' }}>${`${item.from_name} <${item.from_addr}> → ${item.to_addr}`}
      ${item.priority && html`<div style=${{ color: item.priority === 'high' ? mod.hue : T.dim, marginTop: 4 }}>${item.priority} · ${item.reason}</div>`}
      ${item.attachments.length > 0 && html`<div style=${{ display: 'flex', alignItems: 'center', gap: 6, color: T.dim, marginTop: 4 }}><${Icon} svg=${ICONS.clip} size=${13} />${item.attachments.join(', ')}</div>`}
    </div>
    ${item.html
      ? html`<div class="mail" style=${body} dangerouslySetInnerHTML=${{ __html: item.html }} />`
      : html`<div style=${{ ...body, lineHeight: 1.6, whiteSpace: 'pre-wrap', wordBreak: 'break-word' }}>${item.body}</div>`}
  </div>`;
}
