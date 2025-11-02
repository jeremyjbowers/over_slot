from typing import Optional, Tuple
import json
from django.conf import settings

from .models import SubscriptionPlan, SubscriptionPrice


DEFAULT_PLAN_SLUG = "standard"
DEFAULT_CURRENCY = "usd"


def get_price_id(plan_slug: str, interval: str, currency: str = DEFAULT_CURRENCY) -> Optional[str]:
    """
    Resolve the active default Stripe price id for the given plan, interval and currency.
    Priority: DB default -> env JSON mapping -> legacy single price setting.
    """
    # 1) DB lookup
    try:
        plan = SubscriptionPlan.objects.get(slug=plan_slug, active=True)
        price = (
            SubscriptionPrice.objects
            .filter(plan=plan, interval=interval, currency=currency, is_active=True, is_default_for_interval=True)
            .order_by("-created")
            .first()
        )
        if price and price.stripe_price_id:
            return price.stripe_price_id
    except SubscriptionPlan.DoesNotExist:
        pass

    # 2) Env JSON fallback: {"standard": {"usd": {"month": "price_...", "year": "price_..."}}}
    mapping_raw = getattr(settings, "SUBSCRIPTION_PRICE_IDS_JSON", None)
    if mapping_raw:
        try:
            mapping = mapping_raw if isinstance(mapping_raw, dict) else json.loads(mapping_raw)
            maybe = (
                mapping
                .get(plan_slug, {})
                .get(currency, {})
                .get(interval)
            )
            if maybe:
                return maybe
        except Exception:
            # Silently ignore malformed JSON; logs can be added if desired
            pass

    # 3) Legacy single price id (monthly only). Kept for backwards compat.
    legacy = getattr(settings, "STRIPE_PRICE_ID", None)
    if legacy and interval == "month":
        return legacy

    return None


def get_default_amounts(plan_slug: str = DEFAULT_PLAN_SLUG, currency: str = DEFAULT_CURRENCY) -> Tuple[Optional[float], Optional[float]]:
    """
    Return (monthly_amount, annual_amount) in display currency for the plan, if present in DB; otherwise fall back to settings.
    """
    monthly_amount = None
    annual_amount = None

    try:
        plan = SubscriptionPlan.objects.get(slug=plan_slug, active=True)
        monthly = (
            SubscriptionPrice.objects
            .filter(plan=plan, interval="month", currency=currency, is_active=True, is_default_for_interval=True)
            .order_by("-created").first()
        )
        annual = (
            SubscriptionPrice.objects
            .filter(plan=plan, interval="year", currency=currency, is_active=True, is_default_for_interval=True)
            .order_by("-created").first()
        )
        if monthly:
            monthly_amount = float(monthly.amount_decimal)
        if annual:
            annual_amount = float(annual.amount_decimal)
    except SubscriptionPlan.DoesNotExist:
        pass

    # Fallbacks from settings
    if monthly_amount is None:
        monthly_amount = float(getattr(settings, "SUBSCRIPTION_PRICE_MONTHLY", 0))
    if annual_amount is None:
        annual_amount = float(getattr(settings, "SUBSCRIPTION_PRICE_ANNUAL", 0))

    return monthly_amount, annual_amount
