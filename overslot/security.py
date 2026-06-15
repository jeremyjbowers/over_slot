import time
import hashlib
import hmac
from typing import Tuple

from django.conf import settings
from django.core.cache import cache


DEFAULT_MIN_FILL_SECONDS = 1.0
DEFAULT_RATE_LIMIT = 8
DEFAULT_RATE_WINDOW_SECONDS = 300  # 5 minutes


def _client_key(request, slug: str) -> str:
    ip = request.META.get("HTTP_X_FORWARDED_FOR", "").split(",")[0].strip() or request.META.get("REMOTE_ADDR", "")
    ua = request.META.get("HTTP_USER_AGENT", "")
    return f"overslot:{slug}:{ip}:{hashlib.sha256(ua.encode()).hexdigest()}"


def rate_limit_allow(request, slug: str, limit: int = DEFAULT_RATE_LIMIT, window_seconds: int = DEFAULT_RATE_WINDOW_SECONDS) -> Tuple[bool, int]:
    key = _client_key(request, f"rl:{slug}")
    bucket = cache.get(key)
    now = int(time.time())
    if not isinstance(bucket, dict):
        bucket = {"start": now, "count": 0}
    # reset window if expired
    if now - bucket["start"] >= window_seconds:
        bucket = {"start": now, "count": 0}
    if bucket["count"] >= limit:
        remaining = window_seconds - (now - bucket["start"]) or 1
        return False, int(remaining)
    bucket["count"] += 1
    # store bucket; timeout ensures eventual cleanup; reset remaining seconds
    remaining_timeout = max(1, window_seconds - (now - bucket["start"]))
    cache.set(key, bucket, timeout=remaining_timeout)
    return True, 0


def get_form_tokens(secret: str, form_slug: str) -> Tuple[str, str]:
    # per-render timestamp
    ts = str(int(time.time()))
    msg = f"{form_slug}:{ts}".encode()
    sig = hmac.new(secret.encode(), msg, hashlib.sha256).hexdigest()
    return ts, sig


def validate_form_tokens(secret: str, form_slug: str, ts: str, sig: str, max_age_seconds: int = 3600) -> bool:
    try:
        ts_int = int(ts)
    except Exception:
        return False
    if (time.time() - ts_int) > max_age_seconds:
        return False
    expected = hmac.new(secret.encode(), f"{form_slug}:{ts}".encode(), hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, sig)


def validate_honeypot(request, field_name: str = "website") -> bool:
    return not (request.POST.get(field_name) or request.GET.get(field_name))


def validate_min_fill_time(request, ts_field: str = "_ts", min_seconds: float = DEFAULT_MIN_FILL_SECONDS) -> bool:
    raw = request.POST.get(ts_field)
    if raw is None:
        # Graceful: allow when timestamp is missing (e.g., non-JS clients/tests)
        return True
    try:
        ts_val = float(raw)
    except Exception:
        return True
    now = time.time()
    return (now - ts_val) >= min_seconds


