// Settings: LEFT = sections · MIDDLE = the chosen section. Live values persist in the settings table.
import { html, T, mono13, Toggle, Button, bytes, dayLabel, clock } from '../rows.js';
import { get, put, post } from '../api.js';

export async function load() {
  return { data: await get('/api/data') };
}

export function meta(app) {
  return app.state.section;
}

const SECTIONS = ['General', 'Modules', 'Claude', 'Data'];

export function Left({ app }) {
  const s = app.state.shell;
  const metaOf = { General: '4', Modules: String(s.modules.filter((m) => !m.error).length), Claude: '5', Data: '3' };
  return html`<div style=${{ display: 'flex', flexDirection: 'column', gap: 2 }}>
    ${SECTIONS.map((label) => html`<div key=${label} class="row" onClick=${() => app.setState({ section: label })}
        style=${{ display: 'flex', alignItems: 'center', gap: 12, height: 36, padding: '0 12px', borderRadius: 6, cursor: 'pointer', background: app.state.section === label ? T.raised : 'transparent', color: app.state.section === label ? T.text : T.muted }}>
      ${label}<span style=${{ ...mono13, color: T.dim }}>${metaOf[label]}</span></div>`)}
  </div>`;
}

const row = (label, right) => html`<div style=${{ display: 'flex', alignItems: 'center', height: 36, padding: '0 12px' }}>${label}<span style=${{ marginLeft: 'auto', display: 'flex', alignItems: 'center', gap: 6, fontSize: 13, color: T.muted }}>${right}</span></div>`;
const monoRight = (v) => html`<span style=${{ ...mono13, color: T.muted, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis', maxWidth: 360 }} title=${v}>${v}</span>`;

export function Middle({ app, data, fmt }) {
  const shell = app.state.shell;
  const st = shell.settings;
  const save = async (patch) => { await put('/api/settings', patch); app.refresh(); };
  const section = app.state.section;
  const num = (key, min, max) => html`<input type="number" min=${min} max=${max} value=${st[key]} onChange=${(e) => save({ [key]: Number(e.target.value) })}
    style=${{ width: 72, height: 26, padding: '0 8px', border: 0, borderRadius: 6, background: T.raised, color: T.text, ...mono13, textAlign: 'right' }} />`;
  const pill = (label, on, onClick) => html`<span onClick=${onClick} style=${{ padding: '2px 8px', borderRadius: 6, fontSize: 13, cursor: 'pointer', background: on ? T.text : 'transparent', color: on ? T.ground : T.muted }}>${label}</span>`;

  if (section === 'General') {
    const pages = [...shell.modules.filter((m) => !m.error && m.enabled).map((m) => m.name), 'activity', 'settings'];
    return html`<div style=${{ display: 'flex', flexDirection: 'column', gap: 2, maxWidth: 560 }}>
      ${row('Start page', html`<select value=${st['ui.start_page']} onChange=${(e) => save({ 'ui.start_page': e.target.value })}>${pages.map((p) => html`<option key=${p} value=${p}>${p}</option>`)}</select>`)}
      ${row('Refresh', html`${num('ui.refresh_seconds', 5, 3600)}<span style=${mono13}>s</span>`)}
      ${row('Time format', html`${pill('24 h', st['ui.time_format'] === '24h', () => save({ 'ui.time_format': '24h' }))}${pill('12 h', st['ui.time_format'] === '12h', () => save({ 'ui.time_format': '12h' }))}`)}
      ${row('Rows per page', num('ui.page_size', 10, 200))}
      ${row('Side panel max', html`${num('ui.side_max', 280, 900)}<span style=${mono13}>px</span>`)}
      ${row('Middle max', html`${num('ui.middle_max', 640, 3000)}<span style=${mono13}>px</span>`)}
    </div>`;
  }
  if (section === 'Modules') {
    // shown = the rail entry; runs = its scheduled tasks. Both are the owner's; nothing else writes them.
    const cols = '1fr 52px 52px';
    const dash = html`<span style=${{ ...mono13, color: T.dim, textAlign: 'right' }}>—</span>`;
    return html`<div style=${{ display: 'flex', flexDirection: 'column', gap: 2, maxWidth: 560 }}>
      <div style=${{ display: 'grid', gridTemplateColumns: cols, gap: 8, alignItems: 'center', height: 28, padding: '0 12px', ...mono13, color: T.dim }}>
        <span></span><span style=${{ textAlign: 'right' }}>shown</span><span style=${{ textAlign: 'right' }}>runs</span></div>
      ${shell.modules.filter((m) => m.name !== 'home').map((m) => html`<div key=${m.name} class="trow" style=${{ display: 'grid', gridTemplateColumns: cols, gap: 8, alignItems: 'center', height: 36, padding: '0 12px', borderRadius: 6 }}>
        <span style=${{ display: 'flex', alignItems: 'center', gap: 10, minWidth: 0 }}>
          <span style=${{ width: 6, height: 6, borderRadius: 3, background: m.hue, flex: '0 0 auto' }} />${m.title}
          ${m.error && html`<span style=${{ ...mono13, color: '#cf7b7b', marginLeft: 'auto', maxWidth: 240, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }} title=${m.error}>failed to load</span>`}
        </span>
        ${m.error ? dash : html`<span style=${{ display: 'flex' }}><${Toggle} on=${m.enabled} onFlip=${() => save({ [`modules.${m.name}.enabled`]: !m.enabled })} /></span>`}
        ${m.error || !m.tasks ? dash : html`<span style=${{ display: 'flex' }}><${Toggle} on=${m.scheduled} onFlip=${() => save({ [`modules.${m.name}.scheduled`]: !m.scheduled })} /></span>`}
      </div>`)}
    </div>`;
  }
  if (section === 'Claude') {
    const c = shell.claude;
    return html`<div style=${{ display: 'flex', flexDirection: 'column', gap: 2, maxWidth: 560 }}>
      ${row('Binary', monoRight(c.binary))}
      ${row('Model', monoRight(c.model))}
      ${row('Agents dir', monoRight(c.agents_dir))}
      ${row('Workspace', monoRight(c.workspace))}
      ${row('Sessions kept', monoRight(`${c.sessions_kept_days} d`))}
      ${row('Background jobs', monoRight(c.background_jobs.join(' · ') || 'none'))}
      <div style=${{ ...mono13, color: T.dim, padding: '12px 12px 0' }}>edit config.toml and relaunch to change these</div>
    </div>`;
  }
  const d = data.data;
  return html`<div style=${{ display: 'flex', flexDirection: 'column', gap: 2, maxWidth: 560 }}>
    ${row('Database', monoRight(d.db))}
    ${row('Size', monoRight(bytes(d.size_bytes)))}
    ${row('Last backup', monoRight(d.last_backup ? `${dayLabel(d.last_backup)} ${clock(d.last_backup, fmt)} · ${d.backups} kept` : 'never'))}
    <div style=${{ display: 'flex', alignItems: 'center', gap: 8, height: 36, padding: '0 12px', marginTop: 8 }}>
      <span onClick=${async () => { await post('/api/data/backup'); app.refresh(); }} style=${{ padding: '5px 10px', borderRadius: 6, background: T.text, color: T.ground, fontSize: 13, fontWeight: 500, cursor: 'pointer' }}>Back up now</span>
      <${Button} label="Vacuum" onClick=${async () => { await post('/api/data/vacuum'); app.refresh(); }} />
    </div>
  </div>`;
}
