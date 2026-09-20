// The tag map: nodes are tags sized by how much carries them, edges are co-occurrence and the owner's curated links.
// The selection is the search bar's tag tokens, an intersection, so it follows the owner into every module's list.
import { S, h, renderAll } from './core.js';

const MAPW = 960, MAPH = 600;
let cache = null;

// One line per pair: a curated link and a co-occurrence between the same two tags are one edge, the heavier weight.
export function graphData(raw) {
  const nodes = (raw && raw.nodes) || [];
  const tags = nodes.map((n) => ({ tag: n.tag, count: Number(n.count) || 0 }));
  const has = new Set(tags.map((t) => t.tag));
  const pairs = {};
  for (const e of (raw && raw.edges) || []) {
    if (!has.has(e.a) || !has.has(e.b)) continue;
    const k = `${e.a}|${e.b}`;
    pairs[k] = Math.max(pairs[k] || 0, Number(e.weight) || 1);
  }
  const edges = Object.entries(pairs).map(([k, w]) => { const [a, b] = k.split('|'); return { a, b, w }; });
  const key = `${tags.map((t) => `${t.tag}:${t.count}`).join(',')}|${edges.map((e) => `${e.a}${e.b}${e.w}`).join(',')}`;
  if (!cache || cache.key !== key) cache = { key, tags, edges, pos: layout(tags, edges) };
  return cache;
}

// A small spring layout: linked tags pull together, every tag pushes every other apart, all drift to the middle. Deterministic.
function layout(nodes, edges) {
  const N = nodes.length;
  const idx = Object.fromEntries(nodes.map((n, i) => [n.tag, i]));
  const pos = nodes.map((n, i) => { const a = (i / Math.max(N, 1)) * Math.PI * 2; return { x: MAPW / 2 + Math.cos(a) * MAPW * 0.32, y: MAPH / 2 + Math.sin(a) * MAPH * 0.34, vx: 0, vy: 0 }; });
  for (let it = 0; it < 320; it++) {
    const t = 1 - it / 320;
    for (let i = 0; i < N; i++) for (let j = i + 1; j < N; j++) {
      let dx = pos[j].x - pos[i].x, dy = pos[j].y - pos[i].y;
      const d2 = dx * dx + dy * dy + 1, d = Math.sqrt(d2), f = 11000 / d2;
      dx /= d; dy /= d;
      pos[i].vx -= dx * f; pos[i].vy -= dy * f; pos[j].vx += dx * f; pos[j].vy += dy * f;
    }
    for (const e of edges) {
      const a = pos[idx[e.a]], b = pos[idx[e.b]];
      let dx = b.x - a.x, dy = b.y - a.y;
      const d = Math.sqrt(dx * dx + dy * dy) + 0.01, rest = 150 - Math.min(e.w, 6) * 10, f = (d - rest) * 0.015 * Math.min(e.w, 4);
      dx /= d; dy /= d;
      a.vx += dx * f; a.vy += dy * f; b.vx -= dx * f; b.vy -= dy * f;
    }
    for (const p of pos) {
      p.vx += (MAPW / 2 - p.x) * 0.007; p.vy += (MAPH / 2 - p.y) * 0.009;
      p.x += p.vx * t * 0.5; p.y += p.vy * t * 0.5; p.vx *= 0.55; p.vy *= 0.55;
      p.x = Math.max(70, Math.min(MAPW - 70, p.x)); p.y = Math.max(30, Math.min(MAPH - 30, p.y));
    }
  }
  return pos;
}

export function neighbours(tag, edges) {
  return edges.filter((e) => e.a === tag || e.b === tag).map((e) => ({ tag: e.a === tag ? e.b : e.a, w: e.w })).sort((x, y) => y.w - x.w || x.tag.localeCompare(y.tag));
}

// The selection lives in the search bar, so it follows you into every module's list.
export const gsel = () => S.tokens.filter((t) => t.kind === 'tag').map((t) => t.value);
// core remembers the page's tokens on its own moves; picking a tag on the map is one of them.
function remember() { try { history.replaceState({ page: S.page, tokens: S.tokens.map((t) => ({ ...t })), sel: S.sel, gpreview: S.gpreview }, '', `#/${S.page}`); } catch { /* a file:// window has no history */ } }
// The pick itself, for a caller already inside a render; gset is the same pick from outside one.
export function gtokens(tags) {
  S.tokens = [...S.tokens.filter((t) => t.kind !== 'tag'), ...tags.map((v) => ({ kind: 'tag', value: v }))];
  remember();
}
export function gset(tags) { S.gpreview = null; gtokens(tags); renderAll(); }
export function gclick(tag, e) {
  const sel = gsel(), add = e && (e.ctrlKey || e.metaKey);
  if (add && e.shiftKey) gset(sel.filter((t) => t !== tag));
  else if (add) gset(sel.includes(tag) ? sel : [...sel, tag]);
  else gset(sel.length === 1 && sel[0] === tag ? [] : [tag]);
}

// Tags adjacent to every selected tag (all) and to any of them (any), with how many they touch (deg).
export function gnear(g) {
  const sel = gsel(), deg = {};
  for (const t of sel) for (const n of neighbours(t, g.edges)) if (!sel.includes(n.tag)) deg[n.tag] = (deg[n.tag] || 0) + 1;
  const any = new Set(Object.keys(deg)), all = new Set(Object.keys(deg).filter((t) => deg[t] === sel.length));
  return { any, all, deg };
}

export function mapEl(g) {
  const { tags, edges, pos } = g;
  const idx = Object.fromEntries(tags.map((t, i) => [t.tag, i]));
  const sel = new Set(gsel()), has = sel.size > 0, many = sel.size > 1;
  const { any, all } = gnear(g);
  const r = (t) => Math.round(5 + Math.sqrt(t.count) * 2.4);
  const lines = edges.map((e) => {
    const p = pos[idx[e.a]], q = pos[idx[e.b]];
    const sa = sel.has(e.a), sb = sel.has(e.b);
    let cls = 'edge';
    if (has) {
      if (sa && sb) cls = 'edge hot shared';
      else if (many && ((sa && all.has(e.b)) || (sb && all.has(e.a)))) cls = 'edge hot shared';
      else if (sa || sb) cls = 'edge hot';
      else cls = 'edge far';
    }
    return `<line class="${cls}" x1="${p.x.toFixed(1)}" y1="${p.y.toFixed(1)}" x2="${q.x.toFixed(1)}" y2="${q.y.toFixed(1)}" stroke-width="${Math.min(4, 0.8 + e.w * 0.6).toFixed(1)}" vector-effect="non-scaling-stroke"></line>`;
  }).join('');
  const box = h('div', { class: 'map-box', html: `<svg viewBox="0 0 ${MAPW} ${MAPH}" preserveAspectRatio="none">${lines}</svg>` });
  tags.forEach((t, i) => {
    const p = pos[i], rad = r(t);
    const role = sel.has(t.tag) ? 'focus' : many && all.has(t.tag) ? 'near shared' : any.has(t.tag) ? 'near' : has ? 'far' : '';
    box.append(h('div', { class: ['gnode', role, p.x > MAPW * 0.8 ? 'left' : ''].filter(Boolean).join(' '), 'data-tag': t.tag, style: `left:${(p.x / MAPW * 100).toFixed(2)}%;top:${(p.y / MAPH * 100).toFixed(2)}%` },
      h('span', { class: 'dot', style: `width:${rad * 2}px;height:${rad * 2}px` }), h('span', { class: 'lbl' }, t.tag, h('span', { class: 'n' }, ` ${t.count}`))));
  });
  box.addEventListener('click', (e) => { const n = e.target.closest('[data-tag]'); if (n && !S.point) gclick(n.dataset.tag, e); });
  return box;
}
