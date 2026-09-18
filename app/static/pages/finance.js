// Finance: LEFT = kind chips + one group per kind, amount and next date in the stamp slot · MIDDLE blank = totals, `+` for the capture form.
import { html, T, meta13, nums, Row, GroupHeader, Chips, Search, Empty, Plus, Enter, DateInput, isoDate, dateLabel, dayLabel, stamp, input } from '../rows.js';
import { get, post } from '../api.js';
import { Inspector } from '../shell.js';

const SUFFIX = { monthly: '/mo', yearly: '/yr', weekly: '/wk' };

function money(cents) {
  return (cents / 100).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

export async function load(app) {
  const { query, chip } = app.state;
  const q = new URLSearchParams({ query, chip });
  const [left, blank] = await Promise.all([get(`/api/finance/left?${q}`), get('/api/finance/blank')]);
  return { left, blank };
}

export function Left({ app, data, mod }) {
  const sel = app.state.sel;
  const rerun = (patch) => app.setState(patch, () => app.refresh());
  return html`<div style=${{ display: 'flex', flexDirection: 'column', gap: 20 }}>
    <${Search} value=${app.state.query} hue=${mod.hue} onInput=${(v) => rerun({ query: v })} />
    <${Chips} chips=${data.left.chips} active=${data.left.chip} hue=${mod.hue} onPick=${(c) => rerun({ chip: c })} />
    ${data.left.groups.length === 0 && html`<${Empty} text=${app.state.query ? 'no matches' : 'nothing entered yet'} />`}
    ${data.left.groups.map((g) => html`<div key=${g.label} style=${{ display: 'flex', flexDirection: 'column', gap: 4 }}>
      <${GroupHeader} label=${g.label} />
      ${g.rows.map((r) => html`<${Row} key=${r.id} row=${r} hue=${mod.hue} selected=${!!sel && String(sel.id) === String(r.id)} onSelect=${() => app.select({ module: 'finance', id: r.id })} />`)}
    </div>`)}
  </div>`;
}

const capture = { open: false, kind: 'account', name: '', amount: '', cadence: 'monthly', note: '', due_on: '' };   // due_on as typed, DD-MM-YYYY
let amountDraft = '';
let dueDraft = { id: null, from: '', value: '' };   // follows the entry and the date it was synced from, so a write lands back in the box

export function Middle({ app, data, mod, fmt }) {
  const hue = mod.hue;
  const chip = (label, on, onClick) => html`<span key=${label} class="ring" onClick=${onClick} style=${{ padding: '3px 9px', borderRadius: 6, fontSize: 13, cursor: 'pointer', background: on ? hue : 'transparent', color: on ? T.ground : T.muted }}>${label}</span>`;
  if (app.state.sel) {
    const item = app.state.item;
    const stored = (item && item.due_on) || '';
    if (item && (dueDraft.id !== item.id || dueDraft.from !== stored)) dueDraft = { id: item.id, from: stored, value: dateLabel(stored) };
    const act = async (a) => {
      if (a.verb === 'update') {
        if (!amountDraft.trim()) return;
        await post('/api/finance/action/update', { id: item.id, amount: amountDraft.trim() });
        amountDraft = '';
      } else if (a.verb === 'due') {
        const iso = isoDate(dueDraft.value);
        if (iso === null) return;   // still being typed
        await post('/api/finance/action/due', { id: item.id, due_on: iso });
      } else {
        if (a.confirm && !window.confirm(a.confirm)) return;
        await post(`/api/finance/action/${a.verb}`, { id: item.id });
      }
      if (a.removes) app.select(null); else app.loadItem(app.state.sel);
      app.refresh();
    };
    const body = item && !item.error ? html`<div style=${{ display: 'flex', flexDirection: 'column', gap: 12 }}>
      <div style=${{ display: 'flex', alignItems: 'center', gap: 8, ...meta13, color: T.muted }}>
        <span>amount</span>
        <input placeholder=${money(item.amount)} value=${amountDraft} onInput=${(e) => { amountDraft = e.target.value; }}
          onKeyDown=${(e) => { if (e.key === 'Enter') act({ verb: 'update' }); }} style=${input(hue, { width: 116, ...nums })} />
        ${item.ended_at && html`<span style=${{ color: T.dim }}>ended ${stamp(item.ended_at, fmt)}</span>`}
      </div>
      ${item.kind === 'recurring' && html`<div style=${{ display: 'flex', alignItems: 'center', gap: 8, ...meta13, color: T.muted }}>
        <span>due</span>
        <${DateInput} value=${dueDraft.value} hue=${hue} onInput=${(v) => { dueDraft = { id: item.id, from: stored, value: v }; app.forceUpdate(); }} onEnter=${() => act({ verb: 'due' })} />
      </div>`}
      <div style=${{ display: 'flex', flexDirection: 'column', gap: 2 }}>
        <${GroupHeader} label="history" />
        ${item.history.map((h) => html`<div key=${h.ts} style=${{ display: 'flex', alignItems: 'center', gap: 12, height: 32, padding: '0 12px', ...meta13, ...nums }}>
          <span style=${{ color: T.text }}>${money(h.amount)}</span><span style=${{ marginLeft: 'auto', color: T.dim }}>${dayLabel(h.ts)}</span>
        </div>`)}
      </div>
    </div>` : null;
    return html`<${Inspector} app=${app} item=${item} mod=${mod} fmt=${fmt} onAction=${act}>${body}<//>`;
  }
  const b = data.blank;
  const needsCadence = capture.kind === 'recurring' || capture.kind === 'budget';
  const save = async () => {
    if (!capture.name.trim() || !capture.amount.trim()) return;
    const due = capture.kind === 'recurring' ? isoDate(capture.due_on) : '';
    if (due === null) return;   // still being typed
    await post('/api/finance/action/capture', { kind: capture.kind, name: capture.name.trim(), amount: capture.amount.trim(), cadence: capture.cadence, note: capture.note.trim(), due_on: due });
    capture.name = ''; capture.amount = ''; capture.note = ''; capture.due_on = ''; capture.open = false;
    app.refresh();
  };
  const onKey = (e) => {
    if (e.key === 'Enter') save();
    if (e.key === 'Escape') { capture.open = false; app.forceUpdate(); }
  };
  const numbers = [
    ['accounts', b.totals.accounts], ['holdings', b.totals.holdings],
    ['recurring /mo', b.totals.monthly_recurring], ['budget /mo', b.totals.monthly_budget],
  ];
  return html`<div style=${{ display: 'flex', flexDirection: 'column', gap: 28 }}>
    <div style=${{ display: 'flex', alignItems: 'flex-start', gap: 12 }}>
      <div style=${{ flex: 1, display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(140px, 1fr))', gap: '24px 32px', maxWidth: 720 }}>
        ${numbers.map(([label, cents]) => html`<div key=${label} style=${{ display: 'flex', flexDirection: 'column', gap: 4 }}>
          <span style=${{ fontSize: 28, lineHeight: 1.1, fontWeight: 500, ...nums }}>${money(cents)}</span>
          <span style=${{ fontSize: 13, color: T.muted }}>${label}</span>
        </div>`)}
      </div>
      <${Plus} title="new entry" active=${capture.open} onClick=${() => { capture.open = !capture.open; app.forceUpdate(); }} />
    </div>
    ${capture.open && html`<div style=${{ display: 'flex', flexDirection: 'column', gap: 12 }}>
      <div style=${{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
        ${b.kinds.map((k) => chip(k, capture.kind === k, () => { capture.kind = k; app.forceUpdate(); }))}
      </div>
      <div style=${{ display: 'flex', gap: 8 }}>
        <input autofocus placeholder="name" value=${capture.name} onInput=${(e) => { capture.name = e.target.value; }} onKeyDown=${onKey} style=${input(hue, { flex: 1, fontSize: 15 })} />
        <input placeholder="amount" value=${capture.amount} onInput=${(e) => { capture.amount = e.target.value; }} onKeyDown=${onKey} style=${input(hue, { width: 116, ...nums })} />
      </div>
      ${needsCadence && html`<div style=${{ display: 'flex', alignItems: 'center', gap: 8 }}>
        ${b.cadences.map((c) => chip(c, capture.cadence === c, () => { capture.cadence = c; app.forceUpdate(); }))}
        <span style=${{ ...meta13, color: T.dim }}>${SUFFIX[capture.cadence]}</span>
        ${capture.kind === 'recurring' && html`<div style=${{ display: 'flex', alignItems: 'center', gap: 8, marginLeft: 'auto', ...meta13, color: T.muted }}>due
          <${DateInput} value=${capture.due_on} hue=${hue} onInput=${(v) => { capture.due_on = v; app.forceUpdate(); }} onEnter=${save} />
        </div>`}
      </div>`}
      <div style=${{ display: 'flex', alignItems: 'center', gap: 8 }}>
        <input placeholder="note" value=${capture.note} onInput=${(e) => { capture.note = e.target.value; }} onKeyDown=${onKey} style=${input(hue, { flex: 1 })} />
        <${Enter} onClick=${save} />
      </div>
    </div>`}
  </div>`;
}
