"""Feedback submission tests: valid submit, validation, honeypot spam block."""


def _payload(**over):
    base = {
        "type": "bug",
        "name": "Reporter",
        "email": "reporter@example.com",
        "subject": "Something broke",
        "message": "The quiz button did nothing when I clicked it twice.",
        "website": "",
    }
    base.update(over)
    return base


def test_submit_feedback_anonymous(client):
    res = client.post("/api/feedback", json=_payload())
    assert res.status_code == 201, res.text
    body = res.json()
    assert body["type"] == "bug"
    assert body["status"] == "open"


def test_submit_all_types(client):
    for t in ["feedback", "bug", "complaint", "feature", "support"]:
        res = client.post("/api/feedback", json=_payload(type=t, email=f"{t}@ex.com"))
        assert res.status_code == 201, f"{t}: {res.text}"


def test_honeypot_blocks_spam(client):
    # A populated honeypot must be rejected (schema enforces max_length=0 -> 422).
    res = client.post("/api/feedback", json=_payload(website="http://spam.example"))
    assert res.status_code in (400, 422)


def test_invalid_email_rejected(client):
    res = client.post("/api/feedback", json=_payload(email="not-an-email"))
    assert res.status_code == 422


def test_short_message_rejected(client):
    res = client.post("/api/feedback", json=_payload(message="hi"))
    assert res.status_code == 422


def test_mine_requires_auth(client):
    assert client.get("/api/feedback/mine").status_code == 401
