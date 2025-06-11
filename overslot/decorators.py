from functools import wraps
from django.shortcuts import redirect, render
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.urls import reverse

from overslot.models import Subscription


def subscription_required(view_func):
    """
    Decorator that checks if user has an active subscription.
    Staff users have full access to all content.
    Redirects to subscription page if not authenticated or no active subscription.
    """
    @wraps(view_func)
    def _wrapped_view(request, *args, **kwargs):
        # First check if user is authenticated
        if not request.user.is_authenticated:
            messages.info(request, 'Please log in to access this content.')
            return redirect('account_login')
        
        # Staff users get full access
        if request.user.is_staff:
            return view_func(request, *args, **kwargs)
        
        # Check if user has an active subscription
        try:
            subscription = request.user.subscription
            if subscription.can_access_premium_content():
                return view_func(request, *args, **kwargs)
            else:
                # User has subscription but it's not active
                messages.warning(request, 'Your subscription is not active. Please update your billing information.')
                return redirect('subscription_dashboard')
        except Subscription.DoesNotExist:
            # User doesn't have a subscription
            messages.info(request, 'This content requires a subscription. Please subscribe to continue.')
            return render(request, 'subscription/required.html')
    
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