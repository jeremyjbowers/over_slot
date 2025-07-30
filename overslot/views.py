import csv
import datetime
import itertools
from django.http import HttpResponse
from django.views.decorators.csrf import csrf_exempt
from django.shortcuts import render, get_object_or_404
from django.db.models import Count, Avg, Sum, Max, Min, Q
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
    # Carousel content - show unpublished articles only to staff users
    if request.user.is_staff:
        carousel_articles = models.Article.objects.filter(is_carousel=True)
        latest_articles = models.Article.objects.filter(is_carousel=True).order_by('-created')[:2]
    else:
        carousel_articles = models.Article.objects.filter(publish=True, is_carousel=True)
        latest_articles = models.Article.objects.filter(publish=True, is_carousel=True).order_by('-created')[:2]
    
    # Add active players to carousel articles
    for article in carousel_articles:
        article.active_players = article.players.filter(active=True)
    
    # Add active players to latest articles
    for article in latest_articles:
        article.active_players = article.players.filter(active=True)
    context['latest_articles'] = latest_articles
    
    # Carousel rankings - show unpublished rankings only to staff users
    if request.user.is_staff:
        carousel_rankings = models.Ranking.objects.filter(is_mock_draft=False, is_carousel=True)
        context['latest_ranking'] = models.Ranking.objects.filter(active=True, is_mock_draft=False, is_carousel=True).order_by('-created').first()
    else:
        carousel_rankings = models.Ranking.objects.filter(is_mock_draft=False, publish=True, is_carousel=True)
        context['latest_ranking'] = models.Ranking.objects.filter(active=True, is_mock_draft=False, publish=True, is_carousel=True).order_by('-created').first()
    
    # Content lists below carousel - last 10 regardless of carousel flag
    if request.user.is_staff:
        context['articles'] = models.Article.objects.all().order_by('-created')[:10]
        context['rankings'] = models.Ranking.objects.filter(is_mock_draft=False).order_by('-created')[:10]
    else:
        context['articles'] = models.Article.objects.filter(publish=True).order_by('-created')[:10]
        context['rankings'] = models.Ranking.objects.filter(is_mock_draft=False, publish=True).order_by('-created')[:10]
    
    # Add active players to content articles
    for article in context['articles']:
        article.active_players = article.players.filter(active=True)

    return render(request, "index.html", context)

def articles_list(request):
    context = {}
    # Show unpublished articles only to staff users
    if request.user.is_staff:
        articles = models.Article.objects.all()
    else:
        articles = models.Article.objects.filter(publish=True)
    
    # Add active players to each article
    for article in articles:
        article.active_players = article.players.filter(active=True)
    context['articles'] = articles
    
    # Add recent rankings for sidebar - show drafts to staff
    if request.user.is_staff:
        context['recent_rankings'] = models.Ranking.objects.filter(active=True).order_by('-created')[:3]
    else:
        context['recent_rankings'] = models.Ranking.objects.filter(active=True, publish=True).order_by('-created')[:3]

    return render(request, "articles_list.html", context)


@subscription_required
def articles_detail(request, slug):
    context = {}
    # Non-staff users can only access published articles
    if request.user.is_staff:
        context['article'] = get_object_or_404(models.Article, slug=slug)
    else:
        context['article'] = get_object_or_404(models.Article, slug=slug, publish=True)
    
    # Filter out inactive players from the article
    context['article'].active_players = context['article'].players.filter(active=True)

    return render(request, "articles_detail.html", context)


def rankings_list(request):
    context = {}
    # Show unpublished rankings only to staff users
    if request.user.is_staff:
        context['rankings'] = models.Ranking.objects.filter(is_mock_draft=False)
    else:
        context['rankings'] = models.Ranking.objects.filter(is_mock_draft=False, publish=True)

    return render(request, "rankings_list.html", context)


def mock_drafts_list(request):
    context = {}
    # Show unpublished mock drafts only to staff users
    if request.user.is_staff:
        context['rankings'] = models.Ranking.objects.filter(is_mock_draft=True)
    else:
        context['rankings'] = models.Ranking.objects.filter(is_mock_draft=True, publish=True)

    return render(request, "rankings_list.html", context)


@subscription_required
def rankings_detail(request, slug):
    context = {}
    # Non-staff users can only access published rankings
    if request.user.is_staff:
        ranking = get_object_or_404(models.Ranking, slug=slug)
    else:
        ranking = get_object_or_404(models.Ranking, slug=slug, publish=True)
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
    
    # Add recent articles for sidebar - show drafts to staff
    if request.user.is_staff:
        context['recent_articles'] = models.Article.objects.all().order_by('-created')[:5]
    else:
        context['recent_articles'] = models.Article.objects.filter(publish=True).order_by('-created')[:5]

    return render(request, "rankings_detail.html", context)


@subscription_required
def players_detail(request, slug):
    context = {}
    context['player'] = get_object_or_404(models.Player, slug=slug, active=True)
    context['rankings'] = models.PlayerRanking.objects.filter(player=context['player'])
    
    latest_ranking = context['rankings'].order_by('-ranking__year', '-created').first()
    
    if latest_ranking:
        context['radar_chart_data'] = json.dumps({
            'hitter_percentile': latest_ranking.hitter_percentile,
            'game_power_percentile': latest_ranking.game_power_percentile,
            'raw_power_percentile': latest_ranking.raw_power_percentile,
            'approach_percentile': latest_ranking.approach_percentile,
            'confidence': latest_ranking.confidence
        })
        if latest_ranking.hitter_percentile is None or latest_ranking.game_power_percentile is None or latest_ranking.raw_power_percentile is None or latest_ranking.approach_percentile is None:
            context['radar_chart_data'] = None

    # Show unpublished articles only to staff users
    if request.user.is_staff:
        context['articles'] = models.Article.objects.filter(players=context['player'])
    else:
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

    # Search rankings - include rankings that contain matching players
    rankings = models.Ranking.objects.filter(
        Q(headline__icontains=query) |
        Q(subhead__icontains=query) |
        Q(blurb__icontains=query) |
        Q(year__icontains=query) |
        Q(playerranking__player__name__icontains=query, playerranking__player__active=True)
    ).distinct()[:5]

    # Search players (only active players)
    players = models.Player.objects.filter(
        Q(name__icontains=query) |
        Q(position__icontains=query) |
        Q(school__icontains=query),
        active=True
    )[:5]

    def get_ranking_title(ranking):
        parts = [str(ranking.year)]
        
        if ranking.is_mock_draft:
            if ranking.ranking_type:
                parts.append(ranking.ranking_type)
            parts.append(f"Mock Draft v{ranking.mock_draft_version}" if ranking.mock_draft_version else "Mock Draft")
        elif ranking.is_draft:
            parts.append("Draft")
            if ranking.ranking_length:
                parts.append(f"Top {ranking.ranking_length}")
            elif ranking.ranking_type:
                parts.extend([ranking.ranking_type, "Draft Board"])
        else:
            if ranking.ranking_type:
                parts.append(ranking.ranking_type)
            parts.append("Rankings")
        
        return " ".join(parts)

    return JsonResponse({
        'articles': [{
            'headline': article.headline,
            'slug': article.slug,
            'created': template_localtime(article.created).strftime('%b %d, %Y')
        } for article in articles],
        'rankings': [{
            'headline': get_ranking_title(ranking),
            'slug': ranking.slug,
            'year': ranking.year,
            'preview': next(
                (pr.player.name for pr in ranking.playerranking_set.filter(player__active=True)
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
