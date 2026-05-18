"""
Regression tests for Stripe webhooks / subscription syncing.

stripe-python parses webhook payloads as StripeObject-ish values: bracket / attribute access
works, but ``.get(...)` does NOT (the production bug that triggered 500s on API churn).

Uses StripeBag fixtures to encode that invariant so future deps / API-shape changes surface
quickly here instead of affecting real subscribers.

Run::
    django-admin test tests.test_stripe_integration --settings=config.dev.settings
"""

from types import SimpleNamespace
from unittest.mock import patch

import stripe
from django.contrib.auth.models import User
from django.core.cache import cache
from django.test import Client, TestCase, override_settings
from django.urls import reverse

from overslot import subscription_views as sub_views
from overslot.models import Subscription


class StripeBag:
    """
    Minimal Stripe webhook object: bracket + attribute lookups, deliberately no `.get`.
    Mirrors the failure mode behind KeyError('get') / AttributeError when code used `.get()`
    instead of `_stripe_pick` / bracket access.
    """

    __slots__ = ('_data',)

    def __init__(self, data):
        self._data = dict(data)

    def __getitem__(self, key):
        return self._data[key]

    def __getattr__(self, key):
        if key.startswith('_') or key in ('_data',):
            raise AttributeError(key)
        try:
            return self._data[key]
        except KeyError:
            raise AttributeError(key)

    # Intentionally do not inherit dict / implement .get


def stripe_bagify(value):
    if isinstance(value, dict):
        inner = {k: stripe_bagify(v) for k, v in value.items()}
        return StripeBag(inner)
    if isinstance(value, list):
        return [stripe_bagify(v) for v in value]
    return value


class StripeWebhookRegressionTests(TestCase):
    """End-to-end HTTP webhook behavior with mocked signature verification."""

    def setUp(self):
        cache.clear()

    def _post_webhook(self, fake_event_payload):
        with patch.object(
            stripe.Webhook,
            'construct_event',
            return_value=fake_event_payload,
        ):
            return self.client.post(
                reverse('stripe_webhook'),
                data=b'{}',
                content_type='application/json',
                HTTP_STRIPE_SIGNATURE='t=1,v=test',
            )

    @override_settings(
        STRIPE_WEBHOOK_SECRET='whsec_test',
        STRIPE_SECRET_KEY='sk_test_dummy',
        STRIPE_PUBLISHABLE_KEY='pk_test_dummy',
    )
    def test_subscription_updated_stripe_like_object_no_get_method(self):
        """Updating DB from customer.subscription.updated must not call .get on payload."""
        user = User.objects.create_user(
            username='stripeuser@example.com',
            email='stripeuser@example.com',
            password='pwd',
        )
        Subscription.objects.create(
            user=user,
            stripe_customer_id='cus_123',
            stripe_subscription_id='sub_abc',
            status='inactive',
        )

        sub_obj = stripe_bagify(
            {
                'id': 'sub_abc',
                'customer': 'cus_123',
                'status': 'active',
                'items': StripeBag({'data': []}),
            }
        )

        evt = StripeBag({'type': 'customer.subscription.updated', 'data': StripeBag({'object': sub_obj})})

        response = self._post_webhook(evt)
        self.assertEqual(response.status_code, 200)

        refreshed = Subscription.objects.get(user=user)
        self.assertEqual(refreshed.status, 'active')
        self.assertEqual(refreshed.stripe_subscription_id, 'sub_abc')

    @override_settings(
        STRIPE_WEBHOOK_SECRET='whsec_test',
        STRIPE_SECRET_KEY='sk_test_dummy',
    )
    def test_subscription_created_with_nested_items_stripe_like(self):
        user = User.objects.create_user(username='pay@example.com', email='pay@example.com', password='pwd')
        Subscription.objects.create(
            user=user,
            stripe_customer_id='cus_88',
            status='inactive',
        )

        sub_obj = stripe_bagify(
            {
                'id': 'sub_new',
                'customer': 'cus_88',
                'status': 'trialing',
                'current_period_start': 1740000000,
                'current_period_end': 1742678400,
                'items': {
                    'data': [
                        {'price': {'id': 'price_xyz', 'nickname': 'Monthly Test'}},
                    ]
                },
            }
        )

        evt = StripeBag({'type': 'customer.subscription.created', 'data': StripeBag({'object': sub_obj})})
        response = self._post_webhook(evt)

        self.assertEqual(response.status_code, 200)
        row = Subscription.objects.get(user=user)
        self.assertEqual(row.status, 'trialing')
        self.assertEqual(row.stripe_subscription_id, 'sub_new')
        self.assertEqual(row.price_id, 'price_xyz')

    @override_settings(
        STRIPE_WEBHOOK_SECRET='whsec_test',
        STRIPE_SECRET_KEY='sk_test_dummy',
    )
    @patch.object(sub_views.logger, 'exception')
    @patch.object(sub_views, 'handle_checkout_session_completed')
    def test_webhook_returns_500_on_handler_failure_so_stripe_retries(self, mock_handler, mock_log):
        """Unhandled errors must return 500 (Stripe backoff / DLQ semantics)."""
        mock_handler.side_effect = RuntimeError('simulated handler bug')
        evt = StripeBag(
            {'type': 'checkout.session.completed', 'data': StripeBag({'object': StripeBag({'id': 'cs_x'})})}
        )
        response = self._post_webhook(evt)
        self.assertEqual(response.status_code, 500)


class StripeUnitTests(TestCase):
    """Pure helper / branch coverage."""

    def test_stripe_pick_dict_vs_stripe_like(self):
        d = {'a': 1}
        self.assertEqual(sub_views._stripe_pick(d, 'a'), 1)
        self.assertIsNone(sub_views._stripe_pick(d, 'missing'))

        bag = StripeBag({'a': 2, 'nested': StripeBag({'b': True})})
        self.assertEqual(sub_views._stripe_pick(bag, 'a'), 2)
        nested = bag['nested']
        self.assertEqual(sub_views._stripe_pick(nested, 'b'), True)
        self.assertIsNone(sub_views._stripe_pick(bag, 'no_such'))

    def test_apply_stripe_record_tolerates_missing_period_fields_on_object(self):
        user = User.objects.create_user(username='a@example.com', email='a@example.com', password='x')
        sub = Subscription.objects.create(
            user=user,
            stripe_customer_id='cus_1',
            stripe_subscription_id='sub_1',
            status='inactive',
        )

        api_sub = StripeBag({'id': 'sub_9', 'status': 'active', 'items': StripeBag({'data': []})})
        sub_views.apply_stripe_subscription_to_record(sub, api_sub)
        self.assertEqual(sub.stripe_subscription_id, 'sub_9')
        self.assertEqual(sub.status, 'active')
        self.assertIsNone(sub.current_period_start)

    def test_pick_subscription_prefers_explicit_checkout_subscription_id(self):
        older = SimpleNamespace(id='sub_old', status='active', created=111)
        preferred = SimpleNamespace(id='sub_target', status='active', created=999)

        def list_side_effect(*args, customer=None, status=None, **kwargs):
            if status == 'active':
                return SimpleNamespace(data=[older, preferred])
            return SimpleNamespace(data=[])

        with patch.object(stripe.Subscription, 'list', side_effect=list_side_effect):
            picked = sub_views._pick_subscription_for_customer_access(
                'cus_any', preferred_subscription_id='sub_target'
            )
            self.assertEqual(picked.id, 'sub_target')


@override_settings(
    STRIPE_SECRET_KEY='sk_test_dummy',
)
class StripeCheckoutSyncTests(TestCase):
    """Checkout-session sync + retrieve fallback."""

    @patch.object(sub_views.logger, 'exception')
    def test_retrieve_fallback_calls_list_when_retrieve_raises(self, _mock_log):
        user = User.objects.create_user(username='c@example.com', email='c@example.com', password='pwd')

        session = StripeBag(
            {
                'mode': 'subscription',
                'payment_status': 'paid',
                'customer': 'cus_fallback',
                'subscription': 'sub_preferred',
            }
        )

        fake_from_list = StripeBag(
            {
                'id': 'sub_from_list',
                'status': 'active',
                'current_period_start': 1740000100,
                'items': StripeBag({'data': []}),
            }
        )

        with patch.object(
            stripe.Subscription,
            'retrieve',
            side_effect=stripe.error.APIConnectionError('boom'),
        ), patch.object(
            sub_views,
            '_pick_subscription_for_customer_access',
            return_value=fake_from_list,
        ):
            row = sub_views.sync_subscription_from_checkout_session(user, session)

        self.assertIsNotNone(row)
        refreshed = Subscription.objects.get(pk=row.pk)
        self.assertEqual(refreshed.stripe_subscription_id, 'sub_from_list')
        self.assertEqual(refreshed.stripe_customer_id, 'cus_fallback')
        self.assertEqual(refreshed.status, 'active')


@override_settings(
    STRIPE_SECRET_KEY='sk_test_dummy',
    STRIPE_PUBLISHABLE_KEY='pk_test_dummy',
)
class StripeDashboardResyncTests(TestCase):
    """POST subscription/resync/"""

    def setUp(self):
        cache.clear()
        self.user = User.objects.create_user(username='r@example.com', email='r@example.com', password='pwd')
        self.subscription = Subscription.objects.create(
            user=self.user,
            stripe_customer_id='cus_resync',
            status='inactive',
        )
        self.client = Client()
        self.client.force_login(self.user)

    def test_resync_flips_subscription_from_stripe_list(self):
        fake_sub = StripeBag(
            {
                'id': 'sub_alive',
                'status': 'active',
                'current_period_end': 1750000000,
                'items': StripeBag({'data': []}),
            }
        )

        def list_side_effect(*args, customer=None, status=None, **kwargs):
            if status == 'active':
                return SimpleNamespace(data=[fake_sub])
            return SimpleNamespace(data=[])

        with patch.object(stripe.Subscription, 'list', side_effect=list_side_effect):
            resp = self.client.post(reverse('stripe_subscription_resync'))

        self.assertEqual(resp.status_code, 302)
        row = Subscription.objects.get(user=self.user)
        self.assertTrue(row.can_access_premium_content())
        self.assertEqual(row.stripe_subscription_id, 'sub_alive')
