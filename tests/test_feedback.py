"""The feedback queue the workflows read: pending rows per module, clearing without deleting, the Patches entries that concern a module."""

import dataclasses
import re

from app.config import ROOT
from app.modules.feedback import queue

SCHEMA = (ROOT / "app" / "modules" / "feedback" / "schema.sql").read_text("utf-8")
ENTRY = "### {title}\n\n- Kind: bug\n- Where: {where}\n- Found: 2026-09-12, test\n- Status: open\n\nWhat happens: x.\n\nExpected: y.\n\nFix: z.\n\n"


def test_feedback_queue(store, config, tmp_path, capsys):
    v0 = re.sub(r",\n  cleared_at .*", "", SCHEMA, count=1)              # the table as it was before the column
    assert "cleared_at" not in v0
    store.migrate(v0)
    with store.raw() as conn:
        queue.add_cleared_at(conn)
        queue.add_cleared_at(conn)
        assert "cleared_at" in {r[1] for r in conn.execute("PRAGMA table_info(feedback)")}
    for page, item_module, text in (("science", None, "shortcuts"), ("home", "science", "cell highlight"), ("email", None, "bodies")):
        store.execute("INSERT INTO feedback(created_at, page, item_module, text) VALUES ('2026-09-12T00:00:00+00:00', ?, ?, ?)", (page, item_module, text))
    assert [r["text"] for r in queue.pending(store, ["science"])] == ["shortcuts", "cell highlight"]   # by page or by item
    assert queue.clear(store, ["science"]) == [1, 2]
    assert queue.pending(store, ["science"]) == [] and [r["id"] for r in queue.pending(store, ["email"])] == [3]
    assert store.scalar("SELECT count(*) FROM feedback") == 3                                          # cleared, not deleted

    docs = tmp_path / "docs"
    (docs / "science").mkdir(parents=True)
    (docs / "email").mkdir()
    (docs / "science" / "CLAUDE.md").write_text("# Science\n\n## Built\n\nx\n\n## Patches\n\n" + ENTRY.format(title="Own", where="`app/static/pages/science.js`"), "utf-8")
    (docs / "email" / "CLAUDE.md").write_text("# Email\n\n## Patches\n\nNone open.\n", "utf-8")
    (docs / "app").mkdir()
    (docs / "app" / "CLAUDE.md").write_text("# App\n\n## Patches\n\n" + ENTRY.format(title="Shared", where="`app/runner.py`; `app/modules/science/tasks.py`") + ENTRY.format(title="Other", where="`app/claude.py`"), "utf-8")
    assert [(e["doc"], e["title"], e["kind"]) for e in queue.patches(tmp_path, ["science"])] == [("app", "Shared", "bug"), ("science", "Own", "bug")]
    assert queue.patches(tmp_path, ["email"]) == []
    assert {e["doc"] for e in queue.patches(tmp_path, ["activity"])} == {"app"}                        # shell pages read the platform doc
    assert [e["title"] for e in queue.patches(tmp_path, ["app"])] == ["Shared", "Other"]
    assert queue.open_counts(tmp_path) == {"app": 2, "science": 1}

    cfg = dataclasses.replace(config, root=tmp_path)
    assert queue.main(["list", "nope"], cfg) == 2 and queue.main([], cfg) == 2
    assert queue.main(["list", "email"], cfg) == 0
    out = capsys.readouterr().out
    assert "1 pending" in out and "bodies" in out and "0 open" in out
    assert queue.main(["clear", "email"], cfg) == 0 and queue.pending(store, ["email"]) == []
