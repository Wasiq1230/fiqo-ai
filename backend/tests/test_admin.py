"""Admin capability tests: RBAC, analytics, feedback CRUD, CSV export, self-guards."""
from tests.conftest import auth_header


def _make_feedback(client, **over):
    base = {
        "type": "complaint", "name": "Sam", "email": "sam@example.com",
        "subject": "Bad experience", "message": "The page was slow to load today.",
        "website": "",
    }
    base.update(over)
    return client.post("/api/feedback", json=base)


def test_analytics_shape(admin, client):
    res = client.get("/api/admin/analytics", headers=auth_header(admin["tokens"]))
    assert res.status_code == 200
    body = res.json()
    assert "users" in body and "feedback" in body
    assert "by_type" in body["feedback"] and "by_status" in body["feedback"]


def test_admin_lists_and_filters_feedback(admin, client):
    _make_feedback(client, type="bug", subject="Crash on upload")
    _make_feedback(client, type="feature", subject="Dark mode please")

    hdr = auth_header(admin["tokens"])
    all_items = client.get("/api/admin/feedback", headers=hdr).json()
    assert all_items["total"] == 2

    only_bugs = client.get("/api/admin/feedback?type=bug", headers=hdr).json()
    assert only_bugs["total"] == 1
    assert only_bugs["items"][0]["type"] == "bug"

    searched = client.get("/api/admin/feedback?q=dark", headers=hdr).json()
    assert searched["total"] == 1


def test_admin_resolves_feedback(admin, client):
    fb = _make_feedback(client).json()
    hdr = auth_header(admin["tokens"])
    res = client.patch(f"/api/admin/feedback/{fb['id']}", json={"status": "resolved"}, headers=hdr)
    assert res.status_code == 200
    body = res.json()
    assert body["status"] == "resolved"
    assert body["resolved_at"] is not None


def test_admin_export_csv(admin, client):
    _make_feedback(client)
    hdr = auth_header(admin["tokens"])
    res = client.get("/api/admin/feedback-export", headers=hdr)
    assert res.status_code == 200
    assert res.headers["content-type"].startswith("text/csv")
    assert "id,type,status" in res.text


def test_admin_cannot_deactivate_self(admin, client):
    hdr = auth_header(admin["tokens"])
    me = client.get("/api/auth/me", headers=hdr).json()
    res = client.patch(f"/api/admin/users/{me['id']}/status?is_active=false", headers=hdr)
    assert res.status_code == 400


def test_search_is_injection_safe(admin, client):
    # A SQL-ish payload must be treated as a literal search string, not executed.
    hdr = auth_header(admin["tokens"])
    res = client.get("/api/admin/feedback", params={"q": "'; DROP TABLE feedback;--"}, headers=hdr)
    assert res.status_code == 200
    assert res.json()["total"] == 0
    # Table still works afterwards.
    assert client.get("/api/admin/analytics", headers=hdr).status_code == 200
