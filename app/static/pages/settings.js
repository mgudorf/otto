// Settings: LEFT = sections · MIDDLE = the chosen section. Live values persist in the settings table.
import { html, T, meta13, nums, rowStyle, Toggle, Button, bytes, dayLabel, clock } from '../rows.js';
import { get, put, post } from '../api.js';

export async function load() {
  return { data: await get('/api/data') };
}

const SECTIONS = ['General', 'Modules', 'Claude', 'Data'];

export function Left({ app }) {
  return html`<div style=${{ display: 'flex', flexDirection: 'column', gap: 4 }}>
    ${SECTIONS.map((label) => html`<div key=${label} class="row" onClick=${() => app.setState({ section: label })} style=${rowStyle({ selected: app.state.section === label, hue: T.muted })}>${label}</div>`)}
  </div>`;
}

const row = (label, right) => html`<div style=${{ display: 'flex', alignItems: 'center', height: 36, padding: '0 12px' }}>${label}<span style=${{ marginLeft: 'auto', display: 'flex', alignItems: 'center', gap: 6, fontSize: 13, color: T.muted }}>${right}</span></div>`;
const right = (v) => html`<span style=${{ ...meta13, color: T.muted, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis', maxWidth: 360 }} title=${v}>${v}</span>`;

export function Middle({ app, data, fmt }) {
  const shell = app.state.shell;
  const st = shell.settings;
  const save = async (patch) => { await put('/api/settings', patch); app.refresh(); };
  const section = app.state.section;
  const num = (key, min, max) => html`<input type="number" min=${min} max=${max} value=${st[key]} onChange=${(e) => save({ [key]: Number(e.target.value) })}
    style=${{ width: 72, height: 26, padding: '0 8px', border: 0, borderRadius: 6, background: T.raised, color: T.text, ...meta13, ...nums, textAlign: 'right' }} />`;
  const pill = (label, on, onClick) => html`<span onClick=${onClick} style=${{ padding: '2px 8px', borderRadius: 6, fontSize: 13, cursor: 'pointer', background: on ? T.text : 'transparent', color: on ? T.ground : T.muted }}>${label}</span>`;

  if (section === 'General') {
    const pages = [...shell.modules.filter((m) => !m.error && m.page && m.enabled).map((m) => m.name), 'activity', 'settings'];
    return html`<div style=${{ display: 'flex', flexDirection: 'column', gap: 2, maxWidth: 560 }}>
      ${row('Start page', html`<select value=${st['ui.start_page']} onChange=${(e) => save({ 'ui.start_page': e.target.value })}>${pages.map((p) => html`<option key=${p} value=${p}>${p}</option>`)}</select>`)}
      ${row('Refresh', html`${num('ui.refresh_seconds', 5, 3600)}<span style=${meta13}>s</span>`)}
      ${row('Time format', html`${pill('24 h', st['ui.time_format'] === '24h', () => save({ 'ui.time_format': '24h' }))}${pill('12 h', st['ui.time_format'] === '12h', () => save({ 'ui.time_format': '12h' }))}`)}
      ${row('Rows per page', num('ui.page_size', 10, 200))}
    </div>`;
  }
  if (section === 'Modules') {
    // shown = the rail entry, kept here because a hidden module's page cannot be reached to show it again.
    // runs, model and effort sit on each module's page; a module without a page keeps them here.
    const cols = '1fr 52px 52px 88px 88px';
    const dash = html`<span style=${{ ...meta13, color: T.dim, textAlign: 'right' }}>—</span>`;
    const pick = (m, k, choices) => html`<select value=${m[k]} onChange=${(e) => save({ [`modules.${m.name}.${k}`]: e.target.value })}>
      ${['default', ...choices].map((c) => html`<option key=${c} value=${c}>${c}</option>`)}</select>`;
    return html`<div style=${{ display: 'flex', flexDirection: 'column', gap: 2, maxWidth: 560 }}>
      <div style=${{ display: 'grid', gridTemplateColumns: cols, gap: 8, alignItems: 'center', height: 28, padding: '0 12px', ...meta13, color: T.dim }}>
        <span></span><span style=${{ textAlign: 'right' }}>shown</span><span style=${{ textAlign: 'right' }}>runs</span><span style=${{ textAlign: 'right' }}>model</span><span style=${{ textAlign: 'right' }}>effort</span></div>
      ${shell.modules.filter((m) => m.name !== 'home').map((m) => html`<div key=${m.name} class="trow" style=${{ display: 'grid', gridTemplateColumns: cols, gap: 8, alignItems: 'center', height: 36, padding: '0 12px', borderRadius: 6 }}>
        <span style=${{ display: 'flex', alignItems: 'center', gap: 10, minWidth: 0, color: m.hue }}>${m.title}
          ${m.error && html`<span style=${{ ...meta13, color: '#cf7b7b', marginLeft: 'auto', maxWidth: 240, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }} title=${m.error}>failed to load</span>`}
        </span>
        ${m.error || !m.page ? dash : html`<span style=${{ display: 'flex' }}><${Toggle} on=${m.enabled} onFlip=${() => save({ [`modules.${m.name}.enabled`]: !m.enabled })} /></span>`}
        ${m.error ? html`${dash}${dash}${dash}` : m.page ? html`<span style=${{ gridColumn: 'span 3', ...meta13, color: T.dim, textAlign: 'right' }}>on its page</span>` : html`
          ${m.tasks ? html`<span style=${{ display: 'flex' }}><${Toggle} on=${m.scheduled} onFlip=${() => save({ [`modules.${m.name}.scheduled`]: !m.scheduled })} /></span>` : dash}
          <span style=${{ display: 'flex', justifyContent: 'flex-end' }}>${pick(m, 'model', shell.claude.models)}</span>
          <span style=${{ display: 'flex', justifyContent: 'flex-end' }}>${pick(m, 'effort', shell.claude.efforts)}</span>`}
      </div>`)}
    </div>`;
  }
  if (section === 'Claude') {
    const c = shell.claude;
    return html`<div style=${{ display: 'flex', flexDirection: 'column', gap: 2, maxWidth: 560 }}>
      ${row('Binary', right(c.binary))}
      ${row('Model', right(c.model))}
      ${row('Models a module may pick', right(c.models.join(' · ')))}
      ${row('Efforts a module may pick', right(c.efforts.join(' · ')))}
      ${row('Agents dir', right(c.agents_dir))}
      ${row('Workspace', right(c.workspace))}
      ${row('Sessions kept', right(`${c.sessions_kept_days} d`))}
      ${row('Background jobs', right(c.background_jobs.join(' · ') || 'none'))}
    </div>`;
  }
  const d = data.data;
  return html`<div style=${{ display: 'flex', flexDirection: 'column', gap: 2, maxWidth: 560 }}>
    ${row('Database', right(d.db))}
    ${row('Size', right(bytes(d.size_bytes)))}
    ${row('Last backup', right(d.last_backup ? `${dayLabel(d.last_backup)} ${clock(d.last_backup, fmt)} · ${d.backups} kept` : 'never'))}
    ${row('Last export', right(d.last_export ? `${dayLabel(d.last_export)} ${clock(d.last_export, fmt)} · ${d.exports} kept` : 'never'))}
    <div style=${{ display: 'flex', alignItems: 'center', gap: 8, height: 36, padding: '0 12px', marginTop: 8 }}>
      <span onClick=${async () => { await post('/api/data/backup'); app.refresh(); }} style=${{ padding: '5px 10px', borderRadius: 6, background: T.text, color: T.ground, fontSize: 13, fontWeight: 500, cursor: 'pointer' }}>Back up now</span>
      <${Button} label="Export" onClick=${async () => { await post('/api/data/export'); app.refresh(); }} />
      <${Button} label="Vacuum" onClick=${async () => { await post('/api/data/vacuum'); app.refresh(); }} />
    </div>
  </div>`;
}
