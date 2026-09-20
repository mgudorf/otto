// Activity: the daemon's own log. Events by day, newest first; the second segment is every scheduled task with its
// switch. An event that came from a job opens that job's result, error and log in the pane.
import { S, h, hue, modOf, card, byDay, dayLabel, stamp, dateLine, pick, sw, toast, renderMain, refresh } from '../core.js';
import { get, post } from '../api.js';
import { md } from '../md.js';

const p2 = (n) => String(n).padStart(2, '0');
// The daemon stamps in UTC; the shell's formatters read a wall clock, so every stamp lands here first.
const localTime = (ts) => { if (!ts) return ''; const d = new Date(ts); return `${d.getFullYear()}-${p2(d.getMonth() + 1)}-${p2(d.getDate())}T${p2(d.getHours())}:${p2(d.getMinutes())}`; };
const setting = (k, fallback) => (S.shell && S.shell.settings && S.shell.settings[k] !== undefined ? S.shell.settings[k] : fallback);
const clock = (t) => {
  const hm = String(t).slice(11, 16);
  if (setting('ui.time_format', '24h') !== '12h' || hm.length < 5) return hm;
  const hr = Number(hm.slice(0, 2));
  return `${((hr + 11) % 12) + 1}:${hm.slice(3)} ${hr < 12 ? 'am' : 'pm'}`;
};
const every = (s) => (s % 86400 === 0 && s > 86400 ? `every ${s / 86400} d` : s % 3600 === 0 ? `every ${s / 3600} h` : s % 60 === 0 ? `every ${s / 60} min` : `every ${s} s`);
// The daemon's own lines stay neutral: System is a module of the log, not a page with a colour.
const tint = (m) => (m === 'system' ? 'var(--ink-3)' : hue(m));
// Every module the shell lists, System and Feedback included: they write events too.
const modules = () => (S.shell ? S.shell.modules.filter((m) => !m.error) : []);
const held = (name) => modules().some((m) => m.name === name && m.scheduled === false);

let span = 0;     // pages of the log beyond the first
let only = '';    // one module's events, asked of the daemon, not sieved out of the window

// A job is fetched when the event it wrote is opened, and again on every reload until it settles, so a queued or
// running job keeps up with itself. A fetch that fails is recorded against this reload rather than dropped: the pane
// is rebuilt on every keystroke in the search bar, and a dropped entry would ask again, and toast, on each one.
let gen = 0;
const jobs = {};
const settled = (j) => !!j && j.status !== 'queued' && j.status !== 'running';
function jobOf(id) {
  const c = jobs[id];
  if (c && (c.gen === gen || c.pending || settled(c.job))) return c.job;
  const had = c ? c.job : null;
  jobs[id] = { gen, job: had, pending: true };
  get(`/api/jobs/${id}`).then((j) => { jobs[id] = { gen, job: j }; renderMain(); }).catch((e) => { jobs[id] = { gen, job: had }; toast(e.message); });
  return jobs[id].job;
}

export default {
  cols: '60px 124px 96px minmax(0,1fr)',
  colsSplit: '56px 100px 84px minmax(0,1fr)',
  chips: ['All', 'Failed'],
  seg: ['Events', 'Tasks'],

  // The picked module narrows the query, so the count behind More is the count of what was picked.
  async load() {
    gen += 1;
    const size = Number(setting('ui.page_size', 40)) || 40;
    const q = `limit=${size * (span + 1)}${only ? `&module=${encodeURIComponent(only)}` : ''}`;
    const [log, tasks] = await Promise.all([get(`/api/events?${q}`), get('/api/tasks')]);
    return {
      // The verb rides as kind: it is what the omnibox and kind: search on.
      items: (log.events || []).map((e) => ({ id: e.id, module: e.module, title: e.text, when: localTime(e.ts), kind: e.verb, job_id: e.job_id, local: true })),
      total: log.total || 0,
      tasks: tasks || [],
    };
  },

  summary: () => {
    const b = S.shell && S.shell.budget;
    return b ? h('span', { class: 'meta' }, `nightly ${b.used} of ${b.max} runs used, window ${String(b.window).replace('-', ' to ')}`) : null;
  },

  filter: (list, chip) => (chip === 'Failed' ? list.filter((i) => i.kind === 'failed') : list),
  groups: (list) => byDay(list),
  cells: (i) => [
    h('span', { class: 'c num' }, clock(i.when)),
    h('span', { class: 'c', style: `color:${tint(i.module)}` }, modOf(i.module).title),
    h('span', { class: 'c', style: i.kind === 'failed' ? 'color:var(--danger)' : null }, i.kind),
    h('span', { class: 't' }, h('span', { class: 'title' }, i.title)),
  ],

  tools: (d) => {
    if (S.seg.activity === 'Tasks') return [];
    return [
      pick([['', 'Every module'], ...modules().map((m) => [m.name, m.title])], only, (v) => { only = v; span = 0; refresh(); }),
      d.items.length < d.total ? h('button', { class: 'btn quiet', onclick: () => { span += 1; refresh(); } }, 'More') : null,
    ];
  },

  // The tasks the clock runs: what each one is, how often, when it last ran and when it runs next, how it ended,
  // and the switch that holds it.
  alt: (d) => {
    if (!d.tasks.length) return h('div', { class: 'empty' }, 'Nothing here yet.');
    const cols = 'minmax(0,1.4fr) 124px 112px 112px 112px 100px 36px';
    return card('', d.tasks.length, d.tasks.map((t) => h('div', { class: `row${t.enabled && !held(t.module) ? '' : ' dim'}`, style: `--cols:${cols}` },
      h('span', { class: 't' }, h('span', { class: 'title mono', style: 'font-weight:400' }, t.name)),
      h('span', { class: 'c', style: `color:${tint(t.module)}` }, modOf(t.module).title),
      h('span', { class: 'c num' }, every(t.interval_seconds)),
      h('span', { class: 'c num' }, t.last_run ? stamp(localTime(t.last_run)) : ''),
      h('span', { class: 'c num' }, t.next_run ? stamp(localTime(t.next_run)) : ''),
      h('span', { class: 'c', style: t.last_status === 'failed' ? 'color:var(--danger)' : null }, t.last_status || ''),
      sw(!!t.enabled, async (on) => {
        try { await post(`/api/tasks/${encodeURIComponent(t.name)}`, { enabled: on }); } catch (e) { toast(e.message); }
        refresh();
      }),
    )));
  },

  detail: (i) => {
    const job = i.job_id ? jobOf(i.job_id) : null;
    const ran = job ? [job.started_at, job.finished_at].filter(Boolean).map((t) => clock(localTime(t))).join(' – ') : '';
    return [
      h('h2', null, i.title),
      dateLine(`${dayLabel(i.when)} ${clock(i.when)}`),
      job ? h('div', { class: 'stamp num' }, [job.task, job.kind, job.status, ran].filter(Boolean).join(' · ')) : null,
      job && job.result ? h('div', { class: 'prose', html: md(job.result) }) : null,
      job && job.error ? h('pre', { class: 'mono', style: 'margin:0 0 12px;white-space:pre-wrap' }, job.error) : null,
      ...(job && job.logs ? job.logs.map((l) => h('div', { class: 'stamp num' }, `${clock(localTime(l.ts))} ${l.message}`)) : []),
    ];
  },
};
