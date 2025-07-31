from django import template
from decimal import Decimal
from overslot.cache_utils import cache_query_result, get_user_cache_state, make_cache_key, has_active_subscription
from django.core.cache import cache

register = template.Library()


@register.simple_tag
def user_has_subscription(user):
    """Template tag to check if user has active subscription."""
    return has_active_subscription(user)


@register.inclusion_tag('includes/subscription_prompt.html', takes_context=True)
def subscription_prompt(context, content_type="content"):
    """Template tag to show subscription prompt for premium content."""
    user = context['request'].user
    return {
        'user': user,
        'has_subscription': has_active_subscription(user),
        'content_type': content_type,
        'request': context['request']
    }


@register.inclusion_tag('includes/recent_articles_sidebar.html', takes_context=True)
def recent_articles_sidebar(context, limit=5):
    """Template tag to show recent articles sidebar with caching."""
    from overslot.models import Article
    
    user = context.get('request', {}).user if context.get('request') else None
    user_state = get_user_cache_state(user) if user else 'anonymous'
    
    cache_key = make_cache_key('recent_articles_sidebar', user_state, limit)
    cached_result = cache.get(cache_key)
    
    if cached_result is not None:
        return cached_result
    
    # Different queries based on user state
    if user_state == 'staff':
        # Staff can see unpublished articles
        recent_articles = Article.objects.all().order_by('-created')[:limit]
    else:
        # Everyone else sees only published articles
        recent_articles = Article.objects.filter(
            publish=True
        ).order_by('-created')[:limit]
    
    # Add active players to avoid N+1 queries later
    for article in recent_articles:
        article.active_players = article.players.filter(active=True)
    
    result = {'recent_articles': recent_articles}
    
    # Cache for 30 minutes
    cache.set(cache_key, result, 1800)
    return result


@register.inclusion_tag('includes/recent_rankings_sidebar.html', takes_context=True)
def recent_rankings_sidebar(context, limit=5):
    """Template tag to show recent rankings sidebar with caching."""
    from overslot.models import Ranking
    
    user = context.get('request', {}).user if context.get('request') else None
    user_state = get_user_cache_state(user) if user else 'anonymous'
    
    cache_key = make_cache_key('recent_rankings_sidebar', user_state, limit)
    cached_result = cache.get(cache_key)
    
    if cached_result is not None:
        return cached_result
    
    # Different queries based on user state
    if user_state == 'staff':
        # Staff can see unpublished rankings
        recent_rankings = Ranking.objects.filter(
            active=True
        ).order_by('-created')[:limit]
    else:
        # Everyone else sees only published rankings
        recent_rankings = Ranking.objects.filter(
            active=True, publish=True
        ).order_by('-created')[:limit]
    
    result = {'recent_rankings': recent_rankings}
    
    # Cache for 30 minutes
    cache.set(cache_key, result, 1800)
    return result