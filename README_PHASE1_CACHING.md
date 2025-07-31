# Phase 1 Valkey Caching Implementation

This document outlines the Phase 1 caching implementation specifically optimized for the homepage and rankings detail pages - the two most highly loaded pages on the site.

## What Was Implemented

### 1. Valkey Cache Configuration
- Added Redis/Valkey cache backend in `config/dev/settings.py`
- Configured with connection pooling and retry logic
- Environment variable support for production deployments

### 2. Cache Utility Framework (`overslot/cache_utils.py`)
- User state-aware caching (anonymous, authenticated, subscriber, staff)
- Smart cache key generation with automatic hashing for long keys
- Subscription status caching with 10-minute TTL
- Cache invalidation utilities

### 3. Template Tag Optimization (`overslot/templatetags/overslot_tags.py`)
- **Recent Articles Sidebar**: Now cached for 30 minutes per user state
- **Recent Rankings Sidebar**: Now cached for 30 minutes per user state
- Eliminates N+1 queries by prefetching active players
- Different cache keys for staff vs. regular users to show/hide unpublished content

### 4. Rankings Detail Page Optimization (`overslot/ranking_cache.py`)
- **Ranking Filters**: Cached for 2 hours (schools, commitments, states, positions)
- **Optimized Queries**: Added `select_related('player')` to avoid N+1 queries
- **Smart Filtering**: Cached position mapping and filter building logic
- Replaces expensive Python processing with cached results

### 5. Homepage Content Caching (`overslot/homepage_cache.py`)
- **Carousel Content**: Cached for 30 minutes per user state
- **Recent Content Lists**: Cached article and ranking lists
- **Player Prefetching**: Eliminates N+1 queries for article-player relationships
- Separate cache variations for staff (see unpublished) vs. regular users

### 6. Subscription Status Caching (`overslot/decorators.py`)
- **Decorator Optimization**: `@subscription_required` now uses cached status
- **Database Query Reduction**: Eliminates repeated subscription checks
- **JSON API Support**: `@subscription_required_json` also optimized

### 7. Automatic Cache Invalidation
- **Model Save Triggers**: Articles, Rankings, and PlayerRankings invalidate related caches
- **Stripe Webhooks**: Subscription status changes clear user cache immediately
- **Smart Invalidation**: Only clears relevant cache keys, not everything

## Performance Impact

### Expected Improvements
- **Homepage Load Time**: 40-60% reduction in database queries
- **Rankings Detail**: 200-500ms faster page loads due to cached filter building
- **Subscription Checks**: 90% reduction in subscription-related database queries
- **Concurrent Users**: 3-5x improvement in server capacity under load

### Cache Hit Scenarios
1. **Anonymous Users**: Best cache hit rates for published content
2. **Returning Subscribers**: Fast subscription status verification from cache
3. **Popular Rankings**: Filter data served from cache instead of expensive computation
4. **Homepage Traffic**: Carousel and recent content served from cache

## Cache Key Strategy

### User State Variations
Each cached item has 4 variations based on user state:
- `anonymous`: Unpaid users, see published content only
- `authenticated`: Logged in but no subscription, see published + prompts
- `subscriber`: Active subscription, see all premium content
- `staff`: Internal users, see published + unpublished content

### Cache TTL Strategy
- **Subscription Status**: 10 minutes (frequent updates from Stripe)
- **Homepage Content**: 30 minutes (frequently changing)
- **Template Sidebars**: 30 minutes (regularly updated)
- **Ranking Filters**: 2 hours (rarely change once published)

## Safe Caching Principles

### What's Cached Safely
✅ Published article lists (same for all anonymous users)
✅ Ranking filter options (same computation for all users)
✅ Template sidebar content (varies by user state, cached separately)
✅ Homepage content (varies by user state, cached separately)

### What's NOT Cached
❌ User-specific data (usernames, personal settings)
❌ Dynamic subscription prompts with user names
❌ Search results (may contain personalized content)
❌ Admin interfaces

## Production Deployment Notes

### Environment Variables
Add to your production environment:
```bash
VALKEY_HOST=your-valkey-host
VALKEY_PORT=6379
VALKEY_USER=your-valkey-username  # Optional
VALKEY_PASSWORD=your-valkey-password  # Optional
```

For development, you can use:
```bash
VALKEY_URL=redis://127.0.0.1:6379/0
```

### Dependencies
Add to requirements.txt:
```
django-redis>=5.4.0
```

### Monitoring
- Monitor cache hit rates in your Redis/Valkey dashboard
- Track database query reduction in your application monitoring
- Watch for improved response times on homepage and rankings pages

### Cache Warming
Consider implementing a cache warming strategy for:
- Most popular rankings filter data
- Recent articles/rankings sidebar content
- Homepage content for all user states

## Testing Recommendations

### Before Deployment
1. **Import Testing**: Verify all Django modules load without circular import errors
2. **Cache Miss Testing**: Verify all pages work correctly with empty cache
3. **Cache Invalidation**: Test that content updates invalidate appropriate caches
4. **User State Testing**: Verify different user types see appropriate cached content
5. **Subscription Flow**: Test that subscription changes immediately update cached status

### Troubleshooting

**Circular Import Errors**: If you encounter template library import errors, ensure:
- `has_active_subscription` is imported from `cache_utils`, not `decorators`
- Function definitions are in the correct order in `cache_utils.py`
- No circular dependencies between modules

### Performance Testing
1. Load test homepage with multiple concurrent users
2. Test rankings detail page with complex filter scenarios
3. Verify subscription checks don't hit database repeatedly
4. Monitor cache hit rates under realistic traffic

## Future Optimization Opportunities (Phase 2)

1. **Search Result Caching**: Cache anonymous user search results
2. **Fragment Caching**: Template-level caching for content cards
3. **CDN Integration**: Static asset caching with longer TTLs
4. **Database Query Optimization**: Additional `select_related`/`prefetch_related` optimizations
5. **Cache Warming**: Automated warming of popular content

## Rollback Plan

If issues arise, you can quickly disable caching by:
1. Set cache timeout to 0 in settings: `'TIMEOUT': 0`
2. Comment out cache decorators in views
3. Remove cache imports from templates

The application will function normally without caching, just with the original performance characteristics.