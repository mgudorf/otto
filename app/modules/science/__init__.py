"""Science: the notebooks and scripts under science.root, run on the user-wide Python, one daemon-owned kernel per notebook, a subprocess per script."""

from app.modules import Agent, Manifest, Schedule
from app.modules.science import state

MANIFEST = Manifest(
    name="science",
    title="Science",
    hue="#7FC0C4",
    icon='<path d="M8 3v6l-4.5 7.5A1 1 0 0 0 4.4 18h11.2a1 1 0 0 0 .9-1.5L12 9V3"></path><path d="M6.5 3h7"></path><path d="M6 13h8"></path>',
    order=4,
    schedules=(Schedule(task="reap", every="5m", resource="science"), Schedule(task="due", every="5m")),
    agent=Agent(
        placeholder="Ask about the notebook…",
        skills=("inspect-cell", "run", "explain-output", "refactor", "files"),
        read_tools=("science_files", "science_notebook", "science_cell", "science_kernels"),
        write_tools=("science_run", "science_set_cell", "science_insert_cell", "science_new"),
        builtins=("Write", "Edit"),
    ),
)


def setup(config) -> None:
    """Called once by daemon.build: hold the [science] config and a fresh kernel registry."""
    config.science.root.mkdir(parents=True, exist_ok=True)
    state.configure(config.science)


async def shutdown() -> None:
    """Called from the daemon's lifespan exit: kernels die with the process."""
    await state.kernels.shutdown_all()
