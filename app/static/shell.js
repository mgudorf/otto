// The frame: rail · header · loading line · three fixed tracks. Pages only fill the tracks.
import { render, Component } from './vendor/preact.mjs';
import { html, T, Icon, mono13, Button, dayLabel } from './rows.js';
import { get, inflight } from './api.js';
import { Session } from './session.js';
import * as home from './pages/home.js';
import * as memory from './pages/memory.js';
import * as business from './pages/business.js';
import * as activity from './pages/activity.js';
import * as settings from './pages/settings.js';

const PAGES = { home, memory, business, activity, settings };
const FOOT = [
  { name: 'activity', title: 'Activity', hue: '#e6e7ea', icon: '<path d="M3 12h4l2-6 3 10 2-6h3"></path>' },
  { name: 'settings', title: 'Settings', hue: '#e6e7ea', icon: '<circle cx="10" cy="10" r="6.5"></circle><circle cx="10" cy="10" r="2"></circle>' },
];

function pageFromHash() {
  const m = /^#\/([a-z_]+)/.exec(location.hash);
  return m ? m[1] : null;
}

class App extends Component {
  constructor() {
    super();
    this.state = { shell: null, page: null, data: null, sel: null, item: null, query: '', chip: 'All', more: 0, op: 1, loading: 0, error: null, prefill: null, section: 'General' };
  }

  async componentDidMount() {
    inflight.listeners.add((n) => this.setState({ loading: n }));
    window.addEventListener('hashchange', () => { const p = pageFromHash(); if (p && p !== this.state.page) this.go(p, true); });
    await this.loadShell();
    this.go(pageFromHash() || this.state.shell.settings['ui.start_page'] || 'home', true);
    this.timer = setInterval(() => this.refresh(), (this.state.shell.settings['ui.refresh_seconds'] || 30) * 1000);
  }

  async loadShell() {
    try {
      const shell = await get('/api/shell');
      this.setState({ shell, error: null });
      return shell;
    } catch (e) {
      this.setState({ error: `daemon unreachable: ${e.message}` });
    }
  }

  module(name) {
    const s = this.state.shell;
    return (s && s.modules.find((m) => m.name === name)) || FOOT.find((f) => f.name === name) || { name, title: name, hue: T.text, icon: '' };
  }

  async go(page, fromHash) {
    if (!fromHash) location.hash = `#/${page}`;
    this.setState({ op: 0 });
    setTimeout(() => this.setState({ page, sel: null, item: null, query: '', chip: 'All', more: 0, data: null, op: 1, prefill: null }, () => this.refresh()), 120);
  }

  async refresh() {
    const page = this.state.page;
    const impl = PAGES[page];
    const shell = await this.loadShell();
    if (!shell) return;
    if (this.timer && (shell.settings['ui.refresh_seconds'] || 30) * 1000 !== this.interval) {
      this.interval = (shell.settings['ui.refresh_seconds'] || 30) * 1000;
      clearInterval(this.timer);
      this.timer = setInterval(() => this.refresh(), this.interval);
    }
    if (!impl) { this.setState({ data: { empty: true } }); return; }
    try {
      const data = await impl.load(this);
      if (this.state.page === page) this.setState({ data, error: null });
    } catch (e) {
      this.setState({ error: e.message });
    }
    if (this.state.sel) this.loadItem(this.state.sel);
  }

  async select(sel) {
    if (this.state.sel && sel && this.state.sel.module === sel.module && String(this.state.sel.id) === String(sel.id)) sel = null;
    this.setState({ sel, item: null });
    if (sel) this.loadItem(sel);
  }

  async loadItem(sel) {
    if (sel.local) { this.setState({ item: sel.local }); return; }
    try {
      const item = await get(`/api/${sel.module}/item/${sel.id}`);
      if (this.state.sel && String(this.state.sel.id) === String(sel.id)) this.setState({ item });
    } catch (e) {
      this.setState({ item: { error: e.message } });
    }
  }

  sendToSession(text) {
    this.setState({ prefill: { text, n: Date.now() } });
  }

  render(_, s) {
    if (!s.shell) return html`<div style=${{ height: '100vh', display: 'grid', placeItems: 'center', background: T.ground, color: T.dim, fontFamily: 'Inter, system-ui, sans-serif', ...mono13 }}>${s.error || 'connecting…'}</div>`;
    const fmt = s.shell.settings['ui.time_format'] || '24h';
    const mod = this.module(s.page);
    const impl = PAGES[s.page];
    const rail = s.shell.modules.filter((m) => m.enabled || m.error);
    const railBtn = (m, active) => html`<div key=${m.name} title=${m.error ? `${m.title}: ${m.error}` : m.title} onClick=${() => !m.error && this.go(m.name)}
        style=${{ width: 32, height: 32, display: 'grid', placeItems: 'center', borderRadius: 6, cursor: m.error ? 'not-allowed' : 'pointer', color: m.error ? T.dim : m.hue, background: active ? T.raised : 'transparent', opacity: m.error ? 0.5 : 1 }}>
        <${Icon} svg=${m.icon || '<circle cx="10" cy="10" r="7"></circle>'} size=${20} sw=${1.5} /></div>`;
    const meta = impl && impl.meta ? impl.meta(this) : '';
    return html`<div style=${{ height: '100vh', display: 'flex', background: T.ground, color: T.text, fontFamily: 'Inter, system-ui, sans-serif', fontSize: 15, lineHeight: 1.4, overflow: 'hidden', '--hue': mod.hue }}>
      <div style=${{ width: 56, flex: 'none', display: 'flex', flexDirection: 'column', alignItems: 'center', padding: '14px 0', gap: 6 }}>
        ${rail.map((m) => railBtn(m, s.page === m.name))}
        <div style=${{ marginTop: 'auto', display: 'flex', flexDirection: 'column', gap: 6 }}>
          ${FOOT.map((f) => railBtn({ ...f, hue: T.muted }, s.page === f.name))}
        </div>
      </div>
      <div style=${{ flex: 1, minWidth: 0, display: 'flex', flexDirection: 'column' }}>
        <div style=${{ height: 48, flex: 'none', display: 'flex', alignItems: 'baseline', gap: 12, padding: '14px 32px 0' }}>
          <span style=${{ fontSize: 20, fontWeight: 600, lineHeight: 1.2 }}>${mod.title}</span>
          <span style=${{ ...mono13, color: T.dim }}>${meta}</span>
          ${s.error && html`<span style=${{ marginLeft: 'auto', ...mono13, color: '#cf7b7b' }}>${s.error}</span>`}
        </div>
        <div style=${{ height: 1, margin: '0 32px', position: 'relative', overflow: 'hidden', flex: 'none' }}>
          ${s.loading > 0 && html`<div style=${{ position: 'absolute', top: 0, left: 0, height: 1, width: '30%', background: T.muted, animation: 'otto-load 1.2s ease-in-out infinite' }} />`}
        </div>
        <div style=${{ flex: 1, minHeight: 0, display: 'grid', gridTemplateColumns: 'minmax(220px,4fr) minmax(300px,9fr) minmax(220px,4fr)', gap: '0 24px', padding: '19px 24px 24px', opacity: s.op, transition: 'opacity 120ms ease' }}>
          <div style=${{ minWidth: 0, minHeight: 0, overflow: 'auto', background: T.panel, borderRadius: 6, padding: '12px 8px 24px' }}>
            ${impl && s.data ? impl.Left({ app: this, data: s.data, mod, fmt }) : null}
          </div>
          <div style=${{ minWidth: 0, minHeight: 0, overflow: 'auto', padding: '8px 16px 40px' }}>
            ${impl && s.data ? impl.Middle({ app: this, data: s.data, mod, fmt }) : null}
          </div>
          ${mod.agent
            ? html`<${Session} module=${s.page} hue=${mod.hue} fmt=${fmt} selected=${!!s.sel} prefill=${s.prefill} onIdle=${() => this.refresh()} />`
            : html`<div style=${{ minWidth: 0, minHeight: 0, background: T.panel, borderRadius: 6, padding: '16px 12px 12px', ...mono13, color: T.dim }}>no agent on this page</div>`}
        </div>
      </div>
    </div>`;
  }
}

// Generic item inspector for modules that return {text, kind?, created_at, tags?, actions[]}.
export function Inspector({ app, item, mod, fmt, children, onAction }) {
  if (!item) return html`<div style=${{ ...mono13, color: T.dim }}>loading…</div>`;
  if (item.error) return html`<div style=${{ ...mono13, color: '#cf7b7b' }}>${item.error}</div>`;
  const hue = (app.module(item.module) || mod).hue;
  const icon = (app.module(item.module) || mod).icon;
  return html`<div style=${{ display: 'flex', flexDirection: 'column', gap: 20, maxWidth: '72ch' }}>
    <div style=${{ display: 'flex', alignItems: 'center', gap: 12 }}>
      <span style=${{ display: 'grid', placeItems: 'center', width: 16, height: 16, color: hue }}><${Icon} svg=${icon} /></span>
      <span style=${{ ...mono13, color: T.muted }}>${item.kind || item.verb || ''}${item.created_at ? ` · ${dayLabel(item.created_at)} ${new Date(item.created_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', hour12: fmt === '12h' })}` : ''}</span>
      <span class="bright-hover" onClick=${() => app.select(null)} style=${{ marginLeft: 'auto', cursor: 'pointer', color: T.dim, padding: '0 4px', lineHeight: 1 }}>×</span>
    </div>
    <div style=${{ lineHeight: 1.6, whiteSpace: 'pre-wrap', wordBreak: 'break-word' }}>${item.text}</div>
    ${children}
    <div style=${{ display: 'flex', gap: 8, marginTop: 6, flexWrap: 'wrap', alignItems: 'center' }}>
      ${(item.actions || []).map((a) => html`<${Button} key=${a.verb} label=${a.label} primary=${a.primary} hue=${hue} onClick=${() => onAction(a)} />`)}
      <${Button} label="Send to session" right=${true} onClick=${() => app.sendToSession(`About the selected item (${item.module} ${item.id}): ${String(item.text).slice(0, 300)}\n\n`)} />
    </div>
  </div>`;
}

render(html`<${App} />`, document.getElementById('root'));
