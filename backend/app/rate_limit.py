"""
Shared rate limiter (SlowAPI).

Why this is not just `get_remote_address`:

Once the app runs behind a reverse proxy (nginx, Caddy, Railway, Render, Fly,
Cloudflare), `request.client.host` is the *proxy's* IP. Every visitor then
shares one rate-limit bucket, which means (a) per-IP limits stop working and
(b) one abusive client locks out the entire user base. So when TRUST_PROXY is
on we read the client IP from X-Forwarded-For instead.

The reverse is just as dangerous: if the app is reachable directly and we trust
X-Forwarded-For, anyone can rotate that header per request and bypass rate
limiting completely. Hence TRUST_PROXY defaults to false and must be turned on
deliberately.
"""
from slowapi import Limiter
from slowapi.util import get_remote_address
from starlette.requests import Request

from app.config import get_settings

settings = get_settings()


def client_ip(request: Request) -> str:
    """Best-effort real client IP, honouring X-Forwarded-For only when trusted."""
    if settings.trust_proxy:
        forwarded = request.headers.get("x-forwarded-for", "")
        if forwarded:
            # Left-most entry is the original client; the rest are proxies.
            first = forwarded.split(",")[0].strip()
            if first:
                return first
        real_ip = request.headers.get("x-real-ip", "").strip()
        if real_ip:
            return real_ip
    return get_remote_address(request) or "unknown"


_storage = settings.rate_limit_storage_uri.strip()

limiter = Limiter(
    key_func=client_ip,
    default_limits=[settings.rate_limit_default],
    # With multiple gunicorn workers, in-memory counters are per-process, so the
    # effective limit is (limit x workers). Point RATE_LIMIT_STORAGE_URI at Redis
    # to enforce one shared limit across every worker and replica.
    storage_uri=_storage or "memory://",
    headers_enabled=False,
)
