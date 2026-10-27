"""FIQO AI backend application package."""
import sys

__version__ = "1.0.0"

# ── Python version guard ─────────────────────────────────────────────────────
# The Docker image runs Python 3.12, and requirements.txt is pinned against it.
# SQLAlchemy 2.0.36 predates Python 3.14 and crashes while mapping any model
# that uses a union annotation (`Mapped[int | None]`) — Python 3.14 changed
# typing.Union's internals. The failure surfaces as a long traceback ending in
# "TypeError: descriptor '__getitem__' requires a 'typing.Union' object", which
# gives no hint that the real problem is the interpreter version.
#
# Catch it here, at import, with an actionable message.
_MIN = (3, 11)
_MAX_EXCLUSIVE = (3, 14)

if sys.version_info < _MIN or sys.version_info >= _MAX_EXCLUSIVE:
    _found = f"{sys.version_info.major}.{sys.version_info.minor}"
    raise RuntimeError(
        f"FIQO AI needs Python 3.11-3.13 (3.12 recommended - it is what the "
        f"Docker image runs). You are on Python {_found}.\n"
        f"\n"
        f"  Windows:  py -3.12 -m venv venv && venv\\Scripts\\activate\n"
        f"  macOS/Linux:  python3.12 -m venv venv && source venv/bin/activate\n"
        f"\n"
        f"  then: pip install -r requirements.txt\n"
        f"\n"
        f"Staying on {_found} would also mean your local stack differs from the "
        f"container you deploy, which is how 'works on my machine' happens."
    )
