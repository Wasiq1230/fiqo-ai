"""
Outbound email.

Four transports behind one function, chosen by EMAIL_PROVIDER:

* ``smtp``    — any SMTP server (Gmail with an app password, Brevo, Mailgun…)
* ``brevo``   — Brevo's HTTP API
* ``resend``  — Resend's HTTP API
* ``console`` — writes the message to the log; the local-development default

**On SMTP and PaaS hosts.** Render's free web services block outbound traffic
to SMTP ports entirely, and several other platforms do the same to stop their
free tiers being used as spam relays. The failure looks like a connect timeout
deep inside ``smtplib``, which reads like a credentials problem and is not one
— no SMTP configuration can fix it. The two HTTP transports exist for that
case: they talk to port 443, which is never blocked.

Between the two, ``brevo`` is the one that works without owning a domain: it
needs a verified *sender address*, and will then deliver to anyone. Resend
without a verified domain can only send to the account owner's own address,
which is fine for testing and useless for real users.

Two properties matter more than the transport:

**Sending never fails a request.** ``send_email`` returns a bool and swallows
every exception. A signup that succeeded in the database must not report an
error because a mail server was briefly unreachable — the user has an account,
and there is a resend button for the email.

**Sending never blocks the event loop.** SMTP is synchronous socket I/O and can
sit for seconds; doing that inside an async request handler stalls every other
request in the process. Callers hand this to ``BackgroundTasks`` (FastAPI runs
sync background functions in a threadpool), so the HTTP response returns
immediately.
"""
from __future__ import annotations

import logging
import smtplib
import ssl
from email.message import EmailMessage
from email.utils import formataddr, parseaddr

from app.config import get_settings

logger = logging.getLogger("FiQO.email")
settings = get_settings()


def _sender() -> tuple[str, str]:
    """(display name, address) for the From header."""
    name, addr = parseaddr(settings.email_sender)
    return name or settings.app_name, addr or settings.email_sender


def send_email(to: str, subject: str, html_body: str, text_body: str) -> bool:
    """Deliver one message. Returns True on success, False on any failure.

    Both a plain-text and an HTML part are always supplied: text-only clients,
    and the spam filters that penalise HTML-only mail, both need the former.
    """
    provider = settings.email_provider

    try:
        if provider == "console":
            return _send_console(to, subject, text_body)
        if provider == "smtp":
            return _send_smtp(to, subject, html_body, text_body)
        if provider == "brevo":
            return _send_brevo(to, subject, html_body, text_body)
        if provider == "resend":
            return _send_resend(to, subject, html_body, text_body)
        logger.error("Unknown EMAIL_PROVIDER %r — message to %s dropped",
                     provider, _redact(to))
        return False
    except Exception:
        # Log the address in redacted form: full recipient addresses in logs
        # are a privacy problem and log aggregators are rarely access-controlled
        # as tightly as the database.
        logger.exception("Failed to send %r to %s", subject, _redact(to))
        return False


def _redact(email: str) -> str:
    """a.person@gmail.com -> a***n@gmail.com"""
    local, _, domain = email.partition("@")
    if not domain:
        return "***"
    if len(local) <= 2:
        return f"{local[:1]}***@{domain}"
    return f"{local[0]}***{local[-1]}@{domain}"


# ── console ──────────────────────────────────────────────────────────────────


def _send_console(to: str, subject: str, text_body: str) -> bool:
    logger.info(
        "\n"
        "──────── EMAIL (console transport, not actually sent) ────────\n"
        "To:      %s\n"
        "Subject: %s\n"
        "\n%s\n"
        "──────────────────────────────────────────────────────────────",
        to, subject, text_body,
    )
    return True


# ── SMTP ─────────────────────────────────────────────────────────────────────


def _build_message(to: str, subject: str, html_body: str,
                   text_body: str) -> EmailMessage:
    msg = EmailMessage()
    name, addr = _sender()
    msg["From"] = formataddr((name, addr))
    msg["To"] = to
    msg["Subject"] = subject
    # Gives the recipient's client something sane to reply to, and helps
    # deliverability versus a bare no-reply with no reply path.
    msg["Reply-To"] = addr
    msg.set_content(text_body)
    msg.add_alternative(html_body, subtype="html")
    return msg


def _send_smtp(to: str, subject: str, html_body: str, text_body: str) -> bool:
    if not (settings.smtp_host and settings.smtp_user and settings.smtp_password):
        logger.error("SMTP is selected but not configured — message dropped")
        return False

    msg = _build_message(to, subject, html_body, text_body)
    context = ssl.create_default_context()
    timeout = settings.smtp_timeout_seconds

    try:
        if settings.smtp_use_ssl:
            # Implicit TLS, normally port 465.
            with smtplib.SMTP_SSL(settings.smtp_host, settings.smtp_port,
                                  timeout=timeout, context=context) as server:
                server.login(settings.smtp_user, settings.smtp_password)
                server.send_message(msg)
        else:
            # Plain connection upgraded with STARTTLS, normally port 587. The
            # upgrade is mandatory when smtp_use_tls is set: silently continuing
            # unencrypted would put the SMTP password on the wire in cleartext.
            with smtplib.SMTP(settings.smtp_host, settings.smtp_port,
                              timeout=timeout) as server:
                server.ehlo()
                if settings.smtp_use_tls:
                    server.starttls(context=context)
                    server.ehlo()
                server.login(settings.smtp_user, settings.smtp_password)
                server.send_message(msg)
    except (OSError, smtplib.SMTPConnectError) as exc:
        # Failing before authentication means the socket never opened. On a PaaS
        # that is almost always the host blocking outbound SMTP, not a bad
        # password — and the raw traceback points at smtplib, which sends people
        # off regenerating credentials that were fine. Name the real cause here.
        raise RuntimeError(
            f"Could not open an SMTP connection to {settings.smtp_host}:"
            f"{settings.smtp_port} ({exc.__class__.__name__}: {exc}). This is a "
            "network problem, not a credentials problem — many hosts (Render's "
            "free tier among them) block outbound SMTP ports. Switch to an HTTP "
            "transport: EMAIL_PROVIDER=brevo with BREVO_API_KEY."
        ) from exc

    logger.info("Sent %r to %s via SMTP", subject, _redact(to))
    return True


# ── Brevo HTTP API ───────────────────────────────────────────────────────────


def _send_brevo(to: str, subject: str, html_body: str, text_body: str) -> bool:
    """Send over HTTPS instead of SMTP.

    Chosen when the host blocks SMTP ports. Brevo only requires the *sender*
    address to be verified, not a whole domain, so it works on a free account
    with a plain Gmail address as the From — which Resend does not.
    """
    import httpx

    if not settings.brevo_api_key:
        logger.error("Brevo is selected but BREVO_API_KEY is unset — dropped")
        return False

    name, addr = _sender()
    response = httpx.post(
        "https://api.brevo.com/v3/smtp/email",
        headers={
            "api-key": settings.brevo_api_key,
            "accept": "application/json",
            "content-type": "application/json",
        },
        json={
            "sender": {"name": name, "email": addr},
            "to": [{"email": to}],
            "subject": subject,
            "htmlContent": html_body,
            "textContent": text_body,
        },
        timeout=settings.smtp_timeout_seconds,
    )
    if response.status_code >= 400:
        # Brevo's body explains the rejection — unverified sender, bad key,
        # daily cap. Without it the failure is unfixable guesswork.
        logger.error("Brevo rejected the message (%s): %s",
                     response.status_code, response.text[:500])
        return False

    logger.info("Sent %r to %s via Brevo", subject, _redact(to))
    return True


# ── Resend HTTP API ──────────────────────────────────────────────────────────


def _send_resend(to: str, subject: str, html_body: str, text_body: str) -> bool:
    import httpx

    if not settings.resend_api_key:
        logger.error("Resend is selected but RESEND_API_KEY is unset — dropped")
        return False

    name, addr = _sender()
    response = httpx.post(
        "https://api.resend.com/emails",
        headers={"Authorization": f"Bearer {settings.resend_api_key}"},
        json={
            "from": formataddr((name, addr)),
            "to": [to],
            "subject": subject,
            "html": html_body,
            "text": text_body,
        },
        timeout=settings.smtp_timeout_seconds,
    )
    if response.status_code >= 400:
        # Resend returns a JSON body explaining the rejection (unverified
        # domain, bad key). Without it the failure is unfixable guesswork.
        logger.error("Resend rejected the message (%s): %s",
                     response.status_code, response.text[:500])
        return False

    logger.info("Sent %r to %s via Resend", subject, _redact(to))
    return True


# ── Message templates ────────────────────────────────────────────────────────


def _shell(title: str, intro: str, button_label: str, link: str,
           footer: str) -> str:
    """Minimal, table-free HTML that survives Gmail, Outlook and Apple Mail.

    Inline styles only — every major client strips <style> blocks.
    """
    return f"""\
<!doctype html>
<html>
  <body style="margin:0;padding:24px;background:#f5f6f8;
               font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',
               Roboto,Helvetica,Arial,sans-serif;color:#1a1a1a;">
    <div style="max-width:520px;margin:0 auto;background:#ffffff;
                border-radius:12px;padding:32px;
                box-shadow:0 1px 3px rgba(0,0,0,0.08);">
      <h1 style="margin:0 0 8px;font-size:22px;font-weight:650;">FIQO<span
          style="color:#5b6cff;">.</span></h1>
      <p style="margin:0 0 24px;font-size:13px;color:#6b7280;">
        Your AI-powered university study workspace</p>

      <h2 style="margin:0 0 12px;font-size:18px;font-weight:600;">{title}</h2>
      <p style="margin:0 0 24px;font-size:15px;line-height:1.6;color:#374151;">
        {intro}</p>

      <a href="{link}"
         style="display:inline-block;background:#5b6cff;color:#ffffff;
                text-decoration:none;padding:12px 24px;border-radius:8px;
                font-size:15px;font-weight:600;">{button_label}</a>

      <p style="margin:24px 0 0;font-size:13px;line-height:1.6;color:#6b7280;">
        Or paste this link into your browser:<br>
        <span style="word-break:break-all;color:#5b6cff;">{link}</span></p>

      <hr style="border:none;border-top:1px solid #e5e7eb;margin:24px 0;">
      <p style="margin:0;font-size:12px;line-height:1.6;color:#9ca3af;">
        {footer}</p>
    </div>
  </body>
</html>"""


def send_verification_email(to: str, name: str, link: str,
                            expires_hours: int) -> bool:
    subject = "Confirm your email address — FIQO AI"
    intro = (
        f"Hi {name}, thanks for signing up. Confirm this address to activate "
        "your account and start uploading course material."
    )
    footer = (
        f"This link expires in {expires_hours} hours and can be used once. "
        "If you did not create a FIQO account, ignore this email — no account "
        "will be activated."
    )
    text = (
        f"Hi {name},\n\n"
        "Confirm your email address to activate your FIQO AI account:\n\n"
        f"{link}\n\n"
        f"The link expires in {expires_hours} hours and can be used once.\n"
        "If you did not sign up, you can ignore this message.\n"
    )
    return send_email(to, subject, _shell(
        "Confirm your email address", intro, "Confirm email", link, footer
    ), text)


def send_password_reset_email(to: str, name: str, link: str,
                              expires_hours: int) -> bool:
    subject = "Reset your password — FIQO AI"
    intro = (
        f"Hi {name}, we received a request to reset the password on your FIQO "
        "account. Choose a new one using the button below."
    )
    # The "you can ignore this" line is not filler. Most people who receive an
    # unexpected reset email assume they have been hacked; saying plainly that
    # the password is unchanged until the link is used prevents a panic.
    footer = (
        f"This link expires in {expires_hours} hour(s) and can be used once. "
        "If you did not request a reset, ignore this email — your password "
        "stays exactly as it is, and nobody can change it without this link. "
        "Resetting also signs your account out everywhere."
    )
    text = (
        f"Hi {name},\n\n"
        "Use this link to choose a new FIQO AI password:\n\n"
        f"{link}\n\n"
        f"It expires in {expires_hours} hour(s) and can be used once.\n"
        "If you did not request this, ignore the message — your password is "
        "unchanged.\n"
    )
    return send_email(to, subject, _shell(
        "Reset your password", intro, "Choose a new password", link, footer
    ), text)
