import csv
import os
import datetime
import itertools
from django.http import HttpResponse
from django.views.decorators.csrf import csrf_exempt
from django.shortcuts import render, get_object_or_404, redirect
from django.db.models import Count, Avg, Sum, Max, Min, Q, Case, When, Value, IntegerField
from django.core.paginator import EmptyPage, PageNotAnInteger, Paginator
from django.http import JsonResponse
from django.conf import settings
from django.contrib.auth.decorators import login_required
from decimal import *
from django.utils.timezone import template_localtime, now
from django.template.response import TemplateResponse
from dateutil import parser
from datetime import timedelta
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


def games_list(request, year=None, month=None, day=None):
    """
    Display games for a specific date. If no date provided, shows today's games
    (or opening day if today is before opening day).
    """
    context = {}
    
    # Get season opening day from settings
    try:
        season_opening_day = parser.parse(getattr(settings, 'SEASON_OPENING_DAY', '2026-02-12')).date()
    except (ValueError, TypeError):
        season_opening_day = datetime.date(2026, 2, 12)  # Fallback
    
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
    
    games = models.Game.objects.filter(
        active=True,
        start_datetime__gte=start_of_day,
        start_datetime__lte=end_of_day
    ).select_related('home_team', 'away_team').order_by('start_datetime')
    
    # Ensure all teams have slugs (for teams created before slug field was added)
    for game in games:
        if game.home_team and not game.home_team.slug:
            game.home_team.save()  # Auto-generates slug
            game.home_team.refresh_from_db()
        if game.away_team and not game.away_team.slug:
            game.away_team.save()  # Auto-generates slug
            game.away_team.refresh_from_db()
    
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
    """
    context = {}
    team = get_object_or_404(models.Team, slug=slug, active=True)
    context['team'] = team
    
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
    
    return render(request, "team_detail.html", context)


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
    
    # Build charts from PlayerStatSeason across all available stat years (most recent first)
    season_qs = models.PlayerStatSeason.objects.filter(player=context['player']).order_by('-year')
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
        else:
            hitter_seasons.append(sc)
    
    context['season_charts'] = season_charts
    context['pitcher_seasons_by_year'] = pitcher_seasons_by_year
    context['hitter_seasons'] = hitter_seasons

    # Only show published articles
    context['articles'] = models.Article.objects.filter(players=context['player'], publish=True)
    
    # Get 643 stats for this player
    stats_643_qs = models.Player643StatSeason.objects.filter(
        player=context['player']
    ).order_by('-year', 'team_name')
    
    # Check if we have any stats with actual data (hitting or pitching)
    has_hitting_stats = stats_643_qs.filter(
        Q(hit_games_played__isnull=False) |
        Q(hit_plate_appearances__isnull=False) |
        Q(hit_at_bats__isnull=False) |
        Q(hit_hits__isnull=False)
    ).exists()
    
    has_pitching_stats = stats_643_qs.filter(
        pitch_appearances__isnull=False
    ).exists()
    
    context['stats_643'] = stats_643_qs
    context['has_stats_643'] = has_hitting_stats or has_pitching_stats
    context['has_pitching_stats'] = has_pitching_stats

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

    # Hard-coded year navigation lists (stable; data changes infrequently)
    college_years = [2025, 2024]
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
    college_years = [2025, 2024]
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
