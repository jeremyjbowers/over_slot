import logging
import sys
from datetime import UTC, datetime

import stripe
from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.shortcuts import render, redirect
from django.http import HttpResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST
from django.contrib import messages
from django.db import IntegrityError, transaction
from django.core.cache import cache
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils import timezone

from overslot.models import StripeWebhookEvent, Subscription, SubscriptionNotice
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


def _stripe_event_id(event):
    event_id = _stripe_pick(event, 'id')
    if not event_id:
        event_id = getattr(event, 'id', None)
    if not event_id:
        return None
    return str(event_id)


def _stripe_contains(obj, key):
    """True when key is present, including keys whose value is None or False."""
    if obj is None:
        return False
    if isinstance(obj, dict):
        return key in obj
    try:
        obj[key]
    except (KeyError, AttributeError, TypeError, IndexError):
        return False
    return True


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


def _collection_pause_is_set(value):
    """Stripe sets pause_collection to an object while collection is paused, otherwise null."""
    if value is None or value is False or value == '':
        return False
    if isinstance(value, dict):
        return bool(value)
    return True


def apply_stripe_subscription_to_record(
    local_sub,
    stripe_subscription,
    *,
    force_status=None,
    force_collection_paused=None,
):
    """
    Copy Stripe subscription fields onto a local Subscription row.

    Used for both Subscription.retrieve() results and webhook data.object payloads.
    Does not save and does not send mail. Returns False when the Stripe object has no id.
    """
    sid = _stripe_pick(stripe_subscription, 'id') or getattr(stripe_subscription, 'id', None)
    if not sid:
        logger.warning('apply_stripe_subscription_to_record: missing subscription id on Stripe object')
        return False

    local_sub.stripe_subscription_id = sid

    if _stripe_contains(stripe_subscription, 'status'):
        status = _stripe_pick(stripe_subscription, 'status')
        if status:
            local_sub.status = status

    # Older/newer Stripe API payloads and transient states omit period fields — treat as absent, not fatal.
    if _stripe_contains(stripe_subscription, 'current_period_start'):
        cp_start = _stripe_pick(stripe_subscription, 'current_period_start')
        if cp_start is not None:
            local_sub.current_period_start = stripe_timestamp_to_datetime(cp_start)
    if _stripe_contains(stripe_subscription, 'current_period_end'):
        cp_end = _stripe_pick(stripe_subscription, 'current_period_end')
        if cp_end is not None:
            local_sub.current_period_end = stripe_timestamp_to_datetime(cp_end)

    items = _stripe_pick(stripe_subscription, 'items')
    row_data = _stripe_pick(items, 'data') if items is not None else None
    if row_data:
        try:
            row0 = row_data[0]
        except (IndexError, KeyError, TypeError):
            row0 = None
        if row0 is not None:
            price_data = _stripe_pick(row0, 'price')
            if price_data is not None:
                pid = _stripe_pick(price_data, 'id')
                if pid:
                    local_sub.price_id = pid
                nickname = _stripe_pick(price_data, 'nickname') or ''
                if nickname:
                    local_sub.plan_name = nickname

    if not local_sub.plan_name:
        local_sub.plan_name = 'Premium Plan'

    if _stripe_contains(stripe_subscription, 'cancel_at_period_end'):
        local_sub.cancel_at_period_end = bool(
            _stripe_pick(stripe_subscription, 'cancel_at_period_end')
        )

    if _stripe_contains(stripe_subscription, 'canceled_at'):
        raw_canceled = _stripe_pick(stripe_subscription, 'canceled_at')
        local_sub.canceled_at = stripe_timestamp_to_datetime(raw_canceled) if raw_canceled else None

    if _stripe_contains(stripe_subscription, 'pause_collection'):
        local_sub.collection_paused = _collection_pause_is_set(
            _stripe_pick(stripe_subscription, 'pause_collection')
        )

    if force_status:
        local_sub.status = force_status
    if force_collection_paused is not None:
        local_sub.collection_paused = bool(force_collection_paused)

    if local_sub.status == 'canceled' and not local_sub.canceled_at:
        local_sub.canceled_at = timezone.now()

    return True


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
    collection_paused = bool(subscription and subscription.collection_paused)
    period_end_in_future = bool(
        subscription
        and subscription.current_period_end
        and subscription.current_period_end > timezone.now()
    )

    context = {
        'subscription': subscription,
        'stripe_publishable_key': settings.STRIPE_PUBLISHABLE_KEY,
        'monthly_amount': monthly_amount,
        'annual_amount': annual_amount,
        'annual_equiv_monthly': annual_equiv_monthly,
        'has_monthly_price': has_monthly_price,
        'has_annual_price': has_annual_price,
        'has_any_price': has_any_price,
        'period_end_in_future': period_end_in_future,
        'show_subscription_resync_card': (not has_full_access)
            and not collection_paused
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


# Events the Stripe dashboard endpoint should send. Unknown types are stored and acknowledged.
STRIPE_WEBHOOK_EVENT_TYPES = (
    'checkout.session.completed',
    'customer.subscription.created',
    'customer.subscription.updated',
    'customer.subscription.deleted',
    'customer.subscription.paused',
    'customer.subscription.resumed',
    'invoice.paid',
    'invoice.payment_succeeded',
    'invoice.payment_failed',
)


def _stripe_webhook_runs_inline():
    """
    Tests POST a webhook and then read the database, so they must finish inline.

    ``'test' in sys.argv`` covers that without a new setting. Production leaves
    STRIPE_WEBHOOK_INLINE false: the view only stores the event, and
    ``run_stripe_worker`` applies it.
    """
    if 'test' in sys.argv:
        return True
    return bool(getattr(settings, 'STRIPE_WEBHOOK_INLINE', False))


@csrf_exempt
@require_POST
def stripe_webhook(request):
    """
    Handle Stripe webhooks to update subscription status.

    Verify the signature, persist a StripeWebhookEvent, and return. Production does
    not apply the event in this request. Run ``django-admin run_stripe_worker`` as a
    long-running process to apply stored events and reconcile with Stripe.
    Tests and STRIPE_WEBHOOK_INLINE apply the event before the response.
    A duplicate event id that is already processed returns 200 and does not email again.

    Stripe dashboard checklist — send these events:
    - checkout.session.completed
    - customer.subscription.created
    - customer.subscription.updated
    - customer.subscription.deleted
    - customer.subscription.paused
    - customer.subscription.resumed
    - invoice.paid
    - invoice.payment_succeeded
    - invoice.payment_failed
    """
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

    event_type = _stripe_event_type(event) or ''
    event_id = _stripe_event_id(event)
    data_object = _stripe_event_data_object(event)

    record = None
    if event_id:
        record, created = _upsert_stripe_webhook_event(
            event_id,
            event_type,
            _json_safe(event),
        )
        if not created and record.status == StripeWebhookEvent.STATUS_PROCESSED:
            return HttpResponse(status=200)

    # No event id means we cannot queue a replay. Apply it here so it is not dropped.
    run_inline = _stripe_webhook_runs_inline()
    if not event_id and not run_inline:
        logger.warning('Stripe webhook type=%s has no event id; applying inline', event_type)
    if run_inline or not event_id:
        try:
            _run_webhook_handling(record, event_type, data_object, event_id)
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


def handle_subscription_created(subscription_data, event_id=None):
    """Handle subscription creation."""
    try:
        customer_id = _stripe_object_id(_stripe_pick(subscription_data, 'customer'))
        if not customer_id:
            return
        subscription_obj = Subscription.objects.get(stripe_customer_id=customer_id)
    except Subscription.DoesNotExist:
        return
    sync_local_subscription_from_stripe(
        subscription_obj,
        subscription_data,
        event_id=event_id,
    )


def handle_subscription_updated(subscription_data, event_id=None, *, force_collection_paused=None):
    """Handle subscription updates, including pause and resume payloads."""
    try:
        sub_id = _stripe_pick(subscription_data, 'id')
        if not sub_id:
            return
        subscription_obj = Subscription.objects.get(stripe_subscription_id=sub_id)
    except Subscription.DoesNotExist:
        return
    sync_local_subscription_from_stripe(
        subscription_obj,
        subscription_data,
        event_id=event_id,
        force_collection_paused=force_collection_paused,
    )


def handle_subscription_deleted(subscription_data, event_id=None):
    """Handle subscription deletion. Status canceled removes premium access."""
    try:
        sub_id = _stripe_pick(subscription_data, 'id')
        if not sub_id:
            return
        subscription_obj = Subscription.objects.get(stripe_subscription_id=sub_id)
    except Subscription.DoesNotExist:
        return
    sync_local_subscription_from_stripe(
        subscription_obj,
        subscription_data,
        event_id=event_id,
        force_status='canceled',
        deleted=True,
    )


def handle_subscription_paused(subscription_data, event_id=None):
    """customer.subscription.paused — collection is paused even if status is still active."""
    handle_subscription_updated(
        subscription_data,
        event_id=event_id,
        force_collection_paused=True,
    )


def handle_subscription_resumed(subscription_data, event_id=None):
    """customer.subscription.resumed — clear the pause flag."""
    handle_subscription_updated(
        subscription_data,
        event_id=event_id,
        force_collection_paused=False,
    )


def handle_payment_succeeded(invoice):
    """Handle successful payment.

    Promotes past_due / incomplete / inactive (and other non-terminal states) to active.
    Does not revive a canceled subscription or one whose collection is paused.
    """
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

    if not subscription_obj:
        return
    if subscription_obj.status == 'canceled' or subscription_obj.collection_paused:
        if subscription_id and not subscription_obj.stripe_subscription_id:
            subscription_obj.stripe_subscription_id = subscription_id
            subscription_obj.save()
        return
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
            # A canceled or collection-paused row must not be moved back into a grantable status.
            if subscription_obj.status == 'canceled' or subscription_obj.collection_paused:
                return
            # Don't immediately cancel, Stripe will handle retry logic
            subscription_obj.status = 'past_due'
            subscription_obj.save()
    except Subscription.DoesNotExist:
        pass


def stripe_timestamp_to_datetime(timestamp):
    """Convert Stripe UNIX timestamp to an aware UTC datetime (Django-safe with USE_TZ)."""
    return datetime.fromtimestamp(timestamp, tz=UTC) if timestamp else None


_SYNC_FIELDS = (
    'stripe_subscription_id',
    'status',
    'current_period_start',
    'current_period_end',
    'plan_name',
    'price_id',
    'cancel_at_period_end',
    'canceled_at',
    'collection_paused',
)


def _snapshot_subscription(local_sub):
    return {field: getattr(local_sub, field) for field in _SYNC_FIELDS}


def _subscription_changes(before, local_sub):
    changes = []
    for field in _SYNC_FIELDS:
        old = before[field]
        new = getattr(local_sub, field)
        if old != new:
            changes.append(f'{field}: {old!r} -> {new!r}')
    return changes


def _period_end_iso(dt):
    if not dt:
        return 'none'
    if timezone.is_naive(dt):
        dt = timezone.make_aware(dt, datetime.UTC)
    return dt.astimezone(UTC).strftime('%Y-%m-%dT%H:%M:%SZ')


def _pause_marker(stripe_subscription):
    pause = None
    if stripe_subscription is not None and _stripe_contains(stripe_subscription, 'pause_collection'):
        pause = _stripe_pick(stripe_subscription, 'pause_collection')
    resumes_at = _stripe_pick(pause, 'resumes_at') if pause else None
    if resumes_at:
        return f'resumes_at:{resumes_at}'
    behavior = _stripe_pick(pause, 'behavior') if pause else None
    return behavior or 'open'


def _state_dedupe_key(notice_type, local_sub, stripe_subscription):
    """Reconcile has no Stripe event id. Key off the transition so cron does not re-email."""
    sub_id = local_sub.stripe_subscription_id or str(local_sub.pk)
    if notice_type == SubscriptionNotice.NOTICE_CANCEL_SCHEDULED:
        return f'cancel_scheduled:{sub_id}:{_period_end_iso(local_sub.current_period_end)}'
    if notice_type == SubscriptionNotice.NOTICE_CANCELED:
        return f'canceled:{sub_id}'
    if notice_type == SubscriptionNotice.NOTICE_PAUSED:
        cycle = SubscriptionNotice.objects.filter(
            subscription=local_sub,
            notice_type=SubscriptionNotice.NOTICE_PAUSED,
        ).count() + 1
        return f'paused:{sub_id}:{_pause_marker(stripe_subscription)}:c{cycle}'
    cycle = SubscriptionNotice.objects.filter(
        subscription=local_sub,
        notice_type=SubscriptionNotice.NOTICE_RESUMED,
    ).count() + 1
    return f'resumed:{sub_id}:{_period_end_iso(local_sub.current_period_end)}:c{cycle}'


def _notice_transitions(before, local_sub, *, deleted=False):
    hard_cancel = deleted or local_sub.status == 'canceled'
    if hard_cancel:
        if before['status'] != 'canceled':
            return [SubscriptionNotice.NOTICE_CANCELED]
        return []
    notices = []
    if (not before['cancel_at_period_end']) and local_sub.cancel_at_period_end:
        notices.append(SubscriptionNotice.NOTICE_CANCEL_SCHEDULED)
    if (not before['collection_paused']) and local_sub.collection_paused:
        notices.append(SubscriptionNotice.NOTICE_PAUSED)
    if before['collection_paused'] and not local_sub.collection_paused:
        notices.append(SubscriptionNotice.NOTICE_RESUMED)
    return notices


def sync_local_subscription_from_stripe(
    local_sub,
    stripe_subscription,
    *,
    event_id=None,
    dry_run=False,
    force_status=None,
    force_collection_paused=None,
    deleted=False,
):
    """
    Apply Stripe fields, save, and email on a real status transition.

    Webhook deliveries pass event_id so a Stripe retry of that same event does not
    send a second email. Reconcile omits event_id and uses a state key instead.
    """
    before = _snapshot_subscription(local_sub)
    applied = apply_stripe_subscription_to_record(
        local_sub,
        stripe_subscription,
        force_status=force_status,
        force_collection_paused=force_collection_paused,
    )
    if not applied:
        return []
    changes = _subscription_changes(before, local_sub)
    transitions = _notice_transitions(before, local_sub, deleted=deleted)
    if dry_run:
        local_sub.refresh_from_db()
        return changes
    if not changes and not transitions:
        return changes

    to_email = ''
    user = getattr(local_sub, 'user', None)
    if user is not None:
        to_email = (getattr(user, 'email', None) or '').strip()

    queued = []
    with transaction.atomic():
        local_sub.save()
        if to_email:
            for notice_type in transitions:
                state_key = _state_dedupe_key(notice_type, local_sub, stripe_subscription)
                dedupe_key = f'{notice_type}:{event_id}' if event_id else state_key
                if SubscriptionNotice.objects.filter(
                    subscription=local_sub,
                    notice_type=notice_type,
                    dedupe_key__in=[dedupe_key, state_key],
                ).exists():
                    continue
                try:
                    with transaction.atomic():
                        SubscriptionNotice.objects.create(
                            subscription=local_sub,
                            notice_type=notice_type,
                            dedupe_key=dedupe_key,
                        )
                except IntegrityError:
                    continue
                queued.append(notice_type)

    for notice_type in queued:
        try:
            _send_subscription_notice(local_sub, notice_type, to_email)
        except Exception:
            logger.exception(
                'subscription notice email failed type=%s subscription=%s',
                notice_type,
                local_sub.pk,
            )
    return changes


def _send_subscription_notice(local_sub, notice_type, to_email):
    period_end_display = None
    if local_sub.current_period_end:
        period_end_display = timezone.localtime(local_sub.current_period_end).strftime('%B %d, %Y')
    receipt_url = None
    if notice_type in (
        SubscriptionNotice.NOTICE_CANCEL_SCHEDULED,
        SubscriptionNotice.NOTICE_CANCELED,
    ):
        receipt_url = _best_effort_receipt_url(local_sub.stripe_subscription_id)
    context = {
        'period_end_display': period_end_display,
        'receipt_url': receipt_url,
        'plan_name': local_sub.plan_name or 'Premium Plan',
    }
    template, subject, text = _notice_email_parts(notice_type, context)
    html = render_to_string(template, context)
    from overslot.auth import MailgunEmailer
    MailgunEmailer.send_email(to_email, subject, html, text_content=text)


def _notice_email_parts(notice_type, context):
    when = context.get('period_end_display') or 'the end of the current billing period'
    receipt = context.get('receipt_url')
    receipt_line = f' Receipt: {receipt}' if receipt else ''
    if notice_type == SubscriptionNotice.NOTICE_CANCEL_SCHEDULED:
        return (
            'subscription/email/cancel_scheduled.html',
            'Your Over Slot subscription will cancel',
            f'Your Over Slot subscription is scheduled to cancel. You keep premium access until {when}.{receipt_line}',
        )
    if notice_type == SubscriptionNotice.NOTICE_CANCELED:
        return (
            'subscription/email/canceled.html',
            'Your Over Slot subscription has been canceled',
            f'Your Over Slot subscription has been canceled.{receipt_line}',
        )
    if notice_type == SubscriptionNotice.NOTICE_PAUSED:
        return (
            'subscription/email/paused.html',
            'Your Over Slot subscription is paused',
            'Your Over Slot subscription is paused. Premium access is paused until billing resumes.',
        )
    return (
        'subscription/email/resumed.html',
        'Your Over Slot premium access is restored',
        'Your Over Slot subscription has resumed. Premium access is restored.',
    )


def _best_effort_receipt_url(stripe_subscription_id):
    """Hosted invoice URL, else a charge receipt URL. Failures return None and do not raise."""
    if not stripe_subscription_id:
        return None
    try:
        invoices = stripe.Invoice.list(subscription=stripe_subscription_id, limit=1)
    except Exception:
        logger.exception(
            'Invoice.list failed while building subscription receipt link sub=%s',
            stripe_subscription_id,
        )
        return None
    data = getattr(invoices, 'data', None)
    if data is None:
        data = _stripe_pick(invoices, 'data')
    if not data:
        return None
    try:
        invoice = data[0]
    except (IndexError, KeyError, TypeError):
        return None
    hosted = _stripe_pick(invoice, 'hosted_invoice_url')
    if hosted:
        return hosted
    charge = _stripe_pick(invoice, 'charge')
    if charge is not None and not isinstance(charge, str):
        receipt = _stripe_pick(charge, 'receipt_url')
        if receipt:
            return receipt
    return None


def retrieve_stripe_subscription_for_local(local_sub):
    """
    Load the Stripe subscription that should win for this local row.

    Prefer Subscription.retrieve when we already have an id (includes canceled and paused).
    Otherwise reuse the customer access picker, then a canceled-list fallback.
    """
    if local_sub.stripe_subscription_id:
        return stripe.Subscription.retrieve(
            local_sub.stripe_subscription_id,
            expand=['items.data.price'],
        )
    if not local_sub.stripe_customer_id:
        return None
    chosen = _pick_subscription_for_customer_access(
        local_sub.stripe_customer_id,
        preferred_subscription_id=local_sub.stripe_subscription_id,
    )
    if chosen is not None:
        return chosen
    resp = stripe.Subscription.list(
        customer=local_sub.stripe_customer_id,
        status='canceled',
        limit=1,
    )
    data = getattr(resp, 'data', None)
    if data is None:
        data = _stripe_pick(resp, 'data')
    if data:
        return data[0]
    return None


def _json_safe(value, depth=0):
    """Plain JSON for StripeWebhookEvent.payload. Never calls .get() on Stripe objects."""
    if depth > 30:
        return None
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, dict):
        return {str(key): _json_safe(item, depth + 1) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(item, depth + 1) for item in value]
    data = getattr(value, '_data', None)
    if isinstance(data, dict):
        return {str(key): _json_safe(item, depth + 1) for key, item in data.items()}
    return None


def _upsert_stripe_webhook_event(event_id, event_type, payload):
    defaults = {
        'event_type': event_type or '',
        'status': StripeWebhookEvent.STATUS_PENDING,
        'payload': payload,
    }
    try:
        record, created = StripeWebhookEvent.objects.get_or_create(
            stripe_event_id=event_id,
            defaults=defaults,
        )
    except IntegrityError:
        record = StripeWebhookEvent.objects.get(stripe_event_id=event_id)
        created = False
    if not created and record.status != StripeWebhookEvent.STATUS_PROCESSED:
        record.event_type = event_type or record.event_type
        record.payload = payload
        record.status = StripeWebhookEvent.STATUS_PENDING
        record.save(update_fields=['event_type', 'payload', 'status', 'last_modified'])
    return record, created


def _run_webhook_handling(record, event_type, data_object, event_id):
    try:
        process_stripe_event_payload(event_type, data_object, event_id=event_id)
    except Exception as exc:
        if record is not None:
            record.status = StripeWebhookEvent.STATUS_FAILED
            record.last_error = str(exc)[:4000]
            record.save(update_fields=['status', 'last_error', 'last_modified'])
        raise
    if record is not None:
        record.status = StripeWebhookEvent.STATUS_PROCESSED
        record.last_error = ''
        record.save(update_fields=['status', 'last_error', 'last_modified'])


def process_stripe_event_payload(event_type, data_object, event_id=None):
    """Dispatch one Stripe event. Unknown types are ignored by the caller after they are stored."""
    if event_type == 'checkout.session.completed' and data_object is not None:
        handle_checkout_session_completed(data_object)
    elif event_type == 'customer.subscription.created' and data_object is not None:
        handle_subscription_created(data_object, event_id=event_id)
    elif event_type == 'customer.subscription.updated' and data_object is not None:
        handle_subscription_updated(data_object, event_id=event_id)
    elif event_type == 'customer.subscription.deleted' and data_object is not None:
        handle_subscription_deleted(data_object, event_id=event_id)
    elif event_type == 'customer.subscription.paused' and data_object is not None:
        handle_subscription_paused(data_object, event_id=event_id)
    elif event_type == 'customer.subscription.resumed' and data_object is not None:
        handle_subscription_resumed(data_object, event_id=event_id)
    elif event_type in ('invoice.paid', 'invoice.payment_succeeded') and data_object is not None:
        handle_payment_succeeded(data_object)
    elif event_type == 'invoice.payment_failed' and data_object is not None:
        handle_payment_failed(data_object)
    elif event_type not in STRIPE_WEBHOOK_EVENT_TYPES:
        logger.info('Stored unhandled Stripe event type=%s', event_type)


def process_stripe_webhook_event(record):
    """Replay one stored StripeWebhookEvent. Safe to call again after success (no-op once processed)."""
    if record.status == StripeWebhookEvent.STATUS_PROCESSED:
        return
    payload = record.payload if isinstance(record.payload, dict) else {}
    event_type = record.event_type or _stripe_pick(payload, 'type') or ''
    data = _stripe_pick(payload, 'data')
    data_object = _stripe_pick(data, 'object') if data is not None else None
    _run_webhook_handling(record, event_type, data_object, record.stripe_event_id)
