# Stdio MCP entry for clients that cannot use remote HTTPS MCP.
# Proxies to the site's token-auth JSON API via OVERSLOT_API_URL + token.
"""Over Slot MCP server — stdio transport.

Preferred path: connect over HTTPS to https://YOUR-HOST/mcp
with Authorization: Bearer overslot_…

This process is for clients that only speak local MCP. It calls the same
read API. There are no write tools.
"""
from __future__ import annotations

import os
import sys
from typing import Optional


def main(argv: Optional[list] = None) -> None:
    import django

    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.dev.settings")
    django.setup()
    from overslot.mcp_app.tools import build_mcp

    build_mcp(mode="remote").run(transport="stdio")


if __name__ == "__main__":
    main(sys.argv[1:])
