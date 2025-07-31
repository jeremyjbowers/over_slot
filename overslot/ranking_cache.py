"""
Caching utilities specifically for ranking-related operations.
Optimizes the expensive filter building logic in rankings detail views.
"""
from django.core.cache import cache
from overslot.cache_utils import make_cache_key


def get_ranking_filters_cached(ranking_id):
    """
    Get cached filter options for a ranking detail page.
    This replaces the expensive filter building logic in rankings_detail view.
    """
    cache_key = make_cache_key('ranking_filters', ranking_id)
    cached_result = cache.get(cache_key)
    
    if cached_result is not None:
        return cached_result
    
    # Import here to avoid circular imports
    from overslot.models import PlayerRanking
    
    # Use optimized query with select_related to avoid N+1 queries
    player_rankings = PlayerRanking.objects.filter(
        ranking_id=ranking_id
    ).select_related('player').order_by('rank')
    
    # Build filter lists efficiently
    schools = set()
    commitments = set()
    states = set()
    all_positions = []
    
    for pr in player_rankings:
        if pr.school:
            schools.add(pr.school)
        if pr.commitment:
            commitments.add(pr.commitment)
        if pr.player and pr.player.state:
            states.add(pr.player.state)
        if pr.position:
            all_positions.append(pr.position)
    
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
    positions = []
    for simple_pos, variants in position_mapping:
        # Check if any player has a position that contains any of the variants
        for player_pos in all_positions:
            if any(variant in player_pos.upper() for variant in variants):
                if simple_pos not in positions:
                    positions.append(simple_pos)
                break
    
    result = {
        'filter_positions': positions,
        'filter_schools': sorted(list(schools)),
        'filter_commitments': sorted(list(commitments)),
        'filter_states': sorted(list(states)),
        'player_rankings': list(player_rankings)  # Cache the queryset results too
    }
    
    # Cache for 2 hours - rankings don't change frequently
    cache.set(cache_key, result, 7200)
    return result


def invalidate_ranking_filters_cache(ranking_id):
    """Invalidate the cached filters for a specific ranking."""
    cache_key = make_cache_key('ranking_filters', ranking_id)
    cache.delete(cache_key)