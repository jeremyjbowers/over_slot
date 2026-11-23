# Production ASGI entry — Django site plus MCP at /mcp.
# Point the app platform at uvicorn config.do_app_platform.asgi:application
# so https://YOUR-HOST/mcp reaches the MCP server. WSGI serves the JSON API only.
import os

settings_file = "config.do_app_platform.settings"
os.environ.setdefault("DJANGO_SETTINGS_MODULE", settings_file)

from django.core.asgi import get_asgi_application

django_app = get_asgi_application()

from overslot.mcp_app.http_app import create_site_asgi_application

application = create_site_asgi_application(django_app)
