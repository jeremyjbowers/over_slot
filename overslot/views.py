import base64
import csv
import os
import datetime
import itertools
from django.http import Http404, HttpResponse
from django.views.decorators.csrf import csrf_exempt
from django.shortcuts import render, get_object_or_404, redirect
from django.db.models import Count, Avg, Sum, Max, Min, Q, Case, When, Value, IntegerField, F
from django.db.models.functions import Coalesce, Least
from django.core.paginator import EmptyPage, PageNotAnInteger, Paginator
from django.http import JsonResponse
from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.contrib.admin.views.decorators import staff_member_required
from django.contrib import messages
from decimal import *
from django.utils.timezone import template_localtime, now
from django.template.loader import render_to_string
from django.template.response import TemplateResponse
from django.views.decorators.cache import never_cache
from django.views.decorators.csrf import ensure_csrf_cookie
from django.views.decorators.http import require_GET, require_POST
from dateutil import parser
from datetime import timedelta
import json
from packaging.version import InvalidVersion, Version

from overslot import models, utils
from overslot.templatetags.overslot_tags import video_embed_url
from overslot.decorators import subscription_required
from overslot.cache_utils import (
    get_cached,
    bust_homepage,
    HOMEPAGE_TIMEOUT,
    ARTICLE_TIMEOUT,
    RANKING_TIMEOUT,
    MOCK_DRAFT_SIM_PAGE_TIMEOUT,
    KEY_MY_MOCK_DRAFT_HTML,
    KEY_COLLECTION,
    KEY_HOMEPAGE,
    KEY_ARTICLES,
    KEY_STOCK_WATCH,
)

# Client endgame binary (inlined in mock_draft_sim.html): magic OSD1 + version + picks.
_ENDGAME_MAGIC = b'OSD1'
_MAX_MOCK_DRAFT_SHARE_BYTES = 32768


def _mock_draft_share_b64url(payload: bytes) -> str:
    return base64.urlsafe_b64encode(payload).decode('ascii').rstrip('=')


def _validate_mock_draft_share_payload(payload: bytes) -> bool:
    if len(payload) < 9 or len(payload) > _MAX_MOCK_DRAFT_SHARE_BYTES:
        return False
    return payload[:4] == _ENDGAME_MAGIC


@staff_member_required
def bust_homepage_cache(request):
    """Staff-only: clear homepage cache and redirect to homepage."""
    bust_homepage()
    messages.success(request, 'Homepage cache cleared.')
    return redirect('index')


def index(request):
    context = {}

    # Carousel: stock watch first, then articles, then rankings, then games
    def _latest_stock_watch():
        return list(models.StockWatchArticle.objects.filter(
            publish=True, active=True, is_carousel=True
        ).select_related('author').order_by('-date', '-created')[:5])
    context['latest_stock_watch'] = get_cached('overslot:homepage:stock_watch', _latest_stock_watch, HOMEPAGE_TIMEOUT)

    def _latest_articles():
        qs = models.Article.objects.filter(
            publish=True, active=True, is_carousel=True
        ).prefetch_related('authors', 'players', 'teams').order_by('-created')[:5]
        articles = list(qs)
        for a in articles:
            a.active_players = [p for p in a.players.all() if p.active]
            a.active_teams = [t for t in a.teams.all() if t.active]
        return articles
    context['latest_articles'] = get_cached('overslot:homepage:articles', _latest_articles, HOMEPAGE_TIMEOUT)

    def _latest_rankings():
        return list(models.Ranking.objects.filter(
            publish=True, is_carousel=True
        ).annotate(
            level_order=Case(
                When(draft_level='Overall', then=Value(0)),
                When(draft_level='College', then=Value(1)),
                When(draft_level='High School', then=Value(2)),
                default=Value(99),
                output_field=IntegerField(),
            )
        ).order_by('-created')[:5])
    context['latest_rankings'] = get_cached('overslot:homepage:rankings_carousel', _latest_rankings, HOMEPAGE_TIMEOUT)

    def _latest_games():
        return list(models.Game.objects.filter(
            active=True, is_carousel=True
        ).exclude(status='past').exclude(name__isnull=True).exclude(name='').exclude(
            streaming_url__isnull=True
        ).exclude(streaming_url='').select_related(
            'home_team', 'away_team'
        ).order_by('start_datetime')[:5])
    context['latest_games'] = get_cached('overslot:homepage:games', _latest_games, HOMEPAGE_TIMEOUT)

    # Flanking lists: left = scouting articles; right = non-scouting
    def _scouting_articles():
        qs = models.Article.objects.filter(
            publish=True, active=True, article_type='scouting'
        ).prefetch_related('authors', 'players').order_by('-created')[:3]
        articles = list(qs)
        for a in articles:
            a.active_players = [p for p in a.players.all() if p.active]
        return articles
    context['scouting_articles'] = get_cached('overslot:homepage:scouting', _scouting_articles, HOMEPAGE_TIMEOUT)

    def _non_scouting_articles():
        qs = models.Article.objects.filter(
            publish=True, active=True
        ).exclude(article_type='scouting').prefetch_related('authors', 'players').order_by('-created')[:3]
        articles = list(qs)
        for a in articles:
            a.active_players = [p for p in a.players.all() if p.active]
        return articles
    context['non_scouting_articles'] = get_cached('overslot:homepage:non_scouting', _non_scouting_articles, HOMEPAGE_TIMEOUT)

    # Rankings grid: current and archived
    def _current_rankings():
        return list(models.Ranking.objects.filter(
            is_mock_draft=False, publish=True, current=True
        ).annotate(
            level_order=Case(
                When(draft_level='Overall', then=Value(0)),
                When(draft_level='College', then=Value(1)),
                When(draft_level='High School', then=Value(2)),
                default=Value(99),
                output_field=IntegerField(),
            )
        ).order_by('year', 'level_order'))
    context['current_rankings'] = get_cached('overslot:homepage:current_rankings', _current_rankings, HOMEPAGE_TIMEOUT)

    def _archived_rankings():
        return list(models.Ranking.objects.filter(
            is_mock_draft=False, publish=True, current=False
        ).annotate(
            level_order=Case(
                When(draft_level='Overall', then=Value(0)),
                When(draft_level='College', then=Value(1)),
                When(draft_level='High School', then=Value(2)),
                default=Value(99),
                output_field=IntegerField(),
            )
        ).order_by('-year', 'level_order'))
    context['archived_rankings'] = get_cached('overslot:homepage:archived_rankings', _archived_rankings, HOMEPAGE_TIMEOUT)

    def _rankings_count():
        return models.Ranking.objects.filter(is_mock_draft=False, publish=True).count()
    context['rankings_count'] = get_cached('overslot:homepage:rankings_count', _rankings_count, HOMEPAGE_TIMEOUT)

    # Player videos sidebar - cache the random selection (re-randomizes on TTL expiry)
    def _player_videos():
        qs = models.Player.objects.filter(
            active=True
        ).exclude(video_url__isnull=True).exclude(video_url="").exclude(
            photo_url__isnull=True
        ).exclude(photo_url="")
        return list(qs.order_by('?')[:9])
    context['player_videos'] = get_cached('overslot:homepage:player_videos', _player_videos, HOMEPAGE_TIMEOUT)

    def _videos_count():
        return models.Player.objects.filter(
            active=True
        ).exclude(video_url__isnull=True).exclude(video_url="").exclude(
            photo_url__isnull=True
        ).exclude(photo_url="").count()
    context['videos_count'] = get_cached('overslot:homepage:videos_count', _videos_count, HOMEPAGE_TIMEOUT)

    def _draft_highlight_reels():
        """
        Random sample of YouTube-backed 2026 draft highlight reels from sheet-loaded PlayerRanking rows.
        """
        qs = models.PlayerRanking.objects.filter(
            active=True,
            ranking__year='2026',
            ranking__is_draft=True,
            ranking__is_mock_draft=False,
            ranking__publish=True,
            player__isnull=False,
            player__active=True,
        ).exclude(
            highlight_reel_url__isnull=True
        ).exclude(
            highlight_reel_url=''
        ).select_related('player')

        candidates = list(qs.order_by('?')[:80])
        reels = []
        seen_player = set()
        for pr in candidates:
            if pr.player_id in seen_player:
                continue
            embed = video_embed_url(pr.highlight_reel_url or '')
            if not embed or 'youtube.com/embed' not in embed:
                continue
            seen_player.add(pr.player_id)
            reels.append({
                'embed_url': embed,
                'player_name': pr.player.name,
            })
            if len(reels) >= 6:
                break
        return reels

    context['draft_highlight_reels'] = get_cached(
        f'{KEY_HOMEPAGE}:draft_highlight_reels',
        _draft_highlight_reels,
        HOMEPAGE_TIMEOUT,
    )

    # Featured games belt
    from django.utils import timezone
    now = timezone.now()
    def _featured_games():
        return list(models.Game.objects.filter(
            active=True, featured=True
        ).exclude(status='past').select_related(
            'home_team', 'away_team'
        ).order_by('start_datetime'))
    context['featured_games'] = get_cached('overslot:homepage:featured_games', _featured_games, HOMEPAGE_TIMEOUT)

    # Podcast belt
    def _latest_podcasts():
        return list(models.PodcastEpisode.objects.filter(
            publish=True
        ).order_by('-featured', '-published_at')[:5])
    context['latest_podcasts'] = get_cached('overslot:homepage:podcasts', _latest_podcasts, HOMEPAGE_TIMEOUT)

    def _homepage_collections():
        return list(
            models.Collection.objects.filter(active=True, show_on_homepage=True).order_by('-last_modified')[:20]
        )

    context['homepage_collections'] = get_cached(
        f'{KEY_HOMEPAGE}:collections',
        _homepage_collections,
        HOMEPAGE_TIMEOUT,
    )

    return render(request, "index.html", context)


def _news_item_sort_ts(item):
    """Unix timestamp for ordering news list items (articles and stock watch)."""
    d = item['date']
    if d is None:
        return 0.0
    if isinstance(d, datetime.date) and not isinstance(d, datetime.datetime):
        dt = datetime.datetime.combine(d, datetime.time.min)
    else:
        dt = d
    try:
        return dt.timestamp()
    except (TypeError, OSError):
        return 0.0


def _build_news_items(list_filter='all'):
    """
    Build combined articles (+ optional stock watch), sorted by date.
    list_filter: 'all' (default), 'scouting' (scouting articles only), or 'news' (non-scouting articles only; stock watch is /stock-watch/).
    """
    items = []

    if list_filter == 'all':
        stock_watch_qs = models.StockWatchArticle.objects.filter(publish=True, active=True).select_related('author').prefetch_related(
            'stock_watch_players__player'
        )
        for sw in stock_watch_qs:
            items.append({
                'item_type': 'stock_watch',
                'url': f'/stock-watch/{sw.slug}/',
                'headline': sw.headline,
                'subhead': sw.deck,
                'featured_image': sw.featured_image,
                'author': sw.author,
                'date': sw.date,
                'players': [swp.player for swp in sw.stock_watch_players.all() if swp.active],
            })

    articles_qs = models.Article.objects.filter(publish=True, active=True).prefetch_related('authors', 'players')
    if list_filter == 'scouting':
        articles_qs = articles_qs.filter(article_type='scouting')
    elif list_filter == 'news':
        articles_qs = articles_qs.exclude(article_type='scouting')

    for a in articles_qs:
        items.append({
            'item_type': 'article',
            'url': f'/articles/{a.slug}/',
            'headline': a.headline,
            'subhead': a.subhead,
            'featured_image': a.featured_image,
            'authors': list(a.authors.all()),
            'date': a.created,
            'players': [p for p in a.players.all() if p.active],
        })
    items.sort(key=_news_item_sort_ts, reverse=True)
    return items


def _recent_rankings():
    """Recent rankings for sidebar. Cached."""
    return list(models.Ranking.objects.filter(
        is_mock_draft=False, publish=True, current=True
    ).annotate(
        level_order=Case(
            When(draft_level='Overall', then=Value(0)),
            When(draft_level='College', then=Value(1)),
            When(draft_level='High School', then=Value(2)),
            default=Value(99),
            output_field=IntegerField(),
        )
    ).order_by('year', 'level_order'))


def articles_list(request):
    context = {}
    category = (request.GET.get('category') or '').strip().lower()
    if category == 'scouting':
        list_filter = 'scouting'
        cache_suffix = 'scouting'
    elif category == 'news':
        list_filter = 'news'
        cache_suffix = 'news'
    else:
        list_filter = 'all'
        cache_suffix = 'all'
        category = ''

    cache_key = f'{KEY_ARTICLES}:list_items' if cache_suffix == 'all' else f'{KEY_ARTICLES}:list_items:{cache_suffix}'
    context['news_items'] = get_cached(
        cache_key,
        lambda lf=list_filter: _build_news_items(lf),
        ARTICLE_TIMEOUT,
    )
    context['recent_rankings'] = get_cached(f'{KEY_ARTICLES}:recent_rankings', _recent_rankings, ARTICLE_TIMEOUT)
    context['articles_list_category'] = category
    return render(request, "articles_list.html", context)


def _build_collection_news_items(slug):
    """Published articles in a collection as news_items-shaped dicts."""
    collection = models.Collection.objects.filter(slug=slug, active=True).first()
    if not collection:
        raise Http404("Collection not found")
    qs = collection.articles.filter(publish=True, active=True).prefetch_related('authors', 'players')
    items = []
    for a in qs:
        items.append({
            'item_type': 'article',
            'url': f'/articles/{a.slug}/',
            'headline': a.headline,
            'subhead': a.subhead,
            'featured_image': a.featured_image,
            'authors': list(a.authors.all()),
            'date': a.created,
            'players': [p for p in a.players.all() if p.active],
        })
    items.sort(key=_news_item_sort_ts, reverse=True)
    return items


def collection_articles_list(request, slug):
    collection = get_object_or_404(models.Collection, slug=slug, active=True)
    context = {
        'collection': collection,
        'news_items': get_cached(
            f'{KEY_COLLECTION}:{slug}',
            lambda: _build_collection_news_items(slug),
            ARTICLE_TIMEOUT,
        ),
        'recent_rankings': get_cached('overslot:articles:recent_rankings', _recent_rankings, ARTICLE_TIMEOUT),
    }
    return render(request, "articles_list.html", context)


def _article_detail_context(slug):
    """Fetch article with active players/teams. Cached per slug. Raises Http404 if not found."""
    article = models.Article.objects.filter(
        slug=slug, publish=True, active=True
    ).prefetch_related('players', 'teams', 'authors').first()
    if not article:
        from django.http import Http404
        raise Http404("Article not found")
    article.active_players = [p for p in article.players.all() if p.active]
    article.active_teams = [t for t in article.teams.all() if t.active]
    return article


@subscription_required
def articles_detail(request, slug):
    context = {}
    context['article'] = get_cached(f'overslot:article:{slug}', lambda: _article_detail_context(slug), ARTICLE_TIMEOUT)
    return render(request, "articles_detail.html", context)


def _get_player_statline(player):
    """
    Get the most recent season stat line for a player.
    Returns dict with type ('hitting' or 'pitching'), year, level, team_name, and stat-specific fields.
    Checks: 643 hitting, 643 pitching, PlayerStatSeason (hs_statline).
    """
    eligibility = utils.college_stat_eligibility_for_players([player.pk])

    def _643_ok(season):
        return utils.player_accepts_college_season(player, season.year, eligibility)

    # Try 643 hitting stats first
    stat_643_hit = (
        models.Player643StatSeason.objects.filter(player=player)
        .exclude(hit_plate_appearances__isnull=True)
        .exclude(hit_plate_appearances=0)
        .order_by('-year')
    )
    stat_643_hit = next((s for s in stat_643_hit if _643_ok(s)), None)
    if stat_643_hit and (stat_643_hit.hit_ba is not None or stat_643_hit.hit_obp is not None or stat_643_hit.hit_slg is not None):
        return {
            'type': 'hitting',
            'pa': stat_643_hit.hit_plate_appearances,
            'ba': stat_643_hit.hit_ba,
            'obp': stat_643_hit.hit_obp,
            'slg': stat_643_hit.hit_slg,
            'ops': stat_643_hit.hit_ops,
            'iso': stat_643_hit.hit_iso,
            'year': stat_643_hit.year,
            'level': None,
            'team_name': stat_643_hit.team_name,
        }
    # Try 643 pitching stats
    stat_643_pitch = (
        models.Player643StatSeason.objects.filter(player=player)
        .exclude(pitch_innings_pitched__isnull=True)
        .filter(pitch_innings_pitched__gt=0)
        .order_by('-year')
    )
    stat_643_pitch = next((s for s in stat_643_pitch if _643_ok(s)), None)
    if stat_643_pitch:
        return {
            'type': 'pitching',
            'ip': stat_643_pitch.pitch_innings_pitched,
            'whip': stat_643_pitch.pitch_whip,
            'ba': stat_643_pitch.pitch_ba,
            'obp': stat_643_pitch.pitch_obp,
            'slg': stat_643_pitch.pitch_slg,
            'ops': stat_643_pitch.pitch_ops,
            'k_pct': stat_643_pitch.pitch_strikeout_rate,
            'bb_pct': stat_643_pitch.pitch_walk_rate,
            'fip': stat_643_pitch.pitch_fip,
            'year': stat_643_pitch.year,
            'level': None,
            'team_name': stat_643_pitch.team_name,
        }
    # Fall back to PlayerStatSeason (Trackman HS or college hitting)
    stat_season = (
        models.PlayerStatSeason.objects.filter(player=player)
        .order_by('-year')
    )
    stat_season = next(
        (
            s for s in stat_season
            if s.level != "College" or utils.player_accepts_college_season(player, s.year, eligibility)
        ),
        None,
    )
    if stat_season:
        if stat_season.level == "High School" and any(
            v is not None for v in [stat_season.hs_pa, stat_season.hs_ba, stat_season.hs_obp]
        ):
            return {
                'type': 'hitting',
                'pa': stat_season.hs_pa,
                'ba': stat_season.hs_ba,
                'obp': stat_season.hs_obp,
                'slg': stat_season.hs_slg,
                'ops': stat_season.hs_ops,
                'iso': stat_season.hs_iso,
                'year': stat_season.year,
                'level': stat_season.level,
                'team_name': stat_season.school,
            }
    return None


def _stock_watch_detail_context(slug):
    """Fetch stock watch article with players and statlines. Cached per slug. Raises Http404 if not found."""
    article = models.StockWatchArticle.objects.filter(
        slug=slug, publish=True, active=True
    ).prefetch_related('stock_watch_players__player').first()
    if not article:
        from django.http import Http404
        raise Http404("Stock watch article not found")
    sw_players = list(
        article.stock_watch_players.filter(active=True)
        .select_related('player')
        .order_by('-direction', 'player__name')
    )
    for swp in sw_players:
        statline = _get_player_statline(swp.player)
        if statline and statline.get('level') == 'High School':
            statline = None
        swp.statline = statline
    return article, sw_players


def _build_stock_watch_list_items():
    """Published stock watch entries as article-list-shaped dicts."""
    items = []
    qs = models.StockWatchArticle.objects.filter(publish=True, active=True).select_related('author').prefetch_related(
        'stock_watch_players__player'
    )
    for sw in qs:
        items.append({
            'item_type': 'stock_watch',
            'url': f'/stock-watch/{sw.slug}/',
            'headline': sw.headline,
            'subhead': sw.deck,
            'featured_image': sw.featured_image,
            'author': sw.author,
            'date': sw.date,
            'players': [swp.player for swp in sw.stock_watch_players.all() if swp.active],
        })
    items.sort(key=_news_item_sort_ts, reverse=True)
    return items


def stock_watch_list(request):
    context = {
        'news_items': get_cached(
            f'{KEY_STOCK_WATCH}:list_items',
            _build_stock_watch_list_items,
            ARTICLE_TIMEOUT,
        ),
        'recent_rankings': get_cached(f'{KEY_ARTICLES}:recent_rankings', _recent_rankings, ARTICLE_TIMEOUT),
        'stock_watch_list_only': True,
    }
    return render(request, 'articles_list.html', context)


@subscription_required
def stock_watch_detail(request, slug):
    context = {}
    article, sw_players = get_cached(
        f'overslot:stock_watch:{slug}',
        lambda: _stock_watch_detail_context(slug),
        ARTICLE_TIMEOUT
    )
    context['article'] = article
    context['stock_watch_players'] = sw_players
    return render(request, "stock_watch_detail.html", context)


def _rankings_list_data():
    """Current + archived rankings for main rankings list. Cached."""
    current = list(models.Ranking.objects.filter(
        is_mock_draft=False, publish=True, current=True
    ).annotate(
        level_order=Case(
            When(draft_level='Overall', then=Value(0)),
            When(draft_level='College', then=Value(1)),
            When(draft_level='High School', then=Value(2)),
            default=Value(99),
            output_field=IntegerField(),
        )
    ).order_by('year', 'level_order'))
    archived = list(models.Ranking.objects.filter(
        is_mock_draft=False, publish=True, current=False
    ).annotate(
        level_order=Case(
            When(draft_level='Overall', then=Value(0)),
            When(draft_level='College', then=Value(1)),
            When(draft_level='High School', then=Value(2)),
            default=Value(99),
            output_field=IntegerField(),
        )
    ).order_by('-year', 'level_order'))
    return current + archived


def rankings_list(request):
    context = {}
    context['rankings'] = get_cached('overslot:rankings:list', _rankings_list_data, RANKING_TIMEOUT)
    return render(request, "rankings_list.html", context)


def _mock_draft_list_year_key(year_str):
    """Sortable year: newest first via reverse sort below."""
    if not year_str:
        return 0
    try:
        return int(str(year_str).strip())
    except (TypeError, ValueError):
        return 0


def _mock_draft_list_version_key(version_str):
    """PEP-440 style version for ordering (e.g. 3.0 > 2.0 > 1.0)."""
    if not version_str or not str(version_str).strip():
        return Version("0")
    raw = str(version_str).strip().lstrip("vV")
    try:
        return Version(raw)
    except InvalidVersion:
        return Version("0")


def _player_ranking_sort_key(pr):
    """
    Sort PlayerRanking rows for player profile pages.

    Order:
      1. Year descending (furthest-future season first).
      2. Within a year, regular rankings before mock drafts.
      3. Within a year's mock drafts, version descending (3.0, 2.0, 1.0).
    """
    ranking = getattr(pr, "ranking", None)
    year_key = _mock_draft_list_year_key(getattr(ranking, "year", None))
    is_mock = 1 if (ranking is not None and ranking.is_mock_draft) else 0
    version_key = _mock_draft_list_version_key(getattr(ranking, "mock_draft_version", None))
    # Negate year/version so a normal ascending sort yields newest-first ordering;
    # is_mock stays positive so regular rankings (0) precede mock drafts (1).
    return (-year_key, is_mock, _NegatedVersion(version_key))


class _NegatedVersion:
    """Wrapper that reverses Version comparison order (since Version cannot be negated)."""

    __slots__ = ("_v",)

    def __init__(self, version):
        self._v = version

    def __lt__(self, other):
        return self._v > other._v

    def __eq__(self, other):
        return self._v == other._v


def _mock_drafts_list_data():
    """Published mock drafts, newest year and newest version first. Cached."""
    qs = models.Ranking.objects.filter(is_mock_draft=True, publish=True).order_by("slug")
    return sorted(
        qs,
        key=lambda r: (
            _mock_draft_list_year_key(r.year),
            _mock_draft_list_version_key(r.mock_draft_version),
        ),
        reverse=True,
    )


def mock_drafts_list(request):
    context = {}
    context['rankings'] = get_cached('overslot:rankings:mock_drafts', _mock_drafts_list_data, RANKING_TIMEOUT)
    return render(request, "rankings_list.html", context)


@ensure_csrf_cookie
@require_GET
def my_mock_draft(request):
    """
    Simulator landing page. Valkey stores one HTML string under a fixed key (no path/query
    variation). Share URLs (/my-mock-draft/s/…/, /my-mock-draft/<uuid>/) are never cached.

    The cached HTML must be rendered with the real incoming request. A synthetic
    RequestFactory request uses Host ``testserver``, which is not in ALLOWED_HOSTS; templates
    that call ``request.build_absolute_uri()`` (e.g. ``og:url`` in base) then raise
    ``DisallowedHost`` and Django returns 400.
    """

    def compute_cached_html():
        return render_to_string(
            "mock_draft_sim.html",
            {"hide_nav_account": True},
            request=request,
        )

    html = get_cached(
        KEY_MY_MOCK_DRAFT_HTML,
        compute_cached_html,
        MOCK_DRAFT_SIM_PAGE_TIMEOUT,
    )
    return HttpResponse(html)


@ensure_csrf_cookie
@never_cache
@require_GET
def my_mock_draft_share(request, draft_share):
    """
    Same template as my_mock_draft; payload lives in the URL path for chat clients.
    Intentionally not cached in Valkey (infinite distinct payloads). draft_share is only
    for URL routing — the client reads the payload from location.pathname. never_cache
    avoids edge/CDN caches treating each share URL as a cacheable document.
    """
    return render(request, "mock_draft_sim.html", {"hide_nav_account": True})


@ensure_csrf_cookie
@never_cache
@require_GET
def my_mock_draft_share_by_uuid(request, share_id):
    """
    Share link with payload loaded from DB (short URL for chat clients).
    """
    share = get_object_or_404(models.MockDraftShare, pk=share_id)
    payload = bytes(share.payload)
    return render(
        request,
        "mock_draft_sim.html",
        {
            "hide_nav_account": True,
            "mock_draft_share_id": str(share.id),
            "mock_draft_share_payload_b64": _mock_draft_share_b64url(payload),
        },
    )


@require_POST
def mock_draft_share_create(request):
    """Persist finished draft binary; returns UUID for /my-mock-draft/<uuid>/"""
    try:
        body = json.loads(request.body.decode('utf-8'))
    except (json.JSONDecodeError, UnicodeDecodeError):
        return JsonResponse({'error': 'invalid json'}, status=400)
    enc = body.get('payload')
    if not isinstance(enc, str) or not enc:
        return JsonResponse({'error': 'missing payload'}, status=400)
    pad = '=' * (-len(enc) % 4)
    try:
        payload = base64.urlsafe_b64decode(enc + pad)
    except Exception:
        return JsonResponse({'error': 'invalid base64'}, status=400)
    if not _validate_mock_draft_share_payload(payload):
        return JsonResponse({'error': 'invalid payload'}, status=400)
    share = models.MockDraftShare.objects.create(payload=payload)
    return JsonResponse({'id': str(share.id)})


def videos_list(request):
    context = {}
    players = models.Player.objects.filter(
        active=True
    ).exclude(video_url__isnull=True).exclude(video_url="")\
     .exclude(photo_url__isnull=True).exclude(photo_url="")

    # Sort by last name, then first name using simple split fallback
    def sort_key(p):
        parts = (p.name or "").strip().split()
        if not parts:
            return ("", "")
        if len(parts) == 1:
            return (parts[0].lower(), "")
        return (parts[-1].lower(), " ".join(parts[:-1]).lower())

    players = sorted(players, key=sort_key)
    context['players'] = players

    return render(request, "videos_list.html", context)


def _draft_highlight_reel_list_items():
    """
    One entry per active player with a usable YouTube highlight reel on published draft rankings.
    Picks best PlayerRanking per player (highest year, then Overall > College > HS, then last_modified).
    """
    from collections import defaultdict
    from django.utils import timezone as dj_tz

    qs = models.PlayerRanking.objects.filter(
        active=True,
        ranking__is_draft=True,
        ranking__is_mock_draft=False,
        ranking__publish=True,
        player__isnull=False,
        player__active=True,
    ).exclude(
        highlight_reel_url__isnull=True
    ).exclude(
        highlight_reel_url=''
    ).select_related('player', 'ranking')

    by_player = defaultdict(list)
    for pr in qs:
        by_player[pr.player_id].append(pr)

    level_pri = {'Overall': 0, 'College': 1, 'High School': 2}

    def _pr_sort_key(pr):
        y = 0
        if pr.ranking_id and pr.ranking.year:
            ys = str(pr.ranking.year).strip()
            if ys.isdigit():
                y = int(ys)
        dl = level_pri.get((pr.ranking.draft_level if pr.ranking else '') or '', 99)
        lm = pr.last_modified or pr.created
        if lm is None:
            lm = dj_tz.now()
        return (y, -dl, lm)

    items = []
    for player_id, prs in by_player.items():
        best = max(prs, key=_pr_sort_key)
        embed = (video_embed_url(best.highlight_reel_url or '') or '').strip()
        if not embed or 'youtube.com/embed' not in embed:
            continue
        pos = (best.position or best.player.position or '').strip()
        items.append({
            'embed_url': embed,
            'player': best.player,
            'position': pos,
        })

    def _name_sort_key(entry):
        p = entry['player']
        parts = (p.name or "").strip().split()
        if not parts:
            return ("", "")
        if len(parts) == 1:
            return (parts[0].lower(), "")
        return (parts[-1].lower(), " ".join(parts[:-1]).lower())

    items.sort(key=_name_sort_key)
    return items


@subscription_required
def reels_list(request):
    context = {'reels': _draft_highlight_reel_list_items()}
    return TemplateResponse(request, "reels_list.html", context)


def games_list(request, year=None, month=None, day=None):
    """
    Display games for a specific date. If no date provided, shows today's games
    (or opening day if today is before opening day).
    
    NOTE: This view is PUBLIC and should NOT be paywalled. Games list and player
    rankings shown on game cards are free content.
    """
    context = {}
    
    # Get season opening day from settings
    try:
        season_opening_day = parser.parse(getattr(settings, 'SEASON_OPENING_DAY', '2025-02-13')).date()
    except (ValueError, TypeError):
        season_opening_day = datetime.date(2026, 2, 13)  # Fallback
    
    today = now().date()
    
    # Determine which date to show
    if year and month and day:
        try:
            display_date = datetime.date(year, month, day)
        except (ValueError, TypeError):
            # Invalid date format, redirect to today/opening day
            return redirect('games_list')
    else:
        # Default: show today's games, or opening day if before opening day
        display_date = max(today, season_opening_day)
    
    # Don't allow dates before opening day
    if display_date < season_opening_day:
        display_date = season_opening_day
    
    # Get games for this date (start of day to end of day)
    start_of_day = datetime.datetime.combine(display_date, datetime.time.min)
    end_of_day = datetime.datetime.combine(display_date, datetime.time.max)
    
    # Make timezone-aware if needed
    from django.utils import timezone
    if timezone.is_naive(start_of_day):
        start_of_day = timezone.make_aware(start_of_day)
    if timezone.is_naive(end_of_day):
        end_of_day = timezone.make_aware(end_of_day)
    
    # For games at same time: highest-ranked team first (lowest rank number). Unranked games last.
    home_rank = Coalesce(
        F('home_team__current_ranking'),
        F('home_team_ranking'),
        Value(9999),
        output_field=IntegerField(),
    )
    away_rank = Coalesce(
        F('away_team__current_ranking'),
        F('away_team_ranking'),
        Value(9999),
        output_field=IntegerField(),
    )
    games = models.Game.objects.filter(
        active=True,
        start_datetime__gte=start_of_day,
        start_datetime__lte=end_of_day
    ).select_related('home_team', 'away_team').annotate(
        best_rank=Least(home_rank, away_rank),
    ).order_by('start_datetime', 'best_rank')
    
    # Collect all unique teams
    teams = set()
    for game in games:
        if game.home_team:
            teams.add(game.home_team)
        if game.away_team:
            teams.add(game.away_team)
    
    # Ensure all teams have slugs (for teams created before slug field was added)
    for team in teams:
        if not team.slug:
            team.save()  # Auto-generates slug
            team.refresh_from_db()
    
    # Prefetch player rankings for all teams at once (from current, published rankings)
    # Deduplicate by player - only keep the most recent ranking for each player
    team_ids = [team.id for team in teams]
    player_rankings_by_team = {}
    if team_ids:
        rankings_qs = models.PlayerRanking.objects.filter(
            school_team_id__in=team_ids,
            ranking__publish=True,
            ranking__current=True,
            ranking__is_mock_draft=False,
            active=True,
            player__isnull=False  # Ensure player exists
        ).select_related('player', 'ranking', 'school_team').annotate(
            # Create priority: Overall = 0, others = 1 (so Overall comes first)
            ranking_priority=Case(
                When(ranking__draft_level='Overall', then=Value(0)),
                default=Value(1),
                output_field=IntegerField(),
            )
        ).order_by(
            'school_team_id', 
            'player_id',
            'ranking_priority',  # Overall rankings first
            '-ranking__created'  # Then most recent ranking
        )
        
        # Track preferred ranking per (team, player) pair
        # Prefers Overall rankings, then falls back to most recent
        # Key: (team_id, player_id), Value: PlayerRanking
        preferred_by_player = {}
        
        for pr in rankings_qs:
            if not pr.player_id or not pr.school_team_id:
                continue
            
            key = (pr.school_team_id, pr.player_id)
            # Only keep the first ranking for each player
            # Due to ordering, this will be Overall if available, otherwise most recent
            if key not in preferred_by_player:
                preferred_by_player[key] = pr
        
        # Group deduplicated rankings by team
        for (team_id, player_id), pr in preferred_by_player.items():
            if team_id not in player_rankings_by_team:
                player_rankings_by_team[team_id] = []
            player_rankings_by_team[team_id].append(pr)
        
        # Sort by year ascending, Overall before College, then rank ascending. Limit to top 10 per team.
        def _draft_level_priority(dl):
            if dl == 'Overall':
                return 0
            if dl == 'College':
                return 1
            return 2  # High School or other
        for team_id in player_rankings_by_team:
            player_rankings_by_team[team_id].sort(key=lambda pr: (
                pr.ranking.year if (pr.ranking and pr.ranking.year) else '9999',
                _draft_level_priority(pr.ranking.draft_level if pr.ranking else None),
                pr.rank if pr.rank else 9999,
            ))
            player_rankings_by_team[team_id] = player_rankings_by_team[team_id][:10]
    
    # Attach rankings to teams
    for team in teams:
        team.player_rankings_list = player_rankings_by_team.get(team.id, [])
    
    context['games'] = games
    context['display_date'] = display_date
    context['season_opening_day'] = season_opening_day
    context['today'] = today
    
    # Calculate previous and next dates for navigation
    prev_date = display_date - timedelta(days=1)
    next_date = display_date + timedelta(days=1)
    
    # Don't allow going back before opening day
    if prev_date < season_opening_day:
        context['has_prev'] = False
    else:
        context['has_prev'] = True
        context['prev_date'] = prev_date
    
    # Always allow going forward
    context['has_next'] = True
    context['next_date'] = next_date
    
    return render(request, "games_list.html", context)


def teams_list(request):
    """
    Display a list of all teams that have games, grouped by first letter, alphabetically sorted.
    
    NOTE: This view is PUBLIC and should NOT be paywalled.
    """
    context = {}
    # Only show teams that have at least one game (home or away)
    teams = models.Team.objects.filter(
        active=True
    ).filter(
        Q(home_games__isnull=False) | Q(away_games__isnull=False)
    ).distinct().order_by('name')
    
    # Group teams by first letter
    teams_by_letter = {}
    for team in teams:
        first_letter = team.name[0].upper() if team.name else 'Other'
        if first_letter not in teams_by_letter:
            teams_by_letter[first_letter] = []
        teams_by_letter[first_letter].append(team)
    
    # Sort letters and convert to list of tuples
    context['teams_by_letter'] = sorted(teams_by_letter.items())
    
    return render(request, "teams_list.html", context)


def team_detail(request, slug):
    """
    Display team detail page with upcoming games for this team.
    
    NOTE: This view is PUBLIC and should NOT be paywalled. Team pages and player
    rankings shown on team detail pages are free content.
    """
    context = {}
    team = get_object_or_404(models.Team, slug=slug, active=True)
    context['team'] = team
    
    # Ensure team has slug (for teams created before slug field was added)
    if not team.slug:
        team.save()  # Auto-generates slug
        team.refresh_from_db()
    
    # Get upcoming games for this team (home or away)
    from django.utils import timezone
    now = timezone.now()
    
    upcoming_games = models.Game.objects.filter(
        active=True,
        start_datetime__gte=now
    ).filter(
        Q(home_team=team) | Q(away_team=team)
    ).select_related('home_team', 'away_team').order_by('start_datetime')[:20]  # Next 20 games
    
    context['upcoming_games'] = upcoming_games
    
    # Get player rankings for this team (from current, published rankings)
    # Deduplicate by player - prefer Overall rankings, then most recent
    rankings_qs = models.PlayerRanking.objects.filter(
        school_team=team,
        ranking__publish=True,
        ranking__current=True,
        ranking__is_mock_draft=False,
        active=True,
        player__isnull=False  # Ensure player exists
    ).select_related('player', 'ranking', 'school_team').annotate(
        # Create priority: Overall = 0, others = 1 (so Overall comes first)
        ranking_priority=Case(
            When(ranking__draft_level='Overall', then=Value(0)),
            default=Value(1),
            output_field=IntegerField(),
        )
    ).order_by(
        'player_id',
        'ranking_priority',  # Overall rankings first
        '-ranking__created'  # Then most recent ranking
    )
    
    # Track preferred ranking per player
    # Prefers Overall rankings, then falls back to most recent
    preferred_by_player = {}
    
    for pr in rankings_qs:
        if not pr.player_id:
            continue
        
        # Only keep the first ranking for each player
        # Due to ordering, this will be Overall if available, otherwise most recent
        if pr.player_id not in preferred_by_player:
            preferred_by_player[pr.player_id] = pr
    
    # Get deduplicated rankings, sort by rank, and limit to top 50
    player_rankings_list = list(preferred_by_player.values())
    player_rankings_list.sort(key=lambda pr: pr.rank if pr.rank else 9999)
    team.player_rankings_list = player_rankings_list[:50]  # Top 50 players
    
    return render(request, "team_detail.html", context)


def _ranking_detail_context(slug, is_mock_draft):
    """Build full ranking detail context. Cached per slug. Raises Http404 if not found."""
    from django.http import Http404
    ranking = models.Ranking.objects.filter(
        slug=slug, publish=True, is_mock_draft=is_mock_draft
    ).first()
    if not ranking:
        raise Http404("Ranking not found")
    player_rankings = list(
        models.PlayerRanking.objects.filter(ranking=ranking, active=True)
        .select_related('player')
        .order_by('rank')
    )
    schools = sorted([pr.school for pr in player_rankings if pr.school])
    commitments = sorted([pr.commitment for pr in player_rankings if pr.commitment])
    states = sorted([pr.player.state for pr in player_rankings if pr.player and pr.player.state])
    schools = list(dict.fromkeys(schools))
    commitments = list(dict.fromkeys(commitments))
    states = list(dict.fromkeys(states))
    position_mapping = [
        ('P', ['P', 'RHP', 'LHP']),
        ('C', ['C']),
        ('1B', ['1B']),
        ('2B', ['2B']),
        ('3B', ['3B']),
        ('SS', ['SS']),
        ('OF', ['OF', 'LF', 'CF', 'RF']),
        ('INF', ['INF']),
        ('UTL', ['UTL', 'UTIL'])
    ]
    all_positions = [pr.position for pr in player_rankings if pr.position]
    positions = []
    for simple_pos, variants in position_mapping:
        for player_pos in all_positions:
            if any(variant in player_pos.upper() for variant in variants):
                if simple_pos not in positions:
                    positions.append(simple_pos)
                break
    recent_articles = list(models.Article.objects.filter(publish=True, active=True).order_by('-created')[:5])
    return (ranking, player_rankings, positions, schools, commitments, states, recent_articles)


@subscription_required
def rankings_detail(request, slug):
    context = {}
    data = get_cached(
        f'overslot:ranking:{slug}',
        lambda: _ranking_detail_context(slug, is_mock_draft=False),
        RANKING_TIMEOUT
    )
    ranking = data[0]
    ranking.get_playerrankings = lambda: data[1]  # Use cached list so template avoids DB query
    context['ranking'] = ranking
    context['filter_positions'] = data[2]
    context['filter_schools'] = data[3]
    context['filter_commitments'] = data[4]
    context['filter_states'] = data[5]
    context['recent_articles'] = data[6]
    return render(request, "rankings_detail.html", context)


@subscription_required
def mock_drafts_detail(request, slug):
    context = {}
    data = get_cached(
        f'overslot:mock_draft:{slug}',
        lambda: _ranking_detail_context(slug, is_mock_draft=True),
        RANKING_TIMEOUT
    )
    ranking = data[0]
    ranking.get_playerrankings = lambda: data[1]
    context['ranking'] = ranking
    context['filter_positions'] = data[2]
    context['filter_schools'] = data[3]
    context['filter_commitments'] = data[4]
    context['filter_states'] = data[5]
    context['recent_articles'] = data[6]
    return render(request, "rankings_detail.html", context)


@subscription_required
def players_detail(request, slug):
    context = {}
    context['player'] = get_object_or_404(models.Player, slug=slug, active=True)
    
    # Only show active rankings from published rankings.
    # Ordered: newest year first, regular rankings before mock drafts, mock draft
    # versions descending (e.g. 2026 ranking, then 2026 mock 3.0/2.0/1.0, then 2022 HS ranking).
    context['rankings'] = sorted(
        models.PlayerRanking.objects.filter(
            player=context['player'], ranking__publish=True, active=True
        ).select_related('ranking'),
        key=_player_ranking_sort_key,
    )
    
    # Build charts from PlayerStatSeason across all available stat years (most recent first)
    season_qs = models.PlayerStatSeason.objects.filter(player=context['player']).order_by('-year')
    eligibility = utils.college_stat_eligibility_for_players([context['player'].pk])
    season_qs = [
        s for s in season_qs
        if s.level != "College" or utils.player_accepts_college_season(context['player'], s.year, eligibility)
    ]
    season_charts = []
    for s in season_qs:
        # Hitter payloads
        hitter_payload = None
        hs_statline = None
        hitter_items = []
        if s.level == "High School":
            hs_metric_specs = [
                ("Contact%", s.hs_contact_pct_percentile, s.hs_contact_pct_points_above_median),
                ("Chase%", s.hs_chase_pct_percentile, s.hs_chase_pct_points_above_median),
                ("IZ Contact%", s.hs_iz_contact_pct_percentile, s.hs_iz_contact_pct_points_above_median),
                ("OOZ Contact%", s.hs_ooz_contact_pct_percentile, s.hs_ooz_contact_pct_points_above_median),
                ("K%", s.hs_k_pct_percentile, s.hs_k_pct_points_above_median),
                ("GB%", s.hs_gb_pct_percentile, s.hs_gb_pct_points_above_median),
                ("FB%", s.hs_fb_pct_percentile, s.hs_fb_pct_points_above_median),
                ("Air PULL%", s.hs_air_pull_pct_percentile, s.hs_air_pull_pct_points_above_median),
                ("Sprint Speed", s.hs_sprint_speed_percentile, s.hs_sprint_speed_points_above_median),
                ("Bat Speed", s.hs_bat_speed_percentile, s.hs_bat_speed_points_above_median),
                ("Avg Rot. Acc.", s.hs_avg_rot_acc_percentile, s.hs_avg_rot_acc_points_above_median),
                ("Peak Hand Speed", s.hs_peak_hand_speed_percentile, s.hs_peak_hand_speed_points_above_median),
                ("Explosiveness", s.hs_force_plate_explosiveness_percentile, s.hs_force_plate_explosiveness_points_above_median),
            ]
            for axis, percentile_value, delta_value in hs_metric_specs:
                if percentile_value is not None:
                    normalized = max(0.0, min(1.0, float(percentile_value) / 100.0))
                    try:
                        score_value = None if delta_value is None else float(delta_value)
                    except Exception:
                        score_value = None
                    hitter_items.append({'axis': axis, 'value': normalized, 'score': score_value})
            if hitter_items:
                hitter_payload = json.dumps({'items': hitter_items, 'confidence': s.confidence, 'hs_mode': True})
            # HS statline if present
            stat = {
                'pa': s.hs_pa, 'ba': s.hs_ba, 'obp': s.hs_obp, 'slg': s.hs_slg, 'ops': s.hs_ops, 'iso': s.hs_iso,
            }
            if any(v is not None for v in stat.values()):
                hs_statline = stat
        else:
            # College hitters payload (percentiles 0-100 + raw values)
            metric_specs = [
                ("Whiff %", s.whiff_pct, s.whiff_pct_percentile),
                ("In-Zone Whiff %", s.iz_whiff_pct, s.iz_whiff_pct_percentile),
                ("Out-of-Zone Whiff %", s.ooz_whiff_pct, s.ooz_whiff_pct_percentile),
                ("Chase %", s.chase_pct, s.chase_pct_percentile),
                ("K %", s.k_pct, s.k_pct_percentile),
                ("BB %", s.bb_pct, s.bb_pct_percentile),
                ("Avg Exit Velocity", s.avg_exit_velocity, s.avg_exit_velocity_percentile),
                ("90th % Exit Velocity", s.ev_90th, s.ev_90th_percentile),
                ("Barrel %", s.barrel_pct, s.barrel_pct_percentile),
                ("Pull AIR %", s.pull_air_pct, s.pull_air_pct_percentile),
                ("xWOBA", s.xwoba, s.xwoba_percentile),
            ]
            for axis, raw_value, percentile_value in metric_specs:
                if percentile_value is not None:
                    normalized = max(0.0, min(1.0, float(percentile_value) / 100.0))
                    score_value = None
                    try:
                        score_value = None if raw_value is None else float(raw_value)
                    except Exception:
                        score_value = None
                    hitter_items.append({'axis': axis, 'value': normalized, 'score': score_value})
            if hitter_items:
                hitter_payload = json.dumps({'items': hitter_items, 'confidence': s.confidence})
        
        # Pitcher payload (percentiles already 0-1)
        pitcher_data = {}
        pitcher_movement_data = {}
        if s.fourseam_percentile is not None:
            pitcher_data['fourseam_percentile'] = s.fourseam_percentile
            pitcher_data['fourseam_score'] = s.fourseam_score
            if s.fourseam_vert_break is not None and s.fourseam_horiz_break is not None:
                pitcher_movement_data['fourseam'] = {
                    'vert_break': s.fourseam_vert_break,
                    'horiz_break': s.fourseam_horiz_break
                }
        if s.sinker_percentile is not None:
            pitcher_data['sinker_percentile'] = s.sinker_percentile
            pitcher_data['sinker_score'] = s.sinker_score
            if s.sinker_vert_break is not None and s.sinker_horiz_break is not None:
                pitcher_movement_data['sinker'] = {
                    'vert_break': s.sinker_vert_break,
                    'horiz_break': s.sinker_horiz_break
                }
        if s.slider_percentile is not None:
            pitcher_data['slider_percentile'] = s.slider_percentile
            pitcher_data['slider_score'] = s.slider_score
            if s.slider_vert_break is not None and s.slider_horiz_break is not None:
                pitcher_movement_data['slider'] = {
                    'vert_break': s.slider_vert_break,
                    'horiz_break': s.slider_horiz_break
                }
        if s.sweeper_percentile is not None:
            pitcher_data['sweeper_percentile'] = s.sweeper_percentile
            pitcher_data['sweeper_score'] = s.sweeper_score
            if s.sweeper_vert_break is not None and s.sweeper_horiz_break is not None:
                pitcher_movement_data['sweeper'] = {
                    'vert_break': s.sweeper_vert_break,
                    'horiz_break': s.sweeper_horiz_break
                }
        if s.curveball_percentile is not None:
            pitcher_data['curveball_percentile'] = s.curveball_percentile
            pitcher_data['curveball_score'] = s.curveball_score
            if s.curveball_vert_break is not None and s.curveball_horiz_break is not None:
                pitcher_movement_data['curveball'] = {
                    'vert_break': s.curveball_vert_break,
                    'horiz_break': s.curveball_horiz_break
                }
        if s.changeup_percentile is not None:
            pitcher_data['changeup_percentile'] = s.changeup_percentile
            pitcher_data['changeup_score'] = s.changeup_score
            if s.changeup_vert_break is not None and s.changeup_horiz_break is not None:
                pitcher_movement_data['changeup'] = {
                    'vert_break': s.changeup_vert_break,
                    'horiz_break': s.changeup_horiz_break
                }
        if s.cutter_percentile is not None:
            pitcher_data['cutter_percentile'] = s.cutter_percentile
            pitcher_data['cutter_score'] = s.cutter_score
            if s.cutter_vert_break is not None and s.cutter_horiz_break is not None:
                pitcher_movement_data['cutter'] = {
                    'vert_break': s.cutter_vert_break,
                    'horiz_break': s.cutter_horiz_break
                }
        pitcher_payload = json.dumps({**pitcher_data, 'confidence': s.confidence}) if pitcher_data else None
        pitcher_movement_payload = json.dumps(pitcher_movement_data) if pitcher_movement_data else None
        
        if hitter_payload or pitcher_payload:
            # Determine pitcher handedness for movement chart
            pitcher_handedness = None
            if pitcher_payload and context['player'].throws:
                throws = context['player'].throws.strip().upper()
                if throws == 'L' or throws == 'LHP' or throws.startswith('L'):
                    pitcher_handedness = 'lh'
                elif throws == 'R' or throws == 'RHP' or throws.startswith('R'):
                    pitcher_handedness = 'rh'
            
            season_charts.append({
                'year': s.year,
                'level': s.level,
                'hitter_json': hitter_payload,
                'pitcher_json': pitcher_payload,
                'pitcher_movement_json': pitcher_movement_payload,
                'pitcher_handedness': pitcher_handedness,
                'hs_statline': hs_statline,
                'chart_index': len(season_charts),  # Track original index for chart rendering
            })
    
    # Group pitcher seasons by year for nested tab structure
    pitcher_seasons_by_year = {}
    hitter_seasons = []
    for sc in season_charts:
        if sc.get('pitcher_json'):
            year = sc['year']
            if year not in pitcher_seasons_by_year:
                pitcher_seasons_by_year[year] = []
            pitcher_seasons_by_year[year].append(sc)
        if sc.get('hitter_json'):
            hitter_seasons.append(sc)

    def _stat_year_sort_key(entry):
        try:
            return int(entry['year'])
        except (TypeError, ValueError):
            return 0

    hitter_seasons.sort(key=_stat_year_sort_key, reverse=True)

    context['season_charts'] = season_charts
    context['pitcher_seasons_by_year'] = pitcher_seasons_by_year
    context['hitter_seasons'] = hitter_seasons

    # Only show published articles
    context['articles'] = models.Article.objects.filter(players=context['player'], publish=True, active=True)

    # Stock watch entries (from published stock watch articles)
    context['stock_watch_entries'] = models.StockWatchPlayer.objects.filter(
        player=context['player'],
        active=True,
        stock_watch_article__publish=True,
        stock_watch_article__active=True
    ).select_related('stock_watch_article', 'stock_watch_article__author').order_by('-stock_watch_article__date')

    # Get 643 stats for this player (drop name-collision college seasons on HS prospects)
    stats_643_qs = models.Player643StatSeason.objects.filter(
        player=context['player']
    ).order_by('-year', 'team_name')
    stats_643_ids = [
        s.id for s in stats_643_qs
        if utils.player_accepts_college_season(context['player'], s.year, eligibility)
    ]
    stats_643_qs = stats_643_qs.filter(id__in=stats_643_ids)
    
    # Check if we have any stats with actual data (hitting or pitching)
    # Only count as having hitting stats if player has at least 1 plate appearance
    has_hitting_stats = stats_643_qs.filter(
        hit_plate_appearances__gt=0
    ).exists()
    
    # Only count as having pitching stats if player has at least 1 inning pitched
    has_pitching_stats = stats_643_qs.filter(
        pitch_innings_pitched__gt=0
    ).exists()
    
    context['stats_643'] = stats_643_qs
    context['has_stats_643'] = has_hitting_stats or has_pitching_stats
    context['has_hitting_stats'] = has_hitting_stats
    context['has_pitching_stats'] = has_pitching_stats

    # Draft highlight reel (sheet → PlayerRanking), when embed differs from spotlight video
    hr_raw = context['player'].get_highlight_reel_url()
    hr_embed = (video_embed_url(hr_raw or '') or '').strip()
    spotlight_embed = (video_embed_url(context['player'].video_url or '') or '').strip()
    if hr_embed and spotlight_embed and hr_embed == spotlight_embed:
        hr_embed = ''
    context['highlight_reel_embed_url'] = hr_embed

    return render(request, "players_detail.html", context)

def search(request):
    query = request.GET.get('q', '').strip()
    if len(query) < 2:
        return JsonResponse({
            'articles': [],
            'rankings': [],
            'players': [],
            'teams': []
        })

    # Search articles
    articles = models.Article.objects.filter(
        Q(headline__icontains=query) |
        Q(subhead__icontains=query) |
        Q(blurb__icontains=query) |
        Q(body__icontains=query)
    ).filter(publish=True, active=True)[:5]

    # Search rankings - include rankings that contain matching players, only published
    rankings = models.Ranking.objects.filter(
        Q(headline__icontains=query) |
        Q(subhead__icontains=query) |
        Q(blurb__icontains=query) |
        Q(year__icontains=query) |
        Q(playerranking__player__name__icontains=query, playerranking__player__active=True)
    ).filter(publish=True).distinct()[:5]

    # Search players (only active players)
    players = models.Player.objects.filter(
        Q(name__icontains=query) |
        Q(position__icontains=query) |
        Q(school__icontains=query),
        active=True
    )[:5]

    # Search teams (only active teams with slugs)
    teams = models.Team.objects.filter(
        Q(name__icontains=query) |
        Q(abbreviation__icontains=query),
        active=True,
        slug__isnull=False
    ).exclude(slug='')[:5]

    return JsonResponse({
        'articles': [{
            'headline': article.headline,
            'slug': article.slug,
            'created': template_localtime(article.created).strftime('%b %d, %Y')
        } for article in articles],
        'rankings': [{
            'headline': str(ranking),  # Uses the ranking's __unicode__ method
            'slug': ranking.slug,
            'year': ranking.year,
            'is_mock_draft': ranking.is_mock_draft,
            'preview': next(
                (pr.player.name for pr in ranking.playerranking_set.filter(player__active=True, active=True)
                 if query.lower() in pr.player.name.lower()),
                None
            )
        } for ranking in rankings],
        'players': [{
            'name': player.name,
            'slug': player.slug,
            'position': player.position or '',
            'school': player.school or ''
        } for player in players],
        'teams': [{
            'name': team.name,
            'slug': team.slug or '',
            'ranking': team.current_ranking,
            'abbreviation': team.abbreviation or ''
        } for team in teams]
    })


def robots_txt(request):
    lines = [
        "User-agent: *",
        "Allow: /",
        "Sitemap: https://overslotbaseball.com/sitemap.xml",
    ]
    return HttpResponse("\n".join(lines), content_type="text/plain")


def about_us(request):
    """
    Display the about-us page with authors, their bios, photos, and recent articles.
    Founders are displayed in hero-sized boxes, other authors in card layout.
    """
    from django.db.models import Prefetch
    
    context = {}
    
    # Prefetch published articles for each author
    published_articles = models.Article.objects.filter(
        publish=True, active=True
    ).order_by('-created')
    
    articles_prefetch = Prefetch(
        'articles',
        queryset=published_articles,
        to_attr='recent_articles_prefetch'
    )
    
    # Get all active authors with prefetched articles
    authors_qs = models.Author.objects.filter(active=True).prefetch_related(
        articles_prefetch
    )
    
    # Separate founders from regular authors
    founders = []
    regular_authors = []
    
    for author in authors_qs:
        # Get the 3 most recent articles from prefetched list
        author.recent_articles = getattr(author, 'recent_articles_prefetch', [])[:3]
        
        if author.founder:
            founders.append(author)
        else:
            regular_authors.append(author)
    
    context['founders'] = founders
    context['regular_authors'] = regular_authors
    
    return render(request, "about_us.html", context)


def api_players(request):
    """Return all Player records as JSON or CSV with all fields, including IDs."""
    # API key check via query param against environment variable
    expected_key = os.environ.get('OVERSLOT_API_KEY')
    if not expected_key:
        return JsonResponse({
            'error': 'Server misconfiguration',
            'message': 'OVERSLOT_API_KEY not set'
        }, status=500)

    provided_key = request.GET.get('overslot_api_key')
    if not provided_key or provided_key != expected_key:
        return JsonResponse({
            'error': 'Unauthorized',
            'message': 'Invalid or missing API key.'
        }, status=401)

    # Determine response format via ?format= and Accept header
    format_param = (request.GET.get('format') or '').lower()
    accept_header = request.META.get('HTTP_ACCEPT', '')
    wants_csv = format_param == 'csv' or 'text/csv' in accept_header

    # Concrete model fields only (no relations), including BaseModel fields
    player_model = models.Player
    fields = [f.name for f in player_model._meta.fields]

    queryset = player_model.objects.all()

    if wants_csv:
        response = HttpResponse(content_type='text/csv; charset=utf-8')
        response['Content-Disposition'] = 'attachment; filename="players.csv"'
        writer = csv.writer(response)
        writer.writerow(fields)
        for player in queryset.iterator():
            row = []
            for field_name in fields:
                value = getattr(player, field_name)
                # Normalize boolean/None for CSV readability
                if value is None:
                    row.append('')
                else:
                    row.append(str(value))
            writer.writerow(row)
        return response

    # Default: JSON
    data = []
    for player in queryset.iterator():
        record = {}
        for field_name in fields:
            record[field_name] = getattr(player, field_name)
        data.append(record)

    return JsonResponse(data, safe=False)


@subscription_required
def college_hitters_list(request):
    """
    Render a sortable table of college hitters using percentile metrics from the latest available
    published PlayerRanking per player.
    """
    # New behavior: redirect to the latest available year-specific page
    latest_year = (
        models.PlayerStatSeason.objects.filter(active=True, level="College")
        .values_list("year", flat=True)
        .distinct()
        .order_by("-year")
        .first()
    )
    if latest_year:
        try:
            return redirect("college_hitters_year", year=int(latest_year))
        except Exception:
            # Fallback if year is not numeric; still redirect with string
            return redirect("college_hitters_year", year=latest_year)

    # Define columns: key -> (field on PlayerRanking, display label)
    columns = [
        ("whiff_pct_percentile", "Whiff %"),
        ("iz_whiff_pct_percentile", "IZ Whiff %"),
        ("ooz_whiff_pct_percentile", "OOZ Whiff %"),
        ("chase_pct_percentile", "Chase %"),
        ("k_pct_percentile", "K %"),
        ("bb_pct_percentile", "BB %"),
        ("avg_exit_velocity_percentile", "Avg EV"),
        ("ev_90th_percentile", "90th % EV"),
        ("barrel_pct_percentile", "Barrel %"),
        ("pull_air_pct_percentile", "Pull AIR %"),
        ("xwoba_percentile", "xwOBA"),
    ]

    # Base queryset: published college rankings, players active, with at least one college hitter percentile present
    percentile_fields = [c[0] for c in columns]
    any_percentile_q = Q()
    for f in percentile_fields:
        any_percentile_q |= Q(**{f"{f}__isnull": False})
    pr_qs = models.PlayerRanking.objects.filter(
        ranking__publish=True,
        active=True,
        player__active=True,
        level="College",
    ).filter(any_percentile_q).select_related("player", "ranking").order_by("-ranking__year", "-created")

    # Pick latest per player
    latest_by_player = {}
    for pr in pr_qs:
        pid = pr.player_id
        if pid not in latest_by_player:
            latest_by_player[pid] = pr

    rows = []
    for pr in latest_by_player.values():
        row = {
            "player_name": pr.player.name,
            "player_slug": pr.player.slug,
            "school": pr.school,
        }
        for key, _label in columns:
            row[key] = getattr(pr, key)
        rows.append(row)

    context = {
        "page_title": "College Hitters",
        "columns": columns,
        "rows": rows,
        "is_college": True,
    }
    return TemplateResponse(request, "hitters_list.html", context)


@subscription_required
def hs_hitters_list(request):
    """
    Render a sortable table of high school hitters using percentile metrics from the latest available
    published PlayerRanking per player.
    """
    # New behavior: redirect to the latest available year-specific page
    latest_year = (
        models.PlayerStatSeason.objects.filter(active=True, level="High School")
        .values_list("year", flat=True)
        .distinct()
        .order_by("-year")
        .first()
    )
    if latest_year:
        try:
            return redirect("hs_hitters_year", year=int(latest_year))
        except Exception:
            return redirect("hs_hitters_year", year=latest_year)

    columns = [
        ("hs_contact_pct_percentile", "Contact%"),
        ("hs_chase_pct_percentile", "Chase%"),
        ("hs_iz_contact_pct_percentile", "IZ Contact%"),
        ("hs_ooz_contact_pct_percentile", "OOZ Contact%"),
        ("hs_k_pct_percentile", "K%"),
        ("hs_gb_pct_percentile", "GB%"),
        ("hs_fb_pct_percentile", "FB%"),
        ("hs_air_pull_pct_percentile", "AIR Pull%"),
        ("hs_sprint_speed_percentile", "Sprint"),
        ("hs_bat_speed_percentile", "Bat Speed"),
        ("hs_avg_rot_acc_percentile", "Avg Rot Acc"),
        ("hs_peak_hand_speed_percentile", "Peak Hand"),
        ("hs_force_plate_explosiveness_percentile", "Explosive"),
    ]
    # Append baseball-card style raw stats when available (not used to filter presence)
    columns += [
        ("hs_pa", "PA"),
        ("hs_ba", "BA"),
        ("hs_obp", "OBP"),
        ("hs_slg", "SLG"),
        ("hs_ops", "OPS"),
        ("hs_iso", "ISO"),
    ]

    # Only percentile fields are used to decide whether a row should appear
    percentile_fields = [
        "hs_contact_pct_percentile",
        "hs_chase_pct_percentile",
        "hs_iz_contact_pct_percentile",
        "hs_ooz_contact_pct_percentile",
        "hs_k_pct_percentile",
        "hs_gb_pct_percentile",
        "hs_fb_pct_percentile",
        "hs_air_pull_pct_percentile",
        "hs_sprint_speed_percentile",
        "hs_bat_speed_percentile",
        "hs_avg_rot_acc_percentile",
        "hs_peak_hand_speed_percentile",
        "hs_force_plate_explosiveness_percentile",
    ]
    any_percentile_q = Q()
    for f in percentile_fields:
        any_percentile_q |= Q(**{f"{f}__isnull": False})
    pr_qs = models.PlayerRanking.objects.filter(
        ranking__publish=True,
        active=True,
        player__active=True,
        level="High School",
    ).filter(any_percentile_q).select_related("player", "ranking").order_by("-ranking__year", "-created")

    latest_by_player = {}
    for pr in pr_qs:
        pid = pr.player_id
        if pid not in latest_by_player:
            latest_by_player[pid] = pr

    rows = []
    for pr in latest_by_player.values():
        row = {
            "player_name": pr.player.name,
            "player_slug": pr.player.slug,
            "school": pr.school,
        }
        for key, _label in columns:
            row[key] = getattr(pr, key)
        rows.append(row)

    context = {
        "page_title": "High School Hitters",
        "columns": columns,
        "rows": rows,
        "is_college": False,
    }
    return TemplateResponse(request, "hitters_list.html", context)


@subscription_required
def college_hitters_year(request, year: int):
    """
    Year-specific table for college hitters based on PlayerStatSeason.
    """
    # Normalize year to string for filtering against CharField
    year_str = str(year)

    columns = [
        ("whiff_pct_percentile", "Whiff%"),
        ("iz_whiff_pct_percentile", "IZ Whiff%"),
        ("ooz_whiff_pct_percentile", "OOZ Whiff%"),
        ("chase_pct_percentile", "Chase%"),
        ("k_pct_percentile", "K%"),
        ("bb_pct_percentile", "BB%"),
        ("avg_exit_velocity_percentile", "Avg EV"),
        ("ev_90th_percentile", "90th EV"),
        ("barrel_pct_percentile", "Barrel%"),
        ("pull_air_pct_percentile", "Pull AIR%"),
        ("xwoba_percentile", "xWOBA"),
    ]

    seasons = (
        models.PlayerStatSeason.objects.filter(
            active=True, level="College", year=year_str, player__active=True
        )
        .select_related("player")
    )

    # 404 if no data for the requested year
    if not seasons.exists():
        return get_object_or_404(models.PlayerStatSeason, level="College", year=year_str)  # raises 404

    seasons = utils.filter_plausible_college_seasons(seasons)

    # Hard-coded year navigation lists (stable; data changes infrequently)
    college_years = [2026, 2025, 2024]
    hs_years = [2025, 2024, 2023, 2022]

    rows = []
    for s in seasons:
        row = {
            "player_name": s.player.name,
            "player_slug": s.player.slug,
            "school": s.school,  # Use school from PlayerStatSeason, not Player
            "draft_year": s.draft_year,
        }
        for key, _label in columns:
            row[key] = getattr(s, key)
        rows.append(row)
    
    # Filter out rows with no percentile data (all percentile values are null)
    percentile_keys = [key for key, _label in columns if key.endswith("_percentile")]
    rows = [
        row for row in rows
        if any(row.get(key) is not None for key in percentile_keys)
    ]
    
    # Sort by last name (last word in player name)
    def get_last_name(row):
        name = row.get("player_name", "").strip()
        if not name:
            return ""
        parts = name.split()
        return parts[-1].lower() if parts else ""
    
    rows.sort(key=get_last_name)

    context = {
        "page_title": f"College Hitters {year_str}",
        "columns": columns,
        "rows": rows,
        "is_college": True,
        "year": int(year) if str(year).isdigit() else year_str,
        "college_years": college_years,
        "hs_years": hs_years,
    }
    return TemplateResponse(request, "hitters_list.html", context)


@subscription_required
def hs_hitters_year(request, year: int):
    """
    Year-specific table for high school hitters based on PlayerStatSeason.
    """
    year_str = str(year)

    columns = [
        ("hs_contact_pct_percentile", "Contact%"),
        ("hs_chase_pct_percentile", "Chase%"),
        ("hs_iz_contact_pct_percentile", "IZ Contact%"),
        ("hs_ooz_contact_pct_percentile", "OOZ Contact%"),
        ("hs_k_pct_percentile", "K%"),
        ("hs_gb_pct_percentile", "GB%"),
        ("hs_fb_pct_percentile", "FB%"),
        ("hs_air_pull_pct_percentile", "Air PULL%"),
        ("hs_sprint_speed_percentile", "Sprint Speed"),
        ("hs_bat_speed_percentile", "Bat Speed"),
        ("hs_avg_rot_acc_percentile", "Avg Rot. Acc."),
        ("hs_peak_hand_speed_percentile", "Peak Hand Speed"),
        ("hs_force_plate_explosiveness_percentile", "Explosive"),
    ]
    # Include statline columns at end
    columns += [
        ("hs_pa", "PA"),
        ("hs_ba", "BA"),
        ("hs_obp", "OBP"),
        ("hs_slg", "SLG"),
        ("hs_ops", "OPS"),
        ("hs_iso", "ISO"),
    ]

    seasons = (
        models.PlayerStatSeason.objects.filter(
            active=True, level="High School", year=year_str, player__active=True
        )
        .select_related("player")
    )

    if not seasons.exists():
        return get_object_or_404(models.PlayerStatSeason, level="High School", year=year_str)  # raises 404

    # Hard-coded year navigation lists (stable; data changes infrequently)
    college_years = [2026, 2025, 2024]
    hs_years = [2025, 2024, 2023, 2022]

    rows = []
    for s in seasons:
        row = {
            "player_name": s.player.name,
            "player_slug": s.player.slug,
            "school": s.school,  # Use school from PlayerStatSeason, not Player
            "draft_year": s.draft_year,
        }
        for key, _label in columns:
            row[key] = getattr(s, key)
        rows.append(row)
    
    # Filter out rows with no percentile data (all percentile values are null)
    percentile_keys = [key for key, _label in columns if key.endswith("_percentile")]
    rows = [
        row for row in rows
        if any(row.get(key) is not None for key in percentile_keys)
    ]
    
    # Sort by last name (last word in player name)
    def get_last_name(row):
        name = row.get("player_name", "").strip()
        if not name:
            return ""
        parts = name.split()
        return parts[-1].lower() if parts else ""
    
    rows.sort(key=get_last_name)

    context = {
        "page_title": f"High School Hitters {year_str}",
        "columns": columns,
        "rows": rows,
        "is_college": False,
        "year": int(year) if str(year).isdigit() else year_str,
        "college_years": college_years,
        "hs_years": hs_years,
    }
    return TemplateResponse(request, "hitters_list.html", context)


@subscription_required
def stats_list(request):
    """
    Redirect to the latest available year-specific stats page (hitting stats).
    """
    latest_year = (
        models.Player643StatSeason.objects.filter(
            active=True, player__active=True, hit_plate_appearances__gt=0
        )
        .values_list("year", flat=True)
        .distinct()
        .order_by("-year")
        .first()
    )
    if latest_year:
        try:
            return redirect("stats_hit_year", year=int(latest_year))
        except Exception:
            return redirect("stats_hit_year", year=latest_year)
    # If no data, show empty page
    return redirect("stats_hit_year", year=2025)


@subscription_required
def stats_hit_year(request, year: int):
    """
    Year-specific table for hitting stats from Player643StatSeason.
    """
    year_str = str(year)

    columns = [
        ("hit_games_played", "G"),
        ("hit_plate_appearances", "PA"),
        ("hit_hits", "H"),
        ("hit_singles", "1B"),
        ("hit_doubles", "2B"),
        ("hit_triples", "3B"),
        ("hit_hrs", "HR"),
        ("hit_runs", "R"),
        ("hit_base_on_balls", "BB"),
        ("hit_strikeouts", "SO"),
        ("hit_hit_by_pitch", "HBP"),
        ("hit_stolen_bases", "SB"),
        ("hit_caught_stealing", "CS"),
        ("hit_ba", "BA"),
        ("hit_obp", "OBP"),
        ("hit_slg", "SLG"),
        ("hit_ops", "OPS"),
        ("hit_iso", "ISO"),
        ("hit_babip", "BABIP"),
        ("hit_walk_rate", "BB%"),
        ("hit_strikeout_rate", "K%"),
        ("hit_walk_to_strikeout", "BB/K"),
        ("hit_woba", "wOBA"),
    ]

    seasons = (
        models.Player643StatSeason.objects.filter(
            active=True, year=year_str, player__active=True, hit_plate_appearances__gt=0
        )
        .select_related("player")
        .order_by("-hit_woba", "player__name")
    )

    # 404 if no data for the requested year
    if not seasons.exists():
        return get_object_or_404(models.Player643StatSeason, year=year_str, hit_plate_appearances__gt=0)

    seasons = utils.filter_plausible_college_seasons(seasons)

    # Get available years from the database
    available_years = (
        models.Player643StatSeason.objects.filter(
            active=True, player__active=True
        )
        .values_list("year", flat=True)
        .distinct()
        .order_by("-year")
    )
    # Convert to integers where possible, keep as strings otherwise
    years_list = []
    for y in available_years:
        try:
            years_list.append(int(y))
        except (ValueError, TypeError):
            continue
    years_list = sorted(set(years_list), reverse=True)

    rows = []
    for s in seasons:
        row = {
            "player_name": s.player.name,
            "player_slug": s.player.slug,
            "team_name": s.team_name or "",
            "qualified": s.hit_plate_appearances and s.hit_plate_appearances >= 100,
        }
        for key, _label in columns:
            row[key] = getattr(s, key)
        rows.append(row)

    # Already sorted by queryset (wOBA descending, then player name)
    
    # Determine if this is the current season (2026) - don't enforce qualified for current season
    current_season = 2026
    is_current_season = False
    try:
        year_int = int(year_str)
        is_current_season = year_int == current_season
    except (ValueError, TypeError):
        pass

    context = {
        "page_title": f"Hitting Stats {year_str}",
        "columns": columns,
        "rows": rows,
        "stat_type": "hit",
        "year": int(year) if str(year).isdigit() else year_str,
        "years": years_list,
        "qualification_threshold": 100,
        "qualification_field": "PA",
        "enforce_qualified": not is_current_season,  # Only enforce for past years
    }
    return TemplateResponse(request, "stats_list.html", context)


@subscription_required
def stats_pitch_year(request, year: int):
    """
    Year-specific table for pitching stats from Player643StatSeason.
    """
    year_str = str(year)

    columns = [
        ("pitch_appearances", "G"),
        ("pitch_games_started", "GS"),
        ("pitch_innings_pitched", "IP"),
        ("pitch_batters_faced", "BF"),
        ("pitch_hits", "H"),
        ("pitch_runs", "R"),
        ("pitch_base_on_balls", "BB"),
        ("pitch_strikeouts", "SO"),
        ("pitch_hit_by_pitch", "HBP"),
        ("pitch_whip", "WHIP"),
        ("pitch_ba", "BA"),
        ("pitch_obp", "OBP"),
        ("pitch_slg", "SLG"),
        ("pitch_ops", "OPS"),
        ("pitch_babip", "BABIP"),
        ("pitch_walk_rate", "BB%"),
        ("pitch_strikeout_rate", "K%"),
        ("pitch_walk_to_strikeout", "BB/K"),
        ("pitch_fip", "FIP"),
        ("pitch_xfip", "xFIP"),
        ("pitch_siera", "SIERA"),
    ]

    seasons = (
        models.Player643StatSeason.objects.filter(
            active=True, year=year_str, player__active=True, pitch_innings_pitched__gt=0
        )
        .select_related("player")
        .order_by("pitch_siera", "player__name")  # Sort by SIERA ascending (lower is better)
    )

    # 404 if no data for the requested year
    if not seasons.exists():
        return get_object_or_404(models.Player643StatSeason, year=year_str, pitch_innings_pitched__gt=0)

    seasons = utils.filter_plausible_college_seasons(seasons)

    # Get available years from the database
    available_years = (
        models.Player643StatSeason.objects.filter(
            active=True, player__active=True
        )
        .values_list("year", flat=True)
        .distinct()
        .order_by("-year")
    )
    # Convert to integers where possible, keep as strings otherwise
    years_list = []
    for y in available_years:
        try:
            years_list.append(int(y))
        except (ValueError, TypeError):
            continue
    years_list = sorted(set(years_list), reverse=True)

    rows = []
    for s in seasons:
        row = {
            "player_name": s.player.name,
            "player_slug": s.player.slug,
            "team_name": s.team_name or "",
            "qualified": s.pitch_innings_pitched and s.pitch_innings_pitched >= 20,
        }
        for key, _label in columns:
            row[key] = getattr(s, key)
        rows.append(row)

    # Already sorted by queryset (SIERA ascending, then player name)
    
    # Determine if this is the current season (2026) - don't enforce qualified for current season
    current_season = 2026
    is_current_season = False
    try:
        year_int = int(year_str)
        is_current_season = year_int == current_season
    except (ValueError, TypeError):
        pass

    context = {
        "page_title": f"Pitching Stats {year_str}",
        "columns": columns,
        "rows": rows,
        "stat_type": "pitch",
        "year": int(year) if str(year).isdigit() else year_str,
        "years": years_list,
        "qualification_threshold": 20,
        "qualification_field": "IP",
        "enforce_qualified": not is_current_season,  # Only enforce for past years
    }
    return TemplateResponse(request, "stats_list.html", context)
