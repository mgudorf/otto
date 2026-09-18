// Header control on every module page, beside feedback: the module's own settings. Values persist in the settings table.
import { Component } from './vendor/preact.mjs';
import { html, T, meta13, IconButton, Toggle } from './rows.js';
import { put } from './api.js';

const SLIDERS = '<path d="M3 6h14M3 14h14"></path><circle cx="8" cy="6" r="2" fill="#101114"></circle><circle cx="12" cy="14" r="2" fill="#101114"></circle>';

export class ModuleSettings extends Component {
  constructor() {
    super();
    this.state = { open: false, error: null };
  }

  componentDidUpdate(prev) {
    if (prev.mod.name !== this.props.mod.name) this.setState({ open: false, error: null });
  }

  async save(patch) {
    try {
      await put('/api/settings', patch);
      this.setState({ error: null });
      this.props.onSaved && this.props.onSaved();
    } catch (e) {
      this.setState({ error: e.message });
    }
  }

  render({ mod, claude }, { open, error }) {
    const key = (k) => `modules.${mod.name}.${k}`;
    const row = (label, right) => html`<div style=${{ display: 'flex', alignItems: 'center', gap: 12, height: 32, padding: '0 4px' }}>${label}<span style=${{ marginLeft: 'auto', display: 'flex', alignItems: 'center' }}>${right}</span></div>`;
    const pick = (k, choices) => html`<select value=${mod[k]} onChange=${(e) => this.save({ [key(k)]: e.target.value })}>
      ${['default', ...choices].map((c) => html`<option key=${c} value=${c}>${c}</option>`)}</select>`;
    return html`<span style=${{ position: 'relative' }}>
      <${IconButton} svg=${SLIDERS} title="settings" on=${open} onClick=${() => this.setState({ open: !open })} />
      ${open && html`<div style=${{ position: 'absolute', top: 34, right: 0, width: 280, zIndex: 10, display: 'flex', flexDirection: 'column', gap: 2, padding: 8, background: T.panel, borderRadius: 6, boxShadow: `inset 0 0 0 1px ${T.hair}`, fontSize: 15 }}>
        ${mod.tasks > 0 && row('runs', html`<${Toggle} on=${mod.scheduled} onFlip=${() => this.save({ [key('scheduled')]: !mod.scheduled })} />`)}
        ${row('model', pick('model', claude.models))}
        ${row('effort', pick('effort', claude.efforts))}
        ${error && html`<div style=${{ ...meta13, color: '#cf7b7b', padding: '4px 4px 0' }}>${error}</div>`}
      </div>`}
    </span>`;
  }
}
