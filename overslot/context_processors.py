from django.conf import settings


def settings_context(request):
    """
    Context processor to make certain settings available in templates.
    """
    return {
        'settings': {
            'SUBSCRIPTION_PRICE_MONTHLY': getattr(settings, 'SUBSCRIPTION_PRICE_MONTHLY', 9.99),
        }
    } 