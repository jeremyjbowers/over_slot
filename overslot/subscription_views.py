import logging
import stripe
from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.shortcuts import render, redirect
from django.http import HttpResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST
from django.contrib import messages
from django.urls import reverse
from django.utils import timezone

from overslot.models import Subscription
from overslot.pricing import get_price_id, get_default_amounts

logger = logging.getLogger(__name__)

# Initialize Stripe
stripe.api_key = settings.STRIPE_SECRET_KEY


def _stripe_object_id(field):
    if field is None:
        return None
    if isinstance(field, str):
        return field
    return getattr(field, 'id', None)


def _stripe_pick(obj, key, default=None):
    """
    Safely read a field from Stripe webhook payloads.

    Newer stripe-python parses `event.data.object` as StripeObject (`obj['status']`
    works, but `.get('status')` does not — it raises AttributeError/KeyError).
    """
    if obj is None:
        return default
    if isinstance(obj, dict):
        return obj.get(key, default)
    try:
        val = obj[key]
    except KeyError:
        return default
    return val if val is not None else default


def apply_stripe_subscription_to_record(local_sub, stripe_subscription):
    """Populate local Subscription fields from Stripe Subscription.retrieve() result."""
    local_sub.stripe_subscription_id = stripe_subscription.id
    local_sub.status = stripe_subscription.status
    local_sub.current_period_start = stripe_timestamp_to_datetime(stripe_subscription.current_period_start)
    local_sub.current_period_end = stripe_timestamp_to_datetime(stripe_subscription.current_period_end)
    items = getattr(stripe_subscription, 'items', None)
    if items and getattr(items, 'data', None) and stripe_subscription.items.data:
        price_data = stripe_subscription.items.data[0].price
        local_sub.price_id = price_data.id
        nickname = getattr(price_data, 'nickname', None) or ''
        local_sub.plan_name = nickname if nickname else local_sub.plan_name or 'Premium Plan'
    elif not local_sub.plan_name:
        local_sub.plan_name = 'Premium Plan'


def sync_subscription_from_checkout_session(user, session):
    """
    Upsert local Subscription using a completed Stripe Checkout Session.
    Accepts webhook dict payload or a StripeObject from Session.retrieve(...).
    """
    def _sess(key):
        return session[key] if isinstance(session, dict) else getattr(session, key, None)

    if _sess('mode') != 'subscription' or _sess('payment_status') != 'paid':
        return None

    customer_id = _stripe_object_id(_sess('customer'))
    subscription_id = _stripe_object_id(_sess('subscription'))
    local_sub, _ = Subscription.objects.get_or_create(user=user)

    if customer_id:
        local_sub.stripe_customer_id = customer_id

    stripe_sub_full = None
    if subscription_id:
        stripe_sub_full = stripe.Subscription.retrieve(subscription_id)

    if stripe_sub_full:
        apply_stripe_subscription_to_record(local_sub, stripe_sub_full)

    local_sub.save()
    return local_sub


@login_required
def subscription_dashboard(request):
    """Dashboard for managing user subscriptions."""
    try:
        subscription = request.user.subscription
    except Subscription.DoesNotExist:
        subscription = None

    # Fetch display amounts (DB-first, fallback to settings)
    monthly_amount, annual_amount = get_default_amounts()
    annual_equiv_monthly = round((annual_amount or 0) / 12.0, 2) if annual_amount else None

    # Price availability flags for templates
    monthly_price_id = get_price_id(plan_slug='standard', interval='month', currency='usd')
    annual_price_id = get_price_id(plan_slug='standard', interval='year', currency='usd')
    has_monthly_price = bool(monthly_price_id)
    has_annual_price = bool(annual_price_id)
    has_any_price = has_monthly_price or has_annual_price

    context = {
        'subscription': subscription,
        'stripe_publishable_key': settings.STRIPE_PUBLISHABLE_KEY,
        'monthly_amount': monthly_amount,
        'annual_amount': annual_amount,
        'annual_equiv_monthly': annual_equiv_monthly,
        'has_monthly_price': has_monthly_price,
        'has_annual_price': has_annual_price,
        'has_any_price': has_any_price,
    }
    return render(request, 'subscription/dashboard.html', context)


@login_required
def create_checkout_session(request):
    """Create a Stripe checkout session for subscription."""
    if request.method == 'POST':
        try:
            # Resolve requested interval; default to month
            interval = request.POST.get('interval', 'month')
            plan_slug = request.POST.get('plan', 'standard')

            # Get or create subscription record
            subscription, created = Subscription.objects.get_or_create(
                user=request.user
            )
            
            # Create or get Stripe customer
            if not subscription.stripe_customer_id:
                customer = stripe.Customer.create(
                    email=request.user.email,
                    metadata={'user_id': request.user.id}
                )
                subscription.stripe_customer_id = customer.id
                subscription.save()

            # Resolve price id
            price_id = get_price_id(plan_slug=plan_slug, interval=interval, currency='usd')
            if not price_id:
                messages.error(request, 'Pricing is temporarily unavailable. Please try again later.')
                return redirect('subscription_dashboard')
            
            base_success = request.build_absolute_uri(reverse('subscription_success'))
            sep = '&' if ('?' in base_success) else '?'
            success_url = f'{base_success}{sep}session_id={{CHECKOUT_SESSION_ID}}'

            minute_bucket = timezone.now().strftime('%Y%m%d%H%M')
            checkout_session = stripe.checkout.Session.create(
                customer=subscription.stripe_customer_id,
                payment_method_types=['card'],
                line_items=[{
                    'price': price_id,
                    'quantity': 1,
                }],
                mode='subscription',
                allow_promotion_codes=False,
                success_url=success_url,
                cancel_url=request.build_absolute_uri(reverse('subscription_dashboard')),
                metadata={'user_id': request.user.id, 'plan': plan_slug, 'interval': interval},
                idempotency_key=f'checkout-session-user-{request.user.pk}-price-{price_id}-{minute_bucket}',
            )
            
            return redirect(checkout_session.url)
            
        except Exception as e:
            messages.error(request, f'Error creating checkout session: {str(e)}')
            return redirect('subscription_dashboard')
    
    return redirect('subscription_dashboard')


@login_required
def subscription_success(request):
    """After Checkout: reconcile subscription from Stripe using session_id (webhook fallback)."""
    session_id = request.GET.get('session_id')
    if session_id and settings.STRIPE_SECRET_KEY:
        try:
            session = stripe.checkout.Session.retrieve(
                session_id,
                expand=['subscription'],
            )
            meta = getattr(session, 'metadata', None)
            md = dict(meta) if meta else {}
            checkout_user_id = md.get('user_id')
            if checkout_user_id is not None:
                verified = str(checkout_user_id) == str(request.user.pk)
            else:
                cust_id = _stripe_object_id(session.customer)
                verified = False
                if cust_id:
                    customer = stripe.Customer.retrieve(cust_id)
                    stripe_email = (getattr(customer, 'email', None) or '').strip().lower()
                    user_email = (request.user.email or '').strip().lower()
                    verified = stripe_email and stripe_email == user_email

            if not verified:
                messages.warning(
                    request,
                    'We could not match this checkout to your account. If you were charged, contact support.'
                )
            elif session.payment_status != 'paid' or session.mode != 'subscription':
                messages.info(request, 'Your payment may still be processing. Refresh in a moment or check the subscription dashboard.')
            else:
                sync_subscription_from_checkout_session(request.user, session)
                messages.success(request, 'Your subscription has been activated.')
        except stripe.error.InvalidRequestError:
            messages.warning(request, 'That checkout session is invalid or has expired.')
        except Exception as e:
            logger.exception('subscription_success reconcile failed session_id=%s', session_id)
            messages.warning(
                request,
                'We could not confirm your checkout from Stripe automatically. '
                'If billing shows a charge but you still lack access, try again shortly or contact support.'
            )
    else:
        messages.success(request, 'Your subscription has been created successfully!')
    return render(request, 'subscription/success.html')


@login_required
def cancel_subscription(request):
    """Cancel user's subscription."""
    if request.method == 'POST':
        try:
            subscription = request.user.subscription
            if subscription.stripe_subscription_id:
                # Cancel the subscription in Stripe
                stripe.Subscription.modify(
                    subscription.stripe_subscription_id,
                    cancel_at_period_end=True
                )
                messages.success(request, 'Your subscription will be cancelled at the end of the current billing period.')
            else:
                messages.error(request, 'No active subscription found.')
                
        except Subscription.DoesNotExist:
            messages.error(request, 'No subscription found.')
        except Exception as e:
            messages.error(request, f'Error cancelling subscription: {str(e)}')
    
    return redirect('subscription_dashboard')


@login_required
def manage_billing(request):
    """Create a Stripe billing portal session."""
    try:
        subscription = request.user.subscription
        if subscription.stripe_customer_id:
            portal_session = stripe.billing_portal.Session.create(
                customer=subscription.stripe_customer_id,
                return_url=request.build_absolute_uri(reverse('subscription_dashboard')),
            )
            return redirect(portal_session.url)
        else:
            messages.error(request, 'No billing information found.')
    except Subscription.DoesNotExist:
        messages.error(request, 'No subscription found.')
    except Exception as e:
        messages.error(request, f'Error accessing billing portal: {str(e)}')
    
    return redirect('subscription_dashboard')


@csrf_exempt
@require_POST
def stripe_webhook(request):
    """Handle Stripe webhooks to update subscription status."""
    payload = request.body
    sig_header = request.META.get('HTTP_STRIPE_SIGNATURE')
    endpoint_secret = settings.STRIPE_WEBHOOK_SECRET
    
    try:
        event = stripe.Webhook.construct_event(
            payload, sig_header, endpoint_secret
        )
    except ValueError:
        # Invalid payload
        return HttpResponse(status=400)
    except stripe.error.SignatureVerificationError:
        # Invalid signature
        return HttpResponse(status=400)
    
    # Handle the event
    if event['type'] == 'checkout.session.completed':
        session = event['data']['object']
        handle_checkout_session_completed(session)
    
    elif event['type'] == 'customer.subscription.created':
        subscription_data = event['data']['object']
        handle_subscription_created(subscription_data)
    
    elif event['type'] == 'customer.subscription.updated':
        subscription_data = event['data']['object']
        handle_subscription_updated(subscription_data)
    
    elif event['type'] == 'customer.subscription.deleted':
        subscription_data = event['data']['object']
        handle_subscription_deleted(subscription_data)
    
    elif event['type'] == 'invoice.payment_succeeded':
        invoice = event['data']['object']
        handle_payment_succeeded(invoice)
    
    elif event['type'] == 'invoice.payment_failed':
        invoice = event['data']['object']
        handle_payment_failed(invoice)
    
    return HttpResponse(status=200)


def handle_checkout_session_completed(session):
    """Handle completed checkout session."""
    try:
        meta = _stripe_pick(session, 'metadata') or {}
        user_id = _stripe_pick(meta, 'user_id')
        if user_id:
            user = User.objects.get(id=user_id)
            sync_subscription_from_checkout_session(user, session)
    except User.DoesNotExist:
        pass


def handle_subscription_created(subscription_data):
    """Handle subscription creation."""
    try:
        customer_id = _stripe_pick(subscription_data, 'customer')
        subscription_obj = Subscription.objects.get(stripe_customer_id=customer_id)
        
        subscription_obj.stripe_subscription_id = _stripe_pick(subscription_data, 'id')
        subscription_obj.status = _stripe_pick(subscription_data, 'status')
        subscription_obj.current_period_start = stripe_timestamp_to_datetime(
            _stripe_pick(subscription_data, 'current_period_start')
        )
        subscription_obj.current_period_end = stripe_timestamp_to_datetime(
            _stripe_pick(subscription_data, 'current_period_end')
        )
        
        # Get plan details
        items = _stripe_pick(subscription_data, 'items')
        row_data = _stripe_pick(items, 'data') if items is not None else None
        if row_data:
            first = row_data[0]
            price_data = _stripe_pick(first, 'price')
            if price_data:
                subscription_obj.price_id = _stripe_pick(price_data, 'id')
                nickname = _stripe_pick(price_data, 'nickname')
                subscription_obj.plan_name = nickname or 'Premium Plan'
        
        subscription_obj.save()
    except Subscription.DoesNotExist:
        pass


def handle_subscription_updated(subscription_data):
    """Handle subscription updates."""
    try:
        subscription_obj = Subscription.objects.get(
            stripe_subscription_id=subscription_data['id']
        )
        
        subscription_obj.status = _stripe_pick(subscription_data, 'status')
        subscription_obj.current_period_start = stripe_timestamp_to_datetime(
            _stripe_pick(subscription_data, 'current_period_start')
        )
        subscription_obj.current_period_end = stripe_timestamp_to_datetime(
            _stripe_pick(subscription_data, 'current_period_end')
        )
        subscription_obj.save()
    except Subscription.DoesNotExist:
        pass


def handle_subscription_deleted(subscription_data):
    """Handle subscription deletion."""
    try:
        subscription_obj = Subscription.objects.get(
            stripe_subscription_id=subscription_data['id']
        )
        subscription_obj.status = 'canceled'
        subscription_obj.save()
    except Subscription.DoesNotExist:
        pass


def handle_payment_succeeded(invoice):
    """Handle successful payment."""
    subscription_id = _stripe_pick(invoice, 'subscription')
    customer_id = _stripe_pick(invoice, 'customer')
    subscription_obj = None
    try:
        if subscription_id:
            subscription_obj = Subscription.objects.get(stripe_subscription_id=subscription_id)
    except Subscription.DoesNotExist:
        pass
    try:
        if subscription_obj is None and customer_id:
            subscription_obj = Subscription.objects.get(stripe_customer_id=customer_id)
            if subscription_id and not subscription_obj.stripe_subscription_id:
                subscription_obj.stripe_subscription_id = subscription_id
    except Subscription.DoesNotExist:
        pass
    except Subscription.MultipleObjectsReturned:
        logger.warning(
            'invoice.payment_succeeded: multiple Subscription rows for customer %s',
            customer_id,
        )
        subscription_obj = None

    if subscription_obj:
        subscription_obj.status = 'active'
        subscription_obj.save()


def handle_payment_failed(invoice):
    """Handle failed payment."""
    try:
        subscription_id = _stripe_pick(invoice, 'subscription')
        if subscription_id:
            subscription_obj = Subscription.objects.get(
                stripe_subscription_id=subscription_id
            )
            # Don't immediately cancel, Stripe will handle retry logic
            subscription_obj.status = 'past_due'
            subscription_obj.save()
    except Subscription.DoesNotExist:
        pass


def stripe_timestamp_to_datetime(timestamp):
    """Convert Stripe timestamp to Django datetime."""
    from datetime import datetime
    return datetime.fromtimestamp(timestamp) if timestamp else None
