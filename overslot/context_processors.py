from django.conf import settings
from .pricing import get_price_id


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

    return {
        'settings': {
            'SUBSCRIPTION_PRICE_MONTHLY': getattr(settings, 'SUBSCRIPTION_PRICE_MONTHLY', 9.99),
        },
        # Template hooks for pricing availability
        'has_monthly_price': has_monthly_price,
        'has_annual_price': has_annual_price,
        'has_any_price': has_any_price,
    }