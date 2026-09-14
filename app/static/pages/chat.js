// Chat: LEFT = every conversation by day · MIDDLE = the conversation, composer pinned below · RIGHT = its folder.
import { Component } from '../vendor/preact.mjs';
import { html, T, mono13, Row, GroupHeader, Search, Icon, Empty, bytes, stamp, clock, dayLabel, TextArea } from '../rows.js';
import { get, post } from '../api.js';
import { Markdown } from '../md.js';

const RED = '#cf7b7b';
const drafts = {};   // conversation id (or 'blank') -> {draft, pending}: survives the remount a selection change causes
const plural = (n, word) => `${n} ${word}${n === 1 ? '' : 's'}`;

export async function load(app) {
  const q = new URLSearchParams({ query: app.state.query, page: String(app.state.more) });
  return { left: await get(`/api/chat/left?${q}`) };
}

export function meta(app) {
  const l = app.state.data && app.state.data.left;
  return l ? `${l.showing.split(' / ')[1]} conversations` : '';
}

export function Left({ app, data, mod, fmt }) {
  const sel = app.state.sel;
  const rerun = (patch) => app.setState(patch, () => app.refresh());
  return html`<div style=${{ display: 'flex', flexDirection: 'column', gap: 20 }}>
    <${Search} value=${app.state.query} hue=${mod.hue} onInput=${(v) => rerun({ query: v, more: 0 })} />
    ${data.left.groups.length === 0 && html`<${Empty} text=${app.state.query ? 'no matches' : 'no conversations yet'} />`}
    ${data.left.groups.map((g) => html`<div key=${g.label} style=${{ display: 'flex', flexDirection: 'column', gap: 2 }}>
      <${GroupHeader} label=${g.label} count=${g.count} />
      ${g.rows.map((r) => html`<${Row} key=${r.id} row=${r} hue=${mod.hue} fmt=${fmt} selected=${!!sel && String(sel.id) === String(r.id)} onSelect=${() => app.select({ module: 'chat', id: r.id })} />`)}
    </div>`)}
    <div style=${{ display: 'flex', alignItems: 'center', gap: 16, height: 32, padding: '0 12px', ...mono13, color: T.dim }}>${data.left.showing}
      ${data.left.more && html`<span class="ring" onClick=${() => rerun({ more: app.state.more + 1 })} style=${{ cursor: 'pointer', color: T.muted, padding: '3px 8px', borderRadius: 6 }}>more</span>`}
      <span class="ring" onClick=${() => app.select(null)} style=${{ marginLeft: 'auto', cursor: 'pointer', color: T.muted, padding: '3px 8px', borderRadius: 6 }}>new</span>
    </div>
  </div>`;
}

export function Middle(props) {
  const sel = props.app.state.sel;
  const id = sel ? String(sel.id) : null;
  return html`<${Conversation} key=${id || 'blank'} ...${props} id=${id} />`;
}

export function Right({ app, data, mod, fmt }) {
  const sel = app.state.sel;
  return html`<div style=${{ minWidth: 0, minHeight: 0, overflow: 'auto', display: 'flex', flexDirection: 'column', gap: 14, background: T.panel, borderRadius: 6, padding: '16px 12px 12px' }}>
    ${sel
      ? html`<${Files} key=${sel.id} id=${String(sel.id)} data=${data} hue=${mod.hue} fmt=${fmt} />`
      : html`<div style=${{ ...mono13, color: T.dim, padding: '0 4px' }}>pick or start a conversation</div>`}
  </div>`;
}

async function upload(id, file) {
  const fd = new FormData();
  fd.append('file', file, file.name);
  const r = await fetch(`/api/chat/upload/${id}`, { method: 'POST', body: fd });
  const data = await r.json().catch(() => null);
  if (!r.ok) throw new Error((data && data.detail) || r.statusText);
  return data;
}

// The conversation: its stored turns, then whatever the event stream adds. `id` null is the blank composer.
class Conversation extends Component {
  constructor(props) {
    super(props);
    const d = drafts[props.id || 'blank'] || { draft: '', pending: [] };
    this.state = { turns: [], title: '', tags: [], busy: false, partial: '', draft: d.draft, pending: d.pending, error: null, loading: !!props.id };
    this.es = null;
    this.toolIds = {};
  }

  componentDidMount() {
    if (this.props.id) this.open();
    else if (this.ta) this.ta.focus();
  }

  componentWillUnmount() {
    if (this.es) { this.es.close(); this.es = null; }
    drafts[this.props.id || 'blank'] = { draft: this.state.draft, pending: this.state.pending };
  }

  componentDidUpdate(prev, prevState) {
    if (this.end && (prevState.turns.length !== this.state.turns.length || prevState.partial !== this.state.partial)) this.end.scrollIntoView({ block: 'end' });
  }

  async open() {
    const { id } = this.props;
    this.es = new EventSource(`/api/chat/events/${id}`);
    this.es.onmessage = (e) => this.onEvent(JSON.parse(e.data));
    await this.reload();
    if (this.ta) this.ta.focus();
  }

  async reload() {
    try {
      const item = await get(`/api/chat/item/${this.props.id}`);
      this.toolIds = {};
      this.setState({ turns: item.turns, title: item.title, tags: item.tags, busy: item.busy, loading: false, error: null });
    } catch (e) {
      this.setState({ error: e.message, loading: false });
    }
  }

  onEvent(ev) {
    const turns = this.state.turns.slice();
    let { partial, busy } = this.state;
    if (ev.role === 'user') { turns.push({ role: 'user', text: ev.text, ts: ev.ts }); busy = true; }
    else if (ev.role === 'delta') partial += ev.text;
    else if (ev.role === 'model') { turns.push({ role: 'model', text: ev.text, ts: ev.ts }); partial = ''; }
    else if (ev.role === 'tool') { this.toolIds[ev.id] = turns.length; turns.push({ role: 'tool', tool: ev.tool, status: ev.status, ts: ev.ts }); partial = ''; }
    else if (ev.role === 'tool_result') { const i = this.toolIds[ev.id]; if (i !== undefined && turns[i]) turns[i] = { ...turns[i], status: ev.status }; }
    else if (ev.role === 'system') turns.push({ role: 'system', text: ev.text, ts: ev.ts });
    else if (ev.role === 'error') turns.push({ role: 'system', text: `error: ${ev.text}`, ts: ev.ts });
    else if (ev.role === 'idle') { this.setState({ busy: false, partial: '' }); this.reload(); this.props.app.refresh(); return; }
    else if (ev.role === 'tagged') { this.setState({ title: ev.title, tags: ev.tags }); this.props.app.refresh(); return; }
    else return;
    this.setState({ turns, partial, busy });
  }

  async send() {
    const text = this.state.draft.trim();
    if (!text || this.state.busy) return;
    const { app, id } = this.props;
    const files = this.state.pending;
    this.setState({ draft: '', pending: [], error: null, busy: true });
    try {
      const r = await post('/api/chat/send', { id, text, files });
      if (!id) { drafts.blank = { draft: '', pending: [] }; app.select({ module: 'chat', id: r.id }); }
    } catch (e) {
      this.setState({ error: e.message, draft: text, pending: files, busy: false });
    }
  }

  async attach(fileList) {
    const files = Array.from(fileList || []);
    if (!files.length) return;
    const { app } = this.props;
    let id = this.props.id;
    try {
      if (!id) id = (await post('/api/chat/new')).id;
      const names = [];
      for (const f of files) names.push((await upload(id, f)).name);
      if (id !== this.props.id) {
        drafts[id] = { draft: this.state.draft, pending: names };
        drafts.blank = { draft: '', pending: [] };
        app.select({ module: 'chat', id });
        return;
      }
      this.setState({ pending: [...this.state.pending, ...names], error: null });
      app.refresh();
    } catch (e) {
      this.setState({ error: e.message });
    }
  }

  async remove() {
    const { app, id } = this.props;
    if (!window.confirm(`Delete "${this.state.title}" and its files?`)) return;
    try {
      await post('/api/chat/delete', { id });
      delete drafts[id];
      app.select(null);
      app.refresh();
    } catch (e) {
      this.setState({ error: e.message });
    }
  }

  composer(hue) {
    const { busy, draft, pending } = this.state;
    const ring = 'inset 0 0 0 1px rgba(230,231,234,.14)';
    return html`<div onDragOver=${(e) => e.preventDefault()} onDrop=${(e) => { e.preventDefault(); this.attach(e.dataTransfer.files); }}
        style=${{ position: 'sticky', bottom: 0, background: T.ground, paddingTop: 12, display: 'flex', flexDirection: 'column', gap: 8 }}>
      ${pending.length > 0 && html`<div style=${{ display: 'flex', flexWrap: 'wrap', gap: 6, padding: '0 4px' }}>
        ${pending.map((n) => html`<span key=${n} style=${{ padding: '2px 8px', borderRadius: 6, fontSize: 13, color: T.muted, boxShadow: 'inset 0 0 0 1px rgba(230,231,234,.1)' }}>${n}
          <span onClick=${() => this.setState({ pending: pending.filter((p) => p !== n) })} style=${{ marginLeft: 6, cursor: 'pointer', color: T.dim }}>×</span></span>`)}
      </div>`}
      <${TextArea} taRef=${(el) => (this.ta = el)} value=${draft} placeholder="Ask anything…" hue=${hue}
        onInput=${(e) => this.setState({ draft: e.target.value })}
        onKeyDown=${(e) => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); this.send(); } }} />
      <div style=${{ display: 'flex', alignItems: 'center', gap: 8, ...mono13, color: T.dim, padding: '0 4px' }}>
        <span>${busy ? 'thinking…' : this.props.id ? plural(this.state.turns.filter((t) => t.role === 'user').length, 'message') : 'new conversation · drop files here'}</span>
        <label class="ring" style=${{ marginLeft: 'auto', padding: '3px 8px', borderRadius: 6, color: T.muted, cursor: 'pointer' }}>attach
          <input type="file" multiple hidden onChange=${(e) => { this.attach(e.target.files); e.target.value = ''; }} /></label>
        <span onClick=${() => this.send()} style=${{ padding: '3px 10px', borderRadius: 6, cursor: 'pointer', color: busy ? T.dim : T.text, boxShadow: ring }}>↵</span>
      </div>
    </div>`;
  }

  render({ app, mod, fmt, id }, { turns, title, tags, busy, partial, error, loading }) {
    const hue = mod.hue;
    if (!id) {
      return html`<div style=${{ paddingTop: '18vh', display: 'flex', flexDirection: 'column', gap: 12 }}>
        ${error && html`<div style=${{ ...mono13, color: RED }}>${error}</div>`}
        ${this.composer(hue)}
      </div>`;
    }
    const opened = turns.length ? turns[0].ts : null;
    return html`<div style=${{ display: 'flex', flexDirection: 'column', gap: 16 }}>
      <div style=${{ display: 'flex', alignItems: 'center', gap: 12, minHeight: 24 }}>
        <span style=${{ display: 'grid', placeItems: 'center', width: 16, height: 16, color: hue, flex: 'none' }}><${Icon} svg=${mod.icon} /></span>
        <span style=${{ minWidth: 0, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>${title}</span>
        ${opened && html`<span style=${{ ...mono13, color: T.dim, flex: 'none' }}>${dayLabel(opened)} ${clock(opened, fmt)}</span>`}
        ${tags.map((t) => html`<span key=${t} style=${{ padding: '2px 8px', borderRadius: 6, fontSize: 13, color: T.muted, boxShadow: 'inset 0 0 0 1px rgba(230,231,234,.1)', flex: 'none' }}>${t}</span>`)}
        <span class="ring" onClick=${() => this.remove()} style=${{ marginLeft: 'auto', ...mono13, color: T.dim, cursor: 'pointer', padding: '3px 8px', borderRadius: 6, flex: 'none' }}>delete</span>
        <span class="bright-hover" onClick=${() => app.select(null)} style=${{ cursor: 'pointer', color: T.dim, padding: '0 4px', lineHeight: 1 }}>×</span>
      </div>
      ${error && html`<div style=${{ ...mono13, color: RED }}>${error}</div>`}
      ${loading && html`<div style=${{ ...mono13, color: T.dim }}>loading…</div>`}
      <div style=${{ display: 'flex', flexDirection: 'column', gap: 16 }}>
        ${turns.map((t, i) => {
          if (t.role === 'user') return html`<div key=${i} style=${{ alignSelf: 'flex-end', maxWidth: '85%', background: T.raised, borderRadius: 6, padding: '10px 12px', whiteSpace: 'pre-wrap', lineHeight: 1.5 }}>${t.text}</div>`;
          if (t.role === 'model') return html`<div key=${i} style=${{ padding: '0 2px' }}><${Markdown} text=${t.text} /></div>`;
          if (t.role === 'tool') return html`<div key=${i} style=${{ display: 'flex', alignItems: 'center', gap: 10, height: 28, padding: '0 4px', ...mono13, color: T.muted }}><span style=${{ color: hue }}>▸</span>${t.tool}<span style=${{ marginLeft: 'auto', color: T.dim }}>${t.status || ''}</span></div>`;
          return html`<div key=${i} style=${{ ...mono13, color: T.dim, padding: '0 2px' }}>${t.text}${t.ts ? html`<span style=${{ marginLeft: 8 }}>${clock(t.ts, fmt)}</span>` : null}</div>`;
        })}
        ${partial && html`<div style=${{ padding: '0 2px' }}><${Markdown} text=${partial} /></div>`}
        ${busy && !partial && html`<div style=${{ ...mono13, color: T.dim, padding: '0 2px' }}>thinking…</div>`}
        <div ref=${(el) => (this.end = el)} />
      </div>
      ${this.composer(hue)}
    </div>`;
  }
}

// RIGHT: the conversation's folder, reloaded whenever the page refreshes.
class Files extends Component {
  constructor() {
    super();
    this.state = { files: null };
  }

  componentDidMount() { this.load(); }
  componentDidUpdate(prev) { if (prev.data !== this.props.data) this.load(); }

  async load() {
    try { this.setState({ files: await get(`/api/chat/files/${this.props.id}`) }); } catch { this.setState({ files: [] }); }
  }

  render({ id, hue, fmt }, { files }) {
    const list = files || [];
    return html`<div style=${{ display: 'flex', flexDirection: 'column', gap: 2 }}>
      <${GroupHeader} label="files" count=${list.length} />
      ${files && list.length === 0 && html`<${Empty} text="nothing attached or written yet" />`}
      ${list.map((f) => html`<div key=${f.name} class="row" onClick=${() => window.open(`/api/chat/file/${id}/${encodeURIComponent(f.name)}`, '_blank')}
          style=${{ display: 'flex', alignItems: 'center', gap: 12, height: 32, padding: '0 12px', borderRadius: 6, cursor: 'pointer' }}>
        <span style=${{ width: 6, height: 6, borderRadius: 3, flex: 'none', background: hue }} />
        <span style=${{ flex: 1, minWidth: 0, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>${f.name}</span>
        <span style=${{ ...mono13, color: T.dim, flex: 'none' }}>${bytes(f.bytes)}</span>
        <span style=${{ ...mono13, color: T.dim, flex: 'none' }}>${stamp(f.modified, fmt)}</span>
      </div>`)}
    </div>`;
  }
}
