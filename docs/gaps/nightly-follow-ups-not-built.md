# Scheduled follow-ups are not built

- Where: Nightly Process items 1 and 2 (previously scheduled follow-ups; tracking follow-ups and scheduling them for the future); `app/modules/web_search/`
- Found: 2026-09-10, sync-architecture
- Status: open, roadmap

What happens: a finding is found once, decided once, and never revisited. `search_findings` has no follow-up date and the nightly prompt never asks for one, so a time-bound finding the owner agreed with (a filing deadline, a release, a hearing) is not searched again when its date comes.

Expected: the nightly run may attach a follow-up date to a finding; agreed findings past that date are listed in the next prompt as things to follow up on and surface again on Home.

Fix: `docs/roadmap/web_search/PLAN.md` phase 2 (`follow_up_at`, `parent_id`, the prompt change, kind `follow`).
