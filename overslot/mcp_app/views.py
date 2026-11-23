# JSON views for the read API. Same data and paywall as the MCP tools.
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET

from overslot.mcp_app.auth import require_read_api_key
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


def _respond(func, user, **kwargs):
    try:
        return JsonResponse(func(user, **kwargs))
    except ReadError as exc:
        return JsonResponse(
            {"error": exc.title, "detail": exc.message},
            status=exc.status,
        )


def _query(request, *names):
    params = request.GET
    values = {}
    for name in names:
        if name == "query":
            values[name] = params.get("query") or params.get("q")
        else:
            values[name] = params.get(name)
    return values


@csrf_exempt
@require_GET
@require_read_api_key
def articles_list(request):
    return _respond(
        list_articles,
        request.mcp_user,
        **_query(request, "query", "article_type", "limit", "offset"),
    )


@csrf_exempt
@require_GET
@require_read_api_key
def articles_detail(request, slug):
    return _respond(get_article, request.mcp_user, slug=slug)


@csrf_exempt
@require_GET
@require_read_api_key
def rankings_list(request):
    return _respond(
        list_rankings,
        request.mcp_user,
        **_query(request, "query", "year", "draft_level", "current", "limit", "offset"),
    )


@csrf_exempt
@require_GET
@require_read_api_key
def rankings_detail(request, slug):
    return _respond(get_ranking, request.mcp_user, slug=slug)


@csrf_exempt
@require_GET
@require_read_api_key
def mock_drafts_list(request):
    return _respond(
        list_mock_drafts,
        request.mcp_user,
        **_query(request, "query", "year", "draft_level", "current", "limit", "offset"),
    )


@csrf_exempt
@require_GET
@require_read_api_key
def mock_drafts_detail(request, slug):
    return _respond(get_mock_draft, request.mcp_user, slug=slug)


@csrf_exempt
@require_GET
@require_read_api_key
def players_search(request):
    return _respond(
        search_players,
        request.mcp_user,
        **_query(request, "query", "position", "school", "limit", "offset"),
    )


@csrf_exempt
@require_GET
@require_read_api_key
def players_detail(request, slug):
    return _respond(get_player, request.mcp_user, slug=slug)


@csrf_exempt
@require_GET
@require_read_api_key
def player_stat_seasons(request):
    return _respond(
        list_player_stat_seasons,
        request.mcp_user,
        **_query(request, "player", "year", "level", "kind", "limit", "offset"),
    )
