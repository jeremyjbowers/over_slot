from django import template
from decimal import Decimal
from overslot.decorators import has_active_subscription
from overslot.models import FeatureFlag

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


@register.inclusion_tag('includes/recent_articles_sidebar.html')
def recent_articles_sidebar(limit=5):
    """Template tag to show recent articles sidebar."""
    from overslot.models import Article
    recent_articles = Article.objects.filter(
        publish=True
    ).order_by('-created')[:limit]
    
    return {
        'recent_articles': recent_articles
    }


@register.inclusion_tag('includes/recent_rankings_sidebar.html')
def recent_rankings_sidebar(limit=5):
    """Template tag to show recent rankings sidebar."""
    from overslot.models import Ranking
    recent_rankings = Ranking.objects.filter(
        active=True
    ).order_by('-created')[:limit]
    
    return {
        'recent_rankings': recent_rankings
    }


@register.simple_tag(takes_context=True)
def feature_enabled(context, key):
    """Return True if feature flag `key` is enabled for request.user."""
    request = context.get('request')
    user = getattr(request, 'user', None)
    return FeatureFlag.enabled(key, user)


@register.simple_tag(takes_context=True)
def if_feature(context, key, then_value, else_value=""):
    """Return then_value if flag enabled else else_value (for inline usage)."""
    return then_value if feature_enabled(context, key) else else_value