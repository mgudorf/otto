# Science lists .py scripts but cannot run them

- Where: Science requirement 1 (experiments via .py or .ipynb); `app/modules/science/routes.py` `_run`, `app/static/pages/science.js`
- Found: 2026-09-10, sync-architecture
- Status: deferred by the owner

What happens: a `.py` file under the science root appears in LEFT and MIDDLE shows its source under the label `module`, but `action/run` answers 400 `only notebooks run` and the page offers no run control for it. Only `.ipynb` cells execute.

Expected: a script can be run on the user-wide Python from the page, with its output visible, the way a notebook cell is.

Fix: a roadmap item deciding the execution model for scripts (a subprocess on `science.python` with stdout streamed over the same events key, or a throwaway kernel); the owner scoped it out of Science version 0 on 2026-09-08.
