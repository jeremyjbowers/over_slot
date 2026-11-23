# Per-request user and read API key for in-process MCP tool calls.
from __future__ import annotations

from contextvars import ContextVar

from django.contrib.auth.models import User

from overslot.models import ReadAPIKey

_current_user: ContextVar[User | None] = ContextVar("overslot_mcp_user", default=None)
_current_key: ContextVar[ReadAPIKey | None] = ContextVar(
    "overslot_mcp_key", default=None
)


def set_current_user(user: User | None):
    return _current_user.set(user)


def reset_current_user(token):
    _current_user.reset(token)


def get_current_user() -> User | None:
    return _current_user.get()


def set_current_key(key: ReadAPIKey | None):
    return _current_key.set(key)


def reset_current_key(token):
    _current_key.reset(token)


def get_current_key() -> ReadAPIKey | None:
    return _current_key.get()
