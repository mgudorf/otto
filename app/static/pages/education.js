// Education: LEFT = the due queue, then history by day · MIDDLE = the question with an answer box under each part,
// or the progress table with Generate. Setups, prompts and explanations are markdown with LaTeX.
import { Component } from '../vendor/preact.mjs';
import { html, T, mono13, Row, GroupHeader, Search, Button, Empty, Icon, stamp, dayLabel } from '../rows.js';
import { get, post } from '../api.js';
import { Markdown } from '../md.js';

const VERDICT = { correct: '#7fb894', partial: '#d1a36a', incorrect: '#cf7b7b' }; // the palette's green, amber and red
const RED = '#cf7b7b';

export async function load(app) {
  const { query, more } = app.state;
  const q = new URLSearchParams({ query, page: String(more) });
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
  return html`<div style=${{ display: 'flex', flexDirection: 'column', gap: 20 }}>
    <${Search} value=${app.state.query} hue=${mod.hue} onInput=${(v) => rerun({ query: v, more: 0 })} />
    ${data.left.groups.length === 0 && html`<${Empty} text=${app.state.query ? 'no matches' : 'no questions yet'} />`}
    ${data.left.groups.map((g) => html`<div key=${g.label} style=${{ display: 'flex', flexDirection: 'column', gap: 2 }}>
      <${GroupHeader} label=${g.label} count=${g.count} />
      ${g.rows.map((r) => html`<${Row} key=${r.id} row=${r} hue=${mod.hue} fmt=${fmt} selected=${!!sel && String(sel.id) === String(r.id)} onSelect=${() => app.select({ module: 'education', id: r.id })} />`)}
    </div>`)}
    <div style=${{ display: 'flex', alignItems: 'center', gap: 16, height: 32, padding: '0 12px', ...mono13, color: T.dim }}>${data.left.showing}
      ${data.left.more && html`<span class="ring" onClick=${() => rerun({ more: app.state.more + 1 })} style=${{ cursor: 'pointer', color: T.muted, padding: '3px 8px', borderRadius: 6 }}>more</span>`}
    </div>
  </div>`;
}

// One part: the letter, the prompt, then the answer box or the graded block.
function Part({ p, item, hue, draft, busy, error, onDraft, onSubmit }) {
  const closed = item.status === 'graded' || item.status === 'skipped';
  const color = VERDICT[p.verdict] || T.muted;
  let body;
  if (p.graded_at) {
    body = html`<div style=${{ display: 'flex', flexDirection: 'column', gap: 8 }}>
      <div style=${{ background: T.raised, borderLeft: `3px solid ${color}`, borderRadius: 6, padding: '8px 12px' }}>
        <div style=${{ display: 'flex', alignItems: 'baseline', gap: 10, ...mono13, color: T.muted, marginBottom: 4 }}>your answer<span style=${{ marginLeft: 'auto', color, fontWeight: 500 }}>${p.score}</span></div>
        <div style=${{ whiteSpace: 'pre-wrap', lineHeight: 1.5 }}>${p.answer || '(no answer)'}</div>
      </div>
      ${p.note && html`<div style=${{ background: `color-mix(in srgb, ${hue} 8%, transparent)`, borderRadius: 6, padding: '8px 12px' }}>
        <div style=${{ ...mono13, color: hue, marginBottom: 4 }}>explanation</div>
        <${Markdown} text=${p.note} />
      </div>`}
    </div>`;
  } else if (closed) {
    body = html`<span style=${{ ...mono13, color: T.dim }}>not answered</span>`;
  } else {
    body = html`<div style=${{ display: 'flex', flexDirection: 'column', gap: 8 }}>
      <textarea rows="4" value=${draft} disabled=${busy} placeholder="Type your answer…"
        onInput=${(e) => onDraft(e.target.value)}
        onKeyDown=${(e) => { if ((e.ctrlKey || e.metaKey) && e.key === 'Enter') onSubmit(); }}
        style=${{ width: '100%', resize: 'vertical', padding: '10px 12px', border: 0, borderRadius: 6, background: T.raised, color: T.text, fontSize: 15, lineHeight: 1.5, '--hue': hue }} />
      <div style=${{ display: 'flex', alignItems: 'center', gap: 12 }}>
        <${Button} label=${busy ? 'grading…' : 'Submit'} primary=${!busy} hue=${hue} onClick=${() => !busy && onSubmit()} />
        ${error ? html`<span style=${{ ...mono13, color: RED }}>${error}</span>`
          : p.answered_at ? html`<span style=${{ ...mono13, color: T.dim }}>answered, not graded</span>` : null}
      </div>
    </div>`;
  }
  return html`<div style=${{ display: 'flex', gap: 12 }}>
    <span style=${{ ...mono13, color: hue, flex: 'none', width: 28, paddingTop: 3 }}>(${p.label})</span>
    <div style=${{ flex: 1, minWidth: 0, display: 'flex', flexDirection: 'column', gap: 10 }}>
      <${Markdown} text=${p.text} />
      ${body}
    </div>
  </div>`;
}

// The question view: the inspector's header line, the title, chips, the setup, the parts, feedback, actions.
// Drafts and in-flight grades live here, keyed by part; a new question is a new instance (key = id).
class Question extends Component {
  constructor() {
    super();
    this.state = { drafts: {}, busy: {}, errors: {} };
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

  render({ app, item, mod, fmt, onAction }, { drafts, busy, errors }) {
    const hue = mod.hue;
    const chip = { padding: '2px 8px', borderRadius: 6, fontSize: 13, color: T.muted, boxShadow: 'inset 0 0 0 1px rgba(230,231,234,.1)' };
    const when = `${dayLabel(item.created_at)} ${new Date(item.created_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', hour12: fmt === '12h' })}`;
    return html`<div style=${{ display: 'flex', flexDirection: 'column', gap: 20, maxWidth: '72ch' }}>
      <div style=${{ display: 'flex', alignItems: 'center', gap: 12 }}>
        <span style=${{ display: 'grid', placeItems: 'center', width: 16, height: 16, color: hue }}><${Icon} svg=${mod.icon} /></span>
        <span style=${{ ...mono13, color: T.muted }}>${item.kind} · ${when}</span>
        <span class="bright-hover" onClick=${() => app.select(null)} style=${{ marginLeft: 'auto', cursor: 'pointer', color: T.dim, padding: '0 4px', lineHeight: 1 }}>×</span>
      </div>
      <div style=${{ display: 'flex', flexDirection: 'column', gap: 10 }}>
        <div style=${{ fontSize: 17, fontWeight: 600, lineHeight: 1.3 }}>${item.title}</div>
        <div style=${{ display: 'flex', flexWrap: 'wrap', gap: 6 }}>
          <span style=${chip}>${item.topic}</span>
          ${item.topic_tag && html`<span style=${chip}>${item.topic_tag}</span>`}
        </div>
      </div>
      <${Markdown} text=${item.setup} />
      <div style=${{ display: 'flex', flexDirection: 'column', gap: 18 }}>
        ${item.parts.map((p) => html`<${Part} key=${p.n} p=${p} item=${item} hue=${hue}
          draft=${drafts[p.n] !== undefined ? drafts[p.n] : p.answer || ''} busy=${!!busy[p.n]} error=${errors[p.n]}
          onDraft=${(v) => this.setState({ drafts: { ...drafts, [p.n]: v } })} onSubmit=${() => this.submit(p)} />`)}
      </div>
      ${item.feedback.length > 0 && html`<div style=${{ display: 'flex', flexDirection: 'column', gap: 4, ...mono13, color: T.muted }}>
        ${item.feedback.map((f, i) => html`<span key=${i}>“${f}”</span>`)}
      </div>`}
      <div style=${{ display: 'flex', gap: 8, marginTop: 6, flexWrap: 'wrap', alignItems: 'center' }}>
        ${item.actions.map((a) => html`<${Button} key=${a.verb} label=${a.label} primary=${a.primary} hue=${hue} onClick=${() => onAction(a)} />`)}
        <${Button} label="Send to session" right=${true} onClick=${() => app.sendToSession(`Q${item.id} "${item.title}": `)} />
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
    const act = async (a) => {
      await post(`/api/education/action/${a.verb}`, { id: item.id });
      app.loadItem(app.state.sel);
      app.refresh();
    };
    return html`<${Question} key=${item.id} app=${app} item=${item} mod=${mod} fmt=${fmt} onAction=${act} />`;
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
  const cols = 'minmax(0,1fr) 28px 56px 40px 120px 64px 16px';
  const cell = { whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' };
  return html`<div style=${{ display: 'flex', flexDirection: 'column', gap: 16, maxWidth: 720 }}>
    <span style=${{ ...mono13, color: T.dim }}>${b.due} due · ${b.topics.length} topics</span>
    <${Generate} app=${app} hue=${hue} />
    <div style=${{ display: 'flex', flexDirection: 'column', ...mono13 }}>
      <div style=${{ display: 'grid', gridTemplateColumns: cols, gap: 12, height: 28, alignItems: 'center', padding: '0 12px', color: T.muted }}>topic<span>d</span><span>graded</span><span>avg</span><span>recent</span><span>last</span><span /></div>
      ${b.topics.length === 0 && html`<${Empty} text="no topics yet" />`}
      ${b.topics.map((t) => html`<div key=${t.id} class="trow" title=${t.description || ''} style=${{ display: 'grid', gridTemplateColumns: cols, gap: 12, height: 32, alignItems: 'center', padding: '0 12px', borderTop: `1px solid ${T.hair}`, color: T.text }}>
        <span style=${{ ...cell, fontFamily: 'Inter, system-ui, sans-serif', fontSize: 15 }}>${t.name}</span>
        <span style=${{ color: hue }}>d${t.difficulty}</span>
        <span style=${{ color: T.muted }}>${t.graded}/${t.asked}</span>
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
