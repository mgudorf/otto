// RIGHT track: the module's Claude sessions, one tab each. Shell is identical everywhere; agent and tools differ.
import { Component } from './vendor/preact.mjs';
import { html, T, mono13, clock } from './rows.js';
import { get, post } from './api.js';
import { Markdown } from './md.js';

export class Session extends Component {
  constructor() {
    super();
    this.state = { sessions: [], sid: null, turns: [], busy: false, draft: '', agent: null, contextLabel: '', error: null };
    this.es = null;
    this.toolIds = {};
  }

  componentDidMount() { this.open(); }
  componentWillUnmount() { this.close(); }
  componentDidUpdate(prev) {
    if (prev.module !== this.props.module) { this.close(); this.open(); }
    else if (this.props.tick !== prev.tick) this.relist();
    if (this.props.prefill && this.props.prefill !== prev.prefill) {
      this.setState({ draft: this.props.prefill.text });
      if (this.ta) this.ta.focus();
    }
    if (this.list && this.state.turns.length !== (this.lastLen || 0)) {
      this.lastLen = this.state.turns.length;
      this.list.scrollTop = this.list.scrollHeight;
    }
  }

  // The tab list; then the newest open tab, or the one asked for. `null` is a blank tab: its first send opens the session.
  async open(pick) {
    const m = this.props.module;
    this.setState({ turns: [], busy: false, agent: null, contextLabel: '', error: null });
    try {
      const s = await get(`/api/session/${m}`);
      const sid = pick === undefined ? (s.sessions.length ? s.sessions[s.sessions.length - 1].id : null) : pick;
      this.setState({ sessions: s.sessions, agent: s.agent, contextLabel: s.context_label, sid });
      await this.show(sid);
    } catch (e) {
      this.setState({ error: e.message });
    }
  }

  // The tab list again on the shell's refresh: a turn a page action started (Education's Submit) lands in the newest
  // tab, which a blank tab follows; the strip's labels and busy marks catch up.
  async relist() {
    try {
      const s = await get(`/api/session/${this.props.module}`);
      this.setState({ sessions: s.sessions, contextLabel: s.context_label });
      if (this.state.sid === null && s.sessions.length) await this.show(s.sessions[s.sessions.length - 1].id);
    } catch { /* the next refresh tries again */ }
  }

  async show(sid) {
    this.close();
    this.setState({ sid, turns: [], busy: false, error: null });
    if (!sid) return;
    const m = this.props.module;
    const s = await get(`/api/session/${m}/${sid}`);
    if (this.state.sid !== sid) return;
    this.setState({ turns: s.turns, busy: s.busy });
    this.es = new EventSource(`/api/session/${m}/${sid}/events`);
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
    else if (ev.role === 'delta') return;                            // Chat's page uses it; the pane shows whole turns
    else if (ev.role === 'error') turns.push({ role: 'system', text: `error: ${ev.text}`, ts: ev.ts });
    else if (ev.role === 'system') turns.push({ role: 'system', text: ev.text, ts: ev.ts });   // `session cleared`: the tagger is running
    else if (ev.role === 'tagged') { this.open(null); return; }      // the tab is closed: the list shrinks and a blank tab opens
    else if (ev.role === 'idle') { this.setState({ turns, busy: false }); this.props.onIdle && this.props.onIdle(); return; }
    else if (ev.role === 'result') { this.setState({ turns }); return; }
    this.setState({ turns, busy: ev.role === 'user' ? true : this.state.busy });
  }

  async send(text) {
    text = (text === undefined ? this.state.draft : text).trim();
    if (!text || this.state.busy) return;
    const { sid } = this.state;
    this.setState({ draft: '', error: null });
    try {
      const r = await post(`/api/session/${this.props.module}/send`, { text, id: sid });
      if (r.session && r.session !== sid) await this.open(r.session);   // a blank tab became a session: its tab appears and streams
      if (r.cleared === false) this.setState({ turns: [{ role: 'system', text: 'nothing to clear', ts: new Date().toISOString() }] });
    } catch (e) {
      this.setState({ error: e.message, draft: text });
    }
  }

  render({ module, hue, fmt, selected }, { sessions, sid, turns, busy, draft, agent, contextLabel, error }) {
    const ring = 'inset 0 0 0 1px rgba(230,231,234,.14)';
    const tab = (id, label, active, onPick) => html`<span key=${id || 'blank'} onClick=${onPick} title=${label}
        style=${{ ...mono13, padding: '3px 8px', borderRadius: 6, cursor: 'pointer', flex: '0 1 auto', minWidth: 0, maxWidth: 140, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis', background: active ? T.raised : 'transparent', color: active ? T.text : T.muted }}>${label}</span>`;
    return html`<div style=${{ minWidth: 0, minHeight: 0, display: 'flex', flexDirection: 'column', gap: 14, background: T.panel, borderRadius: 6, padding: '16px 12px 12px', '--hue': hue }}>
      <div style=${{ display: 'flex', alignItems: 'center', gap: 10, height: 24, padding: '0 4px', ...mono13, color: T.muted }}>
        <span style=${{ width: 6, height: 6, borderRadius: 3, background: hue }} />${agent ? agent.cmd : `claude · ${module}`}
        ${busy && html`<span style=${{ marginLeft: 'auto', color: T.dim }}>thinking…</span>`}
      </div>
      <div style=${{ display: 'flex', alignItems: 'center', gap: 4, padding: '0 4px', minWidth: 0 }}>
        ${sessions.map((s) => tab(s.id, s.busy && s.id !== sid ? `${s.label} …` : s.label, s.id === sid, () => this.show(s.id)))}
        ${sid === null && tab(null, 'new', true, () => {})}
        ${sid !== null && html`<span class="ring" title="new tab" onClick=${() => this.show(null)} style=${{ ...mono13, padding: '3px 8px', borderRadius: 6, cursor: 'pointer', color: T.muted, flex: 'none' }}>+</span>`}
        ${sid !== null && html`<span class="ring" title="close this tab: tag it and end the session" onClick=${() => this.send('/clear')} style=${{ ...mono13, marginLeft: 'auto', padding: '3px 8px', borderRadius: 6, cursor: 'pointer', color: T.dim, flex: 'none' }}>×</span>`}
      </div>
      <div style=${{ display: 'flex', flexWrap: 'wrap', gap: 6, padding: '0 4px' }}>
        ${(agent ? agent.skills : []).map((s) => html`<span key=${s} style=${{ padding: '2px 8px', borderRadius: 6, fontSize: 13, color: T.muted, boxShadow: 'inset 0 0 0 1px rgba(230,231,234,.1)' }}>${s}</span>`)}
      </div>
      <div ref=${(el) => (this.list = el)} style=${{ flex: 1, minHeight: 0, overflow: 'auto', display: 'flex', flexDirection: 'column', gap: 16, padding: '8px 4px' }}>
        ${error && html`<div style=${{ ...mono13, color: '#cf7b7b', padding: '0 2px' }}>${error}</div>`}
        ${turns.map((t, i) => {
          if (t.role === 'user') return html`<div key=${i} style=${{ alignSelf: 'flex-end', maxWidth: '85%', background: T.raised, borderRadius: 6, padding: '10px 12px', whiteSpace: 'pre-wrap', lineHeight: 1.5 }}>${t.text}</div>`;
          if (t.role === 'model') return html`<div key=${i} style=${{ padding: '0 2px' }}><${Markdown} text=${t.text} /></div>`;
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
          <span onClick=${() => this.send()} style=${{ marginLeft: 'auto', padding: '3px 10px', borderRadius: 6, cursor: 'pointer', color: busy ? T.dim : T.text, boxShadow: ring }}>↵</span>
        </div>
      </div>
    </div>`;
  }
}
