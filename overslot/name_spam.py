"""
Helpers for detecting (and querying) spammy first/last names.

Real human names do not contain domains. Bots currently paste promo copy plus a
bare hostname into the name fields (e.g. "Claim Your Bonus jolpo.kesug.com 7f GJ").
"""
from __future__ import annotations

import re

from django.conf import settings
from django.contrib.auth.models import User
from django.core.exceptions import ObjectDoesNotExist
from django.db.models import Q

# gTLDs and spam-heavy ccTLDs. Word-boundary matching avoids false positives
# like "Dr.Combs" (".com" is not a TLD token there).
DEFAULT_NAME_BLOCKED_TLDS = (
    "com",
    "net",
    "org",
    "info",
    "biz",
    "io",
    "co",
    "me",
    "cc",
    "tv",
    "xyz",
    "online",
    "site",
    "app",
    "dev",
    "shop",
    "store",
    "club",
    "live",
    "news",
    "blog",
    "link",
    "click",
    "top",
    "icu",
    "buzz",
    "fun",
    "pro",
    "vip",
    "win",
    "loan",
    "work",
    "space",
    "website",
    "host",
    "tech",
    "digital",
    "cloud",
    "email",
    "today",
    "world",
    "life",
    "guru",
    "ninja",
    "cool",
    "zone",
    "page",
    "pw",
    "edu",
    "gov",
    "ru",
    "su",
    "cn",
    "tk",
    "ml",
    "ga",
    "cf",
    "gq",
)

DEFAULT_SUSPICIOUS_NAME_SUBSTRINGS = [
    "blogspot",
    "wordpress",
    "tumblr",
    "substack",
    "medium",
    "weebly",
    "wixsite",
    "squarespace",
    "blogger",
    "sites.google",
    "linktr.ee",
    "gumroad",
    "onlyfans",
]

MAX_NAME_LENGTH = 60


def name_blocked_tlds() -> tuple[str, ...]:
    configured = getattr(settings, "NAME_BLOCKED_TLDS", None)
    extra = tuple(
        str(t).lower().lstrip(".")
        for t in getattr(settings, "BLOCKED_EMAIL_TLDS", [])
        if t
    )
    if configured:
        base = tuple(str(t).lower().lstrip(".") for t in configured if t)
    else:
        base = DEFAULT_NAME_BLOCKED_TLDS
    return tuple(dict.fromkeys((*base, *extra)))


def _domain_in_name_re() -> re.Pattern[str]:
    alternation = "|".join(re.escape(t) for t in name_blocked_tlds())
    return re.compile(rf"(?i)(?:https?://|www\.)|\.(?:{alternation})\b|@")


def name_contains_domain(first_name: str | None, last_name: str | None) -> bool:
    """
    True if either name field contains a domain-like token (.com, www., @, ...).
    """
    combined = f"{first_name or ''} {last_name or ''}".strip()
    if not combined:
        return False
    if _domain_in_name_re().search(combined):
        return True
    blocked_domains = getattr(settings, "BLOCKED_EMAIL_DOMAINS", [])
    lowered = combined.lower()
    for domain in blocked_domains:
        if domain and domain.lower() in lowered:
            return True
    return False


def name_contains_url(value: str | None) -> bool:
    if not value:
        return False
    return bool(re.search(r"https?:", value, flags=re.IGNORECASE))


def name_is_excessively_long(name: str | None, max_len: int = MAX_NAME_LENGTH) -> bool:
    if not name:
        return False
    return len(name.strip()) > max_len


def name_contains_disallowed_substring(first_name: str | None, last_name: str | None) -> bool:
    terms = getattr(
        settings,
        "SUSPICIOUS_NAME_SUBSTRINGS",
        DEFAULT_SUSPICIOUS_NAME_SUBSTRINGS,
    )
    fn = (first_name or "").lower()
    ln = (last_name or "").lower()
    for term in terms:
        t = (term or "").lower()
        if t and (t in fn or t in ln):
            return True
    return False


def name_looks_like_spam(first_name: str | None, last_name: str | None) -> bool:
    """Combined signup-time heuristic used to reject bot registrations."""
    if name_contains_url(first_name) or name_contains_url(last_name):
        return True
    if name_is_excessively_long(first_name) or name_is_excessively_long(last_name):
        return True
    if name_contains_disallowed_substring(first_name, last_name):
        return True
    if name_contains_domain(first_name, last_name):
        return True
    return False


def users_with_domain_in_name():
    """
    Candidate queryset: names that contain a '.' + known TLD substring.
    Callers should still run name_contains_domain() on each row so word
    boundaries are applied (icontains is a coarse prefilter).
    """
    q = Q()
    for tld in name_blocked_tlds():
        token = f".{tld}"
        q |= Q(first_name__icontains=token) | Q(last_name__icontains=token)
    q |= Q(first_name__icontains="www.") | Q(last_name__icontains="www.")
    q |= Q(first_name__icontains="@") | Q(last_name__icontains="@")
    q |= Q(first_name__icontains="http:") | Q(last_name__icontains="http:")
    q |= Q(first_name__icontains="https:") | Q(last_name__icontains="https:")
    return User.objects.filter(q).distinct().select_related("author_profile", "subscription")


def user_is_protected(user: User) -> str | None:
    """
    Return a skip reason if this account should not be auto-deleted, else None.
    """
    if user.is_superuser:
        return "superuser"
    if user.is_staff:
        return "staff"
    try:
        if user.author_profile is not None:
            return "author"
    except ObjectDoesNotExist:
        pass
    try:
        subscription = user.subscription
    except ObjectDoesNotExist:
        subscription = None
    if subscription is not None and subscription.can_access_premium_content():
        return "active_subscription"
    return None
