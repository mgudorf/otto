// fetch wrapper; the in-flight count drives the loading line in the header.
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
export const put = (p, body) => api(p, { method: 'PUT', body });
