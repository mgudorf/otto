"""Email module: the read/write client split, sync against a fake Gmail, and actions through the app."""

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


def message(mid, sender, subject, labels, body="hello there", ms=1_757_239_200_000):
    return {"id": mid, "from": sender, "subject": subject, "labels": list(labels), "snippet": body[:40], "body": body, "ms": ms}


def gmail_json(m, full):
    out = {
        "id": m["id"], "threadId": "t" + m["id"], "labelIds": m["labels"], "snippet": m["snippet"], "internalDate": str(m["ms"]),
        "payload": {"headers": [{"name": "From", "value": m["from"]}, {"name": "To", "value": "owner@example.com"}, {"name": "Subject", "value": m["subject"]}]},
    }
    if full:
        out["payload"]["mimeType"] = "text/plain"
        out["payload"]["body"] = {"data": base64.urlsafe_b64encode(m["body"].encode()).decode()}
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
    return dataclasses.replace(config, email=Email(client_file=client, token_file=token, backfill_days=30, triage_batch=5))


@pytest.fixture
def fake(monkeypatch):
    g = FakeGmail([
        message("m1", "Ann <ann@example.com>", "Invoice ready", ["INBOX"], ms=1_757_239_200_000),
        message("m2", "Bob <bob@example.com>", "Lunch?", ["INBOX", "UNREAD"], ms=1_757_242_800_000),
        message("m3", "Cy <cy@example.com>", "Contract draft", ["INBOX", "UNREAD", "STARRED"], body="please sign the contract", ms=1_757_246_400_000),
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
    assert "gmail 403" in store.one("SELECT error FROM jobs ORDER BY id DESC")["error"]


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
            left = (await c.get("/api/email/left?chip=Unread")).json()
            assert [r["id"] for r in left["groups"][0]["rows"]] == ["m3", "m2"] and left["showing"] == "2 / 2"
            assert left["groups"][0]["rows"][0]["leading"]["dot"] == MANIFEST.hue

            r = await c.post("/api/email/action/archive", json={"ids": ["m1"]})
            assert r.status_code == 200 and r.json() == {"count": 1}, r.text
            assert fake.modified[-1] == {"ids": ["m1"], "addLabelIds": [], "removeLabelIds": ["INBOX"]}
            assert "m1" not in [x["id"] for g in (await c.get("/api/email/left")).json()["groups"] for x in g["rows"]]

            r = await c.post("/api/email/action/trash", json={"filter": {"query": "lunch", "chip": "Unread"}})
            assert r.json() == {"count": 1} and fake.modified[-1] == {"ids": ["m2"], "addLabelIds": ["TRASH"], "removeLabelIds": ["INBOX"]}
            assert (await c.post("/api/email/action/trash", json={"filter": {"query": "nothing-here", "chip": "All"}})).status_code == 400

            item = (await c.get("/api/email/item/m3")).json()
            assert item["text"] == "Contract draft\n\nplease sign the contract" and item["starred"] is True
            assert [a["verb"] for a in item["actions"]] == ["archive", "trash", "read", "unstar", "open"]
            assert (await c.post("/api/email/action/read", json={"ids": ["m3"]})).json() == {"count": 1}
            assert (await c.get("/api/email/item/m3")).json()["unread"] is False

            blank = (await c.get("/api/email/blank")).json()
            assert (blank["inbox"], blank["unread"], blank["flagged"], blank["priority"]) == (1, 0, 1, 0)
            numbers = (await c.get("/api/home/numbers")).json()
            assert next(n for n in numbers if n["module"] == "email")["value"] == 0
            ev = (await c.get("/api/events?module=email")).json()
            assert [e["verb"] for e in ev["events"]][:3] == ["marked read", "trashed", "archived"]
            assert ev["events"][1]["text"] == "1 messages matching 'lunch' · Unread"
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
        assert store.cursor("email.triage") and store.scalar("SELECT COUNT(*) FROM llm_runs WHERE status = 'done'") == 1
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
    assert store.one("SELECT verb FROM events WHERE module = 'email' ORDER BY id DESC")["verb"] == "flagged"
