# ASGI app exposing Over Slot MCP over Streamable HTTP.
# Authenticates with ReadAPIKey Bearer headers (no OAuth discovery).
from __future__ import annotations

from contextlib import asynccontextmanager

from mcp.server.transport_security import TransportSecuritySettings
from starlette.applications import Starlette
from starlette.middleware import Middleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.routing import Mount, Route
from starlette.types import ASGIApp, Receive, Scope, Send

from overslot.mcp_app.context import (
    reset_current_key,
    reset_current_user,
    set_current_key,
    set_current_user,
)
from overslot.mcp_app.db import db_sync
from overslot.mcp_app.tools import build_mcp
from overslot.models import ReadAPIKey


class ReadKeyBearerMiddleware:
    """
    Require Authorization: Bearer overslot_… for MCP HTTP traffic.

    Does not advertise OAuth resource metadata. A missing or unknown key is a
    plain 401 so clients do not start an OAuth discovery loop.
    """

    def __init__(self, app: ASGIApp):
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        headers = {
            k.decode("latin-1").lower(): v.decode("latin-1")
            for k, v in scope.get("headers", [])
        }
        auth = headers.get("authorization", "")
        raw = None
        if auth.lower().startswith("bearer "):
            raw = auth[7:].strip()
        if not raw:
            raw = headers.get("x-overslot-token", "").strip() or None

        key, reason = await db_sync(ReadAPIKey.authorize, raw)
        if key is None:
            if reason == "unpaid":
                status = 403
                body = (
                    b'{"error":"Subscription required","detail":'
                    b'"An active subscription is required to use the read API."}'
                )
                www_auth = b'Bearer realm="overslot", error="insufficient_scope"'
            else:
                status = 401
                body = b'{"error":"Unauthorized","detail":"Valid Over Slot API key required"}'
                www_auth = b'Bearer realm="overslot"'
            await send(
                {
                    "type": "http.response.start",
                    "status": status,
                    "headers": [
                        (b"content-type", b"application/json"),
                        (b"www-authenticate", www_auth),
                        (b"content-length", str(len(body)).encode()),
                    ],
                }
            )
            await send({"type": "http.response.body", "body": body})
            return

        user_token = set_current_user(key.user)
        key_token = set_current_key(key)
        try:
            await self.app(scope, receive, send)
        finally:
            reset_current_key(key_token)
            reset_current_user(user_token)


class SlashlessMcpMiddleware:
    """
    Serve Streamable HTTP at /mcp as well as /mcp/.

    Starlette Mount matches /mcp/ and /mcp/<rest>, not the exact path /mcp.
    Clients post to the URL as typed. Rewriting here keeps the request body;
    a redirect would drop the handshake.
    """

    def __init__(self, app: ASGIApp):
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] == "http" and scope.get("path") == "/mcp":
            scope["path"] = "/mcp/"
            if scope.get("raw_path") == b"/mcp":
                scope["raw_path"] = b"/mcp/"
        await self.app(scope, receive, send)


async def mcp_health(request: Request) -> Response:
    return JSONResponse(
        {
            "service": "overslot-mcp",
            "auth": "bearer",
            "transport": "streamable-http",
            "reads": [
                "articles",
                "rankings",
                "player_rankings",
                "player_stat_seasons",
                "mock_drafts",
            ],
            "writes": [],
        }
    )


def create_mcp_http_app() -> Starlette:
    """
    Streamable HTTP MCP at `/` (mount this under `/mcp` on the site ASGI app).

    Clients connect to https://YOUR-HOST/mcp with:
      Authorization: Bearer overslot_…
    """
    mcp = build_mcp(mode="local")
    mcp.settings.transport_security = TransportSecuritySettings(
        enable_dns_rebinding_protection=False,
    )
    mcp.settings.streamable_http_path = "/"
    mcp.settings.stateless_http = True
    mcp.settings.json_response = True

    inner = mcp.streamable_http_app()

    @asynccontextmanager
    async def lifespan(app: Starlette):
        async with inner.router.lifespan_context(inner):
            yield

    return Starlette(
        routes=[
            Route("/health", endpoint=mcp_health, methods=["GET"]),
            Mount("/", app=inner),
        ],
        middleware=[Middleware(ReadKeyBearerMiddleware)],
        lifespan=lifespan,
    )


def create_site_asgi_application(django_asgi_app: ASGIApp) -> Starlette:
    """Compose Django + MCP under one host. /mcp needs this ASGI app, not WSGI."""
    mcp_app = create_mcp_http_app()

    @asynccontextmanager
    async def lifespan(app: Starlette):
        async with mcp_app.router.lifespan_context(mcp_app):
            yield

    return Starlette(
        routes=[
            Mount("/mcp", app=mcp_app),
            Mount("/", app=django_asgi_app),
        ],
        middleware=[Middleware(SlashlessMcpMiddleware)],
        lifespan=lifespan,
    )
