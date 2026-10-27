"""PDF routes are protected — unauthenticated access is rejected before any AI call."""


def test_pdf_requires_auth(client):
    # No token → 401/403 before any file processing happens.
    res = client.post("/api/pdf/summarize")
    assert res.status_code in (401, 403)


def test_pdf_rejects_missing_file_when_authenticated(registered, client):
    from tests.conftest import auth_header
    res = client.post("/api/pdf/summarize", headers=auth_header(registered["tokens"]))
    # Authenticated but no file → validation error, not a 500.
    assert res.status_code == 422
