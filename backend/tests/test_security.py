"""
Regression tests for the hardening pass.

Each test here pins down a specific issue that was fixed, so a future refactor
that quietly reintroduces it fails the suite instead of shipping.
"""
import pytest
from fastapi import status

from tests.conftest import auth_header


# ── Session revocation (logout / password change / admin action) ─────────────


def test_logout_invalidates_existing_tokens(client, registered):
    """Clearing localStorage is not logout. The token must die server-side."""
    tokens = registered["tokens"]
    assert client.get("/api/auth/me", headers=auth_header(tokens)).status_code == 200

    assert client.post("/api/auth/logout", headers=auth_header(tokens)).status_code == 200

    # The exact same access token must now be refused.
    assert client.get("/api/auth/me", headers=auth_header(tokens)).status_code == 401


def test_logout_also_kills_the_refresh_token(client, registered):
    """A stolen refresh token used to stay valid for its full lifetime."""
    tokens = registered["tokens"]
    client.post("/api/auth/logout", headers=auth_header(tokens))

    res = client.post("/api/auth/refresh",
                      json={"refresh_token": tokens["refresh_token"]})
    assert res.status_code == 401


def test_password_change_revokes_old_sessions(client, registered):
    tokens = registered["tokens"]
    res = client.post(
        "/api/auth/change-password",
        headers=auth_header(tokens),
        json={"current_password": registered["creds"]["password"],
              "new_password": "BrandNewPass456"},
    )
    assert res.status_code == 200
    new_tokens = res.json()

    # Old token dead, new token alive.
    assert client.get("/api/auth/me", headers=auth_header(tokens)).status_code == 401
    assert client.get("/api/auth/me", headers=auth_header(new_tokens)).status_code == 200


def test_change_password_requires_the_current_one(client, registered):
    res = client.post(
        "/api/auth/change-password",
        headers=auth_header(registered["tokens"]),
        json={"current_password": "NotTheRightOne1", "new_password": "BrandNewPass456"},
    )
    assert res.status_code == 400


def test_admin_can_force_logout_a_user(client, registered, admin):
    user_id = client.get("/api/auth/me",
                         headers=auth_header(registered["tokens"])).json()["id"]

    res = client.post(f"/api/admin/users/{user_id}/revoke-sessions",
                      headers=auth_header(admin["tokens"]))
    assert res.status_code == 200
    assert client.get("/api/auth/me",
                      headers=auth_header(registered["tokens"])).status_code == 401


def test_deactivating_a_user_kills_their_live_session(client, registered, admin):
    """Blocking future logins is not enough if the current token still works."""
    user_id = client.get("/api/auth/me",
                         headers=auth_header(registered["tokens"])).json()["id"]

    client.patch(f"/api/admin/users/{user_id}/status?is_active=false",
                 headers=auth_header(admin["tokens"]))

    assert client.get("/api/auth/me",
                      headers=auth_header(registered["tokens"])).status_code == 401


# ── Token type confusion ─────────────────────────────────────────────────────


def test_refresh_token_cannot_be_used_as_an_access_token(client, registered):
    fake = {"access_token": registered["tokens"]["refresh_token"]}
    assert client.get("/api/auth/me", headers=auth_header(fake)).status_code == 401


@pytest.mark.parametrize("token", [
    "",
    "not-a-jwt",
    "eyJhbGciOiJub25lIiwidHlwIjoiSldUIn0.eyJzdWIiOiIxIiwidHlwZSI6ImFjY2VzcyJ9.",
])
def test_malformed_and_unsigned_tokens_are_rejected(client, token):
    res = client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert res.status_code == 401


# ── Password policy ──────────────────────────────────────────────────────────


def test_password_beyond_bcrypt_limit_is_rejected_not_truncated(client):
    """bcrypt ignores everything past 72 bytes; silent truncation is a trap."""
    res = client.post("/api/auth/register", json={
        "name": "Long Pass", "email": "long@example.com",
        "password": "A1" + "x" * 100,
    })
    assert res.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY


def test_common_passwords_are_rejected(client):
    res = client.post("/api/auth/register", json={
        "name": "Weak", "email": "weak@example.com", "password": "password123",
    })
    assert res.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY


# ── CSV formula injection in the admin export ────────────────────────────────


def test_feedback_export_neutralises_spreadsheet_formulas(client, admin):
    """Feedback is public input; the export is opened by an admin in Excel."""
    payload = {
        "type": "bug", "name": "Attacker", "email": "attacker@example.com",
        "subject": "=cmd|'/c calc'!A1",
        "message": "=HYPERLINK(\"http://evil.example\",\"Click me\") padding text",
        "website": "",
    }
    assert client.post("/api/feedback", json=payload).status_code == 201

    csv_text = client.get("/api/admin/feedback-export",
                          headers=auth_header(admin["tokens"])).text
    for line in csv_text.splitlines()[1:]:
        for cell in line.split(","):
            stripped = cell.strip('"')
            assert not stripped.startswith(("=", "+", "@")), f"live formula in export: {cell}"


# ── Error responses must not echo submitted values ───────────────────────────


def test_validation_errors_do_not_echo_the_submitted_password(client):
    res = client.post("/api/auth/register", json={
        "name": "X", "email": "not-an-email", "password": "SuperSecret123",
    })
    assert res.status_code == 422
    assert "SuperSecret123" not in res.text


# ── Health probes ────────────────────────────────────────────────────────────


def test_liveness_and_readiness(client):
    assert client.get("/health").status_code == 200
    ready = client.get("/health/ready")
    assert ready.status_code == 200
    assert ready.json()["database"] == "up"
