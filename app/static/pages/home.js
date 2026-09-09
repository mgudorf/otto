// Home: LEFT = what waits on a decision, then today per module · MIDDLE blank = one number per module.
import { html, T, mono13, Row, ModuleHeader, Icon, Empty, dayLabel, fmtInt } from '../rows.js';
import { get, post } from '../api.js';
import { Inspector } from '../shell.js';

export async function load() {
  const [left, numbers] = await Promise.all([get('/api/home/left'), get('/api/home/numbers')]);
  return { left, numbers };
}

export function meta() {
  return dayLabel();
}

export function Left({ app, data, fmt }) {
  const sel = app.state.sel;
  return html`<div style=${{ display: 'flex', flexDirection: 'column', gap: 20 }}>
    <span style=${{ ...mono13, color: T.dim, padding: '0 12px' }}>${dayLabel()}</span>
    ${data.left.groups.length === 0 && html`<${Empty} text="no modules report today" />`}
    ${data.left.groups.map((g) => html`<div key=${`${g.label}:${g.module}`} style=${{ display: 'flex', flexDirection: 'column', gap: 2 }}>
      <${ModuleHeader} label=${g.label} count=${g.count} hue=${g.hue} icon=${g.icon} onClick=${() => app.go(g.module)} />
      ${g.rows.length === 0 && html`<${Empty} text="nothing today" />`}
      ${g.rows.map((r) => html`<${Row} key=${r.id} row=${r} hue=${g.hue} fmt=${fmt} selected=${!!sel && sel.module === r.module && String(sel.id) === String(r.id)} onSelect=${() => app.select({ module: r.module, id: r.id })} />`)}
      ${g.more > 0 && html`<div class="dim-hover" onClick=${() => app.go(g.module)} style=${{ display: 'flex', alignItems: 'center', height: 32, padding: '0 12px', ...mono13, color: T.dim, cursor: 'pointer', borderRadius: 6 }}>+${g.more}</div>`}
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
      if (a.verb === 'forget') app.select(null);
      app.refresh();
    }} />`;
  }
  if (data.numbers.length === 0) return html`<div style=${{ ...mono13, color: T.dim }}>no module reports a number yet</div>`;
  return html`<div style=${{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(140px, 1fr))', gap: '40px 32px', maxWidth: 640, margin: '0 auto' }}>
    ${data.numbers.map((n) => html`<div key=${n.module} onClick=${() => app.go(n.module)} style=${{ display: 'flex', flexDirection: 'column', gap: 4, cursor: 'pointer' }}>
      <span style=${{ fontFamily: T.mono, fontSize: 28, lineHeight: 1.1, fontWeight: 500 }}>${fmtInt(n.value)}</span>
      <span style=${{ display: 'flex', alignItems: 'center', gap: 6, fontSize: 13, color: T.muted }}><${Icon} svg=${n.icon} color=${n.hue} />${n.label}</span>
    </div>`)}
  </div>`;
}
