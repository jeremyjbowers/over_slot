from django.conf import settings
from django.utils import timezone
from dateutil import parser
from datetime import datetime, date
from .pricing import get_price_id
from . import models


def settings_context(request):
    """
    Context processor to make certain settings available in templates.
    """
    # Resolve availability of Stripe price ids for template conditionals
    try:
        monthly_price_id = get_price_id(plan_slug='standard', interval='month', currency='usd')
    except Exception:
        monthly_price_id = None
    try:
        annual_price_id = get_price_id(plan_slug='standard', interval='year', currency='usd')
    except Exception:
        annual_price_id = None

    has_monthly_price = bool(monthly_price_id)
    has_annual_price = bool(annual_price_id)
    has_any_price = has_monthly_price or has_annual_price

    # Check if there are any published mock drafts
    has_published_mock_drafts = models.Ranking.objects.filter(
        is_mock_draft=True, 
        publish=True
    ).exists()

    # Check if there are games today (or if we're past opening day)
    has_live_games = False
    try:
        season_opening_day = parser.parse(getattr(settings, 'SEASON_OPENING_DAY', '2026-02-12')).date()
        today = timezone.now().date()
        display_date = max(today, season_opening_day)
        
        # Check if there are any games for today/opening day
        start_of_day = timezone.make_aware(datetime.combine(display_date, datetime.min.time()))
        end_of_day = timezone.make_aware(datetime.combine(display_date, datetime.max.time()))
        
        has_live_games = models.Game.objects.filter(
            active=True,
            start_datetime__gte=start_of_day,
            start_datetime__lte=end_of_day
        ).exists()
    except Exception:
        # If there's any error checking, default to False
        has_live_games = False

    return {
        'settings': {
            'SUBSCRIPTION_PRICE_MONTHLY': getattr(settings, 'SUBSCRIPTION_PRICE_MONTHLY', 9.99),
        },
        # Template hooks for pricing availability
        'has_monthly_price': has_monthly_price,
        'has_annual_price': has_annual_price,
        'has_any_price': has_any_price,
        # Template hook for mock drafts visibility
        'has_published_mock_drafts': has_published_mock_drafts,
        # Template hook for live games nav styling
        'has_live_games': has_live_games,
    }