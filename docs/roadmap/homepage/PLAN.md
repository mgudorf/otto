# Homepage v0 Plan

Status: superseded, 2026-09-08. The nightly search is owned by `docs/roadmap/web_search/PLAN.md` (owner's decision, 2026-09-08).

Home shows the night's findings through the existing `today` and `numbers` hooks of the `web_search` module, the same way it shows Memory and Business: a group on LEFT with a `+N` link, a `to review` number in the grid, and the shared item inspector with `Open`, `Agree`, `Disagree`. No Home code changes for this.

## What this plan had proposed

A `home.search` task, a `findings` table, topics in `[home] topics` in `config.toml`, and a `Review` group on Home. All of it is built by `web_search` instead: task `web_search.nightly`, table `search_findings`, topics as rows typed on the Search page.

## Remaining Home work

None in this item. The Home agent keeps its tool-less Current state block, which already lists every module's today rows, so it sees the findings without a change.
