"""
Compatibility shim.

The real application now lives in the `app/` package (app.main:app). This file
used to contain the entire backend, including a hard-coded API key, wide-open
CORS, and several broken endpoints — all of which have been removed and replaced
by the layered architecture under app/.

Kept only so that older run commands like `uvicorn main:app` continue to work.
Prefer `uvicorn app.main:app` going forward.
"""
from app.main import app  # noqa: F401
