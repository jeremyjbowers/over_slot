import json
import stripe
from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.shortcuts import render, redirect
from django.http import HttpResponse, JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST
from django.utils.decorators import method_decorator
from django.contrib import messages
from django.urls import reverse

from overslot.models import Subscription

# Initialize Stripe
stripe.api_key = settings.STRIPE_SECRET_KEY


@login_required
def subscription_dashboard(request):
    """Dashboard for managing user subscriptions."""
    try:
        subscription = request.user.subscription
    except Subscription.DoesNotExist:
        subscription = None
    
    context = {
        'subscription': subscription,
        'stripe_publishable_key': settings.STRIPE_PUBLISHABLE_KEY,
    }
    return render(request, 'subscription/dashboard.html', context)


@login_required
def create_checkout_session(request):
    """Create a Stripe checkout session for subscription."""
    if request.method == 'POST':
        try:
            # Get or create subscription record
            subscription, created = Subscription.objects.get_or_create(
                user=request.user,
                defaults={'stripe_customer_id': ''}
            )
            
            # Create or get Stripe customer
            if not subscription.stripe_customer_id:
                customer = stripe.Customer.create(
                    email=request.user.email,
                    metadata={'user_id': request.user.id}
                )
                subscription.stripe_customer_id = customer.id
                subscription.save()
            
            # Create checkout session
            checkout_session = stripe.checkout.Session.create(
                customer=subscription.stripe_customer_id,
                payment_method_types=['card'],
                line_items=[{
                    'price': settings.STRIPE_PRICE_ID,
                    'quantity': 1,
                }],
                mode='subscription',
                allow_promotion_codes=True,
                success_url=request.build_absolute_uri(reverse('subscription_success')),
                cancel_url=request.build_absolute_uri(reverse('subscription_dashboard')),
                metadata={'user_id': request.user.id}
            )
            
            return redirect(checkout_session.url)
            
        except Exception as e:
            messages.error(request, f'Error creating checkout session: {str(e)}')
            return redirect('subscription_dashboard')
    
    return redirect('subscription_dashboard')


@login_required
def subscription_success(request):
    """Handle successful subscription creation."""
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
        user_id = session.get('metadata', {}).get('user_id')
        if user_id:
            user = User.objects.get(id=user_id)
            subscription, created = Subscription.objects.get_or_create(
                user=user,
                defaults={'stripe_customer_id': session.get('customer', '')}
            )
            
            if session.get('subscription'):
                subscription.stripe_subscription_id = session['subscription']
                subscription.save()
    except User.DoesNotExist:
        pass


def handle_subscription_created(subscription_data):
    """Handle subscription creation."""
    try:
        customer_id = subscription_data.get('customer')
        subscription_obj = Subscription.objects.get(stripe_customer_id=customer_id)
        
        subscription_obj.stripe_subscription_id = subscription_data.get('id')
        subscription_obj.status = subscription_data.get('status')
        subscription_obj.current_period_start = stripe_timestamp_to_datetime(subscription_data.get('current_period_start'))
        subscription_obj.current_period_end = stripe_timestamp_to_datetime(subscription_data.get('current_period_end'))
        
        # Get plan details
        if subscription_data.get('items', {}).get('data'):
            price_data = subscription_data['items']['data'][0]['price']
            subscription_obj.price_id = price_data['id']
            subscription_obj.plan_name = price_data.get('nickname', 'Premium Plan')
        
        subscription_obj.save()
    except Subscription.DoesNotExist:
        pass


def handle_subscription_updated(subscription_data):
    """Handle subscription updates."""
    try:
        subscription_obj = Subscription.objects.get(
            stripe_subscription_id=subscription_data['id']
        )
        
        subscription_obj.status = subscription_data.get('status')
        subscription_obj.current_period_start = stripe_timestamp_to_datetime(subscription_data.get('current_period_start'))
        subscription_obj.current_period_end = stripe_timestamp_to_datetime(subscription_data.get('current_period_end'))
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
    try:
        subscription_id = invoice.get('subscription')
        if subscription_id:
            subscription_obj = Subscription.objects.get(
                stripe_subscription_id=subscription_id
            )
            subscription_obj.status = 'active'
            subscription_obj.save()
    except Subscription.DoesNotExist:
        pass


def handle_payment_failed(invoice):
    """Handle failed payment."""
    try:
        subscription_id = invoice.get('subscription')
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