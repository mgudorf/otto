// Science: LEFT = files by day with a live-kernel dot · MIDDLE = the selected notebook: cells, outputs, kernel actions, editing.
import { Component } from '../vendor/preact.mjs';
import { html, T, mono13, Row, GroupHeader, Icon, Button, Empty } from '../rows.js';
import { get, post } from '../api.js';

const RED = '#cf7b7b';
const keep = (e) => e.preventDefault();   // on mousedown: keeps the textarea focused so blur does not fire first

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
  const create = async () => {
    const name = window.prompt('New notebook name');
    if (!name) return;
    try {
      const r = await post('/api/science/action/new', { name });
      app.setState({ error: null });
      await app.refresh();
      app.select({ module: 'science', id: r.id });
    } catch (e) { app.setState({ error: e.message }); }
  };
  return html`<div style=${{ display: 'flex', flexDirection: 'column', gap: 20 }}>
    ${data.left.groups.length === 0 && html`<${Empty} text="no notebooks in root" />`}
    ${data.left.groups.map((g) => html`<div key=${g.label} style=${{ display: 'flex', flexDirection: 'column', gap: 2 }}>
      <${GroupHeader} label=${g.label} count=${g.count} />
      ${g.rows.map((r) => html`<${Row} key=${r.id} row=${r} hue=${mod.hue} fmt=${fmt} selected=${!!sel && String(sel.id) === String(r.id)} onSelect=${() => app.select({ module: 'science', id: r.id })} />`)}
    </div>`)}
    <div style=${{ display: 'flex', alignItems: 'center', gap: 16, height: 32, padding: '0 12px', ...mono13, color: T.dim }}>${data.left.showing}
      <span class="ring" onClick=${create} style=${{ cursor: 'pointer', color: T.muted, padding: '3px 8px', borderRadius: 6 }}>new</span>
    </div>
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
    this.state = { live: {}, editing: null };   // live[index] = outputs streamed for a running cell · editing = {index, source}
    this.es = null;
  }

  componentDidMount() {
    this.es = new EventSource('/api/science/events');
    this.es.onmessage = (e) => this.onEvent(JSON.parse(e.data));
  }

  componentWillUnmount() {
    if (this.es) { this.es.close(); this.es = null; }
  }

  componentDidUpdate(prev) {
    const a = prev.app.state.sel, b = this.props.app.state.sel;
    if ((a && a.id) !== (b && b.id)) this.setState({ live: {}, editing: null });
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

  async act(verb, body) {
    const { app } = this.props;
    try {
      const r = await post(`/api/science/action/${verb}`, { id: app.state.item.id, ...body });
      app.setState({ error: null });
      return r;
    } catch (e) {
      app.setState({ error: e.message });
      return null;
    } finally {
      app.refresh();
    }
  }

  // Save the cell being edited if its text changed; optionally run it afterwards.
  async commit(run) {
    const { editing } = this.state;
    if (!editing) return;
    const cell = this.props.app.state.item.cells[editing.index];
    this.setState({ editing: null });
    if (cell && editing.source !== cell.source) await this.act('set_cell', { index: editing.index, source: editing.source });
    if (run && cell && cell.type === 'code') await this.act('run', { index: editing.index });
  }

  render({ app, mod }, { live, editing }) {
    const item = app.state.item;
    const hue = mod.hue;
    if (!item) return html`<div style=${{ ...mono13, color: T.dim }}>loading…</div>`;
    if (item.error) return html`<div style=${{ ...mono13, color: RED }}>${item.error}</div>`;
    const act = (verb, body) => this.act(verb, body);
    const runAll = async () => {
      await this.commit(false);
      for (const c of item.cells) if (c.type === 'code') await act('run', { index: c.index });
    };
    const k = item.kernel;
    const label = item.kind === 'py' ? 'module' : k ? `python3 · ${k.state}` : 'python3 · no kernel';
    const ref = editing ? `cell ${editing.index}` : `${item.cells.length} cells`;
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
        <${Button} label="+ cell" onClick=${() => act('insert_cell', { after: item.cells.length - 1 })} />
        <${Button} label="Send to session" right=${true} onClick=${() => app.sendToSession(`About the selected notebook (science ${item.id}, ${ref}):\n\n`)} />
      </div>`}
      ${item.kind === 'py'
        ? html`<pre style=${{ margin: 0, background: T.panel, borderRadius: 6, padding: '10px 14px', whiteSpace: 'pre-wrap', wordBreak: 'break-word', ...mono13, lineHeight: 1.6 }}>${item.source}</pre>`
        : item.cells.map((c) => html`<${Cell} key=${c.index} cell=${c} live=${live[c.index]} hue=${hue}
            editing=${editing && editing.index === c.index ? editing : null}
            onRun=${() => act('run', { index: c.index })}
            onEdit=${() => { if (!editing) this.setState({ editing: { index: c.index, source: c.source } }); }}
            onInput=${(source) => this.setState({ editing: { index: c.index, source } })}
            onCommit=${(run) => this.commit(run)}
            onCancel=${() => this.setState({ editing: null })}
            onInsert=${(type) => act('insert_cell', { after: c.index, type })}
            onDelete=${() => { if (window.confirm('Delete this cell?')) { this.setState({ editing: null }); act('delete_cell', { index: c.index }); } }} />`)}
    </div>`;
  }
}

// One cell: [n] gutter runs it · click the source to edit · Ctrl+Enter saves and runs · Esc cancels · blur saves.
function Cell({ cell, live, hue, editing, onRun, onEdit, onInput, onCommit, onCancel, onInsert, onDelete }) {
  const code = cell.type === 'code';
  const running = cell.running || live !== undefined;
  const outputs = live !== undefined ? live : cell.outputs;
  const n = running ? '[*]' : cell.execution_count != null ? `[${cell.execution_count}]` : '[ ]';
  const box = { margin: 0, background: code ? T.panel : 'transparent', borderRadius: 6, padding: '10px 14px', whiteSpace: 'pre-wrap', wordBreak: 'break-word', fontFamily: 'inherit', fontSize: 'inherit', lineHeight: 'inherit', color: code ? T.text : T.muted };
  const chip = (label, onClick, color) => html`<span class="ring" onMouseDown=${keep} onClick=${onClick} style=${{ padding: '2px 8px', borderRadius: 6, cursor: 'pointer', color: color || T.muted }}>${label}</span>`;
  const source = editing
    ? html`<textarea value=${editing.source} rows=${Math.max(2, editing.source.split('\n').length + 1)} spellcheck="false" autofocus
        onInput=${(e) => onInput(e.target.value)}
        onKeyDown=${(e) => { if (e.key === 'Enter' && (e.ctrlKey || e.metaKey)) { e.preventDefault(); onCommit(true); } else if (e.key === 'Escape') { e.preventDefault(); onCancel(); } }}
        onBlur=${() => onCommit(false)}
        style=${{ ...box, width: '100%', resize: 'none', border: 0, background: T.raised, color: T.text, '--hue': hue }} />`
    : html`<pre onClick=${onEdit} title="click to edit" style=${{ ...box, cursor: 'text', minHeight: 40 }}>${cell.source || ' '}</pre>`;
  return html`<div style=${{ display: 'grid', gridTemplateColumns: '48px minmax(0,1fr)', gap: '0 12px', ...mono13, lineHeight: 1.6 }}>
    <span class=${code ? 'bright-hover' : ''} title=${code ? 'run' : ''} onClick=${code ? onRun : null}
      style=${{ color: running ? hue : T.dim, paddingTop: 10, cursor: code ? 'pointer' : 'default', userSelect: 'none' }}>${code ? n : ''}</span>
    <div style=${{ display: 'flex', flexDirection: 'column', gap: 10, minWidth: 0 }}>
      ${source}
      ${editing && html`<div style=${{ display: 'flex', alignItems: 'center', gap: 8, height: 28, color: T.dim }}>
        ${code && chip('run', () => onCommit(true))}
        ${chip('+ code', () => onInsert('code'))}
        ${chip('+ markdown', () => onInsert('markdown'))}
        ${chip('delete', onDelete, RED)}
        <span style=${{ marginLeft: 'auto' }}>ctrl+enter runs · esc cancels</span>
      </div>`}
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
