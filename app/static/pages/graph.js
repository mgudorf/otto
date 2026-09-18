// Graph: LEFT = tags by count · MIDDLE = ring of nodes with edges; selecting a tag lights its neighbours.
import { html, T, meta13, nums, rowStyle, Search, Empty, More } from '../rows.js';
import { get } from '../api.js';

export async function load(app) {
  const { query, more } = app.state;
  const q = new URLSearchParams({ query, page: String(more) });
  const [left, graph] = await Promise.all([get(`/api/graph/left?${q}`), get(`/api/graph/graph?${q}`)]);
  return { left, graph };
}

function neighbours(graph, tag) {
  const s = new Set();
  if (!tag) return s;
  for (const e of graph.edges) {
    if (e.a === tag) s.add(e.b);
    else if (e.b === tag) s.add(e.a);
  }
  return s;
}

export function Left({ app, data, mod }) {
  const selTag = app.state.sel && app.state.sel.id;
  const near = neighbours(data.graph, selTag);
  const g = data.left.groups[0];
  const rerun = (patch) => app.setState(patch, () => app.refresh());
  return html`<div style=${{ display: 'flex', flexDirection: 'column', gap: 4 }}>
    <${Search} value=${app.state.query} hue=${mod.hue} onInput=${(v) => rerun({ query: v, more: 0, sel: null, item: null })} />
    ${g.rows.length === 0 && html`<${Empty} text=${app.state.query ? 'no matches' : 'nothing tagged yet'} />`}
    ${g.rows.map((r) => {
      const on = r.id === selTag, nb = near.has(r.id);
      return html`<div class="row" key=${r.id} onClick=${() => app.select({ module: 'graph', id: r.id, local: r })} style=${rowStyle({ selected: on, hue: mod.hue, height: 32 })}>
        <span style=${{ minWidth: 0, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis', color: nb ? mod.hue : 'inherit' }}>${r.text}</span>
        <span style=${{ flex: 'none', marginLeft: 'auto', ...meta13, ...nums, color: T.dim }}>${r.count}</span>
      </div>`;
    })}
    ${data.left.more && html`<${More} onClick=${() => rerun({ more: app.state.more + 1 })} />`}
  </div>`;
}

// Ring layout in the artboard's 800x560 box: angle by position, radius by a hash of the tag so nodes stay put.
function hash(s) {
  let h = 0;
  for (let i = 0; i < s.length; i++) h = (h * 31 + s.charCodeAt(i)) >>> 0;
  return h;
}

function layout(nodes) {
  const n = nodes.length;
  return nodes.map((nd, i) => {
    const a = (i / n) * Math.PI * 2, rad = 150 + (hash(nd.tag) % 100), r = 5 + Math.round(nd.count / 40);
    return { ...nd, x: Math.round(400 + Math.cos(a) * rad * 1.1), y: Math.round(280 + Math.sin(a) * rad * 0.8), r };
  });
}

export function Middle({ app, data, mod }) {
  const hue = mod.hue;
  const selTag = app.state.sel && app.state.sel.id;
  const near = neighbours(data.graph, selTag);
  const nodes = layout(data.graph.nodes);
  if (nodes.length === 0) return html`<${Empty} text=${app.state.query ? 'no matches' : 'nothing tagged yet'} />`;
  const pos = Object.fromEntries(nodes.map((n) => [n.tag, n]));
  return html`<div style=${{ height: '100%', minHeight: 420, display: 'flex', flexDirection: 'column', gap: 12 }}>
    <div style=${{ display: 'flex', alignItems: 'center', gap: 12, height: 24, ...meta13, ...nums, color: T.dim }}>
      <span>${selTag ? `${selTag} · ${near.size} linked` : ''}</span>
      <span class="bright-hover" onClick=${() => app.select(null)} style=${{ marginLeft: 'auto', cursor: 'pointer', padding: '0 4px', lineHeight: 1, color: selTag ? T.dim : 'transparent' }}>×</span>
    </div>
    <div style=${{ flex: 1, minHeight: 0, position: 'relative' }}>
      <svg viewBox="0 0 800 560" preserveAspectRatio="none" style=${{ position: 'absolute', inset: 0, width: '100%', height: '100%' }}>
        ${data.graph.edges.map((e) => {
          const A = pos[e.a], B = pos[e.b];
          if (!A || !B) return null;
          const hot = selTag && (e.a === selTag || e.b === selTag);
          return html`<line key=${`${e.a}|${e.b}|${e.kind}`} x1=${A.x} y1=${A.y} x2=${B.x} y2=${B.y} stroke-width="1"
            stroke=${hot ? hue : selTag ? 'rgba(230,231,234,.06)' : 'rgba(230,231,234,.14)'} />`;
        })}
      </svg>
      ${nodes.map((n) => {
        const on = n.tag === selTag, nb = near.has(n.tag), dim = selTag && !on && !nb, right = n.x > 400;
        return html`<div key=${n.tag} onClick=${() => app.select({ module: 'graph', id: n.tag, local: n })}
          style=${{ position: 'absolute', transform: 'translateY(-50%)', display: 'flex', alignItems: 'center', gap: 8, cursor: 'pointer',
            flexDirection: right ? 'row-reverse' : 'row', top: `${(n.y / 5.6).toFixed(2)}%`,
            left: right ? 'auto' : `calc(${(n.x / 8).toFixed(2)}% - ${n.r}px)`, right: right ? `calc(${(100 - n.x / 8).toFixed(2)}% - ${n.r}px)` : 'auto' }}>
          <span style=${{ flex: 'none', borderRadius: '50%', boxSizing: 'border-box', width: n.r * 2, height: n.r * 2,
            border: `1.5px solid ${on || nb ? hue : 'rgba(230,231,234,.3)'}`, background: on ? hue : T.panel }} />
          <span style=${{ ...meta13, whiteSpace: 'nowrap', color: dim ? 'rgba(230,231,234,.25)' : on ? T.text : T.muted }}>${n.tag}</span>
        </div>`;
      })}
    </div>
  </div>`;
}
