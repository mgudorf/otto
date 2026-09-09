# The fourteen Education topics are not entered

- Where: Education Constraints 2 (the fourteen topics) and 4 (progress tracked by domain); `topics` table
- Found: 2026-09-09, sync-architecture
- Status: open, owner action

What happens: nothing seeds `topics`. The table starts empty, so `education.generate` returns `Skipped("no topics")` every night, Home shows `0 due`, and the progress table on the page has no rows. The module cannot do anything until the topics exist.

Expected: the fourteen topics named in the requirements are present, each at `start_difficulty`, so the nightly run has somewhere to aim.

Fix: add them from the Education page's add-topic box, or ask the tutor to add them with `education_add_topic`, one per requirement line. Giving each a one-line description of what the owner wants from it also steers the nightly prompt.
