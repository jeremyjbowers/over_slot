# ORM calls from the MCP ASGI app, outside Django's request cycle.
# Drops a Postgres connection the server already closed, then retries once.
from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Any

from asgiref.sync import sync_to_async
from django.db import connections
from django.db.utils import Error, InterfaceError, OperationalError

logger = logging.getLogger(__name__)

_CLOSED_CONNECTION_ERRORS = (InterfaceError, OperationalError)


def _drop_connection(conn) -> None:
    try:
        conn.close()
    except Error:
        conn.connection = None


def _release_stale_connections() -> None:
    """
    Forget worker-thread connections Postgres has already closed.

    /mcp is a Starlette app mounted beside Django, so request_started never
    fires and close_old_connections() does not run. sync_to_async keeps one
    thread, and that thread keeps the connection it opened.
    """
    for conn in connections.all(initialized_only=True):
        if conn.in_atomic_block:
            continue
        raw = conn.connection
        if raw is not None and getattr(raw, "closed", 0):
            logger.warning("Dropping a Postgres connection the server already closed")
            _drop_connection(conn)
            continue
        conn.close_if_unusable_or_obsolete()


def _run_with_db(func: Callable[..., Any], args: tuple, kwargs: dict) -> Any:
    _release_stale_connections()
    try:
        return func(*args, **kwargs)
    except _CLOSED_CONNECTION_ERRORS:
        logger.warning("MCP database call lost its Postgres connection; reconnecting")
        for conn in connections.all(initialized_only=True):
            if not conn.in_atomic_block:
                _drop_connection(conn)
        return func(*args, **kwargs)


async def db_sync(func: Callable[..., Any], /, *args: Any, **kwargs: Any) -> Any:
    """Run func against the ORM on the sync_to_async thread."""
    return await sync_to_async(_run_with_db)(func, args, kwargs)
