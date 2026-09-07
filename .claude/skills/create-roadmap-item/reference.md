# PLAN.md sections, in order

Fill each; delete a section only if the item truly has nothing for it, and say so in one line.

1. **Title and status.** `# <Item> Plan`, then `Status: planning, <date>.` One sentence on what the
   item does for the owner and what breaks without it. Layman's terms before mechanisms.
2. **Sources.** Table `Source | Governs`: the ARCHITECTURE section, the app plan sections, the
   artboard elements, the code files, and every input the request named.
3. **Decisions.** Table `# | Decision | Why`, then one `Rejected:` line naming the alternatives.
4. **Layout.** Files added or changed, one line each. A module follows the Module contract:
   `app/modules/<name>/{__init__.py, schema.sql, tasks.py, routes.py, tools.py, agent.md}` plus
   `app/static/pages/<name>.js`.
5. **Contract.** What the shell and daemon expect: manifest fields (name, title, hue, icon,
   order), schedules (task, every, resource, llm), routes and their wire shapes, MCP tools split
   into read and write, the `numbers` / `today` / `item` / `context` hooks, the agent's job in
   one paragraph. Name every departure from the artboard.
6. **Data.** Tables for `schema.sql`, cursors, and external clients: which client scheduled
   tasks receive (read-only) and which user-action routes receive (write), and the test that
   proves the split.
7. **Phases.** Table `Phase | Builds | Usable result`. Each phase ends with something the owner
   can use; the first phase is a working MVP, not a shell.
8. **Tests.** Bullets, minimal. LLM touchpoints mocked at `app.claude.spawn`; the suite must
   stay offline.
9. **Manifest.** Four tables: `Present` (item, version or path, needed for), `Missing`
   (package, version, needed for, install target), `Needs you` (item, how), `Verify` (check,
   command). Versions are what PyPI or the machine reported today.
10. **Worktree.** The exact commands:
    `git worktree add ../otto-<slug> -b <slug>` then work there; when the branch is merged to
    `main`, run `/sync-architecture`.
11. **Pending decisions.** Only questions the owner must answer, numbered.

## Where the constraints come from

- Daemon requirements and module goals: `docs/ARCHITECTURE.md`.
- Frame, module and daemon contracts, tokens, hues, rail order: `docs/roadmap/app/PLAN.md`.
- Tenets and coding rules (no hard-coded parameters, MVP has functionality, minimal tests):
  the user-level and project `CLAUDE.md`, loaded every session.

## Manifest row examples

| Item | Version / location | Needed for |
|---|---|---|
| google-api-python-client | 2.200.0 on PyPI, not installed | Gmail read client |
| `data/secrets/token.json` | present; scopes to verify | Gmail OAuth |

| Check | Command |
|---|---|
| Token carries `gmail.readonly` | `.venv/Scripts/python.exe -c "import json; print(json.load(open('data/secrets/token.json'))['scopes'])"` |
