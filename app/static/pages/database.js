// Database: LEFT = tables with counts, saved queries · MIDDLE = editor, Run / Explain / Save, result grid.
// Run sends whatever is typed straight to SQLite: selects, writes and DDL all land, with no undo.
import { html, T, mono13, GroupHeader, Button, Empty, bytes, stamp } from '../rows.js';
import { get, post } from '../api.js';

class Editor {
  constructor() { this.sql = ''; this.table = null; this.saved = null; this.result = null; this.mode = 'result'; this.page = 0; }
}
const ed = new Editor();

export async function load() {
  const [left, blank] = await Promise.all([get('/api/database/left'), get('/api/database/blank')]);
  return { left, blank };
}

export function meta(app) {
  const b = app.state.data && app.state.data.blank;
  return b ? `${b.db} · ${bytes(b.size_bytes)}` : '';
}

function setSql(app, sql, patch) {
  Object.assign(ed, { sql, result: null, page: 0 }, patch);
  app.forceUpdate();
}

export function Left({ app, data, fmt }) {
  const size = app.state.shell.settings['ui.page_size'] || 40;
  const [tables, saved] = data.left.groups;
  const line = (key, active, onClick, text, right) => html`<div key=${key} class="row" onClick=${onClick}
      style=${{ display: 'flex', alignItems: 'center', gap: 12, height: 32, padding: '0 12px', borderRadius: 6, cursor: 'pointer', ...mono13, background: active ? T.raised : 'transparent', color: active ? T.text : T.muted }}>
    <span style=${{ flex: 1, minWidth: 0, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>${text}</span>
    <span style=${{ color: T.dim }}>${right}</span></div>`;
  return html`<div style=${{ display: 'flex', flexDirection: 'column', gap: 2 }}>
    <${GroupHeader} label="tables" count=${tables.count} />
    ${tables.rows.map((r) => line(r.id, ed.table === r.text,
      () => setSql(app, `select *\nfrom ${r.text}\norder by rowid desc\nlimit ${size};`, { table: r.text, saved: null }), r.text, r.stampText))}
    <div style=${{ height: 18 }} />
    <${GroupHeader} label="saved" count=${saved.count} />
    ${saved.rows.length === 0 && html`<${Empty} text="nothing saved yet" />`}
    ${saved.rows.map((r) => line(r.id, !!ed.saved && ed.saved.id === r.query_id,
      () => setSql(app, r.sql, { table: null, saved: { id: r.query_id, name: r.text } }), r.text, stamp(r.stamp, fmt)))}
  </div>`;
}

export function Middle({ app, data, mod }) {
  const size = app.state.shell.settings['ui.page_size'] || 40;
  const hue = mod.hue;
  const exec = async (verb, mode) => {
    if (!ed.sql.trim()) return;
    ed.result = await post(`/api/database/action/${verb}`, { sql: ed.sql });
    ed.mode = mode; ed.page = 0;
    // A write moves the row counts and can add or drop a table, so the rail is reloaded, not just redrawn.
    if (ed.result.changed || ed.result.ddl) app.refresh(); else app.forceUpdate();
  };
  const save = async () => {
    const name = window.prompt('Name for this query', ed.saved ? ed.saved.name : '');
    if (!name || !name.trim() || !ed.sql.trim()) return;
    const r = await post('/api/database/action/save', { name: name.trim(), sql: ed.sql });
    ed.saved = { id: r.id, name: name.trim() }; ed.table = null;
    app.refresh();
  };
  const del = async () => {
    if (!window.confirm(`Delete saved query "${ed.saved.name}"?`)) return;
    await post('/api/database/action/delete', { id: ed.saved.id });
    ed.saved = null;
    app.refresh();
  };
  const pager = (label, onClick) => html`<span class="ring" onClick=${onClick} style=${{ cursor: 'pointer', color: T.muted, padding: '3px 8px', borderRadius: 6 }}>${label}</span>`;

  const r = ed.result;
  const wrote = r && (r.changed || r.ddl) ? `${r.changed.toLocaleString()} row${r.changed === 1 ? '' : 's'} written · ` : '';
  let line = '';
  if (r && r.error) line = wrote + r.error;
  else if (r && ed.mode === 'explain') line = `${r.lines.length} step${r.lines.length === 1 ? '' : 's'} · ${r.ms} ms`;
  else if (r && r.columns.length) line = `${wrote}${r.total.toLocaleString()}${r.truncated ? '+' : ''} rows · ${r.ms} ms`;
  else if (r) line = `${wrote || 'no rows · '}${r.ms} ms`;

  let body = null;
  if (r && !r.error && ed.mode === 'explain') {
    body = html`<div style=${{ display: 'flex', flexDirection: 'column', ...mono13 }}>
      ${r.lines.map((l, i) => html`<div key=${i} style=${{ height: 32, display: 'flex', alignItems: 'center', padding: '0 12px', borderTop: i ? `1px solid ${T.hair}` : 'none' }}>${l}</div>`)}
    </div>`;
  } else if (r && !r.error && r.columns.length > 0) {
    const start = ed.page * size;
    const rows = r.rows.slice(start, start + size);
    // Header and rows are cells of one grid, so every row shares the same column tracks.
    const cols = `repeat(${r.columns.length}, minmax(96px, max-content))`;
    const cell = { padding: '0 8px', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis', maxWidth: 360 };
    body = html`<div style=${{ display: 'flex', flexDirection: 'column', ...mono13 }}>
      <div style=${{ overflowX: 'auto' }}>
        <div style=${{ display: 'grid', gridTemplateColumns: cols, gridTemplateRows: '28px', gridAutoRows: '32px', padding: '0 4px' }}>
          ${r.columns.map((c, j) => html`<span key=${`h${j}`} style=${{ ...cell, lineHeight: '28px', color: T.muted }}>${c}</span>`)}
          ${rows.map((row, i) => html`<div key=${start + i} class="crow" style=${{ display: 'contents' }}>
            ${row.map((v, j) => html`<span key=${j} title=${v === null ? '' : String(v)} style=${{ ...cell, lineHeight: '32px', borderTop: `1px solid ${T.hair}`, color: v === null ? T.dim : T.text }}>${v === null ? 'null' : String(v)}</span>`)}</div>`)}
        </div>
      </div>
      <div style=${{ display: 'flex', alignItems: 'center', gap: 16, height: 32, padding: '0 12px', borderTop: `1px solid ${T.hair}`, color: T.dim }}>
        ${r.total === 0 ? 'no rows' : `${start + 1}–${Math.min(start + size, r.total)} / ${r.total.toLocaleString()}`}
        ${ed.page > 0 && pager('prev', () => { ed.page -= 1; app.forceUpdate(); })}
        ${start + size < r.total && pager('next', () => { ed.page += 1; app.forceUpdate(); })}
      </div>
    </div>`;
  }

  return html`<div style=${{ display: 'flex', flexDirection: 'column', gap: 16, minWidth: 0 }}>
    <textarea value=${ed.sql} placeholder="select …" spellcheck="false"
      onInput=${(e) => { ed.sql = e.target.value; }}
      onKeyDown=${(e) => { if (e.key === 'Enter' && (e.ctrlKey || e.metaKey)) { e.preventDefault(); exec('run', 'result'); } }}
      style=${{ width: '100%', minHeight: 112, resize: 'vertical', padding: '12px 14px', border: 0, borderRadius: 6, background: T.panel, color: T.text, ...mono13, lineHeight: 1.6, '--hue': hue }} />
    <div style=${{ display: 'flex', alignItems: 'center', gap: 8 }}>
      <${Button} label="Run" primary=${true} hue=${hue} onClick=${() => exec('run', 'result')} />
      <${Button} label="Explain" onClick=${() => exec('explain', 'explain')} />
      <${Button} label="Save" onClick=${save} />
      ${ed.saved && html`<${Button} label="Delete" onClick=${del} />`}
      <span style=${{ marginLeft: 'auto', ...mono13, color: r && r.error ? '#cf7b7b' : T.dim, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }} title=${line}>${line || 'ctrl+enter runs'}</span>
    </div>
    ${body}
  </div>`;
}
