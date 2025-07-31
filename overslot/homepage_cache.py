"""
Caching utilities specifically for homepage operations.
Optimizes the expensive queries in the index view.
"""
from django.core.cache import cache
from overslot.cache_utils import make_cache_key, get_user_cache_state


def get_homepage_content_cached(user):
    """
    Get cached homepage content based on user state.
    This replaces multiple expensive queries in the index view.
    """
    user_state = get_user_cache_state(user)
    cache_key = make_cache_key('homepage_content', user_state)
    cached_result = cache.get(cache_key)
    
    if cached_result is not None:
        return cached_result
    
    # Import here to avoid circular imports
    from overslot.models import Article, Ranking
    
    # Different queries based on user state
    if user_state == 'staff':
        # Staff can see unpublished content
        carousel_articles = Article.objects.filter(is_carousel=True).select_related()
        latest_articles = Article.objects.filter(is_carousel=True).order_by('-created').select_related()
        latest_rankings = Ranking.objects.filter(
            is_mock_draft=False, is_carousel=True
        ).order_by('-created').select_related()
        
        # Content lists below carousel - last 10 regardless of carousel flag
        articles = Article.objects.all().order_by('-created')[:10].select_related()
        rankings = Ranking.objects.filter(is_mock_draft=False).order_by('-created')[:10].select_related()
    else:
        # Everyone else sees only published content
        carousel_articles = Article.objects.filter(
            publish=True, is_carousel=True
        ).select_related()
        latest_articles = Article.objects.filter(
            publish=True, is_carousel=True
        ).order_by('-created').select_related()
        latest_rankings = Ranking.objects.filter(
            is_mock_draft=False, publish=True, is_carousel=True
        ).order_by('-created').select_related()
        
        # Content lists below carousel - last 10 regardless of carousel flag
        articles = Article.objects.filter(publish=True).order_by('-created')[:10].select_related()
        rankings = Ranking.objects.filter(
            is_mock_draft=False, publish=True
        ).order_by('-created')[:10].select_related()
    
    # Prefetch active players for articles to avoid N+1 queries
    for article in carousel_articles:
        article.active_players = list(article.players.filter(active=True))
    
    for article in latest_articles:
        article.active_players = list(article.players.filter(active=True))
    
    for article in articles:
        article.active_players = list(article.players.filter(active=True))
    
    result = {
        'latest_articles': list(latest_articles),
        'latest_rankings': list(latest_rankings),
        'articles': list(articles),
        'rankings': list(rankings)
    }
    
    # Cache for 30 minutes - homepage content changes frequently
    cache.set(cache_key, result, 1800)
    return result


def invalidate_homepage_content_cache():
    """Invalidate all homepage content cache variations."""
    user_states = ['anonymous', 'authenticated', 'subscriber', 'staff']
    for user_state in user_states:
        cache_key = make_cache_key('homepage_content', user_state)
        cache.delete(cache_key)