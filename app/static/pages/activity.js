// Activity: LEFT = event log by day · MIDDLE blank = every scheduled task in one table.
import { html, T, meta13, nums, code13, rowStyle, GroupHeader, Chips, Toggle, Empty, More, dayLabel, clock, stamp, interval } from '../rows.js';
import { get, post } from '../api.js';
import { Markdown } from '../md.js';

const RED = '#cf7b7b';

export async function load(app) {
  const chip = app.state.chip;
  const mods = app.state.shell.modules.filter((m) => !m.error).map((m) => m.name);
  const module = chip === 'All' ? '' : chip;
  const [ev, tasks, jobs] = await Promise.all([get(`/api/events?module=${encodeURIComponent(module)}&limit=${200 * (app.state.more + 1)}`), get('/api/tasks'), get('/api/jobs?limit=50')]);
  return { events: ev.events, total: ev.total, tasks, jobs, chips: ['All', ...mods, 'system'] };
}

function groupByDay(events) {
  const groups = [];
  for (const e of events) {
    const label = dayLabel(e.ts);
    if (!groups.length || groups[groups.length - 1].label !== label) groups.push({ label, rows: [] });
    groups[groups.length - 1].rows.push(e);
  }
  return groups;
}

export function Left({ app, data, fmt }) {
  const sel = app.state.sel;
  const hueOf = (name) => app.module(name).hue;
  return html`<div style=${{ display: 'flex', flexDirection: 'column', gap: 20 }}>
    <${Chips} chips=${data.chips} active=${app.state.chip} hue=${T.text} onPick=${(c) => app.setState({ chip: c, more: 0 }, () => app.refresh())} />
    ${data.events.length === 0 && html`<${Empty} text="no events yet" />`}
    ${groupByDay(data.events).map((g) => html`<div key=${g.label} style=${{ display: 'flex', flexDirection: 'column', gap: 4 }}>
      <${GroupHeader} label=${g.label} />
      ${g.rows.map((e) => html`<div key=${e.id} class="row" onClick=${() => app.select({ module: 'activity', id: e.id, local: e })} style=${rowStyle({ selected: !!sel && sel.id === e.id, hue: T.muted, height: 32 })}>
        <span style=${{ ...meta13, ...nums, color: T.dim, width: 44, flex: 'none' }}>${clock(e.ts, fmt)}</span>
        <span style=${{ fontSize: 13, color: e.verb === 'failed' ? RED : hueOf(e.module), width: 64, flex: 'none', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>${e.verb}</span>
        <span style=${{ flex: 1, minWidth: 0, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis', fontSize: 13 }}>${e.text}</span>
      </div>`)}
    </div>`)}
    ${data.events.length < data.total && html`<${More} onClick=${() => app.setState({ more: app.state.more + 1 }, () => app.refresh())} />`}
  </div>`;
}

class JobView {
  constructor() { this.jobs = {}; }
}
const cache = new JobView();

export function Middle({ app, data, fmt }) {
  const sel = app.state.sel;
  if (sel && sel.local) {
    const e = sel.local;
    const job = e.job_id ? cache.jobs[e.job_id] : null;
    if (e.job_id && !job) get(`/api/jobs/${e.job_id}`).then((j) => { cache.jobs[e.job_id] = j; app.forceUpdate(); });
    return html`<div style=${{ display: 'flex', flexDirection: 'column', gap: 20 }}>
      <div style=${{ display: 'flex', alignItems: 'center', gap: 12 }}>
        <span style=${{ ...meta13, ...nums, color: T.muted }}><span style=${{ color: app.module(e.module).hue }}>${e.module}</span> · ${e.verb} · ${dayLabel(e.ts)} ${clock(e.ts, fmt)}</span>
        <span class="bright-hover" onClick=${() => app.select(null)} style=${{ marginLeft: 'auto', cursor: 'pointer', color: T.dim, padding: '0 4px', lineHeight: 1 }}>×</span>
      </div>
      <${Markdown} text=${e.text} />
      ${job && html`<div style=${{ display: 'flex', flexDirection: 'column', gap: 6, ...meta13, ...nums, color: T.muted }}>
        <div>job ${job.id} · ${job.kind} · ${job.status} · ${job.started_at ? clock(job.started_at, fmt) : ''}${job.finished_at ? ` → ${clock(job.finished_at, fmt)}` : ''}</div>
        ${job.result && html`<div style=${{ color: T.text }}><${Markdown} text=${job.result} /></div>`}
        ${job.error && html`<pre style=${{ margin: 0, color: RED, whiteSpace: 'pre-wrap', ...code13, fontSize: 12 }}>${job.error}</pre>`}
        ${job.logs.map((l, i) => html`<div key=${i}><span style=${{ color: T.dim }}>${clock(l.ts, fmt)}</span> ${l.message}</div>`)}
      </div>`}
    </div>`;
  }
  const budget = app.state.shell.budget;
  const held = new Set(app.state.shell.modules.filter((m) => m.tasks && !m.scheduled).map((m) => m.name));
  const cols = '1.4fr 0.8fr 0.7fr 0.9fr 0.9fr 1.6fr 40px';
  const cell = { whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' };
  return html`<div style=${{ display: 'flex', flexDirection: 'column', gap: 24 }}>
    <div style=${{ display: 'flex', flexDirection: 'column', ...meta13, ...nums }}>
      <div style=${{ display: 'grid', gridTemplateColumns: cols, gap: 16, height: 28, alignItems: 'center', padding: '0 12px', color: T.muted }}>
        <span>task</span><span>module</span><span>every</span><span>last run</span><span>next run</span><span>last result</span><span></span></div>
      ${data.tasks.map((t) => html`<div key=${t.name} class="trow" style=${{ display: 'grid', gridTemplateColumns: cols, gap: 16, height: 32, alignItems: 'center', padding: '0 12px', borderTop: `1px solid ${T.hair}`, color: t.enabled && !held.has(t.module) ? T.text : T.dim }}>
        <span style=${cell}>${t.name}${t.llm ? html`<span style=${{ color: T.dim }}> · llm</span>` : null}</span>
        <span style=${{ ...cell, color: T.muted }}>${t.module}</span>
        <span style=${{ ...cell, color: T.muted }}>${interval(t.interval_seconds)}</span>
        <span style=${{ ...cell, color: T.muted }}>${t.last_run ? stamp(t.last_run, fmt) : '—'}</span>
        <span style=${{ ...cell, color: T.muted }}>${!t.enabled ? 'off' : held.has(t.module) ? 'module off' : t.next_run ? stamp(t.next_run, fmt) : 'off'}</span>
        <span style=${{ ...cell, color: t.last_status === 'failed' ? RED : T.muted }} title=${t.last_result || ''}>${t.last_status ? `${t.last_status}: ${t.last_result || ''}` : ''}</span>
        <${Toggle} on=${!!t.enabled} onFlip=${async () => { await post(`/api/tasks/${t.name}`, { enabled: !t.enabled }); app.refresh(); }} />
      </div>`)}
    </div>
    <div style=${{ ...meta13, ...nums, color: T.dim }}>nightly ${budget.used} / ${budget.max} · ${budget.window} · every ${budget.stagger_minutes} min${budget.in_window ? ' · open' : ''}</div>
    <div style=${{ display: 'flex', flexDirection: 'column', ...meta13, ...nums }}>
      <div style=${{ display: 'grid', gridTemplateColumns: '56px 1.6fr 0.7fr 0.7fr 0.9fr 2fr', gap: 16, height: 28, alignItems: 'center', padding: '0 12px', color: T.muted }}>
        <span>job</span><span>task</span><span>kind</span><span>status</span><span>queued</span><span>result</span></div>
      ${data.jobs.map((j) => html`<div key=${j.id} class="trow" style=${{ display: 'grid', gridTemplateColumns: '56px 1.6fr 0.7fr 0.7fr 0.9fr 2fr', gap: 16, height: 32, alignItems: 'center', padding: '0 12px', borderTop: `1px solid ${T.hair}` }}>
        <span style=${{ color: T.dim }}>${j.id}</span><span style=${cell}>${j.task}</span><span style=${{ color: T.muted }}>${j.kind}</span>
        <span style=${{ color: j.status === 'failed' ? RED : j.status === 'running' ? T.text : T.muted }}>${j.status}</span>
        <span style=${{ color: T.muted }}>${stamp(j.queued_at, fmt)}</span>
        <span style=${{ ...cell, color: T.muted }} title=${j.error || j.result || ''}>${j.error ? j.error.trim().split('\n').pop() : j.result || ''}</span>
      </div>`)}
    </div>
  </div>`;
}
