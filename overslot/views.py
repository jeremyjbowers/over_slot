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

from overslot import models, utils

def index(request):
    context = {}
    context['articles'] = models.Article.objects.filter(publish=True)
    context['rankings'] = models.Ranking.objects.all()

    return render(request, "index.html", context)

def articles_list(request):
    context = {}
    context['articles'] = models.Article.objects.filter(publish=True)

    return render(request, "articles_list.html", context)


def articles_detail(request, slug):
    context = {}
    context['article'] = get_object_or_404(models.Article, slug=slug)

    return render(request, "articles_detail.html", context)


def rankings_list(request):
    context = {}
    context['rankings'] = models.Ranking.objects.all()

    return render(request, "rankings_list.html", context)


def rankings_detail(request, slug):
    context = {}
    context['ranking'] = get_object_or_404(models.Ranking, slug=slug)

    return render(request, "rankings_detail.html", context)


def players_detail(request, slug):
    context = {}
    context['player'] = get_object_or_404(models.Player, slug=slug)
    context['rankings'] = models.PlayerRanking.objects.filter(player=context['player'])
    context['articles'] = models.Article.objects.filter(players=context['player'])

    return render(request, "players_detail.html", context)