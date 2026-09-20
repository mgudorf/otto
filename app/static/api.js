// Every request the browser makes. The in-flight count drives the loading line in the header.
export const inflight = { n: 0, listeners: new Set() };

function bump(d) {
  inflight.n += d;
  inflight.listeners.forEach((f) => f(inflight.n));
}

export async function api(path, opts = {}) {
  bump(1);
  try {
    const init = { method: opts.method || 'GET', headers: { 'content-type': 'application/json' } };
    if (opts.body !== undefined) init.body = JSON.stringify(opts.body);
    const r = await fetch(path, init);
    const text = await r.text();
    let data = null;
    try { data = text ? JSON.parse(text) : null; } catch { data = { detail: text }; }
    if (!r.ok) {
      const d = data && data.detail;
      throw new Error(typeof d === 'string' ? d : d ? JSON.stringify(d) : `${r.status} ${r.statusText}`);
    }
    return data;
  } finally {
    bump(-1);
  }
}

export const get = (p) => api(p);
export const post = (p, body) => api(p, { method: 'POST', body: body === undefined ? {} : body });
export const apiPut = (p, body) => api(p, { method: 'PUT', body });   // `put` is the DOM helper in core.js

// A path with a query string: missing and empty values are left out, a list joins on commas.
export function q(path, params) {
  const parts = [];
  for (const [k, v] of Object.entries(params || {})) {
    const s = Array.isArray(v) ? v.join(',') : v;
    if (s === null || s === undefined || s === '') continue;
    parts.push(`${encodeURIComponent(k)}=${encodeURIComponent(s)}`);
  }
  return parts.length ? `${path}?${parts.join('&')}` : path;
}

// One server-sent stream. The returned function closes it; a stream is not a request, so it never counts as in flight.
export function sse(path, onEvent) {
  const es = new EventSource(path);
  es.onmessage = (e) => { try { onEvent(JSON.parse(e.data)); } catch { /* a malformed frame is skipped */ } };
  return () => es.close();
}
