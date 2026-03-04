"""
Admin views for cache inspection and manual invalidation.
Staff-only. Uses duplicate admin styling.
"""
from django.shortcuts import render, redirect
from django.contrib.admin.views.decorators import staff_member_required
from django.contrib import messages
from django.views.decorators.http import require_POST
from django.core.cache import cache
from django.conf import settings
from django.core.paginator import Paginator

from overslot.cache_utils import (
    bust_homepage,
    bust_articles_list,
    bust_rankings_list,
    KEY_HOMEPAGE,
    KEY_ARTICLES,
    KEY_ARTICLE,
    KEY_STOCK_WATCH,
    KEY_RANKINGS,
    KEY_RANKING,
    KEY_MOCK_DRAFT,
)


def _get_cache_keys():
    """
    List cache keys containing 'overslot'. Works with Valkey (iter_keys),
    LocMemCache (_cache), and DatabaseCache (no list support - returns []).
    """
    keys = []
    try:
        if hasattr(cache, 'iter_keys'):
            keys = list(cache.iter_keys('*overslot*'))
        elif hasattr(cache, 'keys'):
            keys = cache.keys('*overslot*') or []
        elif hasattr(cache, '_cache') and hasattr(cache._cache, 'keys'):
            # LocMemCache stores in _cache dict
            all_keys = list(cache._cache.keys())
            keys = [k for k in all_keys if 'overslot' in str(k)]
    except Exception:
        pass
    return sorted(keys)


def _get_cache_backend_info():
    """Return human-readable cache backend name."""
    backend = settings.CACHES['default']['BACKEND'].lower()
    if 'valkey' in backend:
        return 'Valkey (Redis-compatible)'
    if 'database' in backend or 'db.' in backend:
        return 'Database'
    if 'locmem' in backend:
        return 'Local Memory'
    return 'Other'


def _logical_key(raw_key):
    """
    Extract logical key from raw stored key. Django stores keys as prefix:version:key.
    For delete we need the logical key.
    """
    s = str(raw_key)
    if s.count(':') >= 2:
        parts = s.split(':', 2)
        if parts[0] == '' and parts[1].isdigit():
            return parts[2]
    return s


@staff_member_required
def cache_dashboard(request):
    """Main cache admin dashboard: list keys, bulk actions, delete by key."""
    context = {}

    # Cache backend info
    context['cache_backend'] = _get_cache_backend_info()

    # List keys (Valkey/LocMem; Database cache cannot list)
    raw_keys = _get_cache_keys()
    # Normalize to logical keys for display and delete
    all_keys = list(dict.fromkeys(_logical_key(k) for k in raw_keys))
    context['total_keys'] = len(all_keys)

    # Filter by search
    search = request.GET.get('search', '').strip()
    if search:
        all_keys = [k for k in all_keys if search.lower() in k.lower()]
        context['search'] = search

    # Paginate
    paginator = Paginator(all_keys, 50)
    page = request.GET.get('page', 1)
    context['keys_page'] = paginator.get_page(page)

    # Known static keys for quick-reference / when listing isn't supported
    context['known_static_keys'] = [
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
        f'{KEY_ARTICLES}:list_items',
        f'{KEY_ARTICLES}:recent_rankings',
        f'{KEY_RANKINGS}:list',
        f'{KEY_RANKINGS}:mock_drafts',
    ]

    return render(request, 'admin/cache_dashboard.html', context)


@staff_member_required
@require_POST
def cache_delete_key(request):
    """Delete a single cache key by name."""
    raw_key = (request.POST.get('key') or '').strip()
    if not raw_key:
        messages.error(request, 'No key provided.')
        return redirect('cache_dashboard')

    key = _logical_key(raw_key)
    try:
        cache.delete(key)
        messages.success(request, f'Deleted cache key: {key}')
    except Exception as e:
        messages.error(request, f'Failed to delete key: {e}')

    return redirect('cache_dashboard')


@staff_member_required
@require_POST
def cache_bust_homepage(request):
    """Bust all homepage caches."""
    bust_homepage()
    messages.success(request, 'Homepage cache cleared.')
    return redirect('cache_dashboard')


@staff_member_required
@require_POST
def cache_bust_articles(request):
    """Bust articles list and sidebar caches."""
    bust_articles_list()
    messages.success(request, 'Articles list cache cleared.')
    return redirect('cache_dashboard')


@staff_member_required
@require_POST
def cache_bust_rankings(request):
    """Bust rankings list and mock drafts caches."""
    bust_rankings_list()
    messages.success(request, 'Rankings list cache cleared.')
    return redirect('cache_dashboard')


@staff_member_required
@require_POST
def cache_bust_all(request):
    """Bust all known overslot caches (homepage, articles, rankings)."""
    bust_homepage()
    bust_articles_list()
    bust_rankings_list()
    messages.success(request, 'All known caches cleared (homepage, articles, rankings).')
    return redirect('cache_dashboard')
