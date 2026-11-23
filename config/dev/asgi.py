# Dev ASGI entry — Django site plus MCP at /mcp.
# Use: uvicorn config.dev.asgi:application
# The JSON read API also works on the WSGI app. Remote MCP clients need this file.
import os

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.dev.settings")

from django.core.asgi import get_asgi_application

django_app = get_asgi_application()

from overslot.mcp_app.http_app import create_site_asgi_application

application = create_site_asgi_application(django_app)
