"""Auth flow tests: register, login, refresh, /me, and RBAC guards."""
from tests.conftest import auth_header


def test_health(client):
    res = client.get("/health")
    assert res.status_code == 200
    assert res.json()["status"] == "ok"


def test_security_headers_present(client):
    res = client.get("/health")
    assert res.headers["X-Content-Type-Options"] == "nosniff"
    assert res.headers["X-Frame-Options"] == "DENY"
    assert "Content-Security-Policy" in res.headers


def test_register_and_me(registered, client):
    res = client.get("/api/auth/me", headers=auth_header(registered["tokens"]))
    assert res.status_code == 200
    body = res.json()
    assert body["email"] == "user@example.com"
    assert body["role"] == "user"
    # Password hash must never be serialized to the client.
    assert "hashed_password" not in body and "password" not in body


def test_duplicate_email_rejected(registered, client):
    res = client.post("/api/auth/register", json=registered["creds"])
    assert res.status_code == 409


def test_weak_password_rejected(client):
    res = client.post(
        "/api/auth/register",
        json={"name": "X", "email": "weak@example.com", "password": "short"},
    )
    assert res.status_code == 422


def test_login_wrong_password(registered, client):
    res = client.post(
        "/api/auth/login",
        json={"email": "user@example.com", "password": "WrongPass123"},
    )
    assert res.status_code == 401


def test_login_and_refresh(registered, client):
    login = client.post("/api/auth/login", json={
        "email": registered["creds"]["email"],
        "password": registered["creds"]["password"],
    })
    assert login.status_code == 200
    refresh_token = login.json()["refresh_token"]

    refreshed = client.post("/api/auth/refresh", json={"refresh_token": refresh_token})
    assert refreshed.status_code == 200
    assert "access_token" in refreshed.json()


def test_refresh_rejects_garbage(client):
    res = client.post("/api/auth/refresh", json={"refresh_token": "not-a-token"})
    assert res.status_code == 401


def test_me_requires_auth(client):
    assert client.get("/api/auth/me").status_code == 401


def test_admin_route_forbidden_for_normal_user(registered, client):
    res = client.get("/api/admin/analytics", headers=auth_header(registered["tokens"]))
    assert res.status_code == 403
