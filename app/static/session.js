// RIGHT track: one Claude session per module. Shell is identical everywhere; agent and tools differ.
import { Component } from './vendor/preact.mjs';
import { html, T, mono13, clock } from './rows.js';
import { get, post } from './api.js';

export class Session extends Component {
  constructor() {
    super();
    this.state = { turns: [], busy: false, draft: '', agent: null, contextLabel: '', error: null };
    this.es = null;
    this.toolIds = {};
  }

  componentDidMount() { this.open(); }
  componentWillUnmount() { this.close(); }
  componentDidUpdate(prev) {
    if (prev.module !== this.props.module) { this.close(); this.open(); }
    if (this.props.prefill && this.props.prefill !== prev.prefill) {
      this.setState({ draft: this.props.prefill.text });
      if (this.ta) this.ta.focus();
    }
    if (this.list && this.state.turns.length !== (this.lastLen || 0)) {
      this.lastLen = this.state.turns.length;
      this.list.scrollTop = this.list.scrollHeight;
    }
  }

  async open() {
    const m = this.props.module;
    this.setState({ turns: [], busy: false, agent: null, contextLabel: '', error: null });
    try {
      const s = await get(`/api/session/${m}`);
      this.setState({ turns: s.turns, busy: s.busy, agent: s.agent, contextLabel: s.context_label });
    } catch (e) {
      this.setState({ error: e.message });
      return;
    }
    this.es = new EventSource(`/api/session/${m}/events`);
    this.es.onmessage = (e) => this.onEvent(JSON.parse(e.data));
  }

  close() {
    if (this.es) { this.es.close(); this.es = null; }
    this.toolIds = {};
  }

  onEvent(ev) {
    const turns = this.state.turns.slice();
    if (ev.role === 'user' || ev.role === 'model') turns.push({ role: ev.role, text: ev.text, ts: ev.ts });
    else if (ev.role === 'tool') { this.toolIds[ev.id] = turns.length; turns.push({ role: 'tool', tool: ev.tool, status: ev.status, ts: ev.ts }); }
    else if (ev.role === 'tool_result') { const i = this.toolIds[ev.id]; if (i !== undefined && turns[i]) turns[i] = { ...turns[i], status: ev.status }; }
    else if (ev.role === 'error') turns.push({ role: 'system', text: `error: ${ev.text}`, ts: ev.ts });
    else if (ev.role === 'system') { turns.length = 0; turns.push({ role: 'system', text: ev.text, ts: ev.ts }); }
    else if (ev.role === 'idle') { this.setState({ turns, busy: false }); this.props.onIdle && this.props.onIdle(); return; }
    else if (ev.role === 'result') { this.setState({ turns }); return; }
    this.setState({ turns, busy: ev.role === 'user' ? true : this.state.busy });
  }

  async send() {
    const text = this.state.draft.trim();
    if (!text || this.state.busy) return;
    this.setState({ draft: '', error: null });
    try {
      const r = await post(`/api/session/${this.props.module}/send`, { text });
      if (r.cleared === false) this.setState({ turns: [{ role: 'system', text: 'nothing to clear', ts: new Date().toISOString() }] });
    } catch (e) {
      this.setState({ error: e.message, draft: text });
    }
  }

  render({ module, hue, fmt, selected }, { turns, busy, draft, agent, contextLabel, error }) {
    const ring = 'inset 0 0 0 1px rgba(230,231,234,.14)';
    return html`<div style=${{ minWidth: 0, minHeight: 0, display: 'flex', flexDirection: 'column', gap: 14, background: T.panel, borderRadius: 6, padding: '16px 12px 12px', '--hue': hue }}>
      <div style=${{ display: 'flex', alignItems: 'center', gap: 10, height: 24, padding: '0 4px', ...mono13, color: T.muted }}>
        <span style=${{ width: 6, height: 6, borderRadius: 3, background: hue }} />${agent ? agent.cmd : `claude · ${module}`}
        ${busy && html`<span style=${{ marginLeft: 'auto', color: T.dim }}>thinking…</span>`}
      </div>
      <div style=${{ display: 'flex', flexWrap: 'wrap', gap: 6, padding: '0 4px' }}>
        ${(agent ? agent.skills : []).map((s) => html`<span key=${s} style=${{ padding: '2px 8px', borderRadius: 6, fontSize: 13, color: T.muted, boxShadow: 'inset 0 0 0 1px rgba(230,231,234,.1)' }}>${s}</span>`)}
      </div>
      <div ref=${(el) => (this.list = el)} style=${{ flex: 1, minHeight: 0, overflow: 'auto', display: 'flex', flexDirection: 'column', gap: 16, padding: '8px 4px' }}>
        ${error && html`<div style=${{ ...mono13, color: '#cf7b7b', padding: '0 2px' }}>${error}</div>`}
        ${turns.map((t, i) => {
          if (t.role === 'user') return html`<div key=${i} style=${{ alignSelf: 'flex-end', maxWidth: '85%', background: T.raised, borderRadius: 6, padding: '10px 12px', whiteSpace: 'pre-wrap', lineHeight: 1.5 }}>${t.text}</div>`;
          if (t.role === 'model') return html`<div key=${i} style=${{ lineHeight: 1.6, padding: '0 2px', whiteSpace: 'pre-wrap' }}>${t.text}</div>`;
          if (t.role === 'tool') return html`<div key=${i} style=${{ display: 'flex', alignItems: 'center', gap: 10, height: 28, padding: '0 4px', ...mono13, color: T.muted }}><span style=${{ color: hue }}>▸</span>${t.tool}<span style=${{ marginLeft: 'auto', color: T.dim }}>${t.status || ''}</span></div>`;
          return html`<div key=${i} style=${{ ...mono13, color: T.dim, padding: '0 2px' }}>${t.text}${t.ts ? html`<span style=${{ marginLeft: 8 }}>${clock(t.ts, fmt)}</span>` : null}</div>`;
        })}
      </div>
      <div style=${{ display: 'flex', flexDirection: 'column', gap: 8 }}>
        <textarea ref=${(el) => (this.ta = el)} value=${draft} rows="3" placeholder=${agent ? agent.placeholder : ''}
          onInput=${(e) => this.setState({ draft: e.target.value })}
          onKeyDown=${(e) => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); this.send(); } }}
          style=${{ width: '100%', resize: 'none', padding: '10px 12px', border: 0, borderRadius: 6, background: T.raised, color: T.text, fontSize: 15, lineHeight: 1.4 }} />
        <div style=${{ display: 'flex', alignItems: 'center', gap: 8, ...mono13, color: T.dim, padding: '0 4px' }}>
          <span>${contextLabel}${selected ? ' · 1 selected' : ''}</span>
          <span class="ring" onClick=${() => { this.setState({ draft: '/clear' }, () => this.send()); }} style=${{ marginLeft: 'auto', padding: '3px 8px', borderRadius: 6, color: T.muted, cursor: 'pointer' }}>new</span>
          <span onClick=${() => this.send()} style=${{ padding: '3px 10px', borderRadius: 6, cursor: 'pointer', color: busy ? T.dim : T.text, boxShadow: ring }}>↵</span>
        </div>
      </div>
    </div>`;
  }
}
