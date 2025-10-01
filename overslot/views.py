import csv
import os
import datetime
import itertools
from django.http import HttpResponse
from django.views.decorators.csrf import csrf_exempt
from django.shortcuts import render, get_object_or_404
from django.db.models import Count, Avg, Sum, Max, Min, Q, Case, When, Value, IntegerField
from django.core.paginator import EmptyPage, PageNotAnInteger, Paginator
from django.http import JsonResponse
from django.conf import settings
from django.contrib.auth.decorators import login_required
from decimal import *
from django.utils.timezone import template_localtime
import json

from overslot import models, utils
from overslot.decorators import subscription_required

def index(request):
    context = {}
    # Smaller hero: show a few latest carousel items (articles + rankings)
    latest_articles_qs = models.Article.objects.filter(
        publish=True, is_carousel=True
    ).prefetch_related('authors')
    latest_articles = latest_articles_qs.order_by('-created')[:5]
    for article in latest_articles:
        article.active_players = article.players.filter(active=True)
    context['latest_articles'] = latest_articles

    latest_rankings = models.Ranking.objects.filter(
        publish=True, is_carousel=True
    ).annotate(
        level_order=Case(
            When(draft_level='Overall', then=Value(0)),
            When(draft_level='College', then=Value(1)),
            When(draft_level='High School', then=Value(2)),
            default=Value(99),
            output_field=IntegerField(),
        )
    ).order_by('-created')[:5]
    context['latest_rankings'] = latest_rankings

    # Flanking lists: left = scouting articles; right = non-scouting
    scouting_articles = models.Article.objects.filter(
        publish=True, article_type='scouting'
    ).prefetch_related('authors').order_by('-created')[:3]
    for a in scouting_articles:
        a.active_players = a.players.filter(active=True)
    context['scouting_articles'] = scouting_articles

    non_scouting_articles = models.Article.objects.filter(
        publish=True
    ).exclude(article_type='scouting').prefetch_related('authors').order_by('-created')[:3]
    for a in non_scouting_articles:
        a.active_players = a.players.filter(active=True)
    context['non_scouting_articles'] = non_scouting_articles

    # Rankings grid below: split into current (ordered by year ascending) and archived
    context['current_rankings'] = models.Ranking.objects.filter(
        is_mock_draft=False, publish=True, current=True
    ).annotate(
        level_order=Case(
            When(draft_level='Overall', then=Value(0)),
            When(draft_level='College', then=Value(1)),
            When(draft_level='High School', then=Value(2)),
            default=Value(99),
            output_field=IntegerField(),
        )
    ).order_by('year', 'level_order')
    context['archived_rankings'] = models.Ranking.objects.filter(
        is_mock_draft=False, publish=True, current=False
    ).annotate(
        level_order=Case(
            When(draft_level='Overall', then=Value(0)),
            When(draft_level='College', then=Value(1)),
            When(draft_level='High School', then=Value(2)),
            default=Value(99),
            output_field=IntegerField(),
        )
    ).order_by('-year', 'level_order')
    context['rankings_count'] = models.Ranking.objects.filter(
        is_mock_draft=False, publish=True
    ).count()

    # Player videos sidebar: active players with a video_url
    videos_qs = models.Player.objects.filter(
        active=True
    ).exclude(video_url__isnull=True).exclude(video_url="")\
     .exclude(photo_url__isnull=True).exclude(photo_url="")
    # Randomize selection for spotlight interviews
    context['player_videos'] = videos_qs.order_by('?')[:9]
    context['videos_count'] = videos_qs.count()

    # Podcast belt: top 5, prioritize featured then newest
    context['latest_podcasts'] = models.PodcastEpisode.objects.filter(
        publish=True
    ).order_by('-featured', '-published_at')[:5]

    return render(request, "index.html", context)

def articles_list(request):
    context = {}
    # Only show published articles
    articles = models.Article.objects.filter(publish=True)
    
    # Add active players to each article
    for article in articles:
        article.active_players = article.players.filter(active=True)
    context['articles'] = articles
    
    # Add recent rankings for sidebar - only published
    context['recent_rankings'] = models.Ranking.objects.filter(active=True, publish=True).order_by('-created')[:3]

    return render(request, "articles_list.html", context)


@subscription_required
def articles_detail(request, slug):
    context = {}
    # Only allow access to published articles
    context['article'] = get_object_or_404(models.Article, slug=slug, publish=True)
    
    # Filter out inactive players from the article
    context['article'].active_players = context['article'].players.filter(active=True)

    return render(request, "articles_detail.html", context)


def rankings_list(request):
    context = {}
    # Only show published rankings - show current first (ascending by year), then archived
    current_qs = models.Ranking.objects.filter(is_mock_draft=False, publish=True, current=True).annotate(
        level_order=Case(
            When(draft_level='Overall', then=Value(0)),
            When(draft_level='College', then=Value(1)),
            When(draft_level='High School', then=Value(2)),
            default=Value(99),
            output_field=IntegerField(),
        )
    ).order_by('year', 'level_order')
    archived_qs = models.Ranking.objects.filter(is_mock_draft=False, publish=True, current=False).annotate(
        level_order=Case(
            When(draft_level='Overall', then=Value(0)),
            When(draft_level='College', then=Value(1)),
            When(draft_level='High School', then=Value(2)),
            default=Value(99),
            output_field=IntegerField(),
        )
    ).order_by('-year', 'level_order')
    context['rankings'] = list(current_qs) + list(archived_qs)

    return render(request, "rankings_list.html", context)


def mock_drafts_list(request):
    context = {}
    # Only show published mock drafts
    context['rankings'] = models.Ranking.objects.filter(is_mock_draft=True, publish=True)

    return render(request, "rankings_list.html", context)


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

@subscription_required
def rankings_detail(request, slug):
    context = {}
    # Only allow access to published rankings
    ranking = get_object_or_404(models.Ranking, slug=slug, publish=True, is_mock_draft=False)
    context['ranking'] = ranking
    
    # Get all player rankings for this ranking
    player_rankings = ranking.get_playerrankings()
    
    # Get unique values for filters (sorted alphabetically)
    schools = sorted([pr.school for pr in player_rankings if pr.school])
    commitments = sorted([pr.commitment for pr in player_rankings if pr.commitment])
    states = sorted([pr.player.state for pr in player_rankings if pr.player.state])
    
    # Remove duplicates while preserving order
    schools = list(dict.fromkeys(schools))
    commitments = list(dict.fromkeys(commitments))
    states = list(dict.fromkeys(states))
    
    # Create simplified position categories in baseball positional order
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
    
    # Find which simplified positions are actually present in the data
    all_positions = [pr.position for pr in player_rankings if pr.position]
    positions = []
    
    for simple_pos, variants in position_mapping:
        # Check if any player has a position that contains any of the variants
        for player_pos in all_positions:
            if any(variant in player_pos.upper() for variant in variants):
                if simple_pos not in positions:
                    positions.append(simple_pos)
                break
    
    context['filter_positions'] = positions
    context['filter_schools'] = schools
    context['filter_commitments'] = commitments
    context['filter_states'] = states
    
    # Add recent articles for sidebar - only published
    context['recent_articles'] = models.Article.objects.filter(publish=True).order_by('-created')[:5]

    return render(request, "rankings_detail.html", context)


@subscription_required
def mock_drafts_detail(request, slug):
    context = {}
    # Only allow access to published mock drafts
    ranking = get_object_or_404(models.Ranking, slug=slug, publish=True, is_mock_draft=True)
    context['ranking'] = ranking
    
    # Get all player rankings for this mock draft
    player_rankings = ranking.get_playerrankings()
    
    # Get unique values for filters (sorted alphabetically)
    schools = sorted([pr.school for pr in player_rankings if pr.school])
    commitments = sorted([pr.commitment for pr in player_rankings if pr.commitment])
    states = sorted([pr.player.state for pr in player_rankings if pr.player.state])
    
    # Remove duplicates while preserving order
    schools = list(dict.fromkeys(schools))
    commitments = list(dict.fromkeys(commitments))
    states = list(dict.fromkeys(states))
    
    # Create simplified position categories in baseball positional order
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
    
    # Find which simplified positions are actually present in the data
    all_positions = [pr.position for pr in player_rankings if pr.position]
    positions = []
    
    for simple_pos, variants in position_mapping:
        # Check if any player has a position that contains any of the variants
        for player_pos in all_positions:
            if any(variant in player_pos.upper() for variant in variants):
                if simple_pos not in positions:
                    positions.append(simple_pos)
                break
    
    context['filter_positions'] = positions
    context['filter_schools'] = schools
    context['filter_commitments'] = commitments
    context['filter_states'] = states
    
    # Add recent articles for sidebar - only published
    context['recent_articles'] = models.Article.objects.filter(publish=True).order_by('-created')[:5]

    return render(request, "rankings_detail.html", context)


@subscription_required
def players_detail(request, slug):
    context = {}
    context['player'] = get_object_or_404(models.Player, slug=slug, active=True)
    
    # Only show active rankings from published rankings
    context['rankings'] = models.PlayerRanking.objects.filter(player=context['player'], ranking__publish=True, active=True)
    
    # Prefer the latest non-mock ranking for chart data (mock drafts don't carry metrics)
    rankings_qs = context['rankings']
    latest_ranking = rankings_qs.filter(ranking__is_mock_draft=False).order_by('-ranking__year', '-created').first() or \
                     rankings_qs.order_by('-ranking__year', '-created').first()
    
    if latest_ranking:
        # Build hitter metric chart data from new fields (percentiles drive bars; raw values shown on right)
        hitter_items = []
        metric_specs = [
            ("Whiff %", latest_ranking.whiff_pct, latest_ranking.whiff_pct_percentile),
            ("In-Zone Whiff %", latest_ranking.iz_whiff_pct, latest_ranking.iz_whiff_pct_percentile),
            ("Out-of-Zone Whiff %", latest_ranking.ooz_whiff_pct, latest_ranking.ooz_whiff_pct_percentile),
            ("Chase %", latest_ranking.chase_pct, latest_ranking.chase_pct_percentile),
            ("K %", latest_ranking.k_pct, latest_ranking.k_pct_percentile),
            ("BB %", latest_ranking.bb_pct, latest_ranking.bb_pct_percentile),
            ("Avg Exit Velocity", latest_ranking.avg_exit_velocity, latest_ranking.avg_exit_velocity_percentile),
            ("90th % Exit Velocity", latest_ranking.ev_90th, latest_ranking.ev_90th_percentile),
            ("Barrel %", latest_ranking.barrel_pct, latest_ranking.barrel_pct_percentile),
            ("Pull AIR %", latest_ranking.pull_air_pct, latest_ranking.pull_air_pct_percentile),
            ("xWOBA", latest_ranking.xwoba, latest_ranking.xwoba_percentile),
        ]
        for axis, raw_value, percentile_value in metric_specs:
            if percentile_value is not None and raw_value is not None:
                # Percentiles were stored as 0-100; normalize to 0-1 for charting
                normalized = max(0.0, min(1.0, float(percentile_value) / 100.0))
                try:
                    score_value = float(raw_value)
                except Exception:
                    score_value = None
                hitter_items.append({
                    'axis': axis,
                    'value': normalized,
                    'score': score_value,
                })
        context['hitter_metric_chart_data'] = json.dumps({
            'items': hitter_items,
            'confidence': latest_ranking.confidence,
        }) if hitter_items else None

        # Pitcher chart data - only include pitches where data exists
        pitcher_data = {}
        if latest_ranking.fourseam_percentile is not None:
            pitcher_data['fourseam_percentile'] = latest_ranking.fourseam_percentile
            pitcher_data['fourseam_score'] = latest_ranking.fourseam_score
        if latest_ranking.sinker_percentile is not None:
            pitcher_data['sinker_percentile'] = latest_ranking.sinker_percentile
            pitcher_data['sinker_score'] = latest_ranking.sinker_score
        if latest_ranking.slider_percentile is not None:
            pitcher_data['slider_percentile'] = latest_ranking.slider_percentile
            pitcher_data['slider_score'] = latest_ranking.slider_score
        if latest_ranking.sweeper_percentile is not None:
            pitcher_data['sweeper_percentile'] = latest_ranking.sweeper_percentile
            pitcher_data['sweeper_score'] = latest_ranking.sweeper_score
        if latest_ranking.curveball_percentile is not None:
            pitcher_data['curveball_percentile'] = latest_ranking.curveball_percentile
            pitcher_data['curveball_score'] = latest_ranking.curveball_score
        if latest_ranking.changeup_percentile is not None:
            pitcher_data['changeup_percentile'] = latest_ranking.changeup_percentile
            pitcher_data['changeup_score'] = latest_ranking.changeup_score
        
        if pitcher_data:
            pitcher_data['confidence'] = latest_ranking.confidence
            context['pitcher_chart_data'] = json.dumps(pitcher_data)
        else:
            context['pitcher_chart_data'] = None

    # Only show published articles
    context['articles'] = models.Article.objects.filter(players=context['player'], publish=True)

    return render(request, "players_detail.html", context)

def search(request):
    query = request.GET.get('q', '').strip()
    if len(query) < 2:
        return JsonResponse({
            'articles': [],
            'rankings': [],
            'players': []
        })

    # Search articles
    articles = models.Article.objects.filter(
        Q(headline__icontains=query) |
        Q(subhead__icontains=query) |
        Q(blurb__icontains=query) |
        Q(body__icontains=query)
    ).filter(publish=True)[:5]

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
            'position': player.position,
            'school': player.school
        } for player in players]
    })


def robots_txt(request):
    lines = [
        "User-agent: *",
        "Allow: /",
        "Sitemap: https://overslotbaseball.com/sitemap.xml",
    ]
    return HttpResponse("\n".join(lines), content_type="text/plain")


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
