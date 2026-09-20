// Markdown for the transcript and the prose, LaTeX for a question body. Both return HTML the caller puts inside its
// own element, so `.turn.model`, `.prose` and `.qbody` in styles.css are what give the markup its type.
import { marked } from './vendor/marked.esm.js';
import katex from './vendor/katex/katex.mjs';

let linked = false;

// KaTeX's stylesheet, added to the document the first time math is rendered.
function ensureKatex() {
  if (linked) return;
  linked = true;
  const link = document.createElement('link');
  link.rel = 'stylesheet';
  link.href = 'vendor/katex/katex.min.css';
  document.head.appendChild(link);
}

// Paragraphs, lists, fences, inline code, bold and italics: the tags `.turn.model` and `.prose` are written for.
export function md(text) {
  if (!text) return '';
  return marked.parse(String(text), { breaks: true, gfm: true });
}

// Math is lifted out before the markdown pass, so underscores inside it never become emphasis, and rendered back
// in where it stood.
export function tex(text) {
  if (!text) return '';
  ensureKatex();
  const math = [];
  const s = String(text)
    .replace(/\$\$([\s\S]+?)\$\$/g, (_, t) => { math.push({ t, d: true }); return `@@M${math.length - 1}@@`; })
    .replace(/\$([^$\n]+?)\$/g, (_, t) => { math.push({ t, d: false }); return `@@M${math.length - 1}@@`; });
  return md(s).replace(/@@M(\d+)@@/g, (_, i) => katex.renderToString(math[i].t, { displayMode: math[i].d, throwOnError: false }));
}
