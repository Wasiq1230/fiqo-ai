"""
Tests for the two registration defects this feature exists to fix:

1. Addresses that cannot receive mail were accepted at signup.
2. Anyone could use an account without ever proving they own the address.

conftest disables both checks globally (the rest of the suite runs on
example.com addresses, which are deliberately rejected in production). These
tests switch them back on for their own duration.
"""
import pytest

from app.config import get_settings
from app.models import EmailVerification, User
from app.services import email_validation, verification
from tests.conftest import USER_PASSWORD, TestingSessionLocal, auth_header

settings = get_settings()


# ── Fixtures ────────────────────────────────────────────────────────────────


@pytest.fixture
def verification_on():
    """Enforce email verification for one test, then restore the default.

    `get_settings` is lru_cached, so every module holds this same object and
    mutating it here is visible to the router under test.
    """
    original = settings.require_email_verification
    settings.require_email_verification = True
    yield
    settings.require_email_verification = original


@pytest.fixture
def deliverability_on():
    original = settings.check_email_mx, settings.block_disposable_email
    settings.check_email_mx = True
    settings.block_disposable_email = True
    yield
    settings.check_email_mx, settings.block_disposable_email = original


@pytest.fixture
def sent_emails(monkeypatch):
    """Capture verification emails instead of sending them.

    Patched on the router's namespace because that is where the background task
    resolves the name from.
    """
    captured = []

    def _fake(to, name, link, expires_hours):
        captured.append({"to": to, "name": name, "link": link})
        return True

    monkeypatch.setattr("app.routers.auth.send_verification_email", _fake)
    return captured


def _token_from(link: str) -> str:
    return link.split("verify=", 1)[1]


# ── Fake / undeliverable addresses ──────────────────────────────────────────


def test_disposable_address_rejected(client, deliverability_on):
    res = client.post("/api/auth/register", json={
        "name": "Temp User",
        "email": "throwaway@mailinator.com",
        "password": USER_PASSWORD,
    })
    assert res.status_code == 422
    assert "disposable" in res.json()["detail"].lower()


def test_disposable_subdomain_rejected(client, deliverability_on):
    """Providers hand out dozens of aliases under one apex domain."""
    res = client.post("/api/auth/register", json={
        "name": "Temp User",
        "email": "x@inbox.mailinator.com",
        "password": USER_PASSWORD,
    })
    assert res.status_code == 422


def test_reserved_domain_rejected(client, deliverability_on):
    res = client.post("/api/auth/register", json={
        "name": "Nobody",
        "email": "nobody@example.com",
        "password": USER_PASSWORD,
    })
    assert res.status_code == 422


def test_domain_without_mx_rejected(client, deliverability_on, monkeypatch):
    """The 'asdf@asdf.com' case: syntactically fine, cannot receive mail."""
    monkeypatch.setattr(
        email_validation, "domain_can_receive_mail", lambda domain: False
    )
    res = client.post("/api/auth/register", json={
        "name": "Fake", "email": "asdf@asdf-not-a-real-domain.com",
        "password": USER_PASSWORD,
    })
    assert res.status_code == 422
    assert "mail server" in res.json()["detail"].lower()


def test_dns_failure_allows_registration(deliverability_on, monkeypatch):
    """A resolver outage is our problem — it must not block real signups.

    No live DNS here: a network-dependent assertion turns an unrelated CI
    hiccup into a red build.
    """
    class _ExplodingResolver:
        timeout = 0
        lifetime = 0

        def resolve(self, domain, record_type):
            raise RuntimeError("resolver exploded")

    monkeypatch.setattr(email_validation, "_DNS_AVAILABLE", True)
    monkeypatch.setattr(email_validation, "_cache_get", lambda d: None)
    monkeypatch.setattr(
        email_validation.dns.resolver, "Resolver", _ExplodingResolver
    )

    assert email_validation.domain_can_receive_mail("some-domain.test") is True


def test_good_address_accepted(client, deliverability_on, monkeypatch):
    monkeypatch.setattr(
        email_validation, "domain_can_receive_mail", lambda domain: True
    )
    res = client.post("/api/auth/register", json={
        "name": "Real User", "email": "real.user@gmail.com",
        "password": USER_PASSWORD,
    })
    assert res.status_code == 201


# ── Verification flow ───────────────────────────────────────────────────────


def test_register_returns_no_tokens_when_verification_required(
    client, verification_on, sent_emails
):
    res = client.post("/api/auth/register", json={
        "name": "New User", "email": "new@example.com", "password": USER_PASSWORD,
    })
    assert res.status_code == 201
    body = res.json()
    assert body["verification_required"] is True
    assert body["access_token"] is None
    assert len(sent_emails) == 1
    assert sent_emails[0]["to"] == "new@example.com"


def test_unverified_user_cannot_log_in(client, verification_on, sent_emails):
    client.post("/api/auth/register", json={
        "name": "New User", "email": "new@example.com", "password": USER_PASSWORD,
    })
    res = client.post("/api/auth/login", json={
        "email": "new@example.com", "password": USER_PASSWORD,
    })
    assert res.status_code == 403
    assert res.json()["detail"]["code"] == "email_not_verified"


def test_verify_link_activates_and_signs_in(client, verification_on, sent_emails):
    client.post("/api/auth/register", json={
        "name": "New User", "email": "new@example.com", "password": USER_PASSWORD,
    })
    token = _token_from(sent_emails[0]["link"])

    res = client.post("/api/auth/verify-email", json={"token": token})
    assert res.status_code == 200
    tokens = res.json()
    assert "access_token" in tokens

    me = client.get("/api/auth/me", headers=auth_header(tokens))
    assert me.status_code == 200
    assert me.json()["is_verified"] is True

    # And the account works normally from here on.
    login = client.post("/api/auth/login", json={
        "email": "new@example.com", "password": USER_PASSWORD,
    })
    assert login.status_code == 200


def test_verification_token_is_single_use(client, verification_on, sent_emails):
    client.post("/api/auth/register", json={
        "name": "New User", "email": "new@example.com", "password": USER_PASSWORD,
    })
    token = _token_from(sent_emails[0]["link"])

    assert client.post("/api/auth/verify-email", json={"token": token}).status_code == 200
    second = client.post("/api/auth/verify-email", json={"token": token})
    assert second.status_code == 400


def test_bad_token_rejected(client, verification_on):
    res = client.post("/api/auth/verify-email", json={"token": "x" * 40})
    assert res.status_code == 400


def test_token_is_not_stored_in_plaintext(client, verification_on, sent_emails):
    client.post("/api/auth/register", json={
        "name": "New User", "email": "new@example.com", "password": USER_PASSWORD,
    })
    raw = _token_from(sent_emails[0]["link"])

    db = TestingSessionLocal()
    try:
        stored = db.query(EmailVerification).one()
        assert stored.token_hash != raw
        assert len(stored.token_hash) == 64  # hex sha-256
    finally:
        db.close()


def test_resend_invalidates_the_previous_link(client, verification_on, sent_emails):
    client.post("/api/auth/register", json={
        "name": "New User", "email": "new@example.com", "password": USER_PASSWORD,
    })
    first = _token_from(sent_emails[0]["link"])

    # The cooldown guards the endpoint, so drive the issuing layer directly
    # rather than sleeping through it.
    db = TestingSessionLocal()
    try:
        user = db.query(User).filter(User.email == "new@example.com").one()
        second = verification.issue_token(db, user)
        db.commit()
    finally:
        db.close()

    assert client.post("/api/auth/verify-email", json={"token": first}).status_code == 400
    assert client.post("/api/auth/verify-email", json={"token": second}).status_code == 200


def test_resend_does_not_leak_account_existence(client, verification_on, sent_emails):
    """Unknown address and real address must be indistinguishable."""
    unknown = client.post("/api/auth/resend-verification",
                          json={"email": "nobody-here@example.com"})
    client.post("/api/auth/register", json={
        "name": "New User", "email": "new@example.com", "password": USER_PASSWORD,
    })
    known = client.post("/api/auth/resend-verification",
                        json={"email": "new@example.com"})

    assert unknown.status_code == known.status_code == 200
    assert unknown.json() == known.json()
    # No email was queued for the address that does not exist.
    assert [m["to"] for m in sent_emails] == ["new@example.com"]


def test_reregistering_unverified_email_resends_instead_of_409(
    client, verification_on, sent_emails, monkeypatch
):
    """Otherwise the user is stranded: cannot log in, cannot register again."""
    monkeypatch.setattr(settings, "email_resend_cooldown_seconds", 0)
    payload = {"name": "New User", "email": "new@example.com",
               "password": USER_PASSWORD}

    first = client.post("/api/auth/register", json=payload)
    assert first.status_code == 201

    second = client.post("/api/auth/register", json=payload)
    assert second.status_code == 201
    assert second.json()["verification_required"] is True
    assert len(sent_emails) == 2


def test_verified_email_still_conflicts(client, verification_on, sent_emails):
    payload = {"name": "New User", "email": "new@example.com",
               "password": USER_PASSWORD}
    client.post("/api/auth/register", json=payload)
    client.post("/api/auth/verify-email",
                json={"token": _token_from(sent_emails[0]["link"])})

    res = client.post("/api/auth/register", json=payload)
    assert res.status_code == 409


def test_resend_cooldown_blocks_rapid_reregistration(
    client, verification_on, sent_emails
):
    payload = {"name": "New User", "email": "new@example.com",
               "password": USER_PASSWORD}
    client.post("/api/auth/register", json=payload)
    res = client.post("/api/auth/register", json=payload)
    assert res.status_code == 429
    assert "Retry-After" in res.headers


# ── Degraded configuration ──────────────────────────────────────────────────


def test_verification_skipped_when_no_mail_transport(client, monkeypatch):
    """Enforcing verification with no way to send mail would strand everyone."""
    monkeypatch.setattr(settings, "require_email_verification", True)
    monkeypatch.setattr(settings, "email_provider", "smtp")
    monkeypatch.setattr(settings, "smtp_host", "")

    assert settings.email_verification_enabled is False

    res = client.post("/api/auth/register", json={
        "name": "New User", "email": "new@example.com", "password": USER_PASSWORD,
    })
    assert res.status_code == 201
    assert res.json()["verification_required"] is False
    assert res.json()["access_token"]


# ── Existing accounts ───────────────────────────────────────────────────────


def test_preexisting_account_is_not_locked_out(client, verification_on):
    """Rows created before this feature are grandfathered in as verified."""
    db = TestingSessionLocal()
    try:
        from app.security import hash_password
        db.add(User(
            name="Old User",
            email="old@example.com",
            hashed_password=hash_password(USER_PASSWORD),
            is_verified=True,  # what database.py backfills for existing rows
        ))
        db.commit()
    finally:
        db.close()

    res = client.post("/api/auth/login", json={
        "email": "old@example.com", "password": USER_PASSWORD,
    })
    assert res.status_code == 200
