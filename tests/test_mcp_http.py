# ASGI checks for the HTTPS MCP server at /mcp.
from django.contrib.auth.models import User
from django.test import TestCase, override_settings
from httpx import ASGITransport, AsyncClient

from overslot.mcp_app.http_app import create_mcp_http_app, create_site_asgi_application
from overslot.models import ReadAPIKey, Subscription

_INITIALIZE = {
    "jsonrpc": "2.0",
    "id": 1,
    "method": "initialize",
    "params": {
        "protocolVersion": "2025-03-26",
        "capabilities": {},
        "clientInfo": {"name": "cursor", "version": "1"},
    },
}
_MCP_HEADERS = {
    "Accept": "application/json, text/event-stream",
    "Content-Type": "application/json",
}


async def _site_login_redirect(scope, receive, send):
    await send(
        {
            "type": "http.response.start",
            "status": 302,
            "headers": [(b"location", b"/accounts/login/")],
        }
    )
    await send({"type": "http.response.body", "body": b""})


@override_settings(ALLOWED_HOSTS=["*"])
class MCPHttpAuthTestCase(TestCase):
    def setUp(self):
        user = User.objects.create_user(
            username="http", email="http@example.com", password="x"
        )
        Subscription.objects.create(user=user, status="active")
        self.raw, _key = ReadAPIKey.create_key(user, label="http")
        self.app = create_mcp_http_app()

    async def test_health_requires_a_key(self):
        transport = ASGITransport(app=self.app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get("/health")
            self.assertEqual(response.status_code, 401)

    async def test_health_with_bearer(self):
        transport = ASGITransport(app=self.app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get(
                "/health",
                headers={"Authorization": f"Bearer {self.raw}"},
            )
            self.assertEqual(response.status_code, 200)
            payload = response.json()
            self.assertEqual(payload["service"], "overslot-mcp")
            self.assertEqual(payload["auth"], "bearer")
            self.assertEqual(payload["writes"], [])
            self.assertIn("articles", payload["reads"])
            self.assertIn("mock_drafts", payload["reads"])


@override_settings(ALLOWED_HOSTS=["*"])
class MCPSitePathTestCase(TestCase):
    def setUp(self):
        user = User.objects.create_user(
            username="site", email="site@example.com", password="x"
        )
        Subscription.objects.create(user=user, status="active")
        self.raw, _key = ReadAPIKey.create_key(user, label="site")
        self.app = create_site_asgi_application(_site_login_redirect)

    async def test_slashless_mcp_is_the_mcp_server(self):
        transport = ASGITransport(app=self.app)
        async with self.app.router.lifespan_context(self.app):
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                bare = await client.post("/mcp", headers=_MCP_HEADERS, json=_INITIALIZE)
                self.assertEqual(bare.status_code, 401)
                self.assertEqual(bare.json()["error"], "Unauthorized")
                self.assertNotIn("location", bare.headers)

                other = await client.get("/articles/")
                self.assertEqual(other.status_code, 302)
                self.assertEqual(other.headers["location"], "/accounts/login/")

    async def test_initialize_with_bearer(self):
        transport = ASGITransport(app=self.app)
        headers = {**_MCP_HEADERS, "Authorization": f"Bearer {self.raw}"}
        async with self.app.router.lifespan_context(self.app):
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                response = await client.post("/mcp", headers=headers, json=_INITIALIZE)
                self.assertEqual(response.status_code, 200)
                body = response.json()
                self.assertEqual(body["jsonrpc"], "2.0")
                self.assertEqual(body["result"]["serverInfo"]["name"], "overslot")
