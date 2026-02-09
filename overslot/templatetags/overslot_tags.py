from django import template
from decimal import Decimal
import re
from urllib.parse import urlparse, parse_qs
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


@register.filter
def format_avg3(value):
    """
    Format a numeric stat to three decimals.
    - If value is < 1 and >= 0, drop leading zero (e.g., 0.345 -> .345)
    - If value is >= 1, keep the integer part (e.g., 1.123 -> 1.123)
    - Non-numeric or None returns empty string
    """
    if value is None:
        return ""
    try:
        number = float(value)
    except (TypeError, ValueError):
        return ""
    formatted = f"{number:.3f}"
    # Drop leading zero only for non-negative values between 0 and 1
    if 0 <= number < 1 and formatted.startswith("0"):
        return formatted[1:]
    # Handle potential "-0.xyz" edge case by normalizing to "-.xyz"
    if -1 < number < 0 and formatted.startswith("-0"):
        return "-" + formatted[2:]
    return formatted


@register.filter
def format_avg2(value):
    """
    Format a numeric stat to two decimals.
    - If value is < 1 and >= 0, drop leading zero (e.g., 0.50 -> .50)
    - If value is >= 1, keep the integer part (e.g., 1.50 -> 1.50)
    - Non-numeric or None returns empty string
    """
    if value is None:
        return ""
    try:
        number = float(value)
    except (TypeError, ValueError):
        return ""
    formatted = f"{number:.2f}"
    # Drop leading zero only for non-negative values between 0 and 1
    if 0 <= number < 1 and formatted.startswith("0"):
        return formatted[1:]
    # Handle potential "-0.xy" edge case by normalizing to "-.xy"
    if -1 < number < 0 and formatted.startswith("-0"):
        return "-" + formatted[2:]
    return formatted


@register.filter
def get_item(mapping, key):
    """
    Safely get item from a dict-like mapping in templates.
    Returns None if key is absent or mapping is not subscriptable.
    """
    try:
        return mapping.get(key)
    except Exception:
        try:
            return mapping[key]
        except Exception:
            return None


@register.filter
def video_embed_url(url):
    """
    Convert a video URL to an embed URL.
    Supports YouTube (youtube.com/watch?v=, youtu.be/, youtube.com/embed/) and Vimeo.
    Returns the embed URL if recognized, otherwise returns empty string.
    """
    if not url:
        return ""
    
    original_url = url.strip()
    url = original_url
    
    # Add protocol if missing (needed for urlparse)
    if not url.startswith(('http://', 'https://')):
        url = 'https://' + url
    
    # Parse the URL to handle fragments and query parameters
    try:
        parsed = urlparse(url)
    except Exception:
        # If parsing fails, try regex fallback on original URL
        return _extract_video_id_regex(original_url)
    
    # YouTube: youtube.com/watch?v=VIDEO_ID
    if 'youtube.com' in parsed.netloc or 'youtu.be' in parsed.netloc:
        video_id = None
        
        # Handle youtube.com/embed/VIDEO_ID format (already embed)
        if '/embed/' in parsed.path:
            # Already an embed URL, clean it up
            embed_path = parsed.path.split('/embed/')[-1].split('?')[0].split('&')[0].split('#')[0]
            if embed_path and re.match(r'^[a-zA-Z0-9_-]{10,11}$', embed_path):
                return f"https://www.youtube.com/embed/{embed_path}"
        
        # Try to get video ID from query parameter (youtube.com/watch?v=VIDEO_ID)
        if parsed.path == '/watch' or parsed.path.startswith('/watch/'):
            query_params = parse_qs(parsed.query)
            video_id = query_params.get('v', [None])[0]
        
        # Try to get video ID from path (youtu.be/VIDEO_ID)
        if not video_id and 'youtu.be' in parsed.netloc:
            path = parsed.path.lstrip('/')
            # Remove query params and fragments
            video_id = path.split('?')[0].split('&')[0].split('#')[0]
        
        # Validate and return YouTube embed URL
        if video_id:
            # Clean up video ID - remove any trailing parameters
            video_id = video_id.split('&')[0].split('#')[0].strip()
            # YouTube video IDs are exactly 11 characters (alphanumeric, -, _)
            # Validate it matches the expected pattern
            if video_id and re.match(r'^[a-zA-Z0-9_-]{10,11}$', video_id):
                return f"https://www.youtube.com/embed/{video_id}"
    
    # Vimeo: vimeo.com/VIDEO_ID
    if 'vimeo.com' in parsed.netloc:
        video_id = None
        
        # Already an embed URL
        if 'player.vimeo.com' in parsed.netloc:
            # Clean up any query parameters
            clean_url = f"{parsed.scheme}://{parsed.netloc}{parsed.path}"
            return clean_url
        
        # Extract video ID from path
        path_parts = [p for p in parsed.path.strip('/').split('/') if p]
        for part in path_parts:
            if part.isdigit():
                video_id = part
                break
        
        if video_id:
            return f"https://player.vimeo.com/video/{video_id}"
    
    # Fallback to regex extraction if URL parsing didn't work
    return _extract_video_id_regex(original_url)


def _extract_video_id_regex(url):
    """
    Fallback regex-based extraction for video IDs.
    Used when URL parsing fails or as a backup method.
    """
    # YouTube: youtube.com/watch?v=VIDEO_ID
    youtube_watch_match = re.search(r'youtube\.com/watch\?v=([a-zA-Z0-9_-]{10,11})', url)
    if youtube_watch_match:
        return f"https://www.youtube.com/embed/{youtube_watch_match.group(1)}"
    
    # YouTube: youtu.be/VIDEO_ID
    youtube_short_match = re.search(r'youtu\.be/([a-zA-Z0-9_-]{10,11})', url)
    if youtube_short_match:
        return f"https://www.youtube.com/embed/{youtube_short_match.group(1)}"
    
    # YouTube: Already an embed URL
    youtube_embed_match = re.search(r'youtube\.com/embed/([a-zA-Z0-9_-]{10,11})', url)
    if youtube_embed_match:
        return f"https://www.youtube.com/embed/{youtube_embed_match.group(1)}"
    
    # Vimeo: vimeo.com/VIDEO_ID
    vimeo_match = re.search(r'vimeo\.com/(\d+)', url)
    if vimeo_match:
        return f"https://player.vimeo.com/video/{vimeo_match.group(1)}"
    
    # If we can't recognize it, return empty string (don't embed unknown URLs)
    return ""