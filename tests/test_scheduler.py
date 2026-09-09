from datetime import datetime, time, timedelta

from app.modules import Manifest, Module, Registry, Schedule
from app.runner import Runner
from app.scheduler import Scheduler, in_window, next_window_start
from app.store import iso, now, parse
from tests.conftest import run


def fake_registry(*modules):
    reg = Registry()
    for name, schedules in modules:
        async def task(ctx):
            return "ok"

        m = Manifest(name=name, title=name, hue="#fff", icon="", order=1, schedules=schedules)
        reg.modules[name] = Module(manifest=m, path=None, tasks={s.task: task for s in schedules}, router=None, schema=None,
                                   numbers=None, today=None, queue=None, item=None, context=None, register_tools=None, prompt=None)
    return reg


def test_window_logic():
    assert in_window(time(3, 0), time(2, 0), time(5, 0))
    assert not in_window(time(6, 0), time(2, 0), time(5, 0))
    assert in_window(time(23, 30), time(22, 0), time(1, 0)) and in_window(time(0, 30), time(22, 0), time(1, 0))
    assert not in_window(time(12, 0), time(22, 0), time(1, 0))
    local = datetime(2026, 9, 7, 14, 0).astimezone()
    assert next_window_start(local, time(2, 0)) == datetime(2026, 9, 8, 2, 0).astimezone()
    assert next_window_start(datetime(2026, 9, 7, 1, 0).astimezone(), time(2, 0)) == datetime(2026, 9, 7, 2, 0).astimezone()


def test_sync_creates_rows_and_removes_orphans(store, config):
    reg = fake_registry(("a", (Schedule("t1", "60s"), Schedule("t2", "24h", llm=True))))
    runner = Runner(store, config, reg, None, 1)
    sched = Scheduler(store, config, reg, runner)
    store.execute("INSERT INTO tasks(name, module, interval_seconds, next_run) VALUES ('zombie.x', 'zombie', 5, '2020-01-01T00:00:00+00:00')")
    sched.sync_tasks()
    rows = {r["name"]: r for r in store.query("SELECT * FROM tasks")}
    assert set(rows) == {"a.t1", "a.t2"}
    assert rows["a.t1"]["interval_seconds"] == 60 and rows["a.t1"]["llm"] == 0
    assert rows["a.t2"]["llm"] == 1
    # the llm task is either due now (inside the window) or waits for the window start
    nr = parse(rows["a.t2"]["next_run"]).astimezone()
    start, end = config.nightly.bounds()
    assert nr.time().replace(second=0, microsecond=0) == start or in_window(datetime.now().astimezone().time(), start, end)


def test_tick_submits_due_and_advances(store, config):
    reg = fake_registry(("a", (Schedule("t1", "60s"),)))
    runner = Runner(store, config, reg, None, 1)
    sched = Scheduler(store, config, reg, runner)
    sched.sync_tasks()

    async def main():  # tick submits into the runner, which lives on the loop
        assert sched.tick() == ["a.t1"]
        assert sched.tick() == []  # not due again yet

    run(main())
    row = store.one("SELECT * FROM tasks WHERE name = 'a.t1'")
    assert parse(row["next_run"]) > now() + timedelta(seconds=50)
    assert store.one("SELECT * FROM jobs")["status"] == "queued"


def test_disabled_and_missing_module(store, config):
    reg = fake_registry(("a", (Schedule("t1", "60s"),)))
    runner = Runner(store, config, reg, None, 1)
    sched = Scheduler(store, config, reg, runner)
    sched.sync_tasks()
    sched.set_enabled("a.t1", False)
    assert sched.tick() == []
    sched.set_enabled("a.t1", True)
    del reg.modules["a"]
    assert sched.tick() == []
    assert store.one("SELECT last_status, last_result FROM tasks WHERE name = 'a.t1'")["last_result"] == "module not loaded"
