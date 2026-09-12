# `python-multipart` is required by Chat's upload route but not in requirements.txt

- Where: `requirements.txt`; `app/modules/chat/routes.py` `upload` (`UploadFile = File(...)`)
- Found: 2026-09-12, sync-architecture
- Status: open

What happens: FastAPI needs `python-multipart` to parse a multipart form, and the Chat upload route declares one. The package is installed in the current `.venv` (0.0.32) because it was added by hand, but `requirements.txt` pins seven packages and not this one. A venv rebuilt from the file boots a daemon whose Chat module fails at import with FastAPI's `Form data requires "python-multipart"` error, and the registry drops Chat with that error in `module_errors`.

Expected: `pip install -r requirements.txt` yields a venv on which every module loads.

Fix: add `python-multipart==0.0.32` to `requirements.txt`.
