from app.modules import Agent, Manifest, Schedule

MANIFEST = Manifest(
    name="graph",
    title="Graph",
    hue="#b3b06a",
    icon='<circle cx="5" cy="6" r="2"></circle><circle cx="15" cy="5" r="2"></circle><circle cx="10" cy="15" r="2"></circle><circle cx="16" cy="13" r="1.5"></circle><path d="M7 6.5l6-1M6 7.5l3 6M11.5 14l3-1"></path>',
    order=7,
    schedules=(Schedule(task="rebuild", every="15m", resource="graph"),),
    agent=Agent(
        placeholder="Curate the graph…",
        skills=("neighbors", "link", "merge", "prune"),
        read_tools=("graph_nodes", "graph_neighbors", "graph_items"),
        write_tools=("graph_link", "graph_unlink", "graph_merge", "graph_prune", "graph_restore"),
    ),
)
