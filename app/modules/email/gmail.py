"""Gmail over plain REST. Tasks and tools get GmailRead; GmailWrite exists for user-action routes only.

`python -m app.modules.email.gmail consent` runs the OAuth flow on the client's registered redirect
and writes the token file. TRANSPORT is the seam tests replace with an httpx.MockTransport.
"""

from __future__ import annotations

import asyncio
import base64
import html
import json
import re
import sys
import time
import webbrowser
from datetime import datetime, timedelta, timezone
from email.utils import parseaddr
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlencode, urlparse

import httpx

from app.store import iso, now

API = "https://gmail.googleapis.com/gmail/v1/users/me"
SCOPE = "https://www.googleapis.com/auth/gmail.modify"
MODIFY_CHUNK = 1000                     # ids per batchModify call, the API's maximum
REFRESH_MARGIN = timedelta(seconds=60)  # refresh this long before the access token expires
QUOTA_WAIT = 61.0                       # Gmail's quota is per minute: on a refusal every request pauses this long
RETRY_ATTEMPTS = 5                      # refusals one call tolerates before it fails (about five minutes)
TRANSPORT: httpx.BaseTransport | None = None


class GmailError(Exception):
    def __init__(self, status: int, text: str):
        super().__init__(f"gmail {status}: {text[:300]}")
        self.status = status


def save_token(path: Path, old: dict, fresh: dict) -> dict:
    """Merge a token response into the file. A stale refresh-token lifetime never survives a refresh."""
    data = {k: v for k, v in old.items() if k != "refresh_token_expires_in"}
    data.update(fresh)
    data["expires_at"] = iso(now() + timedelta(seconds=int(fresh["expires_in"])))
    path.write_text(json.dumps(data, indent=1), "utf-8")
    return data


class Token:
    """The owner's OAuth token on disk, refreshed in place when it is about to expire."""

    def __init__(self, client_file: Path, token_file: Path):
        self.client = json.loads(client_file.read_text("utf-8"))["web"]
        self.path = token_file
        self.data = json.loads(token_file.read_text("utf-8"))

    def fresh(self) -> bool:
        return datetime.fromisoformat(self.data["expires_at"]) - REFRESH_MARGIN > now()

    async def bearer(self, http: httpx.AsyncClient) -> str:
        if not self.fresh():
            r = await http.post(self.client["token_uri"], data={
                "client_id": self.client["client_id"], "client_secret": self.client["client_secret"],
                "refresh_token": self.data["refresh_token"], "grant_type": "refresh_token",
            })
            if r.status_code != 200:
                raise GmailError(r.status_code, r.text)
            self.data = save_token(self.path, self.data, r.json())
        return self.data["access_token"]


def quota_refusal(r: httpx.Response) -> bool:
    """Gmail answers a per-minute quota overrun with 429, or 403 naming the quota."""
    if r.status_code == 429:
        return True
    return r.status_code == 403 and ("quota" in r.text.lower() or "ratelimit" in r.text.lower())


class GmailRead:
    """Reads only: profile, message ids, metadata, bodies, history. Nothing here can change the mailbox."""

    def __init__(self, client_file: Path, token_file: Path):
        self.token = Token(client_file, token_file)
        self.http = httpx.AsyncClient(timeout=30, transport=TRANSPORT)
        self.pause_until = 0.0  # monotonic; shared by every in-flight call, so one refusal pauses them all

    async def aclose(self) -> None:
        await self.http.aclose()

    async def _call(self, method: str, path: str, **kw) -> dict:
        for attempt in range(RETRY_ATTEMPTS + 1):
            await asyncio.sleep(max(0.0, self.pause_until - time.monotonic()))
            headers = {"Authorization": f"Bearer {await self.token.bearer(self.http)}"}
            r = await self.http.request(method, f"{API}/{path}", headers=headers, **kw)
            if attempt < RETRY_ATTEMPTS and quota_refusal(r):
                self.pause_until = max(self.pause_until, time.monotonic() + QUOTA_WAIT)
                continue
            if r.status_code >= 400:
                raise GmailError(r.status_code, r.text)
            return r.json() if r.content else {}
        raise AssertionError("unreachable")

    async def profile(self) -> dict:
        return await self._call("GET", "profile")

    async def list_ids(self, query: str) -> list[str]:
        """Every message id matching a Gmail search, newest first. Spam and trash are excluded by Gmail."""
        ids, page = [], None
        while True:
            params = {"q": query, "maxResults": 500}
            if page:
                params["pageToken"] = page
            data = await self._call("GET", "messages", params=params)
            ids += [m["id"] for m in data.get("messages", [])]
            page = data.get("nextPageToken")
            if not page:
                return ids

    async def metadata(self, message_id: str) -> dict:
        """Headers, labels, date and snippet of one message, shaped for an email_messages row."""
        params = [("format", "metadata"), ("metadataHeaders", "From"), ("metadataHeaders", "To"), ("metadataHeaders", "Subject")]
        return parse_metadata(await self._call("GET", f"messages/{message_id}", params=params))

    async def body(self, message_id: str) -> str:
        return extract_text(await self._call("GET", f"messages/{message_id}", params={"format": "full"}))

    async def history(self, start_history_id: str) -> dict:
        """Every history record since start_history_id, plus the newest history id. 404 means the id expired."""
        records, page, newest = [], None, start_history_id
        while True:
            params = {"startHistoryId": start_history_id, "maxResults": 500}
            if page:
                params["pageToken"] = page
            data = await self._call("GET", "history", params=params)
            records += data.get("history", [])
            newest = data.get("historyId", newest)
            page = data.get("nextPageToken")
            if not page:
                return {"history": records, "historyId": str(newest)}


class GmailWrite(GmailRead):
    """Adds the one mutation the module needs. Only user-action routes construct this."""

    async def modify(self, ids: list[str], add: tuple[str, ...] = (), remove: tuple[str, ...] = ()) -> int:
        for i in range(0, len(ids), MODIFY_CHUNK):
            await self._call("POST", "messages/batchModify", json={
                "ids": ids[i:i + MODIFY_CHUNK], "addLabelIds": list(add), "removeLabelIds": list(remove),
            })
        return len(ids)


def read_client(config) -> GmailRead:
    return GmailRead(config.email.client_file, config.email.token_file)


def write_client(config) -> GmailWrite:
    return GmailWrite(config.email.client_file, config.email.token_file)


# ---- message shapes ------------------------------------------------------------------------
def parse_metadata(msg: dict) -> dict:
    headers = {h["name"].lower(): h["value"] for h in msg.get("payload", {}).get("headers", [])}
    name, addr = parseaddr(headers.get("from", ""))
    stamp = datetime.fromtimestamp(int(msg["internalDate"]) / 1000, tz=timezone.utc)
    return {
        "id": msg["id"],
        "thread_id": msg.get("threadId"),
        "from_name": name or addr,
        "from_addr": addr,
        "to_addr": headers.get("to", ""),
        "subject": headers.get("subject", "") or "(no subject)",
        "snippet": html.unescape(msg.get("snippet", "")),
        "internal_date": iso(stamp),
        "labels": json.dumps(msg.get("labelIds", [])),
    }


def extract_text(msg: dict) -> str:
    """text/plain parts joined; failing that, text/html with the tags stripped; failing that, the snippet."""
    plain, rich = [], []

    def walk(part: dict) -> None:
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
    if plain:
        return "\n".join(plain).replace("\r\n", "\n").strip()
    if rich:
        text = re.sub(r"(?is)<(script|style).*?</\1>", "", "\n".join(rich))
        text = re.sub(r"(?i)<br\s*/?>|</p>|</div>|</tr>", "\n", text)
        text = html.unescape(re.sub(r"<[^>]+>", "", text))
        return re.sub(r"\n\s*\n+", "\n\n", text).strip()
    return html.unescape(msg.get("snippet", ""))


# ---- consent ---------------------------------------------------------------------------------
def consent(config) -> None:
    """Interactive, run once: browser consent on the client's registered redirect, then write the token file."""
    client = json.loads(config.email.client_file.read_text("utf-8"))["web"]
    redirect = client["redirect_uris"][0]
    u = urlparse(redirect)
    url = client["auth_uri"] + "?" + urlencode({
        "client_id": client["client_id"], "redirect_uri": redirect, "response_type": "code",
        "scope": SCOPE, "access_type": "offline", "prompt": "consent",
    })
    got: dict[str, str] = {}

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            got.update({k: v[0] for k, v in parse_qs(urlparse(self.path).query).items()})
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"Otto has the code. You can close this tab.")

        def log_message(self, *args):
            pass

    server = HTTPServer((u.hostname, u.port), Handler)
    print("Waiting for consent at", redirect)
    webbrowser.open(url)
    while "code" not in got and "error" not in got:
        server.handle_request()
    server.server_close()
    if "error" in got:
        sys.exit(f"consent refused: {got['error']}")
    r = httpx.post(client["token_uri"], data={
        "code": got["code"], "client_id": client["client_id"], "client_secret": client["client_secret"],
        "redirect_uri": redirect, "grant_type": "authorization_code",
    })
    if r.status_code != 200:
        sys.exit(f"token exchange failed: {r.status_code} {r.text[:300]}")
    data = save_token(config.email.token_file, {}, r.json())
    print("Token written to", config.email.token_file, "scope", data.get("scope"))


if __name__ == "__main__":
    from app.config import load

    if sys.argv[1:] == ["consent"]:
        consent(load())
    else:
        sys.exit("usage: python -m app.modules.email.gmail consent")
