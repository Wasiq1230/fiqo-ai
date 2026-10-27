"""
Shared pytest fixtures.

Design note — one engine, not two.

The previous version built a *second* SQLAlchemy engine (in-memory, StaticPool)
and pointed `get_db` at it via dependency_overrides, while the application kept
its own engine. That meant two different databases in one process: the fixtures
created tables on one, and anything the app touched outside a request — the
startup admin seeding, the /health/ready probe — used the other. Whether a given
test saw its tables then depended on fixture instantiation order, which is
exactly the kind of thing that produces "no such table: users" in one test and a
clean pass in the next.

Now there is a single engine: the application's own, pointed at a throwaway
SQLite file in a temp directory. Every code path — fixtures, requests, startup
hooks, health checks — reads and writes the same database, and the schema is
rebuilt around each test.
"""
import os
import pathlib
import shutil
import tempfile

# ── Environment, set before app import ───────────────────────────────────────
# Assigned unconditionally rather than with setdefault: a test run must never
# inherit the developer's real backend/.env or a stray shell variable.
_TMP_DIR = tempfile.mkdtemp(prefix="FiQO-tests-")
_DB_FILE = pathlib.Path(_TMP_DIR, "test.db")

os.environ["ENVIRONMENT"] = "development"
# A real file, not ":memory:", so every engine and thread sees the same data.
os.environ["DATABASE_URL"] = f"sqlite:///{_DB_FILE.as_posix()}"
os.environ["SECRET_KEY"] = "test-secret-key-that-is-long-enough-1234567890"
os.environ["GROQ_API_KEY"] = "test-key"          # no real key, no real API calls

# Starlette's TestClient sends "Host: testserver". TrustedHostMiddleware sits
# outermost, so without this every request is rejected with
# "400 Invalid host header" before it ever reaches a route.
os.environ["ALLOWED_HOSTS"] = "testserver,localhost,127.0.0.1"

# No first-run admin seeding in tests: the fixtures create their own admin, and
# seeding costs a bcrypt hash (cost 12) on every single test's startup.
os.environ["ADMIN_EMAIL"] = ""
os.environ["ADMIN_PASSWORD"] = ""

# ── Email checks, off by default ─────────────────────────────────────────────
# The deliverability check would reject the example.com addresses the whole
# suite is built on (correctly — example.com is reserved and accepts no mail),
# and a real DNS query per registration makes the suite slow and dependent on
# the network. test_email_verification.py switches these on deliberately for
# the tests that are actually about them.
os.environ["CHECK_EMAIL_MX"] = "false"
os.environ["BLOCK_DISPOSABLE_EMAIL"] = "false"
os.environ["REQUIRE_EMAIL_VERIFICATION"] = "false"
os.environ["EMAIL_PROVIDER"] = "console"
os.environ["FRONTEND_URL"] = "http://localhost:5173"

import pytest
from fastapi.testclient import TestClient

from app.database import Base, SessionLocal, engine
from app.main import app
from app.rate_limit import limiter

# The limiter is a process-wide singleton and the suite deliberately makes many
# auth/feedback calls in quick succession.
limiter.enabled = False

# The app's own session factory — same engine, same database.
TestingSessionLocal = SessionLocal

# Passwords used by fixtures. Deliberately NOT "Password123": that is on the
# common-password blocklist the API enforces, so using it here would make every
# fixture fail validation.
USER_PASSWORD = "TestPass456"
ADMIN_PASSWORD = "AdminPass456"


def pytest_sessionfinish(session, exitstatus):
    """Remove the throwaway database directory when the run ends."""
    shutil.rmtree(_TMP_DIR, ignore_errors=True)


@pytest.fixture(autouse=True)
def _fresh_schema():
    """Rebuild the schema around every test so tests cannot leak into each other."""
    Base.metadata.drop_all(bind=engine)      # idempotent if a run died mid-test
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)


@pytest.fixture
def client(_fresh_schema):
    """Requesting _fresh_schema explicitly guarantees tables exist before startup."""
    with TestClient(app) as c:
        yield c


@pytest.fixture
def registered(client):
    """Register a normal user and return their tokens + credentials."""
    creds = {"name": "Test User", "email": "user@example.com",
             "password": USER_PASSWORD}
    res = client.post("/api/auth/register", json=creds)
    assert res.status_code == 201, res.text
    return {"creds": creds, "tokens": res.json()}


@pytest.fixture
def admin(client):
    """Create an admin directly in the DB, then log in to obtain tokens."""
    from app.models import User, UserRole
    from app.security import hash_password

    db = TestingSessionLocal()
    try:
        db.add(User(
            name="Admin",
            email="admin@example.com",
            hashed_password=hash_password(ADMIN_PASSWORD),
            role=UserRole.admin,
            # Set explicitly so this fixture keeps working in the tests that
            # turn verification on — an unverified admin cannot log in.
            is_verified=True,
        ))
        db.commit()
    finally:
        db.close()

    res = client.post("/api/auth/login", json={
        "email": "admin@example.com", "password": ADMIN_PASSWORD,
    })
    assert res.status_code == 200, res.text
    return {"tokens": res.json()}


def auth_header(tokens):
    return {"Authorization": f"Bearer {tokens['access_token']}"}
