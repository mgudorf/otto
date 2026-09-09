// Markdown with LaTeX for the middle track: marked for the prose, KaTeX for $…$ and $$…$$. Both vendored.
import { marked } from './vendor/marked.esm.js';
import katex from './vendor/katex/katex.mjs';
import { html } from './rows.js';

let styled = false;

// The KaTeX stylesheet and the few rules markdown needs, added to the document once, on first render.
function ensureStyles() {
  if (styled) return;
  styled = true;
  const link = document.createElement('link');
  link.rel = 'stylesheet';
  link.href = 'vendor/katex/katex.min.css';
  document.head.appendChild(link);
  const style = document.createElement('style');
  style.textContent = [
    '.md p{margin:0 0 10px}.md p:last-child{margin-bottom:0}',
    '.md ul,.md ol{margin:0 0 10px;padding-left:22px}.md li{margin:2px 0}',
    ".md code{font-family:'JetBrains Mono',ui-monospace,monospace;font-size:13px;background:#23262c;padding:1px 5px;border-radius:4px}",
    '.md pre{background:#1a1c21;padding:10px 12px;border-radius:6px;overflow-x:auto;margin:0 0 10px}.md pre code{background:none;padding:0}',
    '.md h1,.md h2,.md h3,.md h4{font-size:15px;font-weight:600;margin:12px 0 6px}.md strong{font-weight:600}',
    '.md table{border-collapse:collapse;margin:0 0 10px}.md td,.md th{padding:2px 8px;border:1px solid rgba(230,231,234,.08)}',
    '.md blockquote{margin:0 0 10px;padding-left:12px;border-left:2px solid rgba(230,231,234,.14);color:#8b8f98}',
    '.md .katex-display{margin:10px 0;overflow-x:auto;overflow-y:hidden}.md .katex{font-size:1.05em}',
  ].join('');
  document.head.appendChild(style);
}

// Math is lifted out before marked runs (so underscores inside LaTeX never become emphasis) and rendered back in.
export function renderMarkdown(text) {
  if (!text) return '';
  const math = [];
  let s = String(text);
  s = s.replace(/\$\$([\s\S]+?)\$\$/g, (_, tex) => { math.push({ tex, display: true }); return `@@KX${math.length - 1}@@`; });
  s = s.replace(/\$([^$\n]+?)\$/g, (_, tex) => { math.push({ tex, display: false }); return `@@KX${math.length - 1}@@`; });
  let out = marked.parse(s, { breaks: true, gfm: true });
  out = out.replace(/@@KX(\d+)@@/g, (_, i) => {
    const m = math[+i];
    return katex.renderToString(m.tex, { displayMode: m.display, throwOnError: false });
  });
  return out;
}

export function Markdown({ text }) {
  ensureStyles();
  return html`<div class="md" style=${{ lineHeight: 1.6, wordBreak: 'break-word' }} dangerouslySetInnerHTML=${{ __html: renderMarkdown(text) }} />`;
}
