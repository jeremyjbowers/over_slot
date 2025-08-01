from functools import wraps
from django.shortcuts import redirect, render, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.urls import reverse

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
        
        # If user has subscription, show full content
        if user_has_subscription:
            return view_func(request, *args, **kwargs)
        
        # Otherwise, show preview with subscription prompt
        # We need to call the view function directly and extract its template logic
        # Since we can't easily extract template names from HttpResponse, 
        # we'll map view function names to their templates
        view_name = view_func.__name__
        template_mapping = {
            'articles_detail': 'articles_detail.html',
            'rankings_detail': 'rankings_detail.html', 
            'players_detail': 'players_detail.html',
        }
        
        # Call the view to get the context (but ignore its response)
        response = view_func(request, *args, **kwargs)
        
        # Extract context from the response if it's a TemplateResponse
        if hasattr(response, 'context_data'):
            context = response.context_data.copy()
        else:
            # For regular HttpResponse, we need to recreate the context
            # by calling the view logic directly
            context = {}
            if view_name == 'articles_detail':
                context['article'] = get_object_or_404(Article, slug=kwargs.get('slug'), publish=True)
            elif view_name == 'rankings_detail':
                context['ranking'] = get_object_or_404(Ranking, slug=kwargs.get('slug'), publish=True)
                context['recent_articles'] = Article.objects.filter(publish=True).order_by('-created')[:5]
            elif view_name == 'players_detail':
                player = get_object_or_404(Player, slug=kwargs.get('slug'))
                context['player'] = player
                context['rankings'] = PlayerRanking.objects.filter(player=player, ranking__publish=True)
                context['articles'] = Article.objects.filter(players=player, publish=True)
        
        # Add preview mode flags
        context['preview_mode'] = True
        context['user_authenticated'] = request.user.is_authenticated
        
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