// Finance: LEFT = kind chips + one group per kind, amount in the stamp slot · MIDDLE blank = totals and capture form.
import { html, T, mono13, Row, GroupHeader, Chips, Search, Button, Empty, fmtInt, stamp } from '../rows.js';
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

export function meta(app) {
  const c = app.state.data && app.state.data.blank.counts;
  if (!c) return '';
  return `${fmtInt(Object.values(c).reduce((a, b) => a + b, 0))} records`;
}

export function Left({ app, data, mod, fmt }) {
  const sel = app.state.sel;
  const rerun = (patch) => app.setState(patch, () => app.refresh());
  return html`<div style=${{ display: 'flex', flexDirection: 'column', gap: 20 }}>
    <${Search} value=${app.state.query} hue=${mod.hue} onInput=${(v) => rerun({ query: v })} />
    <${Chips} chips=${data.left.chips} active=${data.left.chip} hue=${mod.hue} onPick=${(c) => rerun({ chip: c })} />
    ${data.left.groups.length === 0 && html`<${Empty} text=${app.state.query ? 'no matches' : 'nothing entered yet'} />`}
    ${data.left.groups.map((g) => html`<div key=${g.label} style=${{ display: 'flex', flexDirection: 'column', gap: 2 }}>
      <${GroupHeader} label=${g.label} count=${g.count} />
      ${g.rows.map((r) => html`<${Row} key=${r.id} row=${r} hue=${mod.hue} fmt=${fmt} selected=${!!sel && String(sel.id) === String(r.id)} onSelect=${() => app.select({ module: 'finance', id: r.id })} />`)}
    </div>`)}
  </div>`;
}

const capture = { kind: 'account', name: '', amount: '', cadence: 'monthly', note: '' };
let amountDraft = '';

const input = (hue, extra = {}) => ({ height: 30, padding: '0 10px', border: 0, borderRadius: 6, background: T.panel, color: T.text, fontSize: 13, '--hue': hue, ...extra });

export function Middle({ app, data, mod, fmt }) {
  const hue = mod.hue;
  if (app.state.sel) {
    const item = app.state.item;
    const act = async (a) => {
      if (a.verb === 'update') {
        if (!amountDraft.trim()) return;
        await post('/api/finance/action/update', { id: item.id, amount: amountDraft.trim() });
        amountDraft = '';
      } else {
        if (a.confirm && !window.confirm(a.confirm)) return;
        await post(`/api/finance/action/${a.verb}`, { id: item.id });
      }
      if (a.verb === 'forget') app.select(null); else app.loadItem(app.state.sel);
      app.refresh();
    };
    const body = item && !item.error ? html`<div style=${{ display: 'flex', flexDirection: 'column', gap: 12 }}>
      <div style=${{ display: 'flex', alignItems: 'center', gap: 8, ...mono13, color: T.muted }}>
        <span>new amount</span>
        <input placeholder=${money(item.amount)} value=${amountDraft} onInput=${(e) => { amountDraft = e.target.value; }}
          onKeyDown=${(e) => { if (e.key === 'Enter') act({ verb: 'update' }); }}
          style=${input(hue, { width: 140, fontFamily: T.mono })} />
        ${item.ended_at && html`<span style=${{ color: T.dim }}>ended ${stamp(item.ended_at, fmt)}</span>`}
      </div>
      <div style=${{ display: 'flex', flexDirection: 'column', gap: 2 }}>
        <${GroupHeader} label="history" count=${item.history.length} />
        ${item.history.map((h) => html`<div key=${h.ts} style=${{ display: 'flex', alignItems: 'center', gap: 12, height: 32, padding: '0 12px', ...mono13 }}>
          <span style=${{ color: T.text }}>${money(h.amount)}</span><span style=${{ marginLeft: 'auto', color: T.dim }}>${stamp(h.ts, fmt)}</span>
        </div>`)}
      </div>
    </div>` : null;
    return html`<${Inspector} app=${app} item=${item} mod=${mod} fmt=${fmt} onAction=${act}>${body}<//>`;
  }
  const b = data.blank;
  const needsCadence = capture.kind === 'recurring' || capture.kind === 'budget';
  const save = async () => {
    if (!capture.name.trim() || !capture.amount.trim()) return;
    await post('/api/finance/action/capture', { kind: capture.kind, name: capture.name.trim(), amount: capture.amount.trim(), cadence: capture.cadence, note: capture.note.trim() });
    capture.name = ''; capture.amount = ''; capture.note = '';
    app.refresh();
  };
  const onKey = (e) => { if (e.key === 'Enter' && (e.ctrlKey || e.metaKey)) { e.preventDefault(); save(); } };
  const numbers = [
    ['accounts', b.totals.accounts], ['holdings', b.totals.holdings],
    ['recurring /mo', b.totals.monthly_recurring], ['budget /mo', b.totals.monthly_budget],
  ];
  return html`<div style=${{ display: 'flex', flexDirection: 'column', gap: 28, maxWidth: 720 }}>
    <div style=${{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(140px, 1fr))', gap: '24px 32px' }}>
      ${numbers.map(([label, cents]) => html`<div key=${label} style=${{ display: 'flex', flexDirection: 'column', gap: 4 }}>
        <span style=${{ fontFamily: T.mono, fontSize: 28, lineHeight: 1.1, fontWeight: 500 }}>${money(cents)}</span>
        <span style=${{ fontSize: 13, color: T.muted }}>${label}</span>
      </div>`)}
    </div>
    <div style=${{ display: 'flex', flexDirection: 'column', gap: 12 }}>
      <div style=${{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
        ${b.kinds.map((k) => html`<span key=${k} class="ring" onClick=${() => { capture.kind = k; app.forceUpdate(); }} style=${{ padding: '3px 9px', borderRadius: 6, fontSize: 13, cursor: 'pointer', background: capture.kind === k ? hue : 'transparent', color: capture.kind === k ? T.ground : T.muted }}>${k}</span>`)}
        <span style=${{ marginLeft: 'auto', ...mono13, color: T.dim }}>${Object.entries(b.counts).map(([k, n]) => `${n} ${k}`).join(' · ') || 'empty'}</span>
      </div>
      <div style=${{ display: 'flex', gap: 8 }}>
        <input placeholder="name" value=${capture.name} onInput=${(e) => { capture.name = e.target.value; }} onKeyDown=${onKey} style=${input(hue, { flex: 1, fontSize: 15 })} />
        <input placeholder="amount" value=${capture.amount} onInput=${(e) => { capture.amount = e.target.value; }} onKeyDown=${onKey} style=${input(hue, { width: 140, fontFamily: T.mono })} />
      </div>
      ${needsCadence && html`<div style=${{ display: 'flex', alignItems: 'center', gap: 8 }}>
        ${b.cadences.map((c) => html`<span key=${c} class="ring" onClick=${() => { capture.cadence = c; app.forceUpdate(); }} style=${{ padding: '3px 9px', borderRadius: 6, fontSize: 13, cursor: 'pointer', background: capture.cadence === c ? hue : 'transparent', color: capture.cadence === c ? T.ground : T.muted }}>${c}</span>`)}
        <span style=${{ ...mono13, color: T.dim }}>${SUFFIX[capture.cadence]}</span>
      </div>`}
      <input placeholder="note" value=${capture.note} onInput=${(e) => { capture.note = e.target.value; }} onKeyDown=${onKey} style=${input(hue)} />
      <div style=${{ display: 'flex', alignItems: 'center', gap: 8 }}>
        <${Button} label="Save" primary=${true} hue=${hue} onClick=${save} />
        <span style=${{ ...mono13, color: T.dim }}>ctrl+enter</span>
      </div>
    </div>
  </div>`;
}
