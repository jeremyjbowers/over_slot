# Read-only lookups for the MCP server and its JSON twin.
# Published content only. Premium text follows the same rules as the site.
from __future__ import annotations

from django.db.models import Q
from django.urls import reverse
from django.utils.html import strip_tags

from overslot import models

DEFAULT_LIMIT = 25
MAX_LIMIT = 100
MAX_BOARD = 1000

ARTICLE_TYPES = {choice for choice, _label in models.Article.ARTICLE_TYPE_CHOICES}
STAT_LEVELS = {choice for choice, _label in models.PlayerStatSeason.LEVEL_CHOICES}
STAT_KINDS = {"trackman", "counting", "both"}


class ReadError(Exception):
    """A read the caller can correct."""

    status = 400
    title = "Bad request"

    def __init__(self, message):
        super().__init__(message)
        self.message = message


class NotFound(ReadError):
    status = 404
    title = "Not found"


class Forbidden(ReadError):
    status = 403
    title = "Subscription required"


def _require_paid(user):
    """Every read is the full published record, and only a paid account can ask."""
    if not models.ReadAPIKey.account_is_paid(user):
        raise Forbidden("An active subscription is required to use the read API.")


def _int(value, name, default):
    if value in (None, ""):
        return default
    try:
        return int(value)
    except (TypeError, ValueError):
        raise BadArgument(f"{name} must be a whole number") from None


class BadArgument(ReadError):
    """An argument outside its allowed values."""


def _limit(value, default=DEFAULT_LIMIT):
    number = _int(value, "limit", default)
    if number < 1:
        raise BadArgument("limit must be at least 1")
    return min(number, MAX_LIMIT)


def _offset(value):
    number = _int(value, "offset", 0)
    if number < 0:
        raise BadArgument("offset cannot be negative")
    return number


def _bool(value, name):
    if value in (None, ""):
        return None
    if isinstance(value, bool):
        return value
    text = str(value).strip().lower()
    if text in ("1", "true", "yes"):
        return True
    if text in ("0", "false", "no"):
        return False
    raise BadArgument(f"{name} must be true or false")


def _page(qs, limit, offset):
    total = qs.count()
    return total, list(qs[offset : offset + limit])


def _iso(value):
    if value is None:
        return None
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return str(value)


def _file_url(field):
    if not field:
        return None
    try:
        return field.url
    except ValueError:
        return None


def _text_from_html(html):
    return " ".join(strip_tags(html or "").split())


def _html_body(html):
    raw = html or ""
    return {"html": raw, "text": _text_from_html(raw)}


def _author_name(author):
    return author.display_name or author.name or "Author"


def player_brief(player):
    if player is None:
        return None
    data = {
        "uuid": str(player.pk),
        "slug": player.slug,
        "name": player.name,
    }
    if player.slug:
        data["path"] = reverse("players_detail", kwargs={"slug": player.slug})
    for field in (
        "position",
        "school",
        "hometown",
        "state",
        "country",
        "height",
        "weight",
        "bats",
        "throws",
        "mlb_id",
        "fg_id",
        "photo_url",
        "video_url",
    ):
        value = getattr(player, field)
        if value not in (None, ""):
            data[field] = value
    if player.birthdate:
        data["birthdate"] = player.birthdate.isoformat()
    if player.raw_age is not None:
        data["age"] = player.raw_age
    return data


def _ranking_ref(ranking):
    if ranking is None:
        return None
    path_name = "mock_drafts_detail" if ranking.is_mock_draft else "rankings_detail"
    data = {
        "uuid": str(ranking.pk),
        "slug": ranking.slug,
        "title": ranking.get_computed_title(),
        "year": ranking.year,
        "draft_level": ranking.draft_level,
        "is_mock_draft": ranking.is_mock_draft,
        "is_free": ranking.is_free,
    }
    if ranking.slug:
        data["path"] = reverse(path_name, kwargs={"slug": ranking.slug})
    return data


def ranking_brief(ranking):
    data = _ranking_ref(ranking)
    data.update(
        {
            "ranking_type": ranking.ranking_type,
            "ranking_length": ranking.ranking_length,
            "is_final": ranking.is_final,
            "is_draft": ranking.is_draft,
            "current": ranking.current,
            "mock_draft_version": ranking.mock_draft_version,
            "headline": ranking.headline,
            "subhead": ranking.subhead,
            "blurb": ranking.blurb,
            "free_number_to_show": ranking.free_number_to_show,
            "featured_image": _file_url(ranking.featured_image),
            "published": _iso(ranking.created),
            "updated": _iso(ranking.last_modified),
        }
    )
    return {key: value for key, value in data.items() if value not in (None, "")}


def _carrying_tools(player_ranking, limit=None):
    tools = []
    for tool in player_ranking.carrying_tools.all():
        tools.append(
            {
                "tool": tool.tool,
                "score": tool.score,
                "description": tool.description or None,
            }
        )
    if limit is not None:
        return tools[:limit]
    return tools


def player_ranking_row(player_ranking, *, include_report=True, tool_limit=None):
    player = player_ranking.player
    ranking = player_ranking.ranking
    row = {
        "id": player_ranking.pk,
        "rank": player_ranking.rank,
        "position": player_ranking.position,
        "school": player_ranking.school,
        "level": player_ranking.level,
        "commitment": player_ranking.commitment,
        "country": player_ranking.country,
        "role": player_ranking.role,
        "risk": player_ranking.risk,
        "age_at_draft": player_ranking.age_at_draft,
        "confidence": player_ranking.confidence,
        "mock_team": player_ranking.mock_team,
        "mock_pick_number": player_ranking.mock_pick_number,
        "highlight_reel_url": player_ranking.highlight_reel_url,
        "carrying_tools": _carrying_tools(player_ranking, tool_limit),
        "player": player_brief(player),
        "ranking": _ranking_ref(ranking),
    }
    if player_ranking.school_team_id and player_ranking.school_team:
        row["school_team"] = {
            "name": player_ranking.school_team.name,
            "slug": player_ranking.school_team.slug,
        }
    if include_report:
        report = player_ranking.scouting_report or ""
        row["scouting_report"] = _html_body(report) if report else None
        row["scouting_report_locked"] = False
    else:
        row["scouting_report"] = None
        row["scouting_report_locked"] = bool(player_ranking.scouting_report)
    return {key: value for key, value in row.items() if value not in (None, "") or key in {
        "scouting_report",
        "scouting_report_locked",
        "rank",
        "carrying_tools",
        "player",
        "ranking",
    }}


def _stat_dict(instance):
    skip = {"player", "active", "created", "last_modified"}
    data = {}
    for field in instance._meta.concrete_fields:
        if field.name in skip:
            continue
        value = getattr(instance, field.attname if field.is_relation else field.name)
        if field.is_relation:
            continue
        if value is None or value == "":
            continue
        data[field.name] = _iso(value) if hasattr(value, "isoformat") else value
    return data


def article_brief(article):
    return {
        "uuid": str(article.pk),
        "slug": article.slug,
        "headline": article.headline,
        "subhead": article.subhead,
        "blurb": article.blurb,
        "article_type": article.article_type,
        "is_free": article.is_free,
        "featured_image": _file_url(article.featured_image),
        "published": _iso(article.created),
        "updated": _iso(article.last_modified),
        "authors": [
            {"name": _author_name(author)} for author in article.authors.all()
        ],
        "players": [player_brief(player) for player in article.players.all()],
        "path": reverse("articles_detail", kwargs={"slug": article.slug})
        if article.slug
        else None,
    }


def _published_articles():
    return (
        models.Article.objects.filter(publish=True, active=True)
        .prefetch_related("authors", "players")
        .order_by("-created", "-uuid")
    )


def _published_rankings(*, mock):
    return models.Ranking.objects.filter(
        publish=True, active=True, is_mock_draft=mock
    )


def list_articles(user, query=None, article_type=None, limit=None, offset=None):
    _require_paid(user)
    if article_type not in (None, "") and article_type not in ARTICLE_TYPES:
        names = ", ".join(sorted(ARTICLE_TYPES))
        raise BadArgument(f"article_type must be one of: {names}")
    qs = _published_articles()
    if article_type:
        qs = qs.filter(article_type=article_type)
    if query:
        qs = qs.filter(
            Q(headline__icontains=query)
            | Q(subhead__icontains=query)
            | Q(blurb__icontains=query)
            | Q(body__icontains=query)
        )
    limit = _limit(limit)
    offset = _offset(offset)
    total, rows = _page(qs, limit, offset)
    return {
        "access": "full",
        "total": total,
        "limit": limit,
        "offset": offset,
        "articles": [article_brief(article) for article in rows],
    }


def get_article(user, slug):
    _require_paid(user)
    article = (
        _published_articles()
        .prefetch_related("teams")
        .filter(slug=slug)
        .first()
    )
    if article is None:
        raise NotFound(f"No published article {slug}")
    data = article_brief(article)
    data["teams"] = [
        {"name": team.name, "slug": team.slug} for team in article.teams.all()
    ]
    data["access"] = "full"
    data["body"] = _html_body(article.body)
    return data


def _filter_boards(qs, query=None, year=None, draft_level=None, current=None):
    if year not in (None, ""):
        qs = qs.filter(year=str(year).strip())
    if draft_level not in (None, ""):
        qs = qs.filter(draft_level__iexact=str(draft_level).strip())
    current_flag = _bool(current, "current")
    if current_flag is not None:
        qs = qs.filter(current=current_flag)
    if query:
        qs = qs.filter(
            Q(headline__icontains=query)
            | Q(custom_title__icontains=query)
            | Q(subhead__icontains=query)
            | Q(blurb__icontains=query)
            | Q(year__icontains=query)
            | Q(mock_draft_version__icontains=query)
        )
    return qs


def _board_page(qs, limit, offset):
    rows = list(qs)
    rows.sort(
        key=lambda ranking: (
            _year_sort(ranking.year),
            ranking.mock_draft_version or "",
            ranking.slug or "",
        ),
        reverse=True,
    )
    total = len(rows)
    return total, rows[offset : offset + limit]


def _year_sort(year):
    try:
        return int(str(year).strip())
    except (TypeError, ValueError):
        return 0


def list_rankings(user, query=None, year=None, draft_level=None, current=None, limit=None, offset=None):
    _require_paid(user)
    qs = _filter_boards(
        _published_rankings(mock=False),
        query=query,
        year=year,
        draft_level=draft_level,
        current=current,
    )
    limit = _limit(limit)
    offset = _offset(offset)
    total, rows = _board_page(qs, limit, offset)
    return {
        "access": "full",
        "total": total,
        "limit": limit,
        "offset": offset,
        "rankings": [ranking_brief(ranking) for ranking in rows],
    }


def list_mock_drafts(user, query=None, year=None, draft_level=None, current=None, limit=None, offset=None):
    _require_paid(user)
    qs = _filter_boards(
        _published_rankings(mock=True),
        query=query,
        year=year,
        draft_level=draft_level,
        current=current,
    )
    limit = _limit(limit)
    offset = _offset(offset)
    total, rows = _board_page(qs, limit, offset)
    return {
        "access": "full",
        "total": total,
        "limit": limit,
        "offset": offset,
        "mock_drafts": [ranking_brief(ranking) for ranking in rows],
    }


def _player_rankings_for(ranking):
    return (
        models.PlayerRanking.objects.filter(ranking=ranking, active=True)
        .select_related("player", "ranking", "school_team")
        .prefetch_related("carrying_tools")
        .order_by("rank", "id")
    )


def _board_detail(user, slug, *, mock):
    _require_paid(user)
    ranking = (
        models.Ranking.objects.filter(slug=slug, publish=True, active=True).first()
    )
    if ranking is None:
        kind = "mock draft" if mock else "ranking"
        raise NotFound(f"No published {kind} {slug}")
    if ranking.is_mock_draft and not mock:
        raise NotFound("That slug is a mock draft. Use get_mock_draft.")
    if mock and not ranking.is_mock_draft:
        raise NotFound("That slug is a ranking. Use get_ranking.")
    rows = _player_rankings_for(ranking)
    total = rows.count()
    visible = list(rows[:MAX_BOARD])
    data = ranking_brief(ranking)
    data["access"] = "full"
    data["body"] = _html_body(ranking.body) if ranking.body else None
    data["players_total"] = total
    data["players_returned"] = len(visible)
    data["players_truncated"] = total > len(visible)
    data["players"] = [
        player_ranking_row(row, include_report=True) for row in visible
    ]
    return data


def get_ranking(user, slug):
    return _board_detail(user, slug, mock=False)


def get_mock_draft(user, slug):
    return _board_detail(user, slug, mock=True)


def _find_player(ref):
    ref = (ref or "").strip()
    if not ref:
        raise BadArgument("player is required")
    qs = models.Player.objects.filter(active=True)
    player = qs.filter(slug=ref).first()
    if player:
        return player
    try:
        import uuid

        uuid.UUID(ref)
    except ValueError:
        pass
    else:
        player = qs.filter(pk=ref).first()
        if player:
            return player
    matches = list(qs.filter(name__iexact=ref)[:5])
    if len(matches) == 1:
        return matches[0]
    if len(matches) > 1:
        raise BadArgument("More than one player has that name. Pass a slug.")
    raise NotFound(f"No player {ref}")


def search_players(user, query=None, position=None, school=None, limit=None, offset=None):
    _require_paid(user)
    text = (query or "").strip()
    if len(text) < 2:
        raise BadArgument("query must be at least 2 characters")
    qs = models.Player.objects.filter(active=True).filter(
        Q(name__icontains=text) | Q(school__icontains=text)
    )
    if position:
        qs = qs.filter(position__iexact=position.strip())
    if school:
        qs = qs.filter(school__icontains=school.strip())
    qs = qs.order_by("name", "uuid")
    limit = _limit(limit)
    offset = _offset(offset)
    total, rows = _page(qs, limit, offset)
    return {
        "access": "full",
        "total": total,
        "limit": limit,
        "offset": offset,
        "players": [player_brief(player) for player in rows],
    }


def _player_history(player):
    rows = list(
        models.PlayerRanking.objects.filter(
            player=player, active=True, ranking__publish=True, ranking__active=True
        )
        .select_related("player", "ranking", "school_team")
        .prefetch_related("carrying_tools")
    )
    rows.sort(key=lambda row: (-_year_sort(row.ranking.year if row.ranking else None), row.rank or 9999))
    return rows


def get_player(user, slug):
    _require_paid(user)
    player = _find_player(slug)
    history = _player_history(player)
    data = player_brief(player)
    data["access"] = "full"
    data["rankings_total"] = len(history)
    data["rankings_locked"] = False
    data["rankings"] = [
        player_ranking_row(row, include_report=True) for row in history
    ]
    data["stat_seasons_locked"] = False
    data["trackman_stat_seasons"] = [
        _stat_dict(season)
        for season in models.PlayerStatSeason.objects.filter(
            player=player, active=True
        ).order_by("-year", "level")
    ]
    data["counting_stat_seasons"] = [
        _stat_dict(season)
        for season in models.Player643StatSeason.objects.filter(
            player=player, active=True
        ).order_by("-year", "team_name")
    ]
    return data


def list_player_stat_seasons(
    user,
    player=None,
    year=None,
    level=None,
    kind=None,
    limit=None,
    offset=None,
):
    _require_paid(user)
    kind = (kind or "both").strip().lower()
    if kind not in STAT_KINDS:
        raise BadArgument("kind must be trackman, counting, or both")
    if level not in (None, ""):
        match = next((name for name in STAT_LEVELS if name.lower() == str(level).strip().lower()), None)
        if match is None:
            names = ", ".join(sorted(STAT_LEVELS))
            raise BadArgument(f"level must be one of: {names}")
        level = match
    year = str(year).strip() if year not in (None, "") else None
    if kind == "counting" and level:
        raise BadArgument(
            "level applies to Trackman seasons. Use kind=trackman or kind=both."
        )
    if not player and not year:
        raise BadArgument("Pass a player slug or name, or a year.")
    player_obj = _find_player(player) if player else None
    limit = _limit(limit)
    offset = _offset(offset)
    payload = {
        "access": "full",
        "player": player_brief(player_obj) if player_obj else None,
        "year": year,
        "level": level,
        "kind": kind,
        "limit": limit,
        "offset": offset,
    }
    if kind in ("trackman", "both"):
        qs = models.PlayerStatSeason.objects.filter(active=True).select_related("player")
        if player_obj:
            qs = qs.filter(player=player_obj)
        if year:
            qs = qs.filter(year=year)
        if level:
            qs = qs.filter(level=level)
        qs = qs.order_by("-year", "level", "player__name")
        total, rows = _page(qs, limit, offset)
        payload["trackman_total"] = total
        payload["trackman_stat_seasons"] = [
            {**_stat_dict(season), "player": player_brief(season.player)} for season in rows
        ]
    if kind in ("counting", "both"):
        qs = models.Player643StatSeason.objects.filter(active=True).select_related("player")
        if player_obj:
            qs = qs.filter(player=player_obj)
        if year:
            qs = qs.filter(year=year)
        qs = qs.order_by("-year", "team_name", "player__name")
        total, rows = _page(qs, limit, offset)
        payload["counting_total"] = total
        payload["counting_stat_seasons"] = [
            {**_stat_dict(season), "player": player_brief(season.player)} for season in rows
        ]
    return payload
