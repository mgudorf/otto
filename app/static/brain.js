// The brain: a figure of dots and a galaxy of tags. The figure is a brain-shaped surface sampled evenly, each dot shaded by
// the facet whose lobe is nearest. One node per immutable tag, which is a facet's, at its lobe; every other tag placed by
// the facets its items belong to (near one, between two, among three or more), its edges to them drawn only while it is
// picked, pointed at, or the open item's. A callout per facet at a fixed place on a ring outside the figure, its leader
// following the lobe; up to nine pinned tags get numbered callouts in the gaps, their number keys toggling them. Picking a
// facet zooms into its cluster: the facet
// at the centre, its tags as a point cloud, every dot a real tag, the ten that matter most in the current mode named in
// words. Both views turn slowly and never stop. Positions come from hashes, so a tag sits where it sat.
import { S, ITEMS, $, h, modOf, hue, tagsOf, addToken, removeToken, registerBrain, isFixed, fixedIcon, FIXED_ORDER, FIXED_MOD, toast, savePins } from './core.js';

const rad = (d) => d * Math.PI / 180;
const unit = (th, ph) => [Math.cos(rad(ph)) * Math.sin(rad(th)), Math.sin(rad(ph)), Math.cos(rad(ph)) * Math.cos(rad(th))];
const norm = (v) => { const l = Math.hypot(v[0], v[1], v[2]) || 1; return [v[0] / l, v[1] / l, v[2] / l]; };
const dot = (a, b) => a[0] * b[0] + a[1] * b[1] + a[2] * b[2];
// Where each facet sits on the figure: a heading around the vertical axis (0 is the front) and an elevation. Entry and
// finance on the frontal lobe either side of the fissure, chats and email on the temporal lobes, education and science
// on the parietal lobes, newsfeed on the occipital lobe, database on the cerebellum, routine on the stem.
const LOBES = { entry: [25, 40], finance: [-25, 40], chats: [-71, -25], email: [71, -25], education: [-140, 40], science: [140, 40], newsfeed: [180, 12], database: [180, -36], routine: [180, -79] };
const FACETS = Object.keys(LOBES);
const LOBE_U = Object.fromEntries(FACETS.map((t) => [t, unit(...LOBES[t])]));
function hash(s) { let x = 2166136261; for (const c of String(s)) { x ^= c.charCodeAt(0); x = Math.imul(x, 16777619); } return x >>> 0; }
const frac = (s) => (hash(s) & 0xffff) / 0xffff;

// ---- the figure: longer than wide and flatter below; two hemispheres parted by the fissure along the top, the cerebellum
// a raised cap under the back, a temporal lobe a raised cap under each side, each cap rimmed by a seam, and a stem below.
// `radius` is how far the surface lies from the centre in a direction; a seam carries no dots.
const CEREBELLUM = { u: norm([0, -0.55, -0.75]), a: 0.5 }, TEMPORAL = [{ u: norm([1, -0.5, 0.35]), a: 0.55 }, { u: norm([-1, -0.5, 0.35]), a: 0.55 }];
const STEM = { u: norm([0, -1, -0.2]), a: 0.17 };
const ang = (n, u) => Math.acos(Math.max(-1, Math.min(1, dot(n, u))));
const cap = (n, c) => 1 / (1 + Math.exp((ang(n, c.u) - c.a) / 0.05));   // 1 inside the cap, 0 outside, soft at the rim
const rim = (n, c) => Math.exp(-(((ang(n, c.u) - c.a) / 0.06) ** 2));
const fissure = (n) => Math.exp(-((n[0] / 0.13) ** 2)) * Math.max(0, Math.min(1, n[1] * 3));
const seam = (n) => (Math.abs(n[0]) < 0.035 && n[1] > 0.12) || [CEREBELLUM, ...TEMPORAL].some((c) => Math.abs(ang(n, c.u) - c.a) < 0.025);
function radius(n) {
  const ry = 0.46 + 0.26 * (0.5 + 0.5 * Math.tanh(5 * n[1]));   // flat below, domed above
  let r = 1 / Math.sqrt((n[0] / 0.84) ** 2 + (n[1] / ry) ** 2 + n[2] ** 2);
  r *= 1 + 0.05 * n[2];   // fuller at the front than the back
  r *= 1 - 0.14 * fissure(n) + 0.05 * (1 - Math.exp(-((n[0] / 0.3) ** 2))) * Math.max(0, n[1]);   // parted, each half crowned
  r *= 1 + 0.18 * cap(n, CEREBELLUM) - 0.1 * rim(n, CEREBELLUM);
  for (const c of TEMPORAL) r *= 1 + 0.08 * cap(n, c) - 0.07 * rim(n, c);
  r *= 1 + 0.5 * cap(n, STEM);
  return r;
}
const shell = (v, k = 1) => { const n = norm(v), r = radius(n) * k; return [n[0] * r, n[1] * r, n[2] * r]; };
// The dots: directions from a Fibonacci spiral, so they sit evenly; each takes the nearest lobe's hue and swells on a
// gyrus and shrinks in a sulcus, a stripe that meanders around the figure; a seam has none.
const DOTS = [];
{
  const N = 3000, ga = Math.PI * (3 - Math.sqrt(5));
  for (let i = 0; i < N; i++) {
    const y = 1 - 2 * (i + 0.5) / N, rr = Math.sqrt(1 - y * y), a = i * ga, n = [rr * Math.cos(a), y, rr * Math.sin(a)];
    let f = FACETS[0], best = -2;
    for (const t of FACETS) { const d = dot(n, LOBE_U[t]); if (d > best) { best = d; f = t; } }
    if (seam(n)) continue;
    const u = Math.atan2(n[2], n[0]), fold = Math.sin(10 * u + 3 * Math.sin(5 * y + 2 * u));
    DOTS.push({ p: shell(n), f, s: 1 + 0.4 * fold });
  }
}
const rgb = (hex) => [1, 3, 5].map((k) => parseInt(hex.slice(k, k + 2), 16));
const mix = (a, b, t) => { const A = rgb(a), B = rgb(b); return `rgb(${A.map((v, i) => Math.round(v + (B[i] - v) * t)).join(',')})`; };
let DOT_COLOR = null;   // the facet hues arrive with the shell, so the dots take their colour on the first frame
const dotColor = () => (DOT_COLOR || (DOT_COLOR = Object.fromEntries(FACETS.map((t) => [t, mix(hue(FIXED_MOD[t]), '#8B92A1', 0.3)]))));
const BAND_ALPHA = [0.05, 0.08, 0.2, 0.34, 0.5];   // by depth, the back of the figure to its front
const SLOT = { entry: -90, chats: -50, email: -10, education: 30, science: 70, finance: 110, newsfeed: 150, database: 190, routine: 230 };   // nine places, 40° apart
const pinSlot = (k) => -70 + 40 * k;   // the gaps between the facets
const MAX_PINS = 9;

let box = null, canvas = null, ctx = null, calloutsEl = null, labelEl = null, wordsEl = null, centerEl = null;
let W = 0, H = 0, dpr = 1, angle = 0.7, still = false, hover = null, raf = 0;
let types = [], tags = [], edges = [], cluster = null, proj = [], calloutEls = {}, pinEls = {}, wordEls = [];
let mode = 'galaxy', trans = null, curType = null;   // the settled view, the zoom in flight, the facet whose cluster is shown
const ease = (p) => (p < 0.5 ? 4 * p * p * p : 1 - Math.pow(-2 * p + 2, 3) / 2);

// ---- the graph, from the items ---------------------------------------------------------------------------------------
const facetOf = (i) => (i.fixed || [])[0];
function typeNodes() {
  return FIXED_ORDER.filter((t) => ITEMS.some((i) => facetOf(i) === t)).map((t) => ({ t, mod: FIXED_MOD[t], count: ITEMS.filter((i) => facetOf(i) === t).length, p: shell(LOBE_U[t]) }));
}
function tagNodes(tn) {
  const at = Object.fromEntries(tn.map((n) => [n.t, n.p])), assoc = {};
  for (const i of ITEMS) { const f = facetOf(i); if (!f) continue; for (const t of i.tags || []) { const a = assoc[t] = assoc[t] || {}; a[f] = (a[f] || 0) + 1; } }
  return Object.entries(assoc).map(([t, byType]) => {
    const total = Object.values(byType).reduce((a, b) => a + b, 0), v = [0, 0, 0];
    for (const [ty, n] of Object.entries(byType)) { const p = at[ty]; if (p) for (let k = 0; k < 3; k++) v[k] += p[k] * n / total; }
    const jit = 0.09, j1 = frac(`${t}/a`) - 0.5, j2 = frac(`${t}/b`) - 0.5, j3 = frac(`${t}/c`) - 0.5;
    const top = Object.entries(byType).sort((x, y) => y[1] - x[1])[0][0];   // the facet most of its items belong to gives the node its colour
    return { t, count: total, byType, hue: hue(FIXED_MOD[top]), p: shell([v[0] + j1 * jit, v[1] + j2 * jit, v[2] + j3 * jit], 0.97 + frac(`${t}/r`) * 0.06) };
  }).sort((a, b) => b.count - a.count || a.t.localeCompare(b.t));
}
// The cluster for one type, a flat map: its tags ranked by what waits (Priority) or by when they last moved (Recent), the
// nearest the centre first, the top ten named.
function clusterOf(type) {
  const items = ITEMS.filter((i) => facetOf(i) === type), score = {};
  for (const i of items) for (const t of i.tags || []) {
    const s = score[t] = score[t] || { t, count: 0, waits: Infinity, when: '' };
    s.count++; if (i.waits) s.waits = Math.min(s.waits, i.waits); if ((i.when || '') > s.when) s.when = i.when || '';
  }
  const list = Object.values(score).sort((a, b) => (S.mode === 'Priority' ? (a.waits - b.waits) || (b.count - a.count) : (b.when > a.when ? 1 : b.when < a.when ? -1 : 0) || (b.count - a.count)));
  const n = Math.max(list.length, 1);
  const pts = list.map((s, k) => { const th = frac(`${type}/${s.t}/t`) * Math.PI * 2, r = 0.42 + 0.58 * (k / n); return { ...s, rank: k, p: [Math.cos(th) * r, Math.sin(th) * r] }; });
  const pairs = new Set(), names = new Set(pts.slice(0, 10).map((s) => s.t));
  for (const i of items) { const mine = (i.tags || []).filter((t) => names.has(t)); for (let a = 0; a < mine.length; a++) for (let b = a + 1; b < mine.length; b++) pairs.add(mine[a] < mine[b] ? `${mine[a]}|${mine[b]}` : `${mine[b]}|${mine[a]}`); }
  return { type, mod: FIXED_MOD[type], pts, links: [...pairs].map((k) => k.split('|')), count: items.length };
}
const typeToken = () => { const t = S.tokens.find((k) => k.kind === 'tag' && isFixed(k.value)); return t ? t.value : null; };

// What is lit: the tokens' tags, the tags the typed text names, and the open item's tags; the view, from the type token.
function sync() {
  if (!box) return;
  types = typeNodes(); tags = tagNodes(types);
  const at = Object.fromEntries(types.map((n) => [n.t, n]));
  edges = [];
  for (const tg of tags) for (const [ty, n] of Object.entries(tg.byType)) if (at[ty]) edges.push({ a: tg, b: at[ty], w: n / tg.count });
  const ty = typeToken(), pick = ty && at[ty] ? ty : null;
  // The zoom starts on the frame clock, so it runs on the same time it is drawn with.
  if (pick !== curType) { trans = { to: pick ? 'cluster' : 'galaxy', start: last || performance.now(), type: pick || curType }; curType = pick; if (pick) cluster = clusterOf(pick); }
  else if (cluster && pick) cluster = clusterOf(pick);
  const tagT = new Set(S.tokens.filter((k) => k.kind === 'tag' && !isFixed(k.value)).map((k) => k.value));
  for (const n of types) {
    const el = calloutEls[n.t]; if (!el) continue;
    const has = !tagT.size || ITEMS.some((i) => facetOf(i) === n.t && [...tagT].every((t) => (i.tags || []).includes(t)));
    el.classList.toggle('on', ty === n.t);
    el.classList.toggle('far', (!!ty && ty !== n.t) || !has);
  }
  for (const [t, el] of Object.entries(calloutEls)) el.hidden = !at[t];
  // Pinned tags: a callout each, numbered by place, named beside it; made when pinned, dropped when unpinned, hidden while
  // the tag has no node.
  const tagAt = Object.fromEntries(tags.map((n) => [n.t, n]));
  for (const t of Object.keys(pinEls)) if (!S.pins.includes(t)) { pinEls[t].remove(); delete pinEls[t]; }
  for (const [k, t] of S.pins.entries()) {
    if (!pinEls[t]) {
      const el = h('div', { class: 'lobe pin', 'aria-label': t },
        h('button', { class: 'mk', onclick: (e) => { e.stopPropagation(); pickTag(t); } }, String(k + 1)),
        h('span', { class: 'nm' }, t),
        h('button', { class: 'x', 'aria-label': `Unpin ${t}`, onclick: (e) => { e.stopPropagation(); togglePin(t); } }, '×'));
      calloutsEl.append(el); pinEls[t] = el; el.nameW = el.children[1].offsetWidth;   // the name's width, to keep it on the page
    }
    const n = tagAt[t], el = pinEls[t];
    el.hidden = !n;
    el.firstChild.textContent = String(k + 1);
    if (n) { el.classList.toggle('on', tagT.has(t)); el.classList.toggle('far', !!ty && !n.byType[ty]); }
  }
  if (centerEl) { if (cluster) { centerEl.style.setProperty('--c', hue(cluster.mod)); centerEl.title = cluster.type; centerEl.firstChild.innerHTML = `<svg viewBox="0 0 20 20" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round">${fixedIcon(cluster.type)}</svg>`; } }
  // The words: one element per named tag of the cluster, reused across frames.
  const want = cluster ? cluster.pts.slice(0, 10) : [];
  while (wordEls.length < want.length) { const b = h('button', { class: 'gword' }); wordsEl.append(b); wordEls.push(b); }
  wordEls.forEach((b, k) => { const s = want[k]; b.hidden = !s; if (s) { b.textContent = s.t; b.dataset.tag = s.t; b.onclick = (e) => { e.stopPropagation(); pickTag(s.t); }; } });
  if (S.gcursor >= nodeList().length) S.gcursor = -1;
}

function resize() {
  if (!box) return;
  const r = box.getBoundingClientRect();
  W = Math.max(1, Math.round(r.width)); H = Math.max(1, Math.round(r.height)); dpr = Math.min(2, window.devicePixelRatio || 1);
  canvas.width = W * dpr; canvas.height = H * dpr;
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
}

// Turned around the vertical axis by the clock, tipped a little toward the viewer, then flattened with mild perspective.
const TILT = 0.3;
let view = 'galaxy';   // which view's geometry is being drawn at this moment
const geom = () => (view === 'cluster' ? { Rp: Math.min(W * 0.44, H * 0.4), cx: W / 2, cy: H * 0.5 } : { Rp: Math.min(W * 0.33, H * 0.26), cx: W / 2, cy: H * 0.5 });
function place(p) {   // tipped and flattened, but not turned: the chamber's frame
  const { Rp, cx, cy } = geom();
  const ct = Math.cos(TILT), st = Math.sin(TILT);
  const yr = p[1] * ct - p[2] * st, zr = p[1] * st + p[2] * ct, sc = 6 / (6 - zr);
  return { x: cx + p[0] * Rp * sc, y: cy - yr * Rp * sc, d: (zr + 1) / 2, sc };
}
function project(p) {
  const c = Math.cos(angle), s = Math.sin(angle);
  return place([p[0] * c + p[2] * s, p[1], -p[0] * s + p[2] * c]);
}
// ---- the chamber: the room the figure floats in, seen from inside. Its back wall, left wall and floor meet in the corner
// at the lower left and run off the page whatever the panel's shape, ruled in large dotted squares; still while the figure
// turns, still under the zoom. Lines are cut at a near plane short of the eye, where perspective would blow up.
const CELL = 0.8, ROOM = { left: -1.8, floor: -1.6, back: -2.6, front: 4.5 }, NEAR = 4.6;
const steps = (a, b) => { const out = []; for (let v = a; v <= b + 1e-9; v += CELL) out.push(v); return out; };
function drawChamber() {
  const { Rp, cx, cy } = geom(), ct = Math.cos(TILT), st = Math.sin(TILT);
  const right = ROOM.left + CELL * Math.ceil(W / (Rp * 0.6) / CELL), top = ROOM.floor + CELL * Math.ceil(H / (Rp * 0.6) / CELL);   // past the page's edges at the back wall
  const tip = (p) => [p[0], p[1] * ct - p[2] * st, p[1] * st + p[2] * ct];
  const cut = (a, b) => { const t = (NEAR - a[2]) / (b[2] - a[2]); return [a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t, NEAR]; };
  const seg = (a, b) => {
    let u = tip(a), v = tip(b);
    if (u[2] > NEAR && v[2] > NEAR) return;
    if (u[2] > NEAR) u = cut(v, u); else if (v[2] > NEAR) v = cut(u, v);
    const pu = 6 / (6 - u[2]), pv = 6 / (6 - v[2]);
    ctx.moveTo(cx + u[0] * Rp * pu, cy - u[1] * Rp * pu); ctx.lineTo(cx + v[0] * Rp * pv, cy - v[1] * Rp * pv);
  };
  const xs = steps(ROOM.left, right), ys = steps(ROOM.floor, top), zs = steps(ROOM.back, ROOM.front);
  ctx.globalAlpha = 0.2; ctx.strokeStyle = '#A6ACB8'; ctx.lineWidth = 1; ctx.setLineDash([1.5, 5]);
  ctx.beginPath();
  for (const x of xs) { seg([x, ROOM.floor, ROOM.back], [x, top, ROOM.back]); seg([x, ROOM.floor, ROOM.back], [x, ROOM.floor, ROOM.front]); }
  for (const y of ys) { seg([ROOM.left, y, ROOM.back], [right, y, ROOM.back]); seg([ROOM.left, y, ROOM.back], [ROOM.left, y, ROOM.front]); }
  for (const z of zs) { seg([ROOM.left, ROOM.floor, z], [right, ROOM.floor, z]); seg([ROOM.left, ROOM.floor, z], [ROOM.left, top, z]); }
  ctx.stroke(); ctx.setLineDash([]);
}
// The cluster lies flat: no turn, no tilt, no depth.
const flat = (p) => { const { Rp, cx, cy } = geom(); return { x: cx + p[0] * Rp, y: cy - p[1] * Rp, d: 1, sc: 1 }; };
const lit = () => {
  const tokens = new Set(S.tokens.filter((k) => k.kind === 'tag').map((k) => k.value));
  const cur = S.open === null ? null : ITEMS.find((i) => String(i.id) === String(S.open));
  const near = new Set(cur ? tagsOf(cur) : []);
  const q = S.q.toLowerCase();
  return { tokens, near, q, narrowed: S.tokens.some((k) => k.kind === 'tag' && !isFixed(k.value)) || !!q };
};
const nodeList = () => (mode === 'cluster' && cluster ? cluster.pts.map((s) => ({ kind: 'tag', t: s.t })) : [...types.map((n) => ({ kind: 'type', t: n.t })), ...tags.map((n) => ({ kind: 'tag', t: n.t }))]);
const cursorKey = () => (S.zone === 'graph' && S.gcursor >= 0 ? (nodeList()[S.gcursor] || {}).t : null);
// One revolution every `turn` minutes, a setting, by the clock, so a faster screen does not turn it faster; 0 holds it still.
let last = 0;
function frame(ts) {
  raf = requestAnimationFrame(frame);
  if (!W || !H) return;
  const dt = last ? Math.min(100, ts - last) : 16; last = ts;
  const minutes = Number(S.layout.turn) || 0;
  if (!still && minutes > 0) angle += dt * (Math.PI * 2 / (minutes * 60000));
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  ctx.clearRect(0, 0, W, H);
  view = 'galaxy'; drawChamber();
  const L = lit(), cur = cursorKey();
  // How far in the zoom is: 0 shows the galaxy, 1 the cluster; a zoom in flight sits between.
  let z = mode === 'cluster' ? 1 : 0;
  if (trans && trans.start > ts) trans.start = ts;   // a zoom begun before the frame clock started runs from this frame
  if (trans) { const p = ease(Math.min(1, (ts - trans.start) / 720)); z = trans.to === 'cluster' ? p : 1 - p; if (p >= 1) { mode = trans.to; trans = null; if (mode === 'galaxy') cluster = null; } }
  const focusType = trans ? trans.type : curType;
  proj = [];
  let focus = null;
  if (z < 0.999) {
    view = 'galaxy';
    const { cx, cy, Rp } = geom();
    const node = focusType ? types.find((n) => n.t === focusType) : null;
    const f = node ? project(node.p) : { x: cx, y: cy };
    const sc = 1 + 2.6 * z, ox = z * (cx - f.x) - (sc - 1) * f.x, oy = z * (cy - f.y) - (sc - 1) * f.y;
    ctx.setTransform(dpr * sc, 0, 0, dpr * sc, dpr * ox, dpr * oy);
    drawGalaxy(L, cur, cx, cy, Rp, 1 - z, z > 0);
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    focus = { x: f.x * sc + ox, y: f.y * sc + oy };
  }
  if (z > 0.001 && cluster) {
    view = 'cluster';
    const { cx, cy } = geom();
    const k = 0.45 + 0.55 * z;
    ctx.setTransform(dpr * k, 0, 0, dpr * k, dpr * cx * (1 - k), dpr * cy * (1 - k));
    drawCluster(L, cur, z, k, cx, cy);
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  }
  view = mode;
  // The facet's symbol: on its node while the galaxy shows, in the top-left corner once the cluster does.
  for (const el of [...Object.values(calloutEls), ...Object.values(pinEls)]) el.style.opacity = (1 - z).toFixed(2);
  calloutsEl.style.pointerEvents = z > 0.5 ? 'none' : '';
  wordsEl.style.opacity = z.toFixed(2);
  if (centerEl) {
    centerEl.hidden = z < 0.02 || !cluster;
    if (!centerEl.hidden) {
      const from = focus || { x: 30, y: 30 }, x = from.x + (30 - from.x) * z, y = from.y + (30 - from.y) * z;
      centerEl.style.transform = `translate(${x.toFixed(1)}px, ${y.toFixed(1)}px) translate(-50%, -50%) scale(${(0.5 + 0.5 * z).toFixed(3)})`;
    }
  }
  ctx.globalAlpha = 1;
  const shown = proj.find((p) => p.t === (hover || cur));
  if (shown && !trans && (mode === 'galaxy' || shown.rank === undefined || shown.rank >= 10)) {
    const q = shown.q;
    labelEl.hidden = false;
    labelEl.innerHTML = `${shown.t.replace(/[&<>]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;' }[c]))}<span class="m"> ${shown.count} item${shown.count === 1 ? '' : 's'}</span>`;
    const lw = labelEl.offsetWidth, left = q.x + 14 + lw > W ? q.x - 14 - lw : q.x + 14;
    labelEl.style.transform = `translate(${Math.max(4, left).toFixed(1)}px, ${Math.max(4, Math.min(H - 34, q.y - 14)).toFixed(1)}px)`;
  } else labelEl.hidden = true;
}

function drawGalaxy(L, cur, cx, cy, Rp, fade = 1, zooming = false) {
  const al = (v) => { ctx.globalAlpha = v * fade; };
  const dim = L.narrowed ? 0.7 : 1;
  // The figure: every dot projected, then grouped by facet and depth band, so each group is one fill; its extent kept.
  const groups = new Map();
  let x0 = Infinity, x1 = -Infinity, y0 = Infinity, y1 = -Infinity;
  for (const d of DOTS) {
    const q = project(d.p), band = Math.min(4, Math.floor(q.d * 5)), key = `${d.f}${band}`;
    if (q.x < x0) x0 = q.x; if (q.x > x1) x1 = q.x; if (q.y < y0) y0 = q.y; if (q.y > y1) y1 = q.y;
    let g = groups.get(key); if (!g) { g = { f: d.f, band, pts: [] }; groups.set(key, g); }
    q.s = d.s; g.pts.push(q);
  }
  for (const g of [...groups.values()].sort((a, b) => a.band - b.band)) {
    al(BAND_ALPHA[g.band] * dim);
    ctx.fillStyle = dotColor()[g.f];
    ctx.beginPath();
    for (const q of g.pts) { const r = 1.25 * q.sc * q.s; ctx.moveTo(q.x + r, q.y); ctx.arc(q.x, q.y, r, 0, Math.PI * 2); }
    ctx.fill();
  }
  const at = {};
  for (const n of types) at[n.t] = project(n.p);
  for (const n of tags) at[n.t] = project(n.p);
  // Edges only while their tag is picked, pointed at, or the open item's.
  ctx.lineCap = 'round';
  for (const e of edges) {
    if (!(L.tokens.has(e.a.t) || e.a.t === hover || e.a.t === cur || L.near.has(e.a.t))) continue;
    const a = at[e.a.t], b = at[e.b.t];
    al(0.75); ctx.strokeStyle = '#ECEEF2'; ctx.lineWidth = 1.4;
    ctx.beginPath(); ctx.moveTo(a.x, a.y); ctx.lineTo(b.x, b.y); ctx.stroke();
  }
  const dots = [...tags.map((n) => ({ ...n, kind: 'tag', q: at[n.t] })), ...types.map((n) => ({ ...n, kind: 'type', q: at[n.t] }))].sort((a, b) => a.q.d - b.q.d);
  for (const n of dots) {
    const isHot = L.tokens.has(n.t) || L.near.has(n.t) || n.t === hover || n.t === cur || (!!L.q && n.t.includes(L.q));
    const far = L.narrowed && !isHot;
    if (!zooming) proj.push({ t: n.t, kind: n.kind, count: n.count, q: n.q });
    al(far ? 0.2 : 0.45 + n.q.d * 0.55);
    if (n.kind === 'type') { ctx.fillStyle = isHot ? '#ECEEF2' : hue(FIXED_MOD[n.t]); ctx.beginPath(); ctx.arc(n.q.x, n.q.y, 3 * n.q.sc, 0, Math.PI * 2); ctx.fill(); }
    else {
      const r = (2.4 + Math.sqrt(n.count) * 1.1) * n.q.sc;
      ctx.beginPath(); ctx.arc(n.q.x, n.q.y, r, 0, Math.PI * 2);
      ctx.fillStyle = L.tokens.has(n.t) ? '#ECEEF2' : '#0B0D11'; ctx.fill();
      ctx.lineWidth = isHot ? 2 : 1.3; ctx.strokeStyle = isHot ? '#ECEEF2' : n.hue;
      if (!L.tokens.has(n.t)) ctx.stroke();
    }
    if (n.t === cur) { al(0.9); ctx.strokeStyle = '#84A9F5'; ctx.lineWidth = 1.5; ctx.beginPath(); ctx.arc(n.q.x, n.q.y, 9, 0, Math.PI * 2); ctx.stroke(); }
  }
  // The callouts: each facet's symbol at its fixed place on the ring, each pinned tag's in the gaps; only the leader moves.
  // A leader runs from the symbol toward its node and stops at the figure's edge: it points, it does not cut through.
  const ex = (x0 + x1) / 2, ey = (y0 + y1) / 2, ea = (x1 - x0) / 2 + 10, eb = (y1 - y0) / 2 + 10;
  const stopAt = (c, q) => {
    const dx = q.x - c.x, dy = q.y - c.y, len = Math.hypot(dx, dy) || 1, ux = dx / len / ea, uy = dy / len / eb, ox = (c.x - ex) / ea, oy = (c.y - ey) / eb;
    const A = ux * ux + uy * uy, B = 2 * (ox * ux + oy * uy), C = ox * ox + oy * oy - 1, D = B * B - 4 * A * C;
    if (D < 0) return q;
    const t = (-B - Math.sqrt(D)) / (2 * A);
    return t <= 0 || t >= len ? q : { x: c.x + dx / len * t, y: c.y + dy / len * t };
  };
  const Rx = Math.min(Rp * 1.42, W / 2 - 26), Ry = Math.min(Rp * 1.7, H / 2 - 26);
  const outs = [...types.map((n) => ({ t: n.t, el: calloutEls[n.t], ang: SLOT[n.t] ?? 0 })), ...S.pins.map((t, k) => ({ t, el: pinEls[t], ang: pinSlot(k) }))].filter((o) => o.el && !o.el.hidden && at[o.t]);
  ctx.lineWidth = 1; ctx.lineCap = 'butt';
  for (const o of outs) {
    const q = at[o.t], ang = rad(o.ang);
    const x = Math.max(26, Math.min(W - 26, cx + Rx * Math.cos(ang))), y = Math.max(26, Math.min(H - 26, cy + Ry * Math.sin(ang)));
    const dx = x - q.x, dy = y - q.y, len = Math.hypot(dx, dy) || 1, c = { x: x - dx / len * 16, y: y - dy / len * 16 }, end = stopAt(c, q), behind = q.d < 0.5;
    al(o.el.classList.contains('far') ? 0.25 : behind ? 0.35 : 0.8);
    ctx.strokeStyle = '#A6ACB8'; ctx.setLineDash([3, 4]);
    ctx.beginPath(); ctx.moveTo(c.x, c.y); ctx.lineTo(end.x, end.y); ctx.stroke();
    ctx.setLineDash([]);
    o.el.style.transform = `translate(${x.toFixed(1)}px, ${y.toFixed(1)}px) translate(-50%, -50%)`;
    if (o.el.nameW) o.el.classList.toggle('left', x + 23 + o.el.nameW > W - 4);   // a name that would leave the page sits on the other side
  }
}

function drawCluster(L, cur, fade = 1, k = 1, cx = 0, cy = 0) {
  const al = (v) => { ctx.globalAlpha = v * fade; };
  const zooming = fade < 0.999;
  const at = {};
  for (const s of cluster.pts) at[s.t] = flat(s.p);
  // Links only while an end is picked or pointed at.
  for (const [a, b] of cluster.links) {
    const pa = at[a], pb = at[b]; if (!pa || !pb) continue;
    if (!(L.tokens.has(a) || L.tokens.has(b) || a === hover || b === hover || a === cur || b === cur)) continue;
    al(0.7); ctx.strokeStyle = '#ECEEF2'; ctx.lineWidth = 1.3;
    ctx.beginPath(); ctx.moveTo(pa.x, pa.y); ctx.lineTo(pb.x, pb.y); ctx.stroke();
  }
  const dots = cluster.pts.map((s) => ({ ...s, q: at[s.t] })).sort((a, b) => a.q.d - b.q.d);
  for (const s of dots) {
    const isHot = L.tokens.has(s.t) || L.near.has(s.t) || s.t === hover || s.t === cur || (!!L.q && s.t.includes(L.q));
    if (!zooming) proj.push({ t: s.t, kind: 'tag', count: s.count, rank: s.rank, q: s.q });
    const r = (s.rank < 10 ? 3.2 : 2) + Math.sqrt(s.count) * 0.6;
    al(L.narrowed && !isHot ? 0.25 : 1);
    ctx.beginPath(); ctx.arc(s.q.x, s.q.y, r, 0, Math.PI * 2);
    ctx.fillStyle = L.tokens.has(s.t) ? '#ECEEF2' : '#0B0D11'; ctx.fill();
    ctx.lineWidth = isHot ? 2 : 1.2; ctx.strokeStyle = isHot ? '#ECEEF2' : hue(cluster.mod);
    if (!L.tokens.has(s.t)) ctx.stroke();
    if (s.t === cur) { al(0.9); ctx.strokeStyle = '#84A9F5'; ctx.lineWidth = 1.5; ctx.beginPath(); ctx.arc(s.q.x, s.q.y, r + 6, 0, Math.PI * 2); ctx.stroke(); }
  }
  // Words keep clear of one another: sorted top to bottom, each sits at least a line below the one above it.
  const placed = wordEls.filter((b) => !b.hidden && at[b.dataset.tag]).map((b) => ({ b, q: at[b.dataset.tag], y: at[b.dataset.tag].y })).sort((a, c) => a.q.y - c.q.y);
  for (let k = 1; k < placed.length; k++) if (Math.abs(placed[k].q.x - placed[k - 1].q.x) < 150 && placed[k].y < placed[k - 1].y + 22) placed[k].y = placed[k - 1].y + 22;
  const rowY = Object.fromEntries(placed.map((p) => [p.b.dataset.tag, p.y]));
  wordEls.forEach((b) => {
    if (b.hidden) return;
    const q = at[b.dataset.tag]; if (!q) return;
    const left = q.x > cx + 20, wy = rowY[b.dataset.tag] ?? q.y, sx = cx + (q.x - cx) * k, sy = cy + (wy - cy) * k;
    b.classList.toggle('left', left);
    b.classList.toggle('on', L.tokens.has(b.dataset.tag));
    b.classList.toggle('near', L.near.has(b.dataset.tag) || b.dataset.tag === hover || b.dataset.tag === cur);
    b.style.opacity = (L.narrowed && !L.tokens.has(b.dataset.tag) && !L.near.has(b.dataset.tag) ? 0.35 : 1).toFixed(2);
    b.style.transform = `translate(${(sx + (left ? -10 : 10)).toFixed(1)}px, ${sy.toFixed(1)}px) translate(${left ? '-100%' : '0'}, -50%)`;
  });
}

// ---- what a click or the keyboard does -------------------------------------------------------------------------------
function pickTag(t) { const i = S.tokens.findIndex((k) => k.kind === 'tag' && k.value === t); if (i >= 0) removeToken(i); else addToken('tag', t); }
// A pin gives a plain tag a numbered callout; `m` pins the tag under the keyboard or the pointer, the palette a picked one;
// the pin's number key toggles the tag in the search.
function togglePin(t) {
  t = t || hover || cursorKey();
  if (!t) { toast('Point at a tag first'); return; }
  if (isFixed(t)) { toast('Facets already have a place'); return; }
  const i = S.pins.indexOf(t);
  if (i < 0 && S.pins.length >= MAX_PINS) { toast(`${MAX_PINS} pins at most`); return; }
  if (i >= 0) S.pins.splice(i, 1); else S.pins.push(t);
  savePins(); sync(); toast(i >= 0 ? `Unpinned #${t}` : `Pinned #${t}`);
}
function pinKey(d) { const t = S.pins[d - 1]; if (t) pickTag(t); }
function nearest(x, y) {
  let best = null, bd = 12;
  for (const p of proj) { const d = Math.hypot(p.q.x - x, p.q.y - y); if (d < bd) { bd = d; best = p; } }
  return best;
}
function step(d) { const n = nodeList().length; if (!n) return; S.gcursor = ((S.gcursor < 0 ? (d > 0 ? -1 : n) : S.gcursor) + d + n) % n; }
function pick() { const n = nodeList()[S.gcursor]; if (n) pickTag(n.t); }

function start(el) {
  box = el; canvas = $('#brainCanvas', el); ctx = canvas.getContext('2d'); calloutsEl = $('#lobes', el); labelEl = $('#glabel', el); wordsEl = $('#words', el);
  for (const t of FIXED_ORDER) {
    const m = modOf(FIXED_MOD[t]);
    const b = h('button', { class: 'lobe', style: `--c:${m.hue}`, 'aria-label': t, title: t, onclick: (e) => { e.stopPropagation(); pickTag(t); } },
      h('span', { class: 'mk', html: `<svg viewBox="0 0 20 20" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round">${fixedIcon(t)}</svg>` }));
    calloutsEl.append(b); calloutEls[t] = b;
  }
  centerEl = h('button', { class: 'lobe center on corner', hidden: true, 'aria-label': 'Back to the brain', onclick: (e) => { e.stopPropagation(); const ty = typeToken(); if (ty) pickTag(ty); } }, h('span', { class: 'mk' }));
  calloutsEl.append(centerEl);
  el.addEventListener('mouseleave', () => { hover = null; el.classList.remove('pointing'); });
  el.addEventListener('mousemove', (e) => { const r = canvas.getBoundingClientRect(); const p = nearest(e.clientX - r.left, e.clientY - r.top); hover = p ? p.t : null; el.classList.toggle('pointing', !!p); });
  canvas.addEventListener('click', (e) => {
    if (S.point) return;
    const r = canvas.getBoundingClientRect(); const p = nearest(e.clientX - r.left, e.clientY - r.top);
    if (!p) return;
    pickTag(p.t);
    S.gcursor = nodeList().findIndex((n) => n.t === p.t);
  });
  new ResizeObserver(resize).observe(el);
  resize(); sync();
  if (!raf) raf = requestAnimationFrame(frame);
  if (matchMedia('(prefers-reduced-motion: reduce)').matches) still = true;   // the system's own preference, not a state of the page
}

registerBrain({ start, sync, resize, step, pick, togglePin, pinKey });
