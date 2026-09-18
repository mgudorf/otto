// Home: LEFT = what waits on a decision, then today per module · MIDDLE blank = one number per module.
import { html, T, meta13, nums, Row, ModuleHeader, Icon, Empty, dayLabel, fmtInt } from '../rows.js';
import { get, post } from '../api.js';
import { Inspector } from '../shell.js';

export async function load() {
  const [left, numbers] = await Promise.all([get('/api/home/left'), get('/api/home/numbers')]);
  return { left, numbers };
}

export function Left({ app, data }) {
  const sel = app.state.sel;
  return html`<div style=${{ display: 'flex', flexDirection: 'column', gap: 20 }}>
    <span style=${{ ...meta13, ...nums, color: T.dim, padding: '0 12px' }}>${dayLabel()}</span>
    ${data.left.groups.length === 0 && html`<${Empty} text="nothing today" />`}
    ${data.left.groups.map((g) => html`<div key=${`${g.label}:${g.module}`} style=${{ display: 'flex', flexDirection: 'column', gap: 4 }}>
      <${ModuleHeader} label=${g.label} hue=${g.hue} icon=${g.icon} onClick=${g.page ? () => app.go(g.module) : null} />
      ${g.rows.length === 0 && html`<${Empty} text="nothing today" />`}
      ${g.rows.map((r) => html`<${Row} key=${r.id} row=${r} hue=${g.hue} selected=${!!sel && sel.module === r.module && String(sel.id) === String(r.id)} onSelect=${() => app.select({ module: r.module, id: r.id })} />`)}
      ${g.more > 0 && html`<div class=${g.page ? 'dim-hover' : ''} onClick=${g.page ? () => app.go(g.module) : null} style=${{ display: 'flex', alignItems: 'center', height: 32, padding: '0 12px', ...meta13, color: T.dim, cursor: g.page ? 'pointer' : 'default', borderRadius: 6 }}>+${g.more}</div>`}
    </div>`)}
  </div>`;
}

export function Middle({ app, data, mod, fmt }) {
  if (app.state.sel) {
    return html`<${Inspector} app=${app} item=${app.state.item} mod=${mod} fmt=${fmt} onAction=${async (a) => {
      const item = app.state.item;
      if (a.href) { window.open(a.href, '_blank'); return; }
      if (a.confirm && !window.confirm(a.confirm)) return;
      await post(`/api/${item.module}/action/${a.verb}`, { id: item.id });
      if (a.removes) app.select(null);
      app.refresh();
    }} />`;
  }
  if (data.numbers.length === 0) return null;
  return html`<div style=${{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(140px, 1fr))', gap: '40px 32px', maxWidth: 640, margin: '0 auto' }}>
    ${data.numbers.map((n) => html`<div key=${n.module} onClick=${n.page ? () => app.go(n.module) : null} style=${{ display: 'flex', flexDirection: 'column', gap: 4, cursor: n.page ? 'pointer' : 'default' }}>
      <span style=${{ fontSize: 28, lineHeight: 1.1, fontWeight: 500, ...nums }}>${fmtInt(n.value)}</span>
      <span style=${{ display: 'flex', alignItems: 'center', gap: 6, fontSize: 13, color: T.muted }}><${Icon} svg=${n.icon} color=${n.hue} />${n.label}</span>
    </div>`)}
  </div>`;
}
