// Science: LEFT = the root's directory tree, a running file in the hue, `+` creating a script, notebook or folder into the open folder · MIDDLE = a notebook as a Lab-style editor (command and edit modes, the JupyterLab keys, every change written straight to the file) or a script highlighted whole with its last run's output, and the owner's schedule for either.
import { Component } from '../vendor/preact.mjs';
import { html, T, meta13, nums, code13, Row, Icon, Button, Empty, Plus, input, interval, stamp } from '../rows.js';
import { get, post } from '../api.js';
import hljs from '../vendor/highlight/core.min.js';
import python from '../vendor/highlight/python.min.js';

hljs.registerLanguage('python', python);

const RED = '#cf7b7b';
const CHORD_MS = 1000;   // JupyterLab's window for the second key of d,d · i,i · 0,0
const INDENT = '    ';
const SCRIPT = 'script';  // the `cell` every script event carries
const trimNl = (s) => s.replace(/^\n+/, '').replace(/\n+$/, '');   // Lab trims both halves of a split
// VS Code Dark Modern's Python colours, on the artboard's panel.
const CODE_CSS = '.hl{color:#cccccc}.hl .hljs-keyword,.hl .hljs-literal{color:#569cd6}.hl .hljs-built_in,.hl .hljs-title.function_,.hl .hljs-meta{color:#dcdcaa}.hl .hljs-title.class_,.hl .hljs-type{color:#4ec9b0}.hl .hljs-string{color:#ce9178}.hl .hljs-number{color:#b5cea8}.hl .hljs-comment{color:#6a9955}.hl .hljs-params,.hl .hljs-variable,.hl .hljs-property{color:#9cdcfe}.hl .hljs-operator{color:#d4d4d4}';

const open = new Set();   // expanded folders, page-local
let folder = '';          // the folder `+` creates into; '' is the root
const creator = { open: false, name: '' };   // the `+` box, page-local

export async function load() {
  return { left: await get('/api/science/left') };
}

// `name.py` is a script, `name.ipynb` a notebook, anything else a folder, all under the open folder.
async function create(app) {
  const name = creator.name.trim().replace(/\/+$/, '');
  if (!name) return;
  const kind = name.endsWith('.py') ? 'py' : name.endsWith('.ipynb') ? 'ipynb' : 'folder';
  try {
    const r = await post('/api/science/action/new', { path: folder ? `${folder}/${name}` : name, kind });
    creator.name = ''; creator.open = false;
    app.setState({ error: null });
    if (kind === 'folder') { open.add(r.id); folder = r.id; }
    await app.refresh();
    if (kind !== 'folder') app.select({ module: 'science', id: r.id });
  } catch (e) { app.setState({ error: e.message }); }
}

export function Left({ app, data, mod }) {
  const sel = app.state.sel;
  const toggle = (id) => { if (open.has(id)) open.delete(id); else open.add(id); folder = id; app.setState({}); };
  return html`<div style=${{ display: 'flex', flexDirection: 'column', gap: 4 }}>
    <div style=${{ display: 'flex', alignItems: 'center', gap: 8, padding: '0 4px 8px' }}>
      ${creator.open && html`<input autofocus placeholder="name.py · name.ipynb · folder" value=${creator.name} onInput=${(e) => { creator.name = e.target.value; }}
        onKeyDown=${(e) => { if (e.key === 'Enter') create(app); if (e.key === 'Escape') { creator.open = false; app.forceUpdate(); } }}
        style=${input(mod.hue, { flex: 1, minWidth: 0, height: 36, fontSize: 15, background: T.raised })} />`}
      <span style=${{ marginLeft: 'auto' }}><${Plus} title="new file or folder" active=${creator.open} onClick=${() => { creator.open = !creator.open; app.forceUpdate(); }} /></span>
    </div>
    ${data.left.tree.length === 0 && html`<${Empty} text="nothing in root" />`}
    ${data.left.tree.map((n) => html`<${Node} key=${n.id} node=${n} depth=${0} sel=${sel} hue=${mod.hue} onToggle=${toggle} onSelect=${(id) => app.select({ module: 'science', id })} />`)}
  </div>`;
}

// A folder row opens on click and becomes the target of `+`; a file row is the shared Row, in the hue while it runs, indented under it.
function Node({ node, depth, sel, hue, onToggle, onSelect }) {
  const pad = { paddingLeft: depth * 16 };
  if (node.kind !== 'dir') {
    const row = { id: node.id, text: node.name, live: node.live };
    return html`<div style=${pad}><${Row} row=${row} hue=${hue} selected=${!!sel && String(sel.id) === node.id} onSelect=${() => onSelect(node.id)} /></div>`;
  }
  const isOpen = open.has(node.id), current = folder === node.id;
  return html`<div style=${{ display: 'flex', flexDirection: 'column', gap: 4 }}>
    <div style=${pad}>
      <div class="row" onClick=${() => onToggle(node.id)} style=${{ display: 'flex', alignItems: 'center', gap: 12, height: 36, padding: '0 12px', borderRadius: 6, cursor: 'pointer', color: current ? T.text : T.muted }}>
        <span style=${{ width: 6, flex: 'none', color: T.dim }}>${isOpen ? '▾' : '▸'}</span>
        <span style=${{ minWidth: 0, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>${node.name}/</span>
      </div>
    </div>
    ${isOpen && node.children.map((c) => html`<${Node} key=${c.id} node=${c} depth=${depth + 1} sel=${sel} hue=${hue} onToggle=${onToggle} onSelect=${onSelect} />`)}
  </div>`;
}

// Artboard: MIDDLE shows nothing until a file is picked.
export function Middle(props) {
  if (!props.app.state.sel) return null;
  return html`<${Notebook} ...${props} />`;
}

// The notebook. Command mode: the notebook element holds focus and keys act on cells. Edit mode: a cell's editor holds focus. A script uses the same frame with one run.
class Notebook extends Component {
  constructor(props) {
    super(props);
    this.state = { live: {}, sel: { anchor: 0, head: 0 }, mode: 'command' };   // live[cell id] = outputs streamed for a running cell (or the script) · sel = selected span, head is the active cell
    this.nbId = props.app.state.sel && props.app.state.sel.id;
    this.hadItem = false;
    this.draft = null;      // {index, source} of the cell being typed in; an instance field so a blur after a structural op cannot resave a stale index
    this.saving = null;     // the set_cell in flight from the last blur; every op waits for it
    this.history = [];      // {a, b, ha, hb}: cells and head before and after each structural op, for z
    this.future = [];       // undone entries, for shift+z
    this.clip = [];         // cut or copied cells
    this.pending = null;    // {key, at}: first key of a two-key chord
    this.areas = {};        // index -> textarea
    this.box = null;        // the notebook element
    this.es = null;
  }

  componentDidMount() {
    this.es = new EventSource('/api/science/events');
    this.es.onmessage = (e) => this.onEvent(JSON.parse(e.data));
  }

  componentWillUnmount() {
    if (this.es) { this.es.close(); this.es = null; }
  }

  componentDidUpdate() {
    const { sel, item } = this.props.app.state;
    const id = sel && sel.id;
    if (id !== this.nbId) {
      this.nbId = id;
      this.draft = null; this.saving = null; this.history = []; this.future = []; this.pending = null;
      this.setState({ live: {}, sel: { anchor: 0, head: 0 }, mode: 'command' });
    }
    const has = !!(item && !item.error);
    if (has && !this.hadItem && this.box) this.box.focus({ preventScroll: true });
    this.hadItem = has;
  }

  onEvent(ev) {
    const sel = this.props.app.state.sel;
    if (!sel || ev.path !== String(sel.id)) return;
    const live = { ...this.state.live };
    if (ev.event === 'started') live[ev.cell] = [];
    else if (ev.event === 'output') live[ev.cell] = [...(live[ev.cell] || []), ev.output];
    else if (ev.event === 'done' || ev.event === 'error') { delete live[ev.cell]; this.props.app.refresh(); }
    this.setState({ live });
  }

  cells() {
    const item = this.props.app.state.item;
    return item && item.cells ? item.cells : [];
  }

  clamp(i) { return Math.max(0, Math.min(i, this.cells().length - 1)); }
  head() { return this.clamp(this.state.sel.head); }

  range() {
    const a = this.clamp(this.state.sel.anchor), b = this.head();
    return [Math.min(a, b), Math.max(a, b)];
  }

  // The cell list as the owner sees it: the file's cells with the draft typed over.
  current() {
    const cells = this.cells().map((c) => ({ id: c.id, type: c.type, source: c.source }));
    const d = this.draft;
    if (d && cells[d.index]) cells[d.index] = { ...cells[d.index], source: d.source };
    return cells;
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
    }
  }

  reload() {
    const { app } = this.props;
    return app.state.sel ? app.loadItem(app.state.sel) : Promise.resolve();
  }

  // Save the cell being typed in if its text changed. Runs on blur; ops wait for it through this.saving.
  commit() {
    const d = this.draft;
    this.draft = null;
    this.setState({ mode: 'command' });
    const cell = d && this.cells()[d.index];
    if (!cell || d.source === cell.source) return this.saving;
    this.saving = (async () => { if (await this.act('set_cell', { index: d.index, source: d.source })) await this.reload(); })();
    return this.saving;
  }

  settle() { return this.draft ? this.commit() : this.saving; }

  // Make `head` the active cell. Edit mode focuses its editor (caret at `caret` if given); command mode focuses the notebook.
  select(head, mode = 'command', caret, anchor = head) {
    head = this.clamp(head);
    anchor = this.clamp(anchor);
    this.setState({ sel: { anchor, head }, mode }, () => {
      const a = this.areas[head];
      if (mode === 'edit' && a) {
        a.focus({ preventScroll: true });
        if (caret != null) { const p = caret === 'end' ? a.value.length : caret; a.setSelectionRange(p, p); }
      } else if (this.box) this.box.focus({ preventScroll: true });
      if (a) a.closest('[data-cell]').scrollIntoView({ block: 'nearest' });
    });
  }

  focusCell(i) {
    const cell = this.cells()[i];
    if (!cell) return;
    if (!this.draft || this.draft.index !== i) this.draft = { index: i, source: cell.source };
    this.setState({ sel: { anchor: i, head: i }, mode: 'edit' });
  }

  typed(i, source) {
    this.draft = { index: i, source };
    this.setState({});
  }

  // One structural change: `edit` gets the current cells (draft included) and returns {cells, head, anchor?}, or null for nothing to do. Recorded for z.
  async op(edit, mode = 'command', caret) {
    await this.saving;
    const a = this.current(), ha = this.head();
    const r = edit(a.map((c) => ({ ...c })));
    if (!r) return;
    this.draft = null;
    this.future = [];
    const entry = { a, ha, b: null, hb: r.head };
    this.history.push(entry);
    await this.write(r.cells, r.head, mode, caret, r.anchor);
    entry.b = this.current();
  }

  async write(cells, head, mode, caret, anchor) {
    if (await this.act('set_cells', { cells })) await this.reload();
    this.select(head, mode, caret, anchor);
  }

  // Cells of `from`, but a cell typed in since the op keeps its text: z undoes the cell operation, not the typing.
  restore(from, to) {
    const now = new Map(this.current().map((c) => [c.id, c.source]));
    const then = new Map(to.map((c) => [c.id, c.source]));
    return from.map((c) => (c.id && now.has(c.id) && now.get(c.id) !== then.get(c.id) ? { ...c, source: now.get(c.id) } : c));
  }

  async undo() {
    await this.saving;
    const e = this.history.pop();
    if (!e) return;
    const cells = this.restore(e.a, e.b);
    this.draft = null;
    this.future.push(e);
    await this.write(cells, e.ha);
    e.a = this.current();
  }

  async redo() {
    await this.saving;
    const e = this.future.pop();
    if (!e) return;
    const cells = this.restore(e.b, e.a);
    this.draft = null;
    this.history.push(e);
    await this.write(cells, e.hb);
    e.b = this.current();
  }

  insert(at, type = 'code', mode = 'command') {
    return this.op((cells) => { cells.splice(at, 0, { type, source: '' }); return { cells, head: at }; }, mode, 0);
  }

  remove(cut) {
    return this.op((cells) => {
      const [a, b] = this.range();
      const gone = cells.splice(a, b - a + 1);
      if (cut) this.clip = gone.map(({ type, source }) => ({ type, source }));
      if (!cells.length) cells.push({ type: 'code', source: '' });
      return { cells, head: Math.min(a, cells.length - 1) };
    });
  }

  copy() {
    const [a, b] = this.range();
    this.clip = this.current().slice(a, b + 1).map(({ type, source }) => ({ type, source }));
  }

  paste(above) {
    if (!this.clip.length) return;
    return this.op((cells) => {
      const [a, b] = this.range();
      const at = above ? a : b + 1;
      cells.splice(at, 0, ...this.clip.map((c) => ({ ...c })));
      return { cells, head: at + this.clip.length - 1 };
    });
  }

  setType(type) {
    return this.op((cells) => {
      const [a, b] = this.range();
      if (cells.slice(a, b + 1).every((c) => c.type === type)) return null;
      for (let i = a; i <= b; i++) cells[i] = { ...cells[i], type };
      return { cells, head: this.head(), anchor: this.state.sel.anchor };
    });
  }

  heading(level) {
    return this.op((cells) => {
      const [a, b] = this.range();
      for (let i = a; i <= b; i++) cells[i] = { ...cells[i], type: 'markdown', source: `${'#'.repeat(level)} ${cells[i].source.replace(/^#+\s*/, '')}` };
      return { cells, head: this.head(), anchor: this.state.sel.anchor };
    });
  }

  split(i, at) {
    return this.op((cells) => {
      const c = cells[i];
      if (!c) return null;
      // The tail keeps the id, so the outputs stay with it, as in Lab.
      cells.splice(i, 1, { type: c.type, source: trimNl(c.source.slice(0, at)) }, { ...c, source: trimNl(c.source.slice(at)) });
      return { cells, head: i + 1 };
    }, this.state.mode, 0);
  }

  merge() {
    return this.op((cells) => {
      let [a, b] = this.range();
      if (a === b) b = a + 1;
      if (b >= cells.length) return null;
      const merged = { type: cells[this.head()].type, source: cells.slice(a, b + 1).map((c) => c.source).join('\n\n') };   // a new cell: Lab drops the outputs
      cells.splice(a, b - a + 1, merged);
      return { cells, head: a };
    });
  }

  move(dir) {
    return this.op((cells) => {
      const [a, b] = this.range();
      if (a + dir < 0 || b + dir >= cells.length) return null;
      const block = cells.splice(a, b - a + 1);
      cells.splice(a + dir, 0, ...block);
      return { cells, head: this.head() + dir, anchor: this.clamp(this.state.sel.anchor) + dir };
    });
  }

  // advance: 'next' (shift+enter) · 'insert' (alt+enter) · undefined (ctrl+enter). Only code cells run; every kind advances.
  async run(indices, advance) {
    await this.settle();
    const cells = this.cells();
    for (const i of indices) if (cells[i] && cells[i].type === 'code') await this.act('run', { index: i });
    const last = Math.max(...indices);
    if (advance === 'insert' || (advance === 'next' && last + 1 >= cells.length)) return this.insert(last + 1, 'code', 'edit');
    this.select(advance === 'next' ? last + 1 : this.head(), 'command');
  }

  // The script as one run; its output streams in under `live.script` and lands in the item's `last` when done.
  async runScript() {
    if (await this.act('run')) this.setState({ live: { ...this.state.live, [SCRIPT]: [] } });
  }

  async kernel(verb) {
    const item = this.props.app.state.item;
    if (item.kind === 'ipynb' && !item.kernel) return;
    if (await this.act(verb)) this.props.app.refresh();
  }

  async schedule() {
    const every = window.prompt('Run every (30m, 6h, 1d)', '1d');
    if (!every) return;
    const at = window.prompt('First run at HH:MM local (blank: one interval from now)', '');
    if (at === null) return;
    if (await this.act('schedule', { every: every.trim(), at: at.trim() || null })) this.reload();
  }

  async unschedule() {
    if (await this.act('unschedule')) this.reload();
  }

  chord(key, fire) {
    const p = this.pending;
    this.pending = null;
    if (p && p.key === key && Date.now() - p.at < CHORD_MS) fire();
    else this.pending = { key, at: Date.now() };
  }

  key(e) {
    if (this.props.app.state.item.kind !== 'ipynb') return;
    if (e.target.tagName === 'TEXTAREA') this.editKey(e, +e.target.dataset.index);
    else this.commandKey(e);
  }

  commandKey(e) {
    const k = e.key.length === 1 ? e.key.toLowerCase() : e.key;
    const sh = e.shiftKey, mod = e.ctrlKey || e.metaKey;
    const head = this.head(), n = this.cells().length;
    const [a, b] = this.range();
    const span = Array.from({ length: b - a + 1 }, (_, j) => a + j);
    const go = (to, extend) => this.select(to, 'command', undefined, extend ? this.state.sel.anchor : undefined);
    if (!(k.length === 1 && 'di0'.includes(k))) this.pending = null;
    let done = true;
    if (k === 'Enter') {
      if (e.altKey) this.run([head], 'insert');
      else if (mod) this.run(span);
      else if (sh) this.run(span, 'next');
      else this.select(head, 'edit');
    }
    else if (mod && sh && (k === 'ArrowUp' || k === 'ArrowDown')) this.move(k === 'ArrowUp' ? -1 : 1);
    else if (mod && k === 'a') this.select(n - 1, 'command', undefined, 0);
    else if (mod && (k === 's' || k === 'm')) {}   // saved already · already command mode
    else if (mod || e.altKey) done = false;
    else if (k === 'ArrowUp' || k === 'k') go(head - 1, sh);
    else if (k === 'ArrowDown' || k === 'j') go(head + 1, sh);
    else if (k === 'a') this.insert(head);
    else if (k === 'b') this.insert(head + 1);
    else if (k === 'x') this.remove(true);
    else if (k === 'c') this.copy();
    else if (k === 'v') this.paste(sh);
    else if (k === 'z') { if (sh) this.redo(); else this.undo(); }
    else if (k === 'y') this.setType('code');
    else if (k === 'm') { if (sh) this.merge(); else this.setType('markdown'); }
    else if (k === 'r') this.setType('raw');
    else if (k >= '1' && k <= '6') this.heading(+k);
    else if (k === 'd') this.chord('d', () => this.remove(false));
    else if (k === 'i') this.chord('i', () => this.kernel('interrupt'));
    else if (k === '0') this.chord('0', () => this.kernel('restart'));
    else done = false;
    if (done) e.preventDefault();
  }

  editKey(e, i) {
    const t = e.target, k = e.key.length === 1 ? e.key.toLowerCase() : e.key;
    const sh = e.shiftKey, mod = e.ctrlKey || e.metaKey, plain = !sh && !mod && !e.altKey;
    const cells = this.cells();
    let done = true;
    if (k === 'Escape' || (mod && k === 'm')) this.select(i, 'command');
    else if (k === 'Enter' && (sh || mod || e.altKey)) this.run([i], e.altKey ? 'insert' : sh ? 'next' : undefined);
    else if (mod && sh && (k === '-' || k === '_')) this.split(i, t.selectionStart);
    else if (mod && k === '/') { if (cells[i].type === 'code') this.comment(t, i); }
    else if (k === 'Tab' || (mod && (k === ']' || k === '['))) this.indent(t, i, sh || k === '[' ? -1 : 1);
    else if (mod && k === 's') {}
    else if (plain && k === 'ArrowUp' && i > 0 && !t.value.slice(0, t.selectionStart).includes('\n')) this.select(i - 1, 'edit', 'end');
    else if (plain && k === 'ArrowDown' && i < cells.length - 1 && !t.value.slice(t.selectionEnd).includes('\n')) this.select(i + 1, 'edit', 0);
    else done = false;
    if (done) e.preventDefault();
  }

  comment(t, i) {
    editLines(t, (lines) => {
      const code = lines.filter((l) => l.trim());
      if (code.length && code.every((l) => /^\s*#/.test(l))) return lines.map((l) => l.replace(/^(\s*)#\s?/, '$1'));
      const col = code.length ? Math.min(...code.map((l) => l.match(/^\s*/)[0].length)) : 0;
      return lines.map((l) => (l.trim() ? `${l.slice(0, col)}# ${l.slice(col)}` : l));
    });
    this.typed(i, t.value);
  }

  indent(t, i, dir) {
    if (dir > 0 && t.selectionStart === t.selectionEnd) {
      if (!document.execCommand('insertText', false, INDENT)) t.setRangeText(INDENT, t.selectionStart, t.selectionEnd, 'end');
    } else editLines(t, (lines) => lines.map((l) => (dir > 0 ? INDENT + l : l.replace(/^ {1,4}/, ''))));
    this.typed(i, t.value);
  }

  render({ app, mod, fmt }, { live }) {
    const item = app.state.item;
    const hue = mod.hue;
    if (!item) return html`<div style=${{ ...meta13, color: T.dim }}>loading…</div>`;
    if (item.error) return html`<div style=${{ ...meta13, color: RED }}>${item.error}</div>`;
    const py = item.kind === 'py';
    const k = item.kernel;
    const running = py && (item.running || live[SCRIPT] !== undefined);
    const label = py ? `script · ${running ? 'running' : 'idle'}` : k ? `python3 · ${k.state}` : 'python3 · no kernel';
    const n = item.cells.length, head = this.head(), [a, b] = this.range();
    const d = this.draft;
    const s = item.schedule;
    const chip = (text, onClick) => html`<span class="ring" onClick=${onClick} style=${{ cursor: 'pointer', color: T.muted, padding: '2px 8px', borderRadius: 6 }}>${text}</span>`;
    return html`<div ref=${(el) => { this.box = el; }} tabIndex="0" onKeyDown=${(e) => this.key(e)} style=${{ display: 'flex', flexDirection: 'column', gap: 24, outline: 'none' }}>
      <style>${'.nb-html table{border-collapse:collapse;font-family:inherit}.nb-html th,.nb-html td{height:28px;padding:0 16px 0 0;text-align:left;border-top:1px solid rgba(230,231,234,.08);font-weight:400}.nb-html th{color:#5f636c}' + CODE_CSS}</style>
      <div style=${{ display: 'flex', alignItems: 'center', gap: 12, ...meta13 }}>
        <span style=${{ display: 'grid', placeItems: 'center', width: 16, height: 16, color: hue }}><${Icon} svg=${mod.icon} /></span>
        <span style=${{ color: T.text }}>${item.text}</span>
        <span style=${{ color: T.dim }}>${label}</span>
        <span class="bright-hover" onClick=${() => app.select(null)} style=${{ marginLeft: 'auto', cursor: 'pointer', color: T.dim, padding: '0 4px', lineHeight: 1 }}>×</span>
      </div>
      <div style=${{ display: 'flex', alignItems: 'center', gap: 8 }}>
        ${py
          ? html`${running
              ? html`<${Button} label="Interrupt" onClick=${() => this.kernel('interrupt')} />`
              : html`<${Button} label="Run" primary=${true} hue=${hue} onClick=${() => this.runScript()} />`}`
          : html`<${Button} label="Run all" primary=${true} hue=${hue} onClick=${() => this.run(item.cells.map((c) => c.index))} />
            ${k && html`<${Button} label="Interrupt" onClick=${() => this.kernel('interrupt')} />`}
            ${k && html`<${Button} label="Restart" onClick=${() => this.kernel('restart')} />`}
            ${k && html`<${Button} label="Shut down" onClick=${() => this.kernel('shutdown')} />`}
            <${Plus} title="add cell" onClick=${() => this.insert(n)} />`}
        <${Button} label="Send to session" right=${true} onClick=${() => app.sendToSession(py ? `About the selected script (science ${item.id}):\n\n` : `About the selected notebook (science ${item.id}, cell ${head} of ${n}):\n\n`)} />
      </div>
      <div style=${{ display: 'flex', alignItems: 'center', gap: 12, ...meta13, ...nums, color: T.dim }}>
        ${s
          ? html`<span>every ${interval(s.every_seconds)}${s.at ? ` at ${s.at}` : ''} · next ${stamp(s.next_run, fmt)} · last ${s.last_status ? `${s.last_status} ${stamp(s.last_run, fmt)}` : 'never'}</span>${chip('unschedule', () => this.unschedule())}`
          : chip('schedule', () => this.schedule())}
      </div>
      ${py
        ? html`<${Script} source=${item.source} last=${item.last} live=${live[SCRIPT]} fmt=${fmt} />`
        : item.cells.map((c, i) => html`<${Cell} key=${c.id || i} cell=${c} i=${i} hue=${hue} live=${live[c.id]}
            source=${d && d.index === i ? d.source : c.source}
            active=${i === head} selected=${i >= a && i <= b}
            area=${(el) => { this.areas[i] = el; }}
            onFocus=${() => this.focusCell(i)} onBlur=${() => this.commit()}
            onInput=${(v) => this.typed(i, v)} onPick=${() => this.select(i, 'command')} />`)}
    </div>`;
  }
}

// One cell: a left bar marks the selection · the gutter or the margin picks it · the source is always an editor. Nothing under a cell depends on the selection, so the list never shifts.
function Cell({ cell, i, hue, live, source, active, selected, area, onFocus, onBlur, onInput, onPick }) {
  const code = cell.type === 'code';
  const running = cell.running || live !== undefined;
  const outputs = live !== undefined ? live : cell.outputs;
  const n = running ? '[*]' : cell.execution_count != null ? `[${cell.execution_count}]` : '[ ]';
  const bar = active ? hue : selected ? T.dim : 'transparent';
  return html`<div data-cell onMouseDown=${(e) => { if (e.target.tagName !== 'TEXTAREA') onPick(); }}
      style=${{ display: 'grid', gridTemplateColumns: '40px minmax(0,1fr)', gap: '0 12px', paddingLeft: 8, boxShadow: `inset 2px 0 0 ${bar}`, ...code13, lineHeight: 1.6 }}>
    <span style=${{ color: running ? hue : T.dim, paddingTop: 10, userSelect: 'none', cursor: 'default' }}>${code ? n : ''}</span>
    <div style=${{ display: 'flex', flexDirection: 'column', gap: 10, minWidth: 0 }}>
      <textarea ref=${area} data-index=${i} value=${source} rows=${source.split('\n').length} spellcheck=${false}
        onFocus=${onFocus} onBlur=${onBlur} onInput=${(e) => onInput(e.target.value)}
        style=${{ display: 'block', width: '100%', minHeight: 40, margin: 0, padding: '10px 14px', border: 0, borderRadius: 6, resize: 'none', fieldSizing: 'content', whiteSpace: 'pre-wrap', wordBreak: 'break-word', fontFamily: 'inherit', fontSize: 'inherit', lineHeight: 'inherit', background: code ? T.panel : 'transparent', color: code ? T.text : cell.type === 'markdown' ? T.muted : T.dim, '--hue': hue }} />
      ${outputs.map((o, j) => html`<${Output} key=${j} o=${o} />`)}
    </div>
  </div>`;
}

// The whole script, highlighted, with a line-number gutter; under it the run streaming now, or the last run's status and output.
function Script({ source, last, live, fmt }) {
  const lines = source.split('\n');
  if (lines.length > 1 && lines[lines.length - 1] === '') lines.pop();
  const code = hljs.highlight(source, { language: 'python' }).value;
  const text = live !== undefined ? live.map((o) => o.text).join('') : last ? last.output : null;
  return html`<div style=${{ display: 'flex', flexDirection: 'column', gap: 10 }}>
    <div style=${{ display: 'grid', gridTemplateColumns: 'auto minmax(0,1fr)', background: T.panel, borderRadius: 6, ...code13, lineHeight: 1.6, overflowX: 'auto' }}>
      <pre style=${{ margin: 0, padding: '10px 0 10px 14px', color: T.dim, textAlign: 'right', userSelect: 'none', fontFamily: 'inherit' }}>${lines.map((_, i) => i + 1).join('\n')}</pre>
      <pre class="hl" style=${{ margin: 0, padding: '10px 14px', fontFamily: 'inherit' }} dangerouslySetInnerHTML=${{ __html: code }} />
    </div>
    ${last && live === undefined && html`<div style=${{ ...meta13, ...nums, color: last.status === 'failed' ? RED : T.dim, padding: '0 14px' }}>${last.status} · ${stamp(last.started_at, fmt)}${last.exit_code != null ? ` · exit ${last.exit_code}` : ''}</div>`}
    ${text ? html`<${Output} o=${{ kind: 'stream', text }} />` : null}
  </div>`;
}

// Replace the whole lines under the selection through the browser's own insert, so ctrl+z still undoes it.
function editLines(t, fn) {
  const v = t.value, s = t.selectionStart, e = t.selectionEnd;
  const from = v.lastIndexOf('\n', s - 1) + 1;
  let to = v.indexOf('\n', e > s && v[e - 1] === '\n' ? e - 1 : e);
  if (to < 0) to = v.length;
  const out = fn(v.slice(from, to).split('\n')).join('\n');
  t.setSelectionRange(from, to);
  if (!document.execCommand('insertText', false, out)) t.setRangeText(out, from, to, 'end');
  if (s === e) { const p = Math.max(from, Math.min(from + out.length, s + out.length - (to - from))); t.setSelectionRange(p, p); }
  else t.setSelectionRange(from, from + out.length);
}

function Output({ o }) {
  const pad = { padding: '2px 14px 6px' };
  if (o.kind === 'image') return html`<div style=${pad}><img src=${`data:image/png;base64,${o.png}`} style=${{ maxWidth: '100%', borderRadius: 6 }} /></div>`;
  if (o.kind === 'html') return html`<div class="nb-html" style=${{ ...pad, color: T.muted, overflowX: 'auto' }} dangerouslySetInnerHTML=${{ __html: o.html }} />`;
  if (o.kind === 'error') return html`<pre style=${{ ...pad, margin: 0, whiteSpace: 'pre-wrap', wordBreak: 'break-word', color: RED, fontFamily: 'inherit' }}>${o.traceback || `${o.ename}: ${o.evalue}`}</pre>`;
  return html`<pre style=${{ ...pad, margin: 0, whiteSpace: 'pre-wrap', wordBreak: 'break-word', color: T.muted, fontFamily: 'inherit' }}>${o.text}</pre>`;
}
