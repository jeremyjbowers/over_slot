"""
Cache utilities for expensive querysets and computed data.

Uses Django's cache framework (Valkey in production when VALKEY_URL is set).
Only caches data that is identical for all users - never user-specific state.
"""
from django.core.cache import cache

# Default TTL for queryset/data caches (seconds)
DEFAULT_TIMEOUT = 300  # 5 minutes
HOMEPAGE_TIMEOUT = 300  # 5 minutes
RANKING_TIMEOUT = 600   # 10 minutes - rankings change less often
ARTICLE_TIMEOUT = 300   # 5 minutes

# Cache key prefixes - centralize for invalidation
KEY_HOMEPAGE = 'overslot:homepage'
KEY_ARTICLES = 'overslot:articles'
KEY_ARTICLE = 'overslot:article'
KEY_STOCK_WATCH = 'overslot:stock_watch'
KEY_RANKINGS = 'overslot:rankings'
KEY_RANKING = 'overslot:ranking'
KEY_MOCK_DRAFT = 'overslot:mock_draft'


def get_cached(key, compute_fn, timeout=DEFAULT_TIMEOUT):
    """
    Get value from cache, or compute and cache it.
    compute_fn is a callable that returns the value (e.g. list(queryset)).
    """
    try:
        return cache.get_or_set(key, compute_fn, timeout)
    except Exception:
        return compute_fn()


def bust_homepage():
    """Invalidate all homepage caches."""
    keys = [
        f'{KEY_HOMEPAGE}:stock_watch',
        f'{KEY_HOMEPAGE}:articles',
        f'{KEY_HOMEPAGE}:rankings_carousel',
        f'{KEY_HOMEPAGE}:games',
        f'{KEY_HOMEPAGE}:scouting',
        f'{KEY_HOMEPAGE}:non_scouting',
        f'{KEY_HOMEPAGE}:current_rankings',
        f'{KEY_HOMEPAGE}:archived_rankings',
        f'{KEY_HOMEPAGE}:rankings_count',
        f'{KEY_HOMEPAGE}:player_videos',
        f'{KEY_HOMEPAGE}:videos_count',
        f'{KEY_HOMEPAGE}:featured_games',
        f'{KEY_HOMEPAGE}:podcasts',
    ]
    cache.delete_many(keys)


def bust_articles_list():
    """Invalidate articles list and sidebar."""
    cache.delete_many([f'{KEY_ARTICLES}:list_items', f'{KEY_ARTICLES}:recent_rankings'])


def bust_article(slug):
    """Invalidate a single article detail."""
    if slug:
        cache.delete(f'{KEY_ARTICLE}:{slug}')


def bust_stock_watch(slug):
    """Invalidate a single stock watch article detail."""
    if slug:
        cache.delete(f'{KEY_STOCK_WATCH}:{slug}')


def bust_rankings_list():
    """Invalidate rankings list and mock drafts list."""
    cache.delete_many([f'{KEY_RANKINGS}:list', f'{KEY_RANKINGS}:mock_drafts'])


def bust_ranking(slug, is_mock_draft=False):
    """Invalidate a single ranking or mock draft detail."""
    if slug:
        key = f'{KEY_MOCK_DRAFT}:{slug}' if is_mock_draft else f'{KEY_RANKING}:{slug}'
        cache.delete(key)
