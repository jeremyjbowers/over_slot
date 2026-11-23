# FastMCP tool registration shared by HTTP and stdio transports.
# Local mode uses Django. Remote mode calls the JSON API.
from __future__ import annotations

import json
import os
from typing import Any, Optional
from urllib.parse import quote

import httpx
from mcp.server.fastmcp import FastMCP

from overslot.mcp_app.context import get_current_user
from overslot.mcp_app.db import db_sync
from overslot.mcp_app.reads import (
    ReadError,
    get_article,
    get_mock_draft,
    get_player,
    get_ranking,
    list_articles,
    list_mock_drafts,
    list_player_stat_seasons,
    list_rankings,
    search_players,
)

INSTRUCTIONS = (
    "Over Slot read tools for published articles, draft rankings, mock drafts, "
    "player scouting reports, and player stat seasons. "
    "Only an account with an active subscription can use these tools. "
    "A key returns the full published record: article bodies, ranking boards, "
    "scouting reports, Trackman and counting stat seasons, and mock drafts. "
    "There are no write tools."
)


def _dump(data: Any) -> str:
    return json.dumps(data, indent=2, default=str)


def _params(**values) -> dict:
    cleaned = {}
    for key, value in values.items():
        if value is None or value == "":
            continue
        cleaned[key] = value
    return cleaned


def _http_get(path: str, params: Optional[dict] = None) -> Any:
    base = (os.environ.get("OVERSLOT_API_URL") or "").rstrip("/")
    token = os.environ.get("OVERSLOT_API_TOKEN") or ""
    if not base or not token:
        raise RuntimeError(
            "Stdio mode requires OVERSLOT_API_URL and OVERSLOT_API_TOKEN"
        )
    headers = {"Authorization": f"Bearer {token}"}
    with httpx.Client(timeout=60.0) as client:
        resp = client.get(f"{base}{path}", params=params or {}, headers=headers)
    if resp.status_code == 401:
        raise RuntimeError("Over Slot API key rejected (401)")
    payload = resp.json()
    if resp.status_code >= 400 and isinstance(payload, dict):
        payload = {**payload, "status": resp.status_code}
    return payload


def _error_payload(exc: ReadError) -> dict:
    return {"error": exc.title, "detail": exc.message, "status": exc.status}


async def _run_local(func, params: dict) -> str:
    user = get_current_user()
    if user is None:
        return _dump(
            {
                "error": "Unauthorized",
                "detail": "Valid Over Slot API key required",
                "status": 401,
            }
        )
    try:
        data = await db_sync(func, user, **params)
    except ReadError as exc:
        return _dump(_error_payload(exc))
    return _dump(data)


def build_mcp(*, mode: str = "local") -> FastMCP:
    """
    mode=local  — in-process Django ORM (HTTPS /mcp on the website)
    mode=remote — HTTP client to OVERSLOT_API_URL (stdio bridge)
    """
    mcp = FastMCP("overslot", instructions=INSTRUCTIONS)
    remote = mode == "remote"

    async def _call(func, path: str, params: dict) -> str:
        if remote:
            return _dump(_http_get(path, params))
        return await _run_local(func, params)

    @mcp.tool()
    async def list_articles(
        query: Optional[str] = None,
        article_type: Optional[str] = None,
        limit: Optional[int] = None,
        offset: Optional[int] = None,
    ) -> str:
        """List published articles. Returns headlines, type, authors, and tagged players, not the body. article_type is scouting, analysis, opinion, or breaking news."""
        params = _params(
            query=query, article_type=article_type, limit=limit, offset=offset
        )
        return await _call(list_articles, "/api/mcp/v1/articles/", params)

    @mcp.tool()
    async def get_article(slug: str) -> str:
        """One published article, including the full body. Requires an active subscription."""
        path = f"/api/mcp/v1/articles/{quote(slug, safe='')}/"
        return await _call(get_article, path, {"slug": slug})

    @mcp.tool()
    async def list_rankings(
        query: Optional[str] = None,
        year: Optional[str] = None,
        draft_level: Optional[str] = None,
        current: Optional[bool] = None,
        limit: Optional[int] = None,
        offset: Optional[int] = None,
    ) -> str:
        """Published draft rankings, not mock drafts. draft_level is Overall, College, or High School. current limits the list to boards marked current."""
        params = _params(
            query=query,
            year=year,
            draft_level=draft_level,
            current=current,
            limit=limit,
            offset=offset,
        )
        return await _call(list_rankings, "/api/mcp/v1/rankings/", params)

    @mcp.tool()
    async def get_ranking(slug: str) -> str:
        """One draft ranking and every player row, including carrying tools and the full scouting report. Requires an active subscription."""
        path = f"/api/mcp/v1/rankings/{quote(slug, safe='')}/"
        return await _call(get_ranking, path, {"slug": slug})

    @mcp.tool()
    async def list_mock_drafts(
        query: Optional[str] = None,
        year: Optional[str] = None,
        draft_level: Optional[str] = None,
        current: Optional[bool] = None,
        limit: Optional[int] = None,
        offset: Optional[int] = None,
    ) -> str:
        """Published mock drafts. Same filters as list_rankings. Player rows are on get_mock_draft."""
        params = _params(
            query=query,
            year=year,
            draft_level=draft_level,
            current=current,
            limit=limit,
            offset=offset,
        )
        return await _call(list_mock_drafts, "/api/mcp/v1/mock-drafts/", params)

    @mcp.tool()
    async def get_mock_draft(slug: str) -> str:
        """One mock draft: pick, team, player, carrying tools, and the full scouting report. Requires an active subscription."""
        path = f"/api/mcp/v1/mock-drafts/{quote(slug, safe='')}/"
        return await _call(get_mock_draft, path, {"slug": slug})

    @mcp.tool()
    async def search_players(
        query: str,
        position: Optional[str] = None,
        school: Optional[str] = None,
        limit: Optional[int] = None,
        offset: Optional[int] = None,
    ) -> str:
        """Find active players by name or school. Returns identity fields, not scouting reports or stats. query must be at least 2 characters. position is an exact match, such as SS or RHP."""
        params = _params(
            query=query, position=position, school=school, limit=limit, offset=offset
        )
        return await _call(search_players, "/api/mcp/v1/players/", params)

    @mcp.tool()
    async def get_player(slug: str) -> str:
        """One player: bio, every ranking and scouting report, Trackman stat seasons, and 6-4-3 counting stats. Requires an active subscription."""
        path = f"/api/mcp/v1/players/{quote(slug, safe='')}/"
        return await _call(get_player, path, {"slug": slug})

    @mcp.tool()
    async def list_player_stat_seasons(
        player: Optional[str] = None,
        year: Optional[str] = None,
        level: Optional[str] = None,
        kind: Optional[str] = None,
        limit: Optional[int] = None,
        offset: Optional[int] = None,
    ) -> str:
        """Trackman seasons (kind=trackman) and 6-4-3 counting seasons (kind=counting). kind defaults to both. Requires an active subscription. Pass a player slug or name, or a year. level is College or High School and applies to Trackman rows."""
        params = _params(
            player=player,
            year=year,
            level=level,
            kind=kind,
            limit=limit,
            offset=offset,
        )
        return await _call(
            list_player_stat_seasons, "/api/mcp/v1/player-stat-seasons/", params
        )

    return mcp
