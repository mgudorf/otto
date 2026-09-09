## OTTO 

Otto, a personification of the word "auto" is a PERSONALIZED dashboard application aimed at meeting MY SPECIFIC NEEDS in regards to optimizing my life, throughput, and reducing wasted time and effort. 

## Intent

1. Dashboard which
   1. Covers the items that I have either had a hard time adopting/keeping up to date
   2. Have interest in or utilize frequently
   3. Slowly creates a catalog of data which defines who "I" am which will be leveraged for either recall, context, or creating "paragon" agents which enforce items that uniquely benefit me. 

## Development

1. Use worktrees for branches for each independent module.
2. **Every module touches the same shared seams, so every merge conflicts there.** The seams: `app/config.py` (a dataclass, a `Config` field, a `load` line), `config.toml` (a section), `app/static/shell.js` (an import and the `PAGES` map), the module contract docstring in `app/modules/__init__.py`, and shared tests that reach into Home. Each branch adds adjacent lines at the same spot, so git cannot auto-merge them.
   - On a branch: add your entries in rail order (the `order` in the manifest), one line each, never reflow neighbours. Tests find a module by name, never by index.
   - Before merging: `git merge main` into the branch first; the branch resolves, `main` stays clean.
   - Resolving: keep both sides in rail order. The contract docstring and shared tests take `main`'s side, then re-add anything only the branch had. Run the suite on `main` before committing the merge, then `/sync-architecture`.