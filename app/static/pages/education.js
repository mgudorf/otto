// Education: LEFT = the active queue or the completed history, one chip each · MIDDLE = the question: title, tags,
// the pinned setup (definitions, then premise), the parts folded or open with an answer box each; or the progress
// table with Generate. Submit hands an answer to the tutor in the session pane, where the grade and explanation land.
import { Component } from '../vendor/preact.mjs';
import { html, T, mono13, Row, GroupHeader, Chips, Search, Button, Empty, Icon, stamp, dayLabel } from '../rows.js';
import { get, post } from '../api.js';
import { Markdown } from '../md.js';

const VERDICT = { correct: '#7fb894', partial: '#d1a36a', incorrect: '#cf7b7b' }; // the palette's green, amber and red
const RED = '#cf7b7b';
const PROSE = { fontSize: 16, lineHeight: 1.65 };   // question prose reads one step above the frame's 15px

export async function load(app) {
  const { query, chip, more } = app.state;
  const q = new URLSearchParams({ query, chip, page: String(more) });
  const [left, blank] = await Promise.all([get(`/api/education/left?${q}`), get('/api/education/blank')]);
  return { left, blank };
}

export function meta(app) {
  const b = app.state.data && app.state.data.blank;
  return b ? `${b.due} due` : '';
}

export function Left({ app, data, mod, fmt }) {
  const sel = app.state.sel;
  const rerun = (patch) => app.setState(patch, () => app.refresh());
  const empty = app.state.query ? 'no matches' : data.left.chip === 'completed' ? 'nothing completed yet' : 'nothing due';
  return html`<div style=${{ display: 'flex', flexDirection: 'column', gap: 20 }}>
    <${Search} value=${app.state.query} hue=${mod.hue} onInput=${(v) => rerun({ query: v, more: 0 })} />
    <${Chips} chips=${data.left.chips} active=${data.left.chip} hue=${mod.hue} onPick=${(c) => rerun({ chip: c, more: 0 })} />
    ${data.left.groups.length === 0 && html`<${Empty} text=${empty} />`}
    ${data.left.groups.map((g) => html`<div key=${g.label} style=${{ display: 'flex', flexDirection: 'column', gap: 2 }}>
      <${GroupHeader} label=${g.label} count=${g.count} />
      ${g.rows.map((r) => html`<${Row} key=${r.id} row=${r} hue=${mod.hue} fmt=${fmt} selected=${!!sel && String(sel.id) === String(r.id)} onSelect=${() => app.select({ module: 'education', id: r.id })} />`)}
    </div>`)}
    <div style=${{ display: 'flex', alignItems: 'center', gap: 16, height: 32, padding: '0 12px', ...mono13, color: T.dim }}>${data.left.showing}
      ${data.left.more && html`<span class="ring" onClick=${() => rerun({ more: app.state.more + 1 })} style=${{ cursor: 'pointer', color: T.muted, padding: '3px 8px', borderRadius: 6 }}>more</span>`}
    </div>
  </div>`;
}

// One part. The header row (letter, title, score, caret) folds it; open, it shows the prompt and the answer box.
// The grade and the tutor's explanation live in the session pane; here only the score shows.
function Part({ p, item, hue, open, onToggle, draft, busy, error, onDraft, onSubmit }) {
  const color = VERDICT[p.verdict] || T.muted;
  const awaiting = !!p.answered_at && !p.graded_at;   // a new answer clears the old grade until the tutor grades again
  const closed = item.status === 'completed';
  const score = p.score === null || p.score === undefined ? (awaiting ? '…' : '–') : String(p.score);
  const header = html`<div class="row" onClick=${onToggle} style=${{ display: 'flex', alignItems: 'center', gap: 12, height: 36, padding: '0 12px', margin: '0 -12px', borderRadius: 6, cursor: 'pointer' }}>
    <span style=${{ ...mono13, color: hue, flex: 'none', width: 28 }}>(${p.label})</span>
    <span style=${{ flex: 1, minWidth: 0, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis', fontWeight: 500 }}>${p.title}</span>
    <span style=${{ ...mono13, color, flex: 'none', fontWeight: 500 }}>${score}</span>
    <span style=${{ ...mono13, color: T.dim, flex: 'none', width: 12, textAlign: 'center' }}>${open ? '▾' : '▸'}</span>
  </div>`;
  if (!open) return header;
  let status = null;
  if (error) status = html`<span style=${{ ...mono13, color: RED }}>${error}</span>`;
  else if (busy) status = html`<span style=${{ ...mono13, color: T.dim }}>sending…</span>`;
  else if (awaiting) status = html`<span style=${{ ...mono13, color: T.dim }}>with the tutor; the grade lands in the session</span>`;
  else if (p.graded_at) status = html`<span style=${{ ...mono13, color: T.dim }}>graded; a resubmit replaces this grade</span>`;
  return html`<div style=${{ display: 'flex', flexDirection: 'column', gap: 12 }}>
    ${header}
    <div style=${{ paddingLeft: 40, display: 'flex', flexDirection: 'column', gap: 12 }}>
      <div style=${PROSE}><${Markdown} text=${p.text} /></div>
      ${closed
        ? html`<div style=${{ background: T.raised, borderLeft: `3px solid ${color}`, borderRadius: 6, padding: '8px 12px', whiteSpace: 'pre-wrap', lineHeight: 1.5 }}>
            ${p.answer || html`<span style=${{ ...mono13, color: T.dim }}>not answered</span>`}</div>`
        : html`<textarea rows="4" value=${draft} disabled=${busy} placeholder="Your answer, in prose…"
            onInput=${(e) => onDraft(e.target.value)}
            onKeyDown=${(e) => { if ((e.ctrlKey || e.metaKey) && e.key === 'Enter') onSubmit(); }}
            style=${{ width: '100%', resize: 'vertical', padding: '10px 12px', border: 0, borderRadius: 6, background: T.raised, color: T.text, fontSize: 15, lineHeight: 1.5, '--hue': hue }} />
          <div style=${{ display: 'flex', alignItems: 'center', gap: 12, minHeight: 28 }}>
            <${Button} label=${p.graded_at ? 'Resubmit' : 'Submit'} primary=${!busy} hue=${hue} onClick=${() => !busy && onSubmit()} />
            ${status}
          </div>`}
    </div>
  </div>`;
}

// The question view: the inspector's header line, title, chips and tags, the pinned setup, the parts, feedback, actions.
// Drafts, in-flight submits and which parts are open live here; a new question is a new instance (key = id).
class Question extends Component {
  constructor() {
    super();
    this.state = { drafts: {}, busy: {}, errors: {}, open: {}, defs: true, tag: '', error: null };
  }

  async submit(p) {
    const { app, item } = this.props;
    const draft = this.state.drafts[p.n];
    const text = (draft !== undefined ? draft : p.answer || '').trim();
    if (!text || this.state.busy[p.n]) return;
    this.setState({ busy: { ...this.state.busy, [p.n]: true }, errors: { ...this.state.errors, [p.n]: null } });
    let error = null;
    try {
      await post('/api/education/action/answer', { id: item.id, n: p.n, answer: text });
    } catch (e) {
      error = e.message;
    }
    this.setState({ busy: { ...this.state.busy, [p.n]: false }, errors: { ...this.state.errors, [p.n]: error } });
    if (app.state.sel && String(app.state.sel.id) === String(item.id)) app.loadItem(app.state.sel);
    app.refresh();
  }

  // An action that fails says so in the fixed line under the buttons; nothing moves when it appears.
  async act(a) {
    const { app, item } = this.props;
    if (a.confirm && !window.confirm(a.confirm)) return;
    this.setState({ error: null });
    try {
      await post(`/api/education/action/${a.verb}`, { id: item.id });
    } catch (e) {
      this.setState({ error: e.message });
      return;
    }
    if (a.verb === 'delete') app.select(null);
    else app.loadItem(app.state.sel);
    app.refresh();
  }

  async saveTags(tags) {
    const { app, item } = this.props;
    this.setState({ error: null, tag: '' });
    try {
      await post('/api/education/action/tags', { id: item.id, tags });
    } catch (e) {
      this.setState({ error: e.message });
      return;
    }
    app.loadItem(app.state.sel);
  }

  // A graded part sits folded until opened; an ungraded one is open until folded.
  isOpen(p) {
    const o = this.state.open[p.n];
    return o !== undefined ? o : p.score === null || p.score === undefined;
  }

  render({ app, item, mod, fmt }, { drafts, busy, errors, defs, tag, error }) {
    const hue = mod.hue;
    const chip = { padding: '2px 8px', borderRadius: 6, fontSize: 13, color: T.muted, boxShadow: 'inset 0 0 0 1px rgba(230,231,234,.1)' };
    const when = `${dayLabel(item.created_at)} ${new Date(item.created_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', hour12: fmt === '12h' })}`;
    const tags = item.tags || [];
    const addTag = () => {
      const t = tag.trim();
      if (t && !tags.includes(t)) this.saveTags([...tags, t]);
      else this.setState({ tag: '' });
    };
    const block = (label, text) => html`<div style=${{ display: 'flex', flexDirection: 'column', gap: 6 }}>
      <span style=${{ ...mono13, color: hue }}>${label}</span>
      <div style=${PROSE}><${Markdown} text=${text} /></div>
    </div>`;
    return html`<div style=${{ display: 'flex', flexDirection: 'column', gap: 20, maxWidth: '72ch', margin: '0 auto' }}>
      <div style=${{ display: 'flex', alignItems: 'center', gap: 12 }}>
        <span style=${{ display: 'grid', placeItems: 'center', width: 16, height: 16, color: hue }}><${Icon} svg=${mod.icon} /></span>
        <span style=${{ ...mono13, color: T.muted }}>${item.kind} · ${when}</span>
        <span class="bright-hover" onClick=${() => app.select(null)} style=${{ marginLeft: 'auto', cursor: 'pointer', color: T.dim, padding: '0 4px', lineHeight: 1 }}>×</span>
      </div>
      <div style=${{ display: 'flex', flexDirection: 'column', gap: 10 }}>
        <div style=${{ fontSize: 18, fontWeight: 600, lineHeight: 1.3 }}>${item.title}</div>
        <div style=${{ display: 'flex', flexWrap: 'wrap', alignItems: 'center', gap: 6 }}>
          <span style=${chip}>${item.topic}</span>
          ${item.topic_tag && html`<span style=${chip}>${item.topic_tag}</span>`}
          ${tags.map((t) => html`<span key=${t} style=${{ ...chip, color: hue }}>${t}
            <span class="bright-hover" title="remove" onClick=${() => this.saveTags(tags.filter((x) => x !== t))} style=${{ marginLeft: 6, cursor: 'pointer', color: T.dim }}>×</span></span>`)}
          <input placeholder="+ tag" value=${tag} onInput=${(e) => this.setState({ tag: e.target.value })}
            onKeyDown=${(e) => { if (e.key === 'Enter') addTag(); }} onBlur=${addTag}
            style=${{ width: 96, height: 24, padding: '0 8px', border: 0, borderRadius: 6, background: 'transparent', boxShadow: 'inset 0 0 0 1px rgba(230,231,234,.1)', color: T.text, fontSize: 13, '--hue': hue }} />
        </div>
      </div>
      <div style=${{ position: 'sticky', top: 0, zIndex: 1, background: T.ground, maxHeight: '50vh', overflow: 'auto', padding: '8px 0 14px', borderBottom: `1px solid ${T.hair}`, display: 'flex', flexDirection: 'column', gap: 16 }}>
        ${item.definitions && html`<div style=${{ display: 'flex', flexDirection: 'column', gap: 6 }}>
          <span onClick=${() => this.setState({ defs: !defs })} style=${{ ...mono13, color: hue, cursor: 'pointer', display: 'flex', alignItems: 'center', gap: 8 }}>definitions<span style=${{ color: T.dim }}>${defs ? '▾' : '▸'}</span></span>
          ${defs && html`<div style=${PROSE}><${Markdown} text=${item.definitions} /></div>`}
        </div>`}
        ${block('premise', item.premise)}
      </div>
      <div style=${{ display: 'flex', flexDirection: 'column', gap: 14 }}>
        ${item.parts.map((p) => html`<${Part} key=${p.n} p=${p} item=${item} hue=${hue} open=${this.isOpen(p)}
          onToggle=${() => this.setState({ open: { ...this.state.open, [p.n]: !this.isOpen(p) } })}
          draft=${drafts[p.n] !== undefined ? drafts[p.n] : p.answer || ''} busy=${!!busy[p.n]} error=${errors[p.n]}
          onDraft=${(v) => this.setState({ drafts: { ...drafts, [p.n]: v } })} onSubmit=${() => this.submit(p)} />`)}
      </div>
      ${item.feedback.length > 0 && html`<div style=${{ display: 'flex', flexDirection: 'column', gap: 4, ...mono13, color: T.muted }}>
        ${item.feedback.map((f, i) => html`<span key=${i}>“${f}”</span>`)}
      </div>`}
      <div style=${{ display: 'flex', flexDirection: 'column', gap: 6, marginTop: 6 }}>
        <div style=${{ display: 'flex', gap: 8, flexWrap: 'wrap', alignItems: 'center' }}>
          ${item.actions.map((a) => html`<${Button} key=${a.verb} label=${a.label} primary=${a.primary} hue=${hue} onClick=${() => this.act(a)} />`)}
          <${Button} label="Send to session" right=${true} onClick=${() => app.sendToSession(`Q${item.id} "${item.title}": `)} />
        </div>
        <div style=${{ ...mono13, color: RED, minHeight: 18 }}>${error || ''}</div>
      </div>
    </div>`;
  }
}

// Generate: one press, one question on the topic that has waited longest; the page selects it when it lands.
class Generate extends Component {
  constructor() {
    super();
    this.state = { busy: false, error: null };
  }

  async run() {
    if (this.state.busy) return;
    this.setState({ busy: true, error: null });
    try {
      const r = await post('/api/education/action/generate');
      this.setState({ busy: false });
      await this.props.app.refresh();
      this.props.app.select({ module: 'education', id: r.id });
    } catch (e) {
      this.setState({ busy: false, error: e.message });
    }
  }

  render({ hue }, { busy, error }) {
    return html`<div style=${{ display: 'flex', alignItems: 'center', gap: 12 }}>
      <${Button} label=${busy ? 'generating…' : 'Generate'} primary=${!busy} hue=${hue} onClick=${() => this.run()} />
      <span style=${{ ...mono13, color: error ? RED : T.dim }}>${error || 'one question on the topic that has waited longest'}</span>
    </div>`;
  }
}

const draft = { name: '', description: '' };

export function Middle({ app, data, mod, fmt }) {
  const hue = mod.hue;
  if (app.state.sel) {
    const item = app.state.item;
    if (!item) return html`<div style=${{ ...mono13, color: T.dim }}>loading…</div>`;
    if (item.error) return html`<div style=${{ ...mono13, color: RED }}>${item.error}</div>`;
    return html`<${Question} key=${item.id} app=${app} item=${item} mod=${mod} fmt=${fmt} />`;
  }
  const b = data.blank;
  const save = async () => {
    const name = draft.name.trim();
    if (!name) return;
    await post('/api/education/action/add_topic', { name, description: draft.description.trim() });
    draft.name = ''; draft.description = '';
    app.refresh();
  };
  const retire = async (t) => {
    if (!window.confirm(`Retire ${t.name}?`)) return;
    await post('/api/education/action/retire_topic', { id: t.id });
    app.refresh();
  };
  const cols = 'minmax(0,1fr) 32px 56px 40px 120px 64px 16px';
  const cell = { whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' };
  return html`<div style=${{ display: 'flex', flexDirection: 'column', gap: 16 }}>
    <span style=${{ ...mono13, color: T.dim }}>${b.due} due · ${b.topics.length} topics</span>
    <${Generate} app=${app} hue=${hue} />
    <div style=${{ display: 'flex', flexDirection: 'column', ...mono13 }}>
      <div style=${{ display: 'grid', gridTemplateColumns: cols, gap: 12, height: 28, alignItems: 'center', padding: '0 12px', color: T.muted }}>topic<span>d</span><span>done</span><span>avg</span><span>recent</span><span>last</span><span /></div>
      ${b.topics.length === 0 && html`<${Empty} text="no topics yet" />`}
      ${b.topics.map((t) => html`<div key=${t.id} class="trow" title=${t.description || ''} style=${{ display: 'grid', gridTemplateColumns: cols, gap: 12, height: 32, alignItems: 'center', padding: '0 12px', borderTop: `1px solid ${T.hair}`, color: T.text }}>
        <span style=${{ ...cell, fontFamily: 'Inter, system-ui, sans-serif', fontSize: 15 }}>${t.name}</span>
        <span style=${{ color: hue }}>d${t.difficulty}</span>
        <span style=${{ color: T.muted }}>${t.completed}/${t.asked}</span>
        <span>${t.average === null ? '–' : t.average}</span>
        <span style=${{ ...cell, color: T.muted }}>${t.recent.join(' ') || '–'}</span>
        <span style=${{ color: T.dim }}>${t.last_asked ? stamp(t.last_asked, fmt) : '–'}</span>
        <span class="bright-hover" title="retire" onClick=${() => retire(t)} style=${{ cursor: 'pointer', color: T.dim, textAlign: 'right' }}>×</span>
      </div>`)}
    </div>
    <div style=${{ display: 'flex', alignItems: 'center', gap: 8, marginTop: 8 }}>
      <input placeholder="new topic" value=${draft.name} onInput=${(e) => { draft.name = e.target.value; }} onKeyDown=${(e) => { if (e.key === 'Enter') save(); }}
        style=${{ width: 220, height: 30, padding: '0 10px', border: 0, borderRadius: 6, background: T.panel, color: T.text, fontSize: 15, '--hue': hue }} />
      <input placeholder="what you want from it, optional" value=${draft.description} onInput=${(e) => { draft.description = e.target.value; }} onKeyDown=${(e) => { if (e.key === 'Enter') save(); }}
        style=${{ flex: 1, height: 30, padding: '0 10px', border: 0, borderRadius: 6, background: T.panel, color: T.text, fontSize: 13, '--hue': hue }} />
      <${Button} label="Add" primary=${true} hue=${hue} onClick=${save} />
    </div>
  </div>`;
}
