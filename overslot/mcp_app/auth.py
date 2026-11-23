# Token auth for the Over Slot read API.
from functools import wraps

from django.http import JsonResponse

from overslot.models import ReadAPIKey


def extract_bearer_token(request):
    """Return the raw key from Authorization: Bearer … or X-Overslot-Token."""
    auth = request.META.get("HTTP_AUTHORIZATION", "") or ""
    if auth.lower().startswith("bearer "):
        return auth[7:].strip()
    header = request.META.get("HTTP_X_OVERSLOT_TOKEN", "") or ""
    return header.strip() or None


def authorization_failure(reason):
    """JSON error for a missing key or an account that is not paid."""
    if reason == "unpaid":
        return JsonResponse(
            {
                "error": "Subscription required",
                "detail": "An active subscription is required to use the read API.",
            },
            status=403,
        )
    return JsonResponse(
        {
            "error": "Unauthorized",
            "detail": "Valid Over Slot API key required",
        },
        status=401,
    )


def require_read_api_key(view_func):
    """Require a read API key whose account has an active subscription."""

    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        key, reason = ReadAPIKey.authorize(extract_bearer_token(request))
        if key is None:
            return authorization_failure(reason)
        request.mcp_key = key
        request.mcp_user = key.user
        return view_func(request, *args, **kwargs)

    return wrapper
