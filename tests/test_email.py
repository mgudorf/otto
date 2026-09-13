"""Email module: the read/write client split, sync against a fake Gmail, actions through the app, and the body sanitizer."""

import ast
import base64
import dataclasses
import json
from datetime import timedelta

import httpx
import pytest

import app.modules.email.gmail as gmail
from app.claude import ClaudeRunner
from app.config import ROOT, Email, Nightly
from app.daemon import build
from app.modules import Registry
from app.modules.email import MANIFEST
from app.modules.email.gmail import SCOPE, GmailRead, GmailWrite
import app.modules.email.routes as routes
import app.modules.email.tasks as tasks_mod
from app.modules.email.tasks import sync, triage
from app.modules.email.tools import register
from app.runner import Runner
from app.store import iso, now
from tests.conftest import fake_spawn, run
from tests.test_app import client_for

TRIAGE = json.dumps({
    "type": "result", "subtype": "success", "is_error": False, "session_id": "s9",
    "result": '[{"id": "m3", "priority": "high", "reason": "Contract needs a signature."}, '
              '{"id": "m2", "priority": "low", "reason": "Social."}, {"id": "zzz", "priority": "high", "reason": "unknown id"}]',
})

EMAIL_DIR = ROOT / "app" / "modules" / "email"
FORBIDDEN = {"GmailWrite", "write_client", "modify", "batchModify", "trash", "delete"}


def message(mid, sender, subject, labels, body="hello there", ms=1_757_239_200_000, html=None):
    return {"id": mid, "from": sender, "subject": subject, "labels": list(labels), "snippet": body[:40], "body": body, "html": html, "ms": ms}


def b64(s):
    return base64.urlsafe_b64encode(s.encode()).decode()


def gmail_json(m, full):
    out = {
        "id": m["id"], "threadId": "t" + m["id"], "labelIds": m["labels"], "snippet": m["snippet"], "internalDate": str(m["ms"]),
        "payload": {"headers": [{"name": "From", "value": m["from"]}, {"name": "To", "value": "owner@example.com"}, {"name": "Subject", "value": m["subject"]}]},
    }
    if full:
        plain = {"mimeType": "text/plain", "body": {"data": b64(m["body"])}}
        if m["html"]:
            out["payload"].update({"mimeType": "multipart/alternative", "parts": [plain, {"mimeType": "text/html", "body": {"data": b64(m["html"])}}]})
        else:
            out["payload"].update(plain)
    return out


class FakeGmail:
    """Stands in for Gmail and the token endpoint behind httpx.MockTransport."""

    def __init__(self, messages):
        self.messages = {m["id"]: m for m in messages}
        self.history, self.history_status, self.history_id = [], 200, "100"
        self.modified, self.refreshes = [], 0
        self.quota_refusals = 0  # metadata gets refused with a 403 quota error before answering
        self.fail_ids = set()    # metadata gets that answer 500

    def handler(self, request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path == "/token":
            self.refreshes += 1
            return httpx.Response(200, json={"access_token": "fresh", "expires_in": 3600, "scope": SCOPE, "token_type": "Bearer"})
        assert request.headers["authorization"].startswith("Bearer ")
        if self.quota_refusals and "/messages/" in path and request.method == "GET":
            self.quota_refusals -= 1
            return httpx.Response(403, json={"error": {"code": 403, "message": "Quota exceeded for quota metric 'Total Query Cost'"}})
        if request.method == "GET" and path.rsplit("/", 1)[1] in self.fail_ids:
            return httpx.Response(500, json={"error": "boom"})
        if path.endswith("/profile"):
            return httpx.Response(200, json={"emailAddress": "owner@example.com", "historyId": self.history_id})
        if path.endswith("/messages"):
            return httpx.Response(200, json={"messages": [{"id": i} for i in self.messages]})
        if path.endswith("/messages/batchModify"):
            body = json.loads(request.content)
            self.modified.append(body)
            for mid in body["ids"]:
                m = self.messages[mid]
                m["labels"] = [l for l in m["labels"] if l not in body["removeLabelIds"]] + body["addLabelIds"]
            return httpx.Response(204)
        if path.endswith("/history"):
            if self.history_status != 200:
                return httpx.Response(self.history_status, json={"error": "expired"})
            return httpx.Response(200, json={"history": self.history, "historyId": self.history_id})
        mid = path.rsplit("/", 1)[1]
        if mid not in self.messages:
            return httpx.Response(404, json={"error": "gone"})
        return httpx.Response(200, json=gmail_json(self.messages[mid], request.url.params.get("format") == "full"))


@pytest.fixture
def email_config(config, tmp_path):
    client = tmp_path / "client.json"
    token = tmp_path / "token.json"
    client.write_text(json.dumps({"web": {
        "client_id": "cid", "client_secret": "sec", "token_uri": "https://oauth2.googleapis.com/token",
        "auth_uri": "https://accounts.google.com/o/oauth2/auth", "redirect_uris": ["http://localhost:8756/m/email/api/oauth/callback"],
    }}))
    token.write_text(json.dumps({"access_token": "old", "refresh_token": "r", "scope": SCOPE, "token_type": "Bearer", "expires_at": iso(now() + timedelta(hours=1))}))
    cfg = dataclasses.replace(config, email=Email(
        client_file=client, token_file=token, backfill_days=30, triage_batch=5, read_on_open=True, consent_warn_days=2))
    routes.CONFIG = cfg   # setup() does this at build; the queue hook and LEFT read it
    return cfg


@pytest.fixture
def fake(monkeypatch):
    g = FakeGmail([
        message("m1", "Ann <ann@example.com>", "Invoice ready", ["INBOX"], ms=1_757_239_200_000),
        message("m2", "Bob <bob@example.com>", "Lunch?", ["INBOX", "UNREAD"], ms=1_757_242_800_000),
        message("m3", "Cy <cy@example.com>", "Contract draft", ["INBOX", "UNREAD", "STARRED"], body="please sign the contract", ms=1_757_246_400_000,
                html="<p>please <b>sign</b> the contract <a href='https://docs.example/c'>here</a></p>"),
    ])
    monkeypatch.setattr(gmail, "TRANSPORT", httpx.MockTransport(g.handler))
    return g


def test_email_client_split(store, email_config):
    for name in ("tasks", "tools"):
        tree = ast.parse((EMAIL_DIR / f"{name}.py").read_text("utf-8"))
        names = {n.attr for n in ast.walk(tree) if isinstance(n, ast.Attribute)} | {n.id for n in ast.walk(tree) if isinstance(n, ast.Name)}
        assert not names & FORBIDDEN, f"{name}.py reaches a Gmail write: {names & FORBIDDEN}"
    assert not hasattr(GmailRead, "modify") and hasattr(GmailWrite, "modify")

    class Srv:
        def __init__(self):
            self.names = []

        def tool(self):
            return lambda f: (self.names.append(f.__name__), f)[1]

    read, full = Srv(), Srv()
    register(read, full, store, email_config)
    assert set(full.names) - set(read.names) == set(MANIFEST.agent.write_tools)
    assert set(read.names) >= set(MANIFEST.agent.read_tools)


def test_email_sync(store, email_config, fake):
    store.migrate((EMAIL_DIR / "schema.sql").read_text("utf-8"))

    async def main():
        r = Runner(store, email_config, registry=None, claude=None)
        await r.start()

        async def go():
            return await r.submit("email.sync", "email", "gmail", "scheduled", sync).done

        assert (await go()).startswith("backfilled 3")
        assert store.cursor("email.history") == "100"
        m3 = store.one("SELECT * FROM email_messages WHERE id = 'm3'")
        assert m3["from_name"] == "Cy" and m3["from_addr"] == "cy@example.com" and json.loads(m3["labels"]) == ["INBOX", "UNREAD", "STARRED"]
        assert store.scalar("SELECT COUNT(*) FROM email_fts WHERE email_fts MATCH 'contract'") == 1

        fake.history = [{"labelsRemoved": [{"message": {"id": "m2"}}]}, {"messagesDeleted": [{"message": {"id": "m1"}}]}]
        fake.messages["m2"]["labels"] = ["INBOX"]
        del fake.messages["m1"]
        fake.history_id = "120"
        assert await go() == "1 updated, 1 removed"
        assert store.cursor("email.history") == "120"
        assert json.loads(store.one("SELECT labels FROM email_messages WHERE id = 'm2'")["labels"]) == ["INBOX"]
        assert store.one("SELECT id FROM email_messages WHERE id = 'm1'") is None

        fake.history, fake.history_status, fake.history_id = [], 404, "130"
        assert (await go()).startswith("backfilled 2")
        assert store.cursor("email.history") == "130"
        await r.drain(1)

    run(main())


def test_email_backfill_resumes(store, email_config, fake, monkeypatch):
    store.migrate((EMAIL_DIR / "schema.sql").read_text("utf-8"))
    monkeypatch.setattr(tasks_mod, "PAGE", 2)
    fake.fail_ids = {"m3"}

    async def main():
        r = Runner(store, email_config, registry=None, claude=None)
        await r.start()
        with pytest.raises(Exception):
            await r.submit("email.sync", "email", "gmail", "scheduled", sync).done
        assert sorted(x["id"] for x in store.query("SELECT id FROM email_messages")) == ["m1", "m2"]
        assert store.cursor("email.history") is None and store.cursor("email.backfill").startswith("100|")
        fake.fail_ids = set()
        assert (await r.submit("email.sync", "email", "gmail", "scheduled", sync).done).startswith("backfilled 1 messages")
        assert store.cursor("email.history") == "100" and store.cursor("email.backfill") is None
        assert store.scalar("SELECT COUNT(*) FROM email_messages") == 3
        await r.drain(1)

    run(main())


def test_email_quota_retry(store, email_config, fake, monkeypatch):
    store.migrate((EMAIL_DIR / "schema.sql").read_text("utf-8"))
    monkeypatch.setattr(gmail, "QUOTA_WAIT", 0.001)
    fake.quota_refusals = 4

    async def main():
        r = Runner(store, email_config, registry=None, claude=None)
        await r.start()
        assert (await r.submit("email.sync", "email", "gmail", "scheduled", sync).done).startswith("backfilled 3")
        fake.quota_refusals = gmail.RETRY_ATTEMPTS + 1
        fake.history, fake.history_id = [{"messagesAdded": [{"message": {"id": "m1"}}]}], "101"
        job = r.submit("email.sync", "email", "gmail", "scheduled", sync)
        with pytest.raises(Exception):
            await job.done
        await r.drain(1)

    run(main())
    assert fake.quota_refusals == 0
    assert "gmail 403" in store.one("SELECT error FROM app_jobs ORDER BY id DESC")["error"]


def test_email_token_refresh(store, email_config, fake):
    store.migrate((EMAIL_DIR / "schema.sql").read_text("utf-8"))
    token = email_config.email.token_file
    data = json.loads(token.read_text())
    token.write_text(json.dumps({**data, "expires_at": iso(now() - timedelta(minutes=1)), "refresh_token_expires_in": 604799}))

    async def main():
        r = Runner(store, email_config, registry=None, claude=None)
        await r.start()
        await r.submit("email.sync", "email", "gmail", "scheduled", sync).done
        await r.drain(1)

    run(main())
    saved = json.loads(token.read_text())
    assert fake.refreshes == 1 and saved["access_token"] == "fresh" and saved["refresh_token"] == "r"
    assert "refresh_token_expires_in" not in saved and saved["expires_at"] > iso(now())


def test_email_actions(email_config, fake):
    async def main():
        app = build(email_config)
        await app.state.runner.start()
        async with client_for(app) as c:
            await app.state.runner.submit("email.sync", "email", "gmail", "scheduled", sync).done
            left = (await c.get("/api/email/left?chip=Flagged")).json()
            assert [r["id"] for r in left["groups"][0]["rows"]] == ["m3"] and left["showing"] == "1 / 1"
            row = left["groups"][0]["rows"][0]
            # the bar builds its verbs from these, so it never waits on item/{id} and never changes height
            assert row["leading"]["dot"] == MANIFEST.hue and row["unread"] is True and row["starred"] is True
            assert left["chips"] == ["All", "Flagged", "Priority"] and left["read_on_open"] is True

            r = await c.post("/api/email/action/archive", json={"ids": ["m1"]})
            assert r.status_code == 200 and r.json() == {"count": 1}, r.text
            assert fake.modified[-1] == {"ids": ["m1"], "addLabelIds": [], "removeLabelIds": ["INBOX"]}
            assert "m1" not in [x["id"] for g in (await c.get("/api/email/left")).json()["groups"] for x in g["rows"]]

            r = await c.post("/api/email/action/trash", json={"filter": {"query": "lunch", "chip": "All"}})
            assert r.json() == {"count": 1} and fake.modified[-1] == {"ids": ["m2"], "addLabelIds": ["TRASH"], "removeLabelIds": ["INBOX"]}
            assert (await c.post("/api/email/action/trash", json={"filter": {"query": "nothing-here", "chip": "All"}})).status_code == 400

            item = (await c.get("/api/email/item/m3")).json()
            assert item["text"] == "Contract draft\n\nplease sign the contract" and item["starred"] is True
            assert item["body"] == "please sign the contract" and item["attachments"] == []
            assert item["html"] == '<p>please <b>sign</b> the contract here<span class="url" title="https://docs.example/c"></span></p>'
            assert app.state.store.scalar("SELECT COUNT(*) FROM email_bodies") == 1
            assert [a["verb"] for a in item["actions"]] == ["archive", "trash", "read", "unstar", "open"]
            assert (await c.post("/api/email/action/read", json={"ids": ["m3"]})).json() == {"count": 1}
            assert (await c.get("/api/email/item/m3")).json()["unread"] is False

            blank = (await c.get("/api/email/blank")).json()
            assert (blank["inbox"], blank["unread"], blank["flagged"], blank["priority"]) == (1, 0, 1, 0)
            numbers = (await c.get("/api/home/numbers")).json()
            assert next(n for n in numbers if n["module"] == "email")["value"] == 0
            ev = (await c.get("/api/events?module=email")).json()
            assert [e["verb"] for e in ev["events"]][:3] == ["marked read", "trashed", "archived"]
            assert ev["events"][1]["text"] == "1 messages matching 'lunch' · All"
        await app.state.runner.drain(1)
        app.state.store.close()

    run(main())


def test_email_triage(store, email_config, fake):
    store.migrate((EMAIL_DIR / "schema.sql").read_text("utf-8"))
    cfg = dataclasses.replace(email_config, nightly=Nightly(window="00:00-23:59", max_sessions=3, max_turns=5, max_minutes=1, stagger_minutes=15))
    calls = []

    async def main():
        reg = Registry()
        reg.load()
        claude = ClaudeRunner(cfg, store, reg, "http://test", spawn_fn=fake_spawn([TRIAGE], calls))
        r = Runner(store, cfg, reg, claude)
        await r.start()
        await r.submit("email.sync", "email", "gmail", "scheduled", sync).done
        assert await r.submit("email.triage", "email", "email", "scheduled", triage).done == "2 triaged, 1 high"
        rows = store.query("SELECT message_id, priority, source FROM email_triage ORDER BY message_id")
        assert rows == [{"message_id": "m2", "priority": "low", "source": "scheduled"}, {"message_id": "m3", "priority": "high", "source": "scheduled"}]
        assert store.cursor("email.triage") and store.scalar("SELECT COUNT(*) FROM app_llm_runs WHERE status = 'done'") == 1
        args = calls[0]["args"]
        allowed = args[args.index("--allowedTools") + 1]
        assert "mcp__otto-read__email_search" in allowed and "email_flag" not in allowed
        # m1 is the only untriaged message left; the canned reply names m3 and m2 again, so nothing new lands
        assert await r.submit("email.triage", "email", "email", "scheduled", triage).done == "0 triaged, 0 high"
        await r.drain(1)

    run(main())
    read, full = [], []

    class Srv:
        def __init__(self, names):
            self.names = names

        def tool(self):
            return lambda f: (self.names.append(f), f)[1]

    register(Srv(read), Srv(full), store, email_config)
    flag = next(f for f in full if f.__name__ == "email_flag")
    assert flag("m1", "high", "Invoice is due.") == {"id": "m1", "priority": "high"}
    assert flag("m1", "bogus", "") ["error"].startswith("priority must be")
    high = next(f for f in read if f.__name__ == "email_triage")()
    assert [(h["id"], h["source"]) for h in high] == [("m3", "scheduled"), ("m1", "session")]
    assert store.one("SELECT verb FROM app_events WHERE module = 'email' ORDER BY id DESC")["verb"] == "flagged"


HTML = """<!DOCTYPE html><html><head><title>page title</title><style>p{color:red}</style>
<meta http-equiv="refresh" content="0;url=https://evil.example"><link rel="stylesheet" href="https://evil.example/x.css"></head>
<body style="background:#fff"><!--[if mso]><table><tr><td>outlook only</td></tr></table><![endif]-->
<div style="display:none;max-height:0">preheader text<p>mobile copy</div><span hidden>hidden span</span><i style="visibility: hidden">invisible</i>
<script>alert(1)</script>
<h1 style="font-size:40px" onclick="alert(2)">Big &amp; bold</h1>
<p>Hello <b>there</b>, <a href="https://shop.example/x?y=1" target="_blank">buy now</a> or <a href="https://example.com/">https://example.com/</a>
<a href="javascript:alert(3)">js</a> <a href="mailto:ann@example.com">write</a></p>
<img src="https://evil.example/pixel.gif" width="1"><img src="cid:hero" alt="Autumn sale">
<a href="https://share.example/icon"><img src="i.png"></a><a href="https://share.example/tw"><img src="t.png" alt="Twitter"></a>
<table border="1"><tr><td colspan="2" width="600">left</td></tr></table>
<form action="https://evil.example"><input name="q"><button>go</button></form>
<svg><a href="https://evil.example">svg link</a></svg><iframe src="https://evil.example"></iframe>
<ul><li>one<li>two</ul><pre>  code
  block</pre>
<div>unclosed <em>emphasis</div></body></html>"""


def test_email_body(store, email_config, fake):
    """The reader gets structure and text only; links become their raw URL; attachments are named, never read."""
    import re

    from app.modules.email.body import extract, sanitize

    out = sanitize(HTML)
    for bad in ("<a", "<img", "<script", "<style", "<meta", "<link", "<form", "<input", "<button", "<svg", "<iframe", "href=", "onclick",
                "style=", "width=", "alert(", "outlook only", "page title", "pixel.gif", "cid:", "javascript:", "svg link", "color:red",
                "preheader", "mobile copy", "hidden span", "invisible"):
        assert bad not in out, bad
    assert {re.sub(r' title="[^"]*"', "", t) for t in re.findall(r"<span[^>]*>", out)} == {'<span class="url">', '<span class="img">'}
    assert "<h1>Big &amp; bold</h1>" in out
    assert 'buy now<span class="url" title="https://shop.example/x?y=1"></span>' in out
    assert out.count("https://example.com/") == 1  # link text already is the url: no title repeats it
    assert 'write<span class="url" title="mailto:ann@example.com"></span>' in out and "\njs " in out
    assert '<span class="img">[image: Autumn sale]</span>' in out
    assert "share.example/icon" not in out  # an icon link with nothing to show shows no URL either
    assert '<span class="img">[image: Twitter]</span><span class="url" title="https://share.example/tw"></span>' in out
    assert '<td colspan="2">left</td>' in out
    assert "<li>one" in out and "<li>two" in out and "<pre>  code\n  block</pre>" in out
    assert "<div>unclosed <em>emphasis</em></div>" in out

    full = {"id": "m9", "snippet": "snip", "payload": {"mimeType": "multipart/mixed", "parts": [
        {"mimeType": "multipart/alternative", "parts": [
            {"mimeType": "text/plain", "body": {"data": b64("plain text\r\nline two")}},
            {"mimeType": "text/html", "body": {"data": b64(HTML)}},
        ]},
        {"mimeType": "text/plain", "filename": "notes.txt", "body": {"attachmentId": "a1", "data": b64("ATTACHED TEXT")}},
        {"mimeType": "application/pdf", "filename": "invoice.pdf", "body": {"attachmentId": "a2", "size": 5000}},
    ]}}
    b = extract(full)
    assert b["text"] == "plain text\nline two" and b["attachments"] == ["notes.txt", "invoice.pdf"]
    assert "ATTACHED" not in b["text"] and "ATTACHED" not in b["html"] and "<h1>Big" in b["html"]
    b = extract({"id": "m8", "snippet": "s", "payload": {"mimeType": "text/html", "body": {"data": b64("<p>Only <i>html</i><br>here</p>")}}})
    assert b == {"text": "Only html\nhere", "html": "<p>Only <i>html</i><br>here</p>", "attachments": []}
    b = extract({"id": "m7", "snippet": "just &amp; snippet", "payload": {"mimeType": "text/html", "body": {"data": b64("<div><img src='x'></div>")}}})
    assert b == {"text": "just & snippet", "html": None, "attachments": []}

    store.migrate((EMAIL_DIR / "schema.sql").read_text("utf-8"))

    async def main():
        r = Runner(store, email_config, registry=None, claude=None)
        await r.start()
        await r.submit("email.sync", "email", "gmail", "scheduled", sync).done
        await r.drain(1)

    run(main())
    read = []

    class Srv:
        def __init__(self, names):
            self.names = names

        def tool(self):
            return lambda f: (self.names.append(f), f)[1]

    register(Srv(read), Srv([]), store, email_config)
    email_get = next(f for f in read if f.__name__ == "email_get")
    got = run(email_get("m3"))
    assert got["body_text"] == "please sign the contract" and got["attachments"] == [] and "html" not in got and "error" not in got
    assert store.scalar("SELECT html FROM email_bodies WHERE message_id = 'm3'").startswith("<p>please <b>sign</b>")
    assert run(email_get("nope")) == {"error": "no message nope"}


def test_email_actions_take_one_id_or_many(email_config, fake):
    """The bar posts ids for a picked set and id for the open message; Home posts id for every module it shows."""

    async def main():
        app = build(email_config)
        await app.state.runner.start()
        async with client_for(app) as c:
            await app.state.runner.submit("email.sync", "email", "gmail", "scheduled", sync).done
            r = await c.post("/api/email/action/star", json={"id": "m1"})
            assert r.status_code == 200 and r.json() == {"count": 1} and fake.modified[-1]["ids"] == ["m1"], r.text
            r = await c.post("/api/email/action/archive", json={"ids": ["m1", "m2"]})
            assert r.json() == {"count": 2} and fake.modified[-1]["ids"] == ["m1", "m2"]
            assert (await c.post("/api/email/action/archive", json={})).status_code == 400
        await app.state.runner.drain(1)
        app.state.store.close()

    run(main())


def test_email_manual_sync(email_config, fake):
    """The button runs the scheduler's own task on the scheduler's own lock, and leaves the stamp the page reads."""

    async def main():
        app = build(email_config)
        await app.state.runner.start()
        async with client_for(app) as c:
            r = await c.post("/api/email/action/sync")
            assert r.status_code == 200 and "backfilled 3" in r.json()["result"], r.text
            synced = app.state.store.cursor("email.synced_at")
            assert synced and (await c.get("/api/email/blank")).json()["last_sync"] == synced
            job = (await c.get("/api/jobs")).json()[0]
            assert job["task"] == "email.sync" and job["resource"] == "gmail" and job["kind"] == "action"
        await app.state.runner.drain(1)
        app.state.store.close()

    run(main())


def test_email_consent_warning(store, email_config):
    """Re-consent is the owner's to run and nothing else can do it, so it waits on them before the outage, not after."""
    from app.modules.email.routes import queue

    token = email_config.email.token_file
    data = json.loads(token.read_text())
    assert queue(store) == []                                    # a token with no expiry never warns

    for delta, expected in ((timedelta(days=5), None), (timedelta(hours=6), "expires soon"), (timedelta(hours=-1), "has expired")):
        data["refresh_expires_at"] = iso(now() + delta)
        token.write_text(json.dumps(data))
        rows = queue(store)
        if expected is None:
            assert rows == [], "outside consent_warn_days"
        else:
            assert len(rows) == 1 and expected in rows[0]["text"] and rows[0]["module"] == "email"
            assert "app.modules.email.gmail consent" in rows[0]["text"]


def test_email_body_drops_what_carries_nothing():
    """A template mail is mostly spacer cells and alt text for images Otto never fetches; both read as blank space."""
    from app.modules.email.body import sanitize

    out = sanitize(
        "<table><tr><td>Refer a Friend</td><td>+ 2000 Points</td></tr>"
        "<tr><td> </td><td>&nbsp;</td></tr></table>"
        "<img alt='Enable images to view this content.' src='x'>"
        "<img alt='spacer' src='x'><img alt='' src='x'>"
        "<img alt='Autumn sale' src='x'><p>a<br><br><br><br>b</p>"
    )
    assert "<td>Refer a Friend</td><td>+ 2000 Points</td>" in out   # a row that means something keeps both cells
    assert "<tr></tr>" not in out and "<td>" in out                 # the spacer row goes entirely, the real one stays
    assert out.count("<tr>") == 1
    assert "Enable images" not in out and "spacer" not in out       # alt text for a client that blocks images says nothing here
    assert '<span class="img">[image: Autumn sale]</span>' in out   # alt text that names the picture survives
    assert "<br><br><br>" not in out
