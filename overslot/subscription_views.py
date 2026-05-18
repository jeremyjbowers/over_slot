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
from django.db import IntegrityError
from django.core.cache import cache
from django.urls import reverse
from django.utils import timezone

from overslot.models import Subscription
from overslot.pricing import get_price_id, get_default_amounts

logger = logging.getLogger(__name__)

# Shown after checkout / sync issues so paying customers have a no-support recovery path.
STRIPE_SELF_HEAL_CTA = (
    ' If premium pages stay locked, open Subscription settings and use '
    '"Refresh subscription status from Stripe".'
)


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
    except (KeyError, AttributeError, TypeError):
        return default
    return val if val is not None else default


def _stripe_event_type(event):
    return _stripe_pick(event, 'type') or getattr(event, 'type', None)


def _stripe_event_data_object(event):
    data = _stripe_pick(event, 'data')
    if data is None:
        return None
    return _stripe_pick(data, 'object')


def _assign_if_present(timestamp_to_dt_fn, subscription_obj, field_name, stripe_value):
    """Only update model field when Stripe sent a value (avoid wiping with None)."""
    if stripe_value is None:
        return
    setattr(subscription_obj, field_name, timestamp_to_dt_fn(stripe_value))


_GRANTABLE_SUB_STATUSES = ('active', 'trialing', 'past_due')
_SUB_STATUS_PRIORITY = {'active': 3, 'trialing': 2, 'past_due': 1}


def _pick_subscription_for_customer_access(customer_id, preferred_subscription_id=None):
    """
    Resolve the Stripe Subscription row that should drive access for this Customer.

    When Checkout created duplicate Stripe subscriptions, Stripe returns multiple rows; prefer
    the Checkout session subscription id when it appears, otherwise prefer active > trialing >
    past_due, then newest by created timestamp.
    """
    if not customer_id:
        return None
    candidates = []
    for status in _GRANTABLE_SUB_STATUSES:
        try:
            resp = stripe.Subscription.list(
                customer=customer_id,
                status=status,
                limit=30,
                expand=['data.items.data.price'],
            )
            candidates.extend(list(resp.data))
        except stripe.error.StripeError:
            logger.exception('_pick_subscription_for_customer_access Subscription.list failed')
    if not candidates:
        return None

    if preferred_subscription_id:
        for sub in candidates:
            if getattr(sub, 'id', None) == preferred_subscription_id:
                return sub

    candidates.sort(
        key=lambda s: (
            _SUB_STATUS_PRIORITY.get(getattr(s, 'status', '') or '', 0),
            getattr(s, 'created', 0) or 0,
        ),
        reverse=True,
    )
    return candidates[0]


def apply_stripe_subscription_to_record(local_sub, stripe_subscription):
    """Populate local Subscription fields from Stripe Subscription.retrieve() result."""
    sid = getattr(stripe_subscription, 'id', None)
    if not sid:
        logger.warning('apply_stripe_subscription_to_record: missing subscription id on Stripe object')
        return

    local_sub.stripe_subscription_id = sid
    status = getattr(stripe_subscription, 'status', None)
    if status:
        local_sub.status = status
    cp_start = getattr(stripe_subscription, 'current_period_start', None)
    cp_end = getattr(stripe_subscription, 'current_period_end', None)
    # Older/newer Stripe API payloads and transient states omit period fields — treat as absent, not fatal.
    if cp_start is not None:
        local_sub.current_period_start = stripe_timestamp_to_datetime(cp_start)
    if cp_end is not None:
        local_sub.current_period_end = stripe_timestamp_to_datetime(cp_end)

    items = getattr(stripe_subscription, 'items', None)
    data = getattr(items, 'data', None) if items is not None else None
    if data:
        try:
            row0 = data[0]
        except (IndexError, KeyError, TypeError):
            row0 = None
        if row0 is not None:
            price_data = getattr(row0, 'price', None)
            if price_data is not None:
                pid = getattr(price_data, 'id', None)
                if pid:
                    local_sub.price_id = pid
                nickname = getattr(price_data, 'nickname', None) or ''
                if nickname:
                    local_sub.plan_name = nickname

    if not local_sub.plan_name:
        local_sub.plan_name = 'Premium Plan'


def sync_subscription_from_checkout_session(user, session):
    """
    Upsert local Subscription using a completed Stripe Checkout Session.
    Accepts webhook dict payload or a StripeObject from Session.retrieve(...).
    """
    def _sess(key):
        return _stripe_pick(session, key)

    if _sess('mode') != 'subscription' or _sess('payment_status') != 'paid':
        return None

    customer_id = _stripe_object_id(_sess('customer'))
    subscription_id = _stripe_object_id(_sess('subscription'))
    local_sub, _ = Subscription.objects.get_or_create(user=user)

    if customer_id:
        local_sub.stripe_customer_id = customer_id

    chosen_sub = None
    if subscription_id:
        try:
            chosen_sub = stripe.Subscription.retrieve(
                subscription_id,
                expand=['items.data.price'],
            )
        except stripe.error.StripeError:
            logger.exception(
                'Subscription.retrieve failed during checkout sync sub_id=%s customer=%s',
                subscription_id,
                customer_id,
            )

    if chosen_sub is None and customer_id:
        chosen_sub = _pick_subscription_for_customer_access(customer_id, subscription_id)

    if chosen_sub:
        apply_stripe_subscription_to_record(local_sub, chosen_sub)

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

    has_full_access = bool(subscription and subscription.can_access_premium_content())

    context = {
        'subscription': subscription,
        'stripe_publishable_key': settings.STRIPE_PUBLISHABLE_KEY,
        'monthly_amount': monthly_amount,
        'annual_amount': annual_amount,
        'annual_equiv_monthly': annual_equiv_monthly,
        'has_monthly_price': has_monthly_price,
        'has_annual_price': has_annual_price,
        'has_any_price': has_any_price,
        'show_subscription_resync_card': (not has_full_access)
            and (
                subscription is None
                or getattr(subscription, 'status', None) != 'canceled'
            ),
    }
    return render(request, 'subscription/dashboard.html', context)


@login_required
@require_POST
def stripe_subscription_resync(request):
    """
    Pull subscription state directly from Stripe and update the local Subscription row.

    Recovery path when payments succeeded but webhooks or partial payloads left the site stale.
    """
    cache_key = f'stripe_sub_resync_throttle:{request.user.pk}'
    if cache.get(cache_key):
        messages.info(request, 'Please wait a minute before syncing again.')
        return redirect('subscription_dashboard')

    if not getattr(settings, 'STRIPE_SECRET_KEY', None):
        messages.error(request, 'Billing sync is unavailable right now. Please try again later.')
        return redirect('subscription_dashboard')

    cooldown = int(getattr(settings, 'STRIPE_RESYNC_COOLDOWN_SECONDS', 45))
    cache.set(cache_key, 1, max(cooldown, 15))

    sub, _ = Subscription.objects.get_or_create(user=request.user)

    cid = sub.stripe_customer_id
    if not cid:
        email = (request.user.email or '').strip()
        if email:
            try:
                cust_list = stripe.Customer.list(email=email, limit=10)
                if cust_list.data:
                    newest = sorted(
                        cust_list.data,
                        key=lambda c: getattr(c, 'created', 0) or 0,
                        reverse=True,
                    )[0]
                    nid = getattr(newest, 'id', None)
                    if nid:
                        try:
                            sub.stripe_customer_id = nid
                            sub.save()
                            cid = nid
                        except IntegrityError:
                            logger.warning(
                                'stripe_subscription_resync: customer %s already linked elsewhere',
                                nid,
                            )
                            messages.error(
                                request,
                                'We found Stripe billing activity for this email, but those charges are tied to '
                                'a different Overslot login. Email support from the receipt address if needed.'
                            )
                            return redirect('subscription_dashboard')
            except stripe.error.StripeError:
                logger.exception('stripe_subscription_resync Customer.list(email=...)')

    if not cid:
        messages.warning(
            request,
            'No Stripe billing profile matched this account yet. If you just checked out, wait a minute and try again. '
            'Confirm you are logged into the same email Stripe emailed your receipt.'
        )
        return redirect('subscription_dashboard')

    try:
        chosen = _pick_subscription_for_customer_access(cid)
        if not chosen:
            messages.warning(
                request,
                'Stripe does not show an active membership for your billing profile right now '
                '(it may still be syncing, canceled, incomplete, or refunded).'
            )
            return redirect('subscription_dashboard')

        apply_stripe_subscription_to_record(sub, chosen)
        sub.save()
        if sub.can_access_premium_content():
            messages.success(
                request,
                'Synced with Stripe. Refresh any locked page—you should now have premium access.'
            )
        else:
            messages.warning(
                request,
                'Stripe synced, but the subscription status still does not qualify for premium access '
                '(for example incomplete checkout). Retry in a minute, or contact support with your Stripe receipt.'
            )
    except stripe.error.StripeError:
        logger.exception('stripe_subscription_resync')
        messages.error(request, 'Could not reach Stripe right now. Please try again shortly.')

    return redirect('subscription_dashboard')


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
            meta_raw = _stripe_pick(session, 'metadata')
            checkout_user_id = _stripe_pick(meta_raw, 'user_id')

            payment_status = getattr(session, 'payment_status', None)
            session_mode = getattr(session, 'mode', None)

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
                    + STRIPE_SELF_HEAL_CTA
                )
            elif payment_status != 'paid' or session_mode != 'subscription':
                messages.info(
                    request,
                    'Your payment may still be processing. Wait a moment, then try the subscription dashboard.'
                    + STRIPE_SELF_HEAL_CTA
                )
            else:
                sync_subscription_from_checkout_session(request.user, session)
                try:
                    sub_row = Subscription.objects.get(user=request.user)
                    if sub_row.can_access_premium_content():
                        messages.success(request, 'Your subscription has been activated.')
                    else:
                        messages.warning(
                            request,
                            'Stripe shows a completed payment, but premium access is not active in our system yet.'
                            + STRIPE_SELF_HEAL_CTA
                        )
                except Subscription.DoesNotExist:
                    messages.warning(
                        request,
                        'We could not create a subscription record for your account after checkout.'
                        + STRIPE_SELF_HEAL_CTA
                    )
        except stripe.error.InvalidRequestError:
            messages.warning(
                request,
                'That checkout session is invalid or has expired.' + STRIPE_SELF_HEAL_CTA
            )
        except Exception as e:
            logger.exception('subscription_success reconcile failed session_id=%s', session_id)
            messages.warning(
                request,
                'We could not confirm your checkout from Stripe automatically. '
                'If billing shows a charge but you still lack access, wait a minute and try syncing from the dashboard.'
                + STRIPE_SELF_HEAL_CTA
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
    event_type = _stripe_event_type(event)
    data_object = _stripe_event_data_object(event)

    try:
        if event_type == 'checkout.session.completed' and data_object is not None:
            handle_checkout_session_completed(data_object)

        elif event_type == 'customer.subscription.created' and data_object is not None:
            handle_subscription_created(data_object)

        elif event_type == 'customer.subscription.updated' and data_object is not None:
            handle_subscription_updated(data_object)

        elif event_type == 'customer.subscription.deleted' and data_object is not None:
            handle_subscription_deleted(data_object)

        elif event_type == 'invoice.payment_succeeded' and data_object is not None:
            handle_payment_succeeded(data_object)

        elif event_type == 'invoice.payment_failed' and data_object is not None:
            handle_payment_failed(data_object)
    except Exception:
        logger.exception('Unhandled error processing Stripe webhook type=%s', event_type)
        return HttpResponse(status=500)

    return HttpResponse(status=200)


def handle_checkout_session_completed(session):
    """Handle completed checkout session."""
    try:
        meta = _stripe_pick(session, 'metadata')
        user_id = _stripe_pick(meta, 'user_id') if meta is not None else None
        if user_id:
            user = User.objects.get(id=user_id)
            sync_subscription_from_checkout_session(user, session)
    except User.DoesNotExist:
        pass


def handle_subscription_created(subscription_data):
    """Handle subscription creation."""
    try:
        customer_id = _stripe_object_id(_stripe_pick(subscription_data, 'customer'))
        if not customer_id:
            return
        subscription_obj = Subscription.objects.get(stripe_customer_id=customer_id)

        sub_id = _stripe_pick(subscription_data, 'id')
        if sub_id:
            subscription_obj.stripe_subscription_id = sub_id
        status = _stripe_pick(subscription_data, 'status')
        if status:
            subscription_obj.status = status

        _assign_if_present(
            stripe_timestamp_to_datetime,
            subscription_obj,
            'current_period_start',
            _stripe_pick(subscription_data, 'current_period_start'),
        )
        _assign_if_present(
            stripe_timestamp_to_datetime,
            subscription_obj,
            'current_period_end',
            _stripe_pick(subscription_data, 'current_period_end'),
        )

        # Get plan details
        items = _stripe_pick(subscription_data, 'items')
        row_data = _stripe_pick(items, 'data') if items is not None else None
        if row_data:
            first = row_data[0]
            price_data = _stripe_pick(first, 'price')
            if price_data:
                pid = _stripe_pick(price_data, 'id')
                if pid:
                    subscription_obj.price_id = pid
                nickname = _stripe_pick(price_data, 'nickname')
                if nickname:
                    subscription_obj.plan_name = nickname

        if not subscription_obj.plan_name:
            subscription_obj.plan_name = 'Premium Plan'

        subscription_obj.save()
    except Subscription.DoesNotExist:
        pass


def handle_subscription_updated(subscription_data):
    """Handle subscription updates."""
    try:
        sub_id = _stripe_pick(subscription_data, 'id')
        if not sub_id:
            return
        subscription_obj = Subscription.objects.get(stripe_subscription_id=sub_id)

        status = _stripe_pick(subscription_data, 'status')
        if status:
            subscription_obj.status = status
        _assign_if_present(
            stripe_timestamp_to_datetime,
            subscription_obj,
            'current_period_start',
            _stripe_pick(subscription_data, 'current_period_start'),
        )
        _assign_if_present(
            stripe_timestamp_to_datetime,
            subscription_obj,
            'current_period_end',
            _stripe_pick(subscription_data, 'current_period_end'),
        )
        subscription_obj.save()
    except Subscription.DoesNotExist:
        pass


def handle_subscription_deleted(subscription_data):
    """Handle subscription deletion."""
    try:
        sub_id = _stripe_pick(subscription_data, 'id')
        if not sub_id:
            return
        subscription_obj = Subscription.objects.get(stripe_subscription_id=sub_id)
        subscription_obj.status = 'canceled'
        subscription_obj.save()
    except Subscription.DoesNotExist:
        pass


def handle_payment_succeeded(invoice):
    """Handle successful payment."""
    subscription_id = _stripe_object_id(_stripe_pick(invoice, 'subscription'))
    customer_id = _stripe_object_id(_stripe_pick(invoice, 'customer'))
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
        subscription_id = _stripe_object_id(_stripe_pick(invoice, 'subscription'))
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
