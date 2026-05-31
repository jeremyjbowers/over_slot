from functools import wraps
from django.shortcuts import redirect, render, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.urls import reverse
from django.template.response import TemplateResponse

from overslot.models import Subscription, Article, Ranking, Player, PlayerRanking


def subscription_required(view_func):
    """
    Decorator that checks if user has an active subscription.
    Staff users have full access to all content.
    Shows preview with subscription prompt if no active subscription.
    """
    @wraps(view_func)
    def _wrapped_view(request, *args, **kwargs):
        # Staff users get full access
        if request.user.is_staff:
            return view_func(request, *args, **kwargs)
        
        # Check if user has an active subscription
        user_has_subscription = False
        if request.user.is_authenticated:
            try:
                subscription = request.user.subscription
                if subscription.can_access_premium_content():
                    user_has_subscription = True
                else:
                    # User has subscription but it's not active
                    messages.warning(request, 'Your subscription is not active. Please update your billing information.')
                    return redirect('subscription_dashboard')
            except Subscription.DoesNotExist:
                pass
        
        # Check if this is an article detail view and if the article is free
        view_name = view_func.__name__
        if view_name == 'articles_detail':
            try:
                article = Article.objects.get(slug=kwargs.get('slug'), publish=True, active=True)
                if article.is_free:
                    # Free articles don't require subscription
                    return view_func(request, *args, **kwargs)
            except Article.DoesNotExist:
                pass

        # Free rankings and mock drafts (same template; scope by is_mock_draft)
        if view_name in ('rankings_detail', 'mock_drafts_detail'):
            slug = kwargs.get('slug')
            is_mock = view_name == 'mock_drafts_detail'
            try:
                ranking = Ranking.objects.get(
                    slug=slug, publish=True, is_mock_draft=is_mock,
                )
                if ranking.is_free:
                    return view_func(request, *args, **kwargs)
            except Ranking.DoesNotExist:
                pass

        # If user has subscription, show full content
        if user_has_subscription:
            return view_func(request, *args, **kwargs)
        
        # Otherwise, show preview with subscription prompt
        # We need to call the view function directly and extract its template logic
        # Since we can't easily extract template names from HttpResponse, 
        # we'll map view function names to their templates
        template_mapping = {
            'articles_detail': 'articles_detail.html',
            'stock_watch_detail': 'stock_watch_detail.html',
            'rankings_detail': 'rankings_detail.html',
            'mock_drafts_detail': 'rankings_detail.html',
            'players_detail': 'players_detail.html',
            'reels_list': 'reels_list.html',
            # Hitters data tables (year-specific views only)
            'college_hitters_year': 'hitters_list.html',
            'hs_hitters_year': 'hitters_list.html',
            # Stats data tables
            'stats_list': 'stats_list.html',
            'stats_hit_year': 'stats_list.html',
            'stats_pitch_year': 'stats_list.html',
        }
        
        # Call the view to get the context (but ignore its response)
        response = view_func(request, *args, **kwargs)
        
        # Extract context from the response if it's a TemplateResponse
        context = {}
        if isinstance(response, TemplateResponse):
            # TemplateResponse has context_data as a property that returns the context dict
            try:
                context_data = response.context_data
                if context_data:
                    # Convert to dict - context_data might be a Context object or dict
                    if isinstance(context_data, dict):
                        context = context_data.copy()
                    elif hasattr(context_data, 'dicts'):
                        # It's a Context object - flatten all dicts
                        context = {}
                        for d in context_data.dicts:
                            if isinstance(d, dict):
                                context.update(d)
                    else:
                        # Try direct conversion
                        try:
                            context = dict(context_data)
                        except (TypeError, ValueError):
                            # If that fails, try iterating
                            context = {k: v for k, v in context_data.items()} if hasattr(context_data, 'items') else {}
            except (AttributeError, TypeError, ValueError):
                # If context_data access fails, context stays empty
                pass
        
        # If still no context and it's not a TemplateResponse, use fallback
        if not context:
            # For regular HttpResponse, we need to recreate the context
            # by calling the view logic directly
            context = {}
            if view_name == 'articles_detail':
                context['article'] = get_object_or_404(Article, slug=kwargs.get('slug'), publish=True, active=True)
            elif view_name == 'rankings_detail':
                context['ranking'] = get_object_or_404(
                    Ranking, slug=kwargs.get('slug'), publish=True, is_mock_draft=False,
                )
                context['recent_articles'] = Article.objects.filter(publish=True, active=True).order_by('-created')[:5]
            elif view_name == 'mock_drafts_detail':
                context['ranking'] = get_object_or_404(
                    Ranking, slug=kwargs.get('slug'), publish=True, is_mock_draft=True,
                )
                context['recent_articles'] = Article.objects.filter(publish=True, active=True).order_by('-created')[:5]
            elif view_name == 'players_detail':
                from overslot.views import _player_ranking_sort_key
                player = get_object_or_404(Player, slug=kwargs.get('slug'))
                context['player'] = player
                context['rankings'] = sorted(
                    PlayerRanking.objects.filter(
                        player=player, ranking__publish=True, active=True
                    ).select_related('ranking'),
                    key=_player_ranking_sort_key,
                )
                context['articles'] = Article.objects.filter(players=player, publish=True, active=True)
            elif view_name == 'stock_watch_detail':
                from overslot.models import StockWatchArticle
                article = get_object_or_404(StockWatchArticle, slug=kwargs.get('slug'), publish=True, active=True)
                context['article'] = article
                sw_players = article.stock_watch_players.filter(active=True).select_related('player').order_by('-direction', 'player__name')
                context['stock_watch_players'] = sw_players
            # For hitters and stats views, the context is already extracted from TemplateResponse above
            # If it's not a TemplateResponse, we'll need to call the view logic
            # But since these views use TemplateResponse(), they should return TemplateResponse
        
        # Add preview mode flags
        context['preview_mode'] = True
        context['user_authenticated'] = request.user.is_authenticated
        
        # Ensure required context variables exist for stats views
        if view_name in ['stats_list', 'stats_hit_year', 'stats_pitch_year']:
            # If context is missing critical variables, the view might have failed
            # In that case, return the original response (which might be an error)
            if not context.get('rows') and not context.get('columns'):
                # Context extraction failed - return original response
                return response
        
        # Get the template name from our mapping
        template_name = template_mapping.get(view_name)
        if not template_name:
            # Fallback to the original response if we can't map it
            return response
        
        return render(request, template_name, context)
    
    return _wrapped_view


def subscription_required_json(view_func):
    """
    Decorator for JSON/API views that checks subscription status.
    Staff users have full access to all content.
    Returns JSON error response instead of redirect.
    """
    @wraps(view_func)
    def _wrapped_view(request, *args, **kwargs):
        from django.http import JsonResponse
        
        if not request.user.is_authenticated:
            return JsonResponse({
                'error': 'Authentication required',
                'message': 'Please log in to access this content.'
            }, status=401)
        
        # Staff users get full access
        if request.user.is_staff:
            return view_func(request, *args, **kwargs)
        
        try:
            subscription = request.user.subscription
            if subscription.can_access_premium_content():
                return view_func(request, *args, **kwargs)
            else:
                return JsonResponse({
                    'error': 'Subscription required',
                    'message': 'This content requires an active subscription.'
                }, status=403)
        except Subscription.DoesNotExist:
            return JsonResponse({
                'error': 'Subscription required',
                'message': 'This content requires a subscription.'
            }, status=403)
    
    return _wrapped_view


def has_active_subscription(user):
    """
    Helper function to check if a user has an active subscription.
    Staff users are considered to have access.
    Can be used in templates and views.
    """
    if not user.is_authenticated:
        return False
    
    # Staff users get full access
    if user.is_staff:
        return True
    
    try:
        subscription = user.subscription
        return subscription.can_access_premium_content()
    except Subscription.DoesNotExist:
        return False 