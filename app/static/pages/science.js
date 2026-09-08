// Science: LEFT = files by day with a live-kernel dot · MIDDLE = the selected notebook: cells, outputs, kernel actions.
import { Component } from '../vendor/preact.mjs';
import { html, T, mono13, Row, GroupHeader, Icon, Button, Empty } from '../rows.js';
import { get, post } from '../api.js';

const RED = '#cf7b7b';

export async function load(app) {
  const [left, blank] = await Promise.all([get('/api/science/left'), get('/api/science/blank')]);
  return { left, blank };
}

export function meta(app) {
  const b = app.state.data && app.state.data.blank;
  return b ? `${b.kernels} kernels · ${b.files} files` : '';
}

export function Left({ app, data, mod, fmt }) {
  const sel = app.state.sel;
  return html`<div style=${{ display: 'flex', flexDirection: 'column', gap: 20 }}>
    ${data.left.groups.length === 0 && html`<${Empty} text="no notebooks in root" />`}
    ${data.left.groups.map((g) => html`<div key=${g.label} style=${{ display: 'flex', flexDirection: 'column', gap: 2 }}>
      <${GroupHeader} label=${g.label} count=${g.count} />
      ${g.rows.map((r) => html`<${Row} key=${r.id} row=${r} hue=${mod.hue} fmt=${fmt} selected=${!!sel && String(sel.id) === String(r.id)} onSelect=${() => app.select({ module: 'science', id: r.id })} />`)}
    </div>`)}
    <div style=${{ ...mono13, color: T.dim, padding: '0 12px', height: 32, display: 'flex', alignItems: 'center' }}>${data.left.showing}</div>
  </div>`;
}

// Artboard: MIDDLE shows nothing until a file is picked.
export function Middle(props) {
  if (!props.app.state.sel) return null;
  return html`<${Notebook} ...${props} />`;
}

class Notebook extends Component {
  constructor() {
    super();
    this.state = { live: {} };   // live[index] = outputs streamed for a running cell since the last item load
    this.es = null;
  }

  componentDidMount() {
    this.es = new EventSource('/api/science/events');
    this.es.onmessage = (e) => this.onEvent(JSON.parse(e.data));
  }

  componentWillUnmount() {
    if (this.es) { this.es.close(); this.es = null; }
  }

  onEvent(ev) {
    const sel = this.props.app.state.sel;
    if (!sel || ev.path !== String(sel.id)) return;
    const live = { ...this.state.live };
    if (ev.event === 'started') live[ev.index] = [];
    else if (ev.event === 'output') live[ev.index] = [...(live[ev.index] || []), ev.output];
    else if (ev.event === 'done' || ev.event === 'error') { delete live[ev.index]; this.props.app.refresh(); }
    this.setState({ live });
  }

  render({ app, mod }, { live }) {
    const item = app.state.item;
    const hue = mod.hue;
    if (!item) return html`<div style=${{ ...mono13, color: T.dim }}>loading…</div>`;
    if (item.error) return html`<div style=${{ ...mono13, color: RED }}>${item.error}</div>`;
    const act = async (verb, body) => {
      try { await post(`/api/science/action/${verb}`, { id: item.id, ...body }); } catch (e) { app.setState({ error: e.message }); }
      app.refresh();
    };
    const runAll = async () => {
      for (const c of item.cells) if (c.type === 'code') await act('run', { index: c.index });
    };
    const k = item.kernel;
    const label = item.kind === 'py' ? 'module' : k ? `python3 · ${k.state}` : 'python3 · no kernel';
    return html`<div style=${{ display: 'flex', flexDirection: 'column', gap: 24, maxWidth: 960 }}>
      <style>${'.nb-html table{border-collapse:collapse;font-family:inherit}.nb-html th,.nb-html td{height:28px;padding:0 16px 0 0;text-align:left;border-top:1px solid rgba(230,231,234,.08);font-weight:400}.nb-html th{color:#5f636c}'}</style>
      <div style=${{ display: 'flex', alignItems: 'center', gap: 12, ...mono13 }}>
        <span style=${{ display: 'grid', placeItems: 'center', width: 16, height: 16, color: hue }}><${Icon} svg=${mod.icon} /></span>
        <span style=${{ color: T.text }}>${item.text}</span>
        <span style=${{ color: T.dim }}>${label}</span>
        <span class="bright-hover" onClick=${() => app.select(null)} style=${{ marginLeft: 'auto', cursor: 'pointer', color: T.dim, padding: '0 4px', lineHeight: 1 }}>×</span>
      </div>
      ${item.kind === 'ipynb' && html`<div style=${{ display: 'flex', alignItems: 'center', gap: 8 }}>
        <${Button} label="Run all" primary=${true} hue=${hue} onClick=${runAll} />
        ${k && html`<${Button} label="Interrupt" onClick=${() => act('interrupt')} />`}
        ${k && html`<${Button} label="Restart" onClick=${() => act('restart')} />`}
        ${k && html`<${Button} label="Shut down" onClick=${() => act('shutdown')} />`}
        <${Button} label="Send to session" right=${true} onClick=${() => app.sendToSession(`About the selected notebook (science ${item.id}):\n\n`)} />
      </div>`}
      ${item.kind === 'py'
        ? html`<pre style=${{ margin: 0, background: T.panel, borderRadius: 6, padding: '10px 14px', whiteSpace: 'pre-wrap', wordBreak: 'break-word', ...mono13, lineHeight: 1.6 }}>${item.source}</pre>`
        : item.cells.map((c) => html`<${Cell} key=${c.index} cell=${c} live=${live[c.index]} hue=${hue} onRun=${() => act('run', { index: c.index })} />`)}
    </div>`;
  }
}

function Cell({ cell, live, hue, onRun }) {
  const code = cell.type === 'code';
  const running = cell.running || live !== undefined;
  const outputs = live !== undefined ? live : cell.outputs;
  const n = running ? '[*]' : cell.execution_count != null ? `[${cell.execution_count}]` : '[ ]';
  return html`<div style=${{ display: 'grid', gridTemplateColumns: '48px minmax(0,1fr)', gap: '0 12px', ...mono13, lineHeight: 1.6 }}>
    <span class=${code ? 'bright-hover' : ''} title=${code ? 'run' : ''} onClick=${code ? onRun : null}
      style=${{ color: running ? hue : T.dim, paddingTop: 10, cursor: code ? 'pointer' : 'default', userSelect: 'none' }}>${code ? n : ''}</span>
    <div style=${{ display: 'flex', flexDirection: 'column', gap: 10, minWidth: 0 }}>
      <pre style=${{ margin: 0, background: code ? T.panel : 'transparent', borderRadius: 6, padding: '10px 14px', whiteSpace: 'pre-wrap', wordBreak: 'break-word', fontFamily: 'inherit', color: code ? T.text : T.muted }}>${cell.source}</pre>
      ${outputs.map((o, i) => html`<${Output} key=${i} o=${o} />`)}
    </div>
  </div>`;
}

function Output({ o }) {
  const pad = { padding: '2px 14px 6px' };
  if (o.kind === 'image') return html`<div style=${pad}><img src=${`data:image/png;base64,${o.png}`} style=${{ maxWidth: '100%', borderRadius: 6 }} /></div>`;
  if (o.kind === 'html') return html`<div class="nb-html" style=${{ ...pad, color: T.muted, overflowX: 'auto' }} dangerouslySetInnerHTML=${{ __html: o.html }} />`;
  if (o.kind === 'error') return html`<pre style=${{ ...pad, margin: 0, whiteSpace: 'pre-wrap', wordBreak: 'break-word', color: RED, fontFamily: 'inherit' }}>${o.traceback || `${o.ename}: ${o.evalue}`}</pre>`;
  return html`<pre style=${{ ...pad, margin: 0, whiteSpace: 'pre-wrap', wordBreak: 'break-word', color: T.muted, fontFamily: 'inherit' }}>${o.text}</pre>`;
}
