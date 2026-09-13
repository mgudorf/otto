"""The body of one message: text for the agent, sanitized HTML for the reader, attachment names for both.

Nothing the reader receives can be clicked, fetched or run. sanitize() keeps text and structure only: no
anchor, image, style, script, form or attribute survives; a link becomes its text with the raw URL on hover,
and an image contributes its alt text only when that text says something the owner cannot already see.
A part that carries a filename is an attachment, inline or not: its name is listed and its content never read.
"""

from __future__ import annotations

import base64
import html
import re
from html.parser import HTMLParser

KEEP = {  # emitted bare, every attribute dropped
    "p", "br", "hr", "wbr", "div", "span", "center", "h1", "h2", "h3", "h4", "h5", "h6",
    "ul", "ol", "li", "dl", "dt", "dd", "blockquote", "pre", "code", "tt", "kbd", "samp", "var",
    "b", "strong", "i", "em", "u", "s", "strike", "del", "ins", "sub", "sup", "small", "abbr", "cite", "q", "mark", "dfn",
    "table", "thead", "tbody", "tfoot", "tr", "th", "td", "caption",
    "section", "article", "header", "footer", "main", "nav", "aside", "figure", "figcaption", "address",
}
ATTRS = {"td": ("colspan", "rowspan"), "th": ("colspan", "rowspan"), "ol": ("start",)}  # kept when a plain integer
SKIP = {  # dropped with everything inside
    "script", "style", "title", "template", "iframe", "frameset", "noframes", "object", "applet", "noscript",
    "svg", "math", "video", "audio", "canvas", "map", "select", "datalist", "textarea", "button", "progress", "meter",
}
VOID = {"br", "hr", "wbr", "img", "area", "base", "col", "embed", "input", "link", "meta", "param", "source", "track", "keygen", "frame"}
SHOWN = ("http://", "https://", "mailto:", "tel:")  # the only link targets written out; anything else is dropped
# Alt text that exists for a client that blocks images. Otto never fetches one, so the sentence tells the owner nothing.
BOILERPLATE = re.compile(r"^(enable images|click here|image|photo|logo|icon|spacer|banner|header|footer|divider)\b|"
                         r"to view this (e-?mail|content)|images? (are )?(off|blocked|disabled)", re.I)
HIDDEN = re.compile(r"(display\s*:\s*none|visibility\s*:\s*hidden)", re.I)  # inline-hidden: preheaders, the mobile copy of a layout


def _bare(url: str) -> str:
    return re.sub(r"^[a-z]+:(//)?", "", url.strip().lower()).rstrip("/")


class _Sanitizer(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.out: list[str] = []
        self.open: list[str] = []       # KEEP tags open now, so the output closes everything it opened
        self.dropped: list[str] = []    # tags open inside a dropped subtree (SKIP or hidden); nothing is emitted while non-empty
        self.link: str | None = None    # href of the open anchor, written as text at </a>
        self.link_text: list[str] = []

    def handle_starttag(self, tag, attrs):
        a = {k: v or "" for k, v in attrs}
        if self.dropped or tag in SKIP or "hidden" in a or HIDDEN.search(a.get("style", "")):
            if tag not in VOID:
                self.dropped.append(tag)
            return
        if tag == "a":
            self._open_link(a.get("href", ""))
        elif tag == "img":
            alt = " ".join(a.get("alt", "").split())
            if alt and not BOILERPLATE.search(alt):
                self.out.append(f'<span class="img">[image: {html.escape(alt)}]</span>')
                self.link_text.append(alt)
        elif tag in VOID:
            if tag in KEEP:
                self.out.append(f"<{tag}>")
        elif tag in KEEP:
            kept = "".join(f' {k}="{a[k]}"' for k in ATTRS.get(tag, ()) if a.get(k, "").isdigit())
            self.out.append(f"<{tag}{kept}>")
            self.open.append(tag)

    def handle_endtag(self, tag):
        if self.dropped:
            if tag in self.dropped:
                while self.dropped.pop() != tag:
                    pass
            return
        if tag == "a":
            self._close_link()
        elif tag in self.open:
            while (t := self.open.pop()) != tag:
                self.out.append(f"</{t}>")
            self.out.append(f"</{tag}>")

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)
        if tag not in VOID:
            self.handle_endtag(tag)

    def handle_data(self, data):
        if self.dropped:
            return
        self.out.append(html.escape(data))
        if self.link is not None:
            self.link_text.append(data)

    def _open_link(self, href: str) -> None:
        self._close_link()  # browsers close an anchor when the next one opens
        self.link = "".join(href.split())
        self.link_text = []

    def _close_link(self) -> None:
        """The URL follows whatever the anchor showed; an anchor that showed nothing (an icon without alt text) shows no URL either."""
        if self.link is None:
            return
        url, text = self.link, "".join(self.link_text).strip()
        self.link = None
        if text and url.lower().startswith(SHOWN) and _bare(url) != _bare(text):
            self.out.append(f'<span class="url" title="{html.escape(url, quote=True)}"></span>')

    def close(self) -> None:
        super().close()
        self._close_link()
        while self.open:
            self.out.append(f"</{self.open.pop()}>")


EMPTY_CELL = re.compile(r"<(td|th)>(\s|&nbsp;|<br>|<wbr>)*</\1>")
EMPTY_ROW = re.compile(r"<tr>(\s|<br>)*</tr>")
RUN_OF_BREAKS = re.compile(r"(<br>\s*){3,}")


def _tidy(markup: str) -> str:
    """A template mail is mostly spacer cells and spacer rows; they carry nothing and read as blank space."""
    for _ in range(3):  # a dropped cell can empty its row, which can empty the row above it
        before = markup
        markup = EMPTY_ROW.sub("", EMPTY_CELL.sub("", markup))
        if markup == before:
            break
    return RUN_OF_BREAKS.sub("<br><br>", markup)


def sanitize(raw: str) -> str:
    """HTML the reader can show: KEEP tags bare, a link as its text with the URL on hover, meaningful alt text, nothing else."""
    p = _Sanitizer()
    p.feed(raw)
    p.close()
    return _tidy("".join(p.out))


def to_text(raw: str) -> str:
    """The html as plain text for the agent: scripts and styles gone, block ends as line breaks, tags stripped."""
    text = re.sub(r"(?is)<(script|style).*?</\1>", "", raw)
    text = re.sub(r"(?i)<br\s*/?>|</p>|</div>|</tr>", "\n", text)
    text = html.unescape(re.sub(r"<[^>]+>", "", text))
    return re.sub(r"\n\s*\n+", "\n\n", text).strip()


def extract(msg: dict) -> dict:
    """{text, html, attachments} of a full-format message. text: plain parts, else the html as text, else the snippet."""
    plain, rich, files = [], [], []

    def walk(part: dict) -> None:
        if part.get("filename"):
            files.append(part["filename"])
            return
        data = part.get("body", {}).get("data")
        if data:
            text = base64.urlsafe_b64decode(data + "=" * (-len(data) % 4)).decode("utf-8", "replace")
            if part.get("mimeType") == "text/plain":
                plain.append(text)
            elif part.get("mimeType") == "text/html":
                rich.append(text)
        for p in part.get("parts", []):
            walk(p)

    walk(msg.get("payload", {}))
    text = "\n".join(plain).replace("\r\n", "\n").strip() if plain else to_text("\n".join(rich)) if rich else ""
    shown = sanitize("\n".join(rich)) if rich else ""
    visible = html.unescape(re.sub(r"<[^>]+>", "", shown)).strip()
    return {"text": text or html.unescape(msg.get("snippet", "")), "html": shown if visible else None, "attachments": files}
