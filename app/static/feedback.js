// Header control on every page: record a change in place; the Feedback agent files it as a row.
// One panel per page: the draft, the panel and the rows below it belong to the page they were opened on.
import { Component } from './vendor/preact.mjs';
import { html, T, mono13, Button, TextArea } from './rows.js';
import { post } from './api.js';

export class Feedback extends Component {
  constructor() {
    super();
    this.state = { open: false, draft: '', error: null, busy: false };
  }

  componentDidUpdate(prevProps, prevState) {
    if (prevProps.page !== this.props.page) this.setState({ open: false, draft: '', error: null, busy: false });
    if (this.state.open && !prevState.open && this.ta) this.ta.focus();
  }

  async send() {
    const text = this.state.draft.trim();
    if (!text || this.state.busy) return;
    const { page, sel, item } = this.props;
    const body = { page, text };
    if (sel && item && !item.error) body.item = { module: sel.module, id: sel.id, text: String(item.text || '').slice(0, 300) };
    this.setState({ busy: true, error: null });
    try {
      await post('/api/feedback/action/add', body);
      this.setState({ draft: '', busy: false, open: false });
      this.props.onSent && this.props.onSent();
    } catch (e) {
      this.setState({ error: e.message, busy: false });
    }
  }

  async retry(id) {
    try {
      await post('/api/feedback/action/retry', { id });
      this.props.onSent && this.props.onSent();
    } catch (e) {
      this.setState({ error: e.message });
    }
  }

  render({ page, hue, sel, recent }, { open, draft, error, busy }) {
    const rows = recent && recent.page === page ? recent.rows : [];   // a fetch still in flight from the page just left
    const context = sel ? `${page} · item ${sel.id}` : page;
    return html`<span style=${{ position: 'relative' }}>
      <span class="ring" onClick=${() => this.setState({ open: !open })} style=${{ ...mono13, color: open ? T.text : T.muted, cursor: 'pointer', padding: '3px 8px', borderRadius: 6 }}>feedback</span>
      ${open && html`<div style=${{ position: 'absolute', top: 30, right: 0, width: 520, zIndex: 10, display: 'flex', flexDirection: 'column', gap: 8, padding: 12, background: T.panel, borderRadius: 6, boxShadow: `inset 0 0 0 1px ${T.hair}`, '--hue': hue }}>
        <${TextArea} taRef=${(el) => (this.ta = el)} value=${draft} placeholder="What should change here?" hue=${hue}
          onInput=${(e) => this.setState({ draft: e.target.value })}
          onKeyDown=${(e) => {
            if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); this.send(); }
            if (e.key === 'Escape') this.setState({ open: false });
          }} />
        <div style=${{ display: 'flex', alignItems: 'center', gap: 8, ...mono13, color: T.dim }}>
          <span style=${{ whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>${context}</span>
          <span style=${{ marginLeft: 'auto' }}><${Button} label=${busy ? '…' : 'Send'} primary=${true} hue=${hue} onClick=${() => this.send()} /></span>
        </div>
        ${error && html`<div style=${{ ...mono13, color: '#cf7b7b' }}>${error}</div>`}
        ${rows.length > 0 && html`<div style=${{ display: 'flex', flexDirection: 'column', marginTop: 4 }}>
          ${rows.map((r) => html`<div key=${r.id} title=${r.error || r.summary || ''} style=${{ display: 'flex', alignItems: 'center', gap: 8, height: 28, padding: '0 4px', ...mono13, color: T.muted, borderTop: `1px solid ${T.hair}` }}>
            ${r.status === 'queued' && html`<span style=${{ color: T.dim }}>filing…</span>`}
            ${r.status === 'filed' && html`<span style=${{ color: hue, flex: 'none' }}>${r.kind}</span><span style=${{ minWidth: 0, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>${r.summary}</span>`}
            ${r.status === 'failed' && html`<span style=${{ color: '#cf7b7b', flex: 'none' }}>failed</span><span style=${{ minWidth: 0, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis', color: T.dim }}>${(r.error || '').split('\n').pop()}</span>
              <span class="ring" onClick=${() => this.retry(r.id)} style=${{ marginLeft: 'auto', flex: 'none', cursor: 'pointer', padding: '2px 6px', borderRadius: 6 }}>retry</span>`}
          </div>`)}
        </div>`}
      </div>`}
    </span>`;
  }
}
