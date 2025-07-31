"""
Cache utilities for overslot application.
Provides safe caching functions that respect user authentication state.
"""
import hashlib
import json
from functools import wraps
from django.core.cache import cache
from django.conf import settings
# Import moved inline to avoid circular imports


def make_cache_key(*parts):
    """
    Create a cache key from multiple parts.
    Automatically adds the KEY_PREFIX from settings.
    """
    key_parts = [str(part) for part in parts if part is not None]
    key = ':'.join(key_parts)
    
    # If key is too long, hash it
    if len(key) > 200:
        key = hashlib.md5(key.encode()).hexdigest()
    
    return key


def get_cached_subscription_status(user):
    """
    Get user subscription status from cache to avoid repeated DB queries.
    Updates cache if not present or expired.
    """
    if not user.is_authenticated:
        return {'is_active': False, 'is_staff': False}
    
    cache_key = make_cache_key('subscription_status', user.id)
    status = cache.get(cache_key)
    
    if status is None:
        # Staff users always have access
        if user.is_staff:
            status = {'is_active': True, 'is_staff': True}
        else:
            try:
                subscription = user.subscription
                status = {
                    'is_active': subscription.can_access_premium_content(),
                    'is_staff': False,
                    'expires': subscription.current_period_end.isoformat() if subscription.current_period_end else None
                }
            except:
                status = {'is_active': False, 'is_staff': False}
        
        # Cache for 10 minutes - short TTL for subscription changes
        cache.set(cache_key, status, 600)
    
    return status


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
    
    subscription_status = get_cached_subscription_status(user)
    return subscription_status['is_active']


def get_user_cache_state(user):
    """
    Determine cache state based on user authentication and subscription status.
    Returns one of: 'anonymous', 'authenticated', 'subscriber', 'staff'
    """
    if not user.is_authenticated:
        return 'anonymous'
    elif user.is_staff:
        return 'staff'
    elif has_active_subscription(user):
        return 'subscriber'
    else:
        return 'authenticated'


def cache_for_user_state(timeout=3600, vary_by_user_state=True):
    """
    Decorator to cache function results based on user state.
    
    Args:
        timeout: Cache timeout in seconds (default 1 hour)
        vary_by_user_state: Whether to include user state in cache key
    """
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            # Build cache key
            cache_key_parts = [func.__name__]
            
            # Add arguments to cache key
            for arg in args:
                if hasattr(arg, 'id'):
                    cache_key_parts.append(f"{arg.__class__.__name__}_{arg.id}")
                elif hasattr(arg, 'is_authenticated'):
                    # This is likely a user object, handle user state
                    if vary_by_user_state:
                        user_state = get_user_cache_state(arg)
                        cache_key_parts.append(f"user_{user_state}")
                else:
                    cache_key_parts.append(str(arg))
            
            # Add keyword arguments
            for key, value in sorted(kwargs.items()):
                cache_key_parts.append(f"{key}_{value}")
            
            cache_key = make_cache_key(*cache_key_parts)
            
            # Try to get from cache
            result = cache.get(cache_key)
            if result is not None:
                return result
            
            # Execute function and cache result
            result = func(*args, **kwargs)
            cache.set(cache_key, result, timeout)
            return result
        
        return wrapper
    return decorator


def cache_query_result(cache_key, timeout=3600):
    """
    Simple decorator to cache database query results.
    Use for functions that don't depend on user state.
    """
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            # Try to get from cache
            result = cache.get(cache_key)
            if result is not None:
                return result
            
            # Execute function and cache result
            result = func(*args, **kwargs)
            cache.set(cache_key, result, timeout)
            return result
        
        return wrapper
    return decorator


def invalidate_cache_pattern(pattern):
    """
    Invalidate all cache keys matching a pattern.
    Note: This requires django-redis backend for pattern support.
    """
    try:
        from django_redis import get_redis_connection
        conn = get_redis_connection("default")
        keys = conn.keys(f"{settings.CACHES['default']['KEY_PREFIX']}*{pattern}*")
        if keys:
            conn.delete(*keys)
            return len(keys)
    except ImportError:
        # Fallback for other cache backends
        pass
    return 0


def clear_user_subscription_cache(user_id):
    """Clear subscription cache for a specific user."""
    cache_key = make_cache_key('subscription_status', user_id)
    cache.delete(cache_key)