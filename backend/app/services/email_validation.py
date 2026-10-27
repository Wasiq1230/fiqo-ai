"""
Registration-time email hygiene: can this address actually receive mail?

Pydantic's `EmailStr` only checks *syntax*. "asdf@asdf.com" is syntactically
perfect, so before this module existed every fake address sailed through
signup. Two independent checks close that gap:

1. **Deliverability (MX/A lookup).** A domain that publishes no MX record — and
   no A/AAAA record to fall back on, per RFC 5321 §5.1 — cannot receive mail
   from anyone. Rejecting it costs one DNS query and removes the entire class
   of made-up domains.

2. **Disposable-address blocklist.** Temp-mail domains *do* accept mail, so DNS
   cannot catch them, but an inbox that self-destructs in ten minutes is not a
   contactable account. These are matched by domain, including subdomains,
   because most providers hand out dozens of aliases under one apex.

Both checks fail *open* on infrastructure problems. A DNS timeout is our
problem, not the user's, and blocking real signups because a resolver blinked
is worse than briefly letting a bad address through — the verification email is
the second line of defence and it still has to be clicked.
"""
from __future__ import annotations

import logging
import re
import time
from typing import Final

from app.config import get_settings

logger = logging.getLogger("FiQO.email_validation")
settings = get_settings()

# dnspython is optional at runtime: if it is missing we skip the MX check
# rather than refusing every registration.
try:  # pragma: no cover - import guard
    import dns.exception
    import dns.resolver

    _DNS_AVAILABLE = True
except ImportError:  # pragma: no cover - import guard
    _DNS_AVAILABLE = False
    logger.warning(
        "dnspython is not installed — MX validation is disabled. "
        "Add 'dnspython' to requirements.txt to enable it."
    )


class EmailNotAcceptable(ValueError):
    """The address is syntactically valid but must not be allowed to register."""


# ── Disposable / throwaway providers ────────────────────────────────────────
# Not exhaustive — no static list can be — but it covers the services that
# actually show up in abuse logs. Anything missed still has to click a
# verification link, and ad-hoc additions go in EXTRA_BLOCKED_EMAIL_DOMAINS
# without a code change.
_DISPOSABLE_DOMAINS: Final[frozenset[str]] = frozenset({
    "0-mail.com", "0clickemail.com", "10minutemail.com", "10minutemail.net",
    "20minutemail.com", "33mail.com", "getairmail.com", "airmail.cc",
    "anonbox.net", "anonymbox.com", "armyspy.com", "binkmail.com",
    "bobmail.info", "bugmenot.com", "burnermail.io", "byom.de",
    "cuvox.de", "dayrep.com", "deadaddress.com", "despam.it",
    "discard.email", "discardmail.com", "disposable.com",
    "disposableinbox.com", "dispostable.com", "dodgeit.com", "dropmail.me",
    "e4ward.com", "einrot.com", "email-fake.com", "emailfake.com",
    "emailondeck.com", "emailsensei.com", "emailtemporanea.net",
    "emailtemporario.com.br", "emltmp.com", "explodemail.com",
    "fakeinbox.com", "fakemail.net", "fakemailgenerator.com",
    "fastmail.fm.de", "filzmail.com", "fleckens.hu", "forgetmail.com",
    "gehensiemirnichtaufdensack.de", "get2mail.fr", "getnada.com",
    "gishpuppy.com", "grr.la", "guerrillamail.biz", "guerrillamail.com",
    "guerrillamail.de", "guerrillamail.info", "guerrillamail.net",
    "guerrillamail.org", "guerrillamailblock.com", "harakirimail.com",
    "hidemail.de", "hmamail.com", "inboxalias.com", "inboxbear.com",
    "incognitomail.org", "jetable.org", "jourrapide.com", "kasmail.com",
    "killmail.com", "klzlk.com", "kurzepost.de", "lroid.com",
    "mail-temporaire.fr", "mail.tm", "mail7.io", "mailbox52.ga",
    "mailcatch.com", "maildrop.cc", "maileater.com", "mailexpire.com",
    "mailforspam.com", "mailfreeonline.com", "mailinater.com",
    "mailinator.com", "mailinator.net", "mailinator.org", "mailismagic.com",
    "mailmetrash.com", "mailnesia.com", "mailnull.com", "mailsac.com",
    "mailtemp.info", "mailtothis.com", "mintemail.com", "moakt.com",
    "mohmal.com", "monumentmail.com", "mt2015.com", "mytemp.email",
    "mytempemail.com", "nada.email", "nowmymail.com", "nwytg.net",
    "objectmail.com", "onetimemail.org", "opayq.com", "pokemail.net",
    "put2.net", "quickinbox.com", "rcpt.at", "rhyta.com", "rppkn.com",
    "safetymail.info", "sharklasers.com", "shieldemail.com", "shitmail.me",
    "sogetthis.com", "spam4.me", "spamavert.com", "spambog.com",
    "spambox.us", "spamdecoy.net", "spamfree24.org", "spamgourmet.com",
    "spamherelots.com", "spaml.com", "spamspot.com", "superrito.com",
    "teleworm.us", "temp-mail.io", "temp-mail.org", "tempail.com",
    "tempemail.com", "tempemail.net", "tempinbox.com", "tempmail.net",
    "tempmail.plus", "tempmailaddress.com", "tempmaildemo.com",
    "tempmailer.com", "tempomail.fr", "temporaryemail.net",
    "temporaryforwarding.com", "temporaryinbox.com", "tempr.email",
    "thankyou2010.com", "throwam.com", "throwawaymail.com", "tmail.ws",
    "tmailinator.com", "trash-mail.at", "trash-mail.com", "trashmail.com",
    "trashmail.de", "trashmail.me", "trashmail.net", "trashmail.org",
    "trbvm.com", "tyldd.com", "vomoto.com", "wegwerfmail.de",
    "wegwerfmail.net", "wegwerfmail.org", "wh4f.org", "whatiaas.com",
    "willselfdestruct.com", "wuzup.net", "xoxy.net", "yopmail.com",
    "yopmail.fr", "yopmail.net", "yourdomain.com", "yuurok.com",
    "zetmail.com", "zippymail.info",
})

# Domains that exist purely as examples in RFCs and documentation. They are
# reserved by IANA and will never accept mail, but some publish records that
# can confuse a naive MX check.
_RESERVED_DOMAINS: Final[frozenset[str]] = frozenset({
    "example.com", "example.net", "example.org", "example.edu",
    "test.com", "invalid", "localhost", "local", "test", "example",
})

# A conservative hostname shape. Guards the DNS call against anything odd that
# slipped past the email parser.
_DOMAIN_RE: Final[re.Pattern[str]] = re.compile(
    r"^(?=.{1,253}$)(?!-)[a-z0-9-]{1,63}(?<!-)(\.(?!-)[a-z0-9-]{1,63}(?<!-))+$"
)

# ── MX result cache ─────────────────────────────────────────────────────────
# Signups cluster on a handful of providers (gmail.com, outlook.com, a
# university domain). Re-resolving those on every request adds latency to the
# registration path for no new information.
_MX_CACHE: dict[str, tuple[bool, float]] = {}
_MX_CACHE_TTL_SECONDS: Final[int] = 6 * 60 * 60
_MX_CACHE_MAX_ENTRIES: Final[int] = 2048


def split_domain(email: str) -> str:
    """Lowercased domain part of an address. Assumes syntax is already valid."""
    return email.rsplit("@", 1)[-1].strip().lower().rstrip(".")


def _matches(domain: str, blocklist: frozenset[str] | set[str]) -> bool:
    """True if `domain` is in the list, or is a subdomain of something in it."""
    if domain in blocklist:
        return True
    return any(domain.endswith("." + blocked) for blocked in blocklist)


def _cache_get(domain: str) -> bool | None:
    entry = _MX_CACHE.get(domain)
    if entry is None:
        return None
    deliverable, stored_at = entry
    if time.monotonic() - stored_at > _MX_CACHE_TTL_SECONDS:
        _MX_CACHE.pop(domain, None)
        return None
    return deliverable


def _cache_put(domain: str, deliverable: bool) -> None:
    # Bounded so a flood of junk domains cannot grow this without limit.
    if len(_MX_CACHE) >= _MX_CACHE_MAX_ENTRIES:
        _MX_CACHE.clear()
    _MX_CACHE[domain] = (deliverable, time.monotonic())


def domain_can_receive_mail(domain: str) -> bool:
    """Does this domain publish records that allow mail delivery?

    Returns True when the answer is yes *or unknown*. Only a definitive
    "this domain does not exist / has no mail records" answer returns False.
    """
    if not _DNS_AVAILABLE or not settings.check_email_mx:
        return True

    cached = _cache_get(domain)
    if cached is not None:
        return cached

    resolver = dns.resolver.Resolver()
    resolver.timeout = settings.email_mx_timeout_seconds
    resolver.lifetime = settings.email_mx_timeout_seconds

    try:
        answers = resolver.resolve(domain, "MX")
        # A domain can publish a "null MX" (RFC 7505): a single record with an
        # empty target, meaning "this domain accepts no mail, ever".
        deliverable = any(str(r.exchange).rstrip(".") for r in answers)
    except dns.resolver.NoAnswer:
        # No MX, but RFC 5321 says fall back to the A/AAAA record.
        deliverable = _has_address_record(resolver, domain)
    except dns.resolver.NXDOMAIN:
        deliverable = False  # the domain itself does not exist
    except (dns.exception.Timeout, dns.resolver.NoNameservers):
        logger.warning("MX lookup for %s failed (network) — allowing", domain)
        return True  # fail open, do not cache a non-answer
    except Exception:  # pragma: no cover - defensive
        logger.exception("Unexpected MX lookup failure for %s — allowing", domain)
        return True

    _cache_put(domain, deliverable)
    return deliverable


def _has_address_record(resolver, domain: str) -> bool:
    for record_type in ("A", "AAAA"):
        try:
            if resolver.resolve(domain, record_type):
                return True
        except Exception:
            continue
    return False


def validate_registration_email(email: str) -> str:
    """Full signup check. Returns the normalised address or raises.

    The messages are deliberately specific: "enter a valid email" tells a user
    who typed `me@gmial.com` nothing, and they will retype the same thing.
    """
    email = email.strip().lower()
    domain = split_domain(email)

    if not domain or not _DOMAIN_RE.match(domain):
        raise EmailNotAcceptable("That email address does not look valid.")

    # Grouped with the MX check because it answers the same question — can mail
    # reach this domain? — just from a static list instead of DNS. Sharing the
    # flag also means tests can disable both deliverability checks at once and
    # keep using example.com addresses.
    if settings.check_email_mx and _matches(domain, _RESERVED_DOMAINS):
        raise EmailNotAcceptable(
            "That domain is reserved for documentation and cannot receive mail. "
            "Please use your real email address."
        )

    allowed = settings.allowed_email_domain_set
    if allowed and not _matches(domain, allowed):
        raise EmailNotAcceptable(
            "Registration is limited to approved email domains: "
            + ", ".join(sorted(allowed))
            + "."
        )

    if settings.block_disposable_email:
        if _matches(domain, _DISPOSABLE_DOMAINS) or \
                _matches(domain, settings.extra_blocked_domain_set):
            raise EmailNotAcceptable(
                "Temporary or disposable email addresses are not accepted. "
                "Please sign up with a permanent address."
            )

    if not domain_can_receive_mail(domain):
        raise EmailNotAcceptable(
            f"No mail server exists for '{domain}', so that address cannot "
            "receive email. Please check the spelling."
        )

    return email
