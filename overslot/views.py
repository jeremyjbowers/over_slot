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

from overslot import models, utils
from overslot.decorators import subscription_required

def index(request):
    context = {}
    context['articles'] = models.Article.objects.filter(publish=True)
    context['rankings'] = models.Ranking.objects.all()

    return render(request, "index.html", context)

def articles_list(request):
    context = {}
    context['articles'] = models.Article.objects.filter(publish=True)
    
    # Add recent rankings for sidebar
    context['recent_rankings'] = models.Ranking.objects.filter(
        active=True
    ).order_by('-created')[:3]

    return render(request, "articles_list.html", context)


@subscription_required
def articles_detail(request, slug):
    context = {}
    context['article'] = get_object_or_404(models.Article, slug=slug)

    return render(request, "articles_detail.html", context)


def rankings_list(request):
    context = {}
    context['rankings'] = models.Ranking.objects.all()

    return render(request, "rankings_list.html", context)


@subscription_required
def rankings_detail(request, slug):
    context = {}
    context['ranking'] = get_object_or_404(models.Ranking, slug=slug)
    
    # Add recent articles for sidebar
    context['recent_articles'] = models.Article.objects.filter(
        publish=True
    ).order_by('-created')[:5]

    return render(request, "rankings_detail.html", context)


@subscription_required
def players_detail(request, slug):
    context = {}
    context['player'] = get_object_or_404(models.Player, slug=slug)
    context['rankings'] = models.PlayerRanking.objects.filter(player=context['player'])
    context['articles'] = models.Article.objects.filter(players=context['player'])

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
        Q(playerranking__player__name__icontains=query)
    ).distinct()[:5]

    # Search players
    players = models.Player.objects.filter(
        Q(name__icontains=query) |
        Q(position__icontains=query) |
        Q(school__icontains=query)
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
                (pr.player.name for pr in ranking.playerranking_set.all()
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