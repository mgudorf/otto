// RIGHT track: the module's Claude sessions, one tab each. Shell is identical everywhere; agent and tools differ.
// Nothing is written on a blank pane: the tabs, `+`, the box, `/` for the agent's skills and `↵`.
import { Component } from './vendor/preact.mjs';
import { html, T, meta13, clock, TextArea, submitOnEnter, Plus, Enter, Busy } from './rows.js';
import { get, post } from './api.js';
import { Markdown } from './md.js';

export class Session extends Component {
  constructor() {
    super();
    this.state = { sessions: [], sid: null, turns: [], busy: false, draft: '', agent: null, error: null, menu: false };
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
    this.setState({ turns: [], busy: false, agent: null, error: null, menu: false });
    try {
      const s = await get(`/api/session/${m}`);
      const sid = pick === undefined ? (s.sessions.length ? s.sessions[s.sessions.length - 1].id : null) : pick;
      this.setState({ sessions: s.sessions, agent: s.agent, sid });
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
      this.setState({ sessions: s.sessions });
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
    this.setState({ draft: '', error: null, menu: false });
    try {
      const r = await post(`/api/session/${this.props.module}/send`, { text, id: sid });
      if (r.session && r.session !== sid) await this.open(r.session);   // a blank tab became a session: its tab appears and streams
      if (r.cleared === false) this.setState({ turns: [{ role: 'system', text: 'nothing to clear', ts: new Date().toISOString() }] });
    } catch (e) {
      this.setState({ error: e.message, draft: text });
    }
  }

  // A skill picked from the `/` menu lands in the box as `/name `, ready for what follows.
  pick(skill) {
    this.setState({ draft: `/${skill} `, menu: false });
    if (this.ta) this.ta.focus();
  }

  render({ hue, fmt }, { sessions, sid, turns, busy, draft, agent, error, menu }) {
    const tab = (id, label, active, onPick) => html`<span key=${id} onClick=${onPick} title=${label}
        style=${{ ...meta13, padding: '3px 8px', borderRadius: 6, cursor: 'pointer', flex: '0 1 auto', minWidth: 0, maxWidth: 140, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis', background: active ? T.raised : 'transparent', color: active ? T.text : T.muted }}>${label}</span>`;
    const skills = agent ? agent.skills : [];
    return html`<div style=${{ minWidth: 0, minHeight: 0, display: 'flex', flexDirection: 'column', gap: 14, background: T.panel, borderRadius: 6, padding: 12, '--hue': hue }}>
      <div style=${{ display: 'flex', alignItems: 'center', gap: 4, padding: '0 4px', minWidth: 0, minHeight: 28 }}>
        ${sessions.map((s) => tab(s.id, s.busy && s.id !== sid ? `${s.label} …` : s.label, s.id === sid, () => this.show(s.id)))}
        <${Plus} title="new tab" active=${sid === null} onClick=${() => sid !== null && this.show(null)} />
        ${sid !== null && html`<span class="ring" title="close this tab" onClick=${() => this.send('/clear')} style=${{ ...meta13, marginLeft: 'auto', padding: '3px 8px', borderRadius: 6, cursor: 'pointer', color: T.dim, flex: 'none' }}>×</span>`}
      </div>
      <div ref=${(el) => (this.list = el)} style=${{ flex: 1, minHeight: 0, overflow: 'auto', display: 'flex', flexDirection: 'column', gap: 16, padding: '8px 4px' }}>
        ${error && html`<div style=${{ ...meta13, color: '#cf7b7b', padding: '0 2px' }}>${error}</div>`}
        ${turns.map((t, i) => {
          if (t.role === 'user') return html`<div key=${i} style=${{ alignSelf: 'flex-end', maxWidth: '85%', background: T.raised, borderRadius: 6, padding: '10px 12px', whiteSpace: 'pre-wrap', lineHeight: 1.5 }}>${t.text}</div>`;
          if (t.role === 'model') return html`<div key=${i} style=${{ padding: '0 2px' }}><${Markdown} text=${t.text} /></div>`;
          if (t.role === 'tool') return html`<div key=${i} style=${{ display: 'flex', alignItems: 'center', gap: 10, height: 28, padding: '0 4px', ...meta13, color: T.muted }}><span style=${{ color: hue }}>▸</span>${t.tool}<span style=${{ marginLeft: 'auto', color: T.dim }}>${t.status || ''}</span></div>`;
          return html`<div key=${i} style=${{ ...meta13, color: T.dim, padding: '0 2px' }}>${t.text}${t.ts ? html`<span style=${{ marginLeft: 8 }}>${clock(t.ts, fmt)}</span>` : null}</div>`;
        })}
      </div>
      <div style=${{ position: 'relative', display: 'flex', flexDirection: 'column', gap: 8 }}>
        ${menu && html`<div style=${{ position: 'absolute', bottom: 36, left: 4, zIndex: 10, minWidth: 160, display: 'flex', flexDirection: 'column', padding: 4, background: T.raised, borderRadius: 6, boxShadow: T.ring }}>
          ${skills.map((s) => html`<span key=${s} class="row" onClick=${() => this.pick(s)} style=${{ padding: '5px 10px', borderRadius: 6, cursor: 'pointer', ...meta13, color: T.text }}>/${s}</span>`)}
        </div>`}
        <${TextArea} taRef=${(el) => (this.ta = el)} value=${draft} hue=${hue}
          onInput=${(e) => this.setState({ draft: e.target.value })}
          onKeyDown=${(e) => { if (e.key === 'Escape') this.setState({ menu: false }); submitOnEnter(() => this.send())(e); }} />
        <div style=${{ display: 'flex', alignItems: 'center', gap: 8, padding: '0 4px' }}>
          ${skills.length > 0 && html`<span class="ring" title="commands" onClick=${() => this.setState({ menu: !menu })} style=${{ display: 'grid', placeItems: 'center', width: 28, height: 28, borderRadius: 6, cursor: 'pointer', ...meta13, color: menu ? T.text : T.muted, background: menu ? T.raised : 'transparent' }}>/</span>`}
          ${busy && html`<${Busy} hue=${hue} />`}
          <${Enter} busy=${busy} onClick=${() => this.send()} />
        </div>
      </div>
    </div>`;
  }
}
