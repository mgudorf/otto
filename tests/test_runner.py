import asyncio

from app.runner import JobFailed, Runner, Skipped
from tests.conftest import run


def make_runner(store, config, cap):
    return Runner(store, config, registry=None, claude=None, max_concurrent=cap)


def test_same_resource_serializes_and_different_overlap(store, config):
    spans = {}

    def job(name, secs):
        async def fn(ctx):
            loop = asyncio.get_running_loop()
            start = loop.time()
            await asyncio.sleep(secs)
            spans[name] = (start, loop.time())
            return name

        return fn

    async def main():
        r = make_runner(store, config, cap=3)
        await r.start()
        a = r.submit("a", "t", "gmail", "scheduled", job("a", 0.15))
        b = r.submit("b", "t", "gmail", "scheduled", job("b", 0.15))
        c = r.submit("c", "t", "other", "scheduled", job("c", 0.15))
        await asyncio.gather(a.done, b.done, c.done)
        await r.drain(1)

    run(main())
    assert spans["a"][1] <= spans["b"][0] or spans["b"][1] <= spans["a"][0], "same resource must not overlap"
    assert spans["c"][0] < min(spans["a"][1], spans["b"][1]), "different resources overlap"
    assert {r["status"] for r in store.query("SELECT status FROM jobs")} == {"done"}


def test_cap_holds(store, config):
    running, peak = [0], [0]

    async def fn(ctx):
        running[0] += 1
        peak[0] = max(peak[0], running[0])
        await asyncio.sleep(0.05)
        running[0] -= 1

    async def main():
        r = make_runner(store, config, cap=2)
        await r.start()
        jobs = [r.submit(f"j{i}", "t", None, "scheduled", fn) for i in range(6)]
        await asyncio.gather(*(j.done for j in jobs))
        await r.drain(1)

    run(main())
    assert peak[0] == 2


def test_failure_is_local(store, config):
    async def boom(ctx):
        raise ValueError('kaput 401: {\n  "reason": "invalid_grant"\n}')

    async def ok(ctx):
        return "fine"

    store.execute("INSERT INTO tasks(name, module, interval_seconds) VALUES ('bad', 'm', 60)")

    async def main():
        r = make_runner(store, config, cap=1)
        await r.start()
        bad = r.submit("bad", "m", "r", "scheduled", boom)
        good = r.submit("good", "m", "r", "scheduled", ok)
        try:
            await bad.done
        except JobFailed:
            pass
        assert await good.done == "fine"
        await r.drain(1)

    run(main())
    rows = {r["task"]: r for r in store.query("SELECT * FROM jobs")}
    assert rows["bad"]["status"] == "failed" and "kaput" in rows["bad"]["error"]
    assert rows["good"]["status"] == "done"
    # a multi-line message keeps its reason: the event names the exception, last_result holds the tail of the traceback
    event = store.one("SELECT * FROM events WHERE verb = 'failed'")["text"]
    assert event.startswith("bad: ValueError: kaput 401:") and "invalid_grant" in event
    assert "invalid_grant" in store.one("SELECT last_result FROM tasks WHERE name = 'bad'")["last_result"]


def test_skipped_and_logs_and_commit(store, config):
    async def fn(ctx):
        ctx.log("hello")
        with ctx.commit(cursor=("k", "v1")) as conn:
            conn.execute("INSERT INTO settings(key, value) VALUES ('x', '1')")
        return Skipped("nothing to do")

    async def main():
        r = make_runner(store, config, cap=1)
        await r.start()
        j = r.submit("s", "m", None, "scheduled", fn)
        await j.done
        await r.drain(1)

    run(main())
    job = store.one("SELECT * FROM jobs")
    assert job["status"] == "skipped" and job["result"] == "nothing to do"
    assert store.one("SELECT * FROM job_logs")["message"] == "hello"
    assert store.cursor("k") == "v1" and store.setting("x") == 1
