"""
Regression tests for Stripe webhooks / subscription syncing.

stripe-python parses webhook payloads as StripeObject-ish values: bracket / attribute access
works, but ``.get(...)` does NOT (the production bug that triggered 500s on API churn).

Uses StripeBag fixtures to encode that invariant so future deps / API-shape changes surface
quickly here instead of affecting real subscribers.

Run::
    django-admin test tests.test_stripe_integration --settings=config.dev.settings
"""

from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import patch

import stripe
from django.contrib.auth.models import User
from django.core.cache import cache
from django.core.management import call_command
from django.test import Client, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from overslot import subscription_views as sub_views
from overslot.models import StripeWebhookEvent, Subscription, SubscriptionNotice


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


def _subscription_event(event_id, event_type, payload):
    return StripeBag(
        {
            'id': event_id,
            'type': event_type,
            'data': StripeBag({'object': stripe_bagify(payload)}),
        }
    )


@override_settings(
    STRIPE_WEBHOOK_SECRET='whsec_test',
    STRIPE_SECRET_KEY='sk_test_dummy',
    STRIPE_PUBLISHABLE_KEY='pk_test_dummy',
)
class StripeReconciliationTests(TestCase):
    """Cancel, pause, resume, idempotent webhooks, and the reconcile command."""

    def setUp(self):
        cache.clear()
        self.user = User.objects.create_user(
            username='recon@example.com',
            email='recon@example.com',
            password='pwd',
        )
        self.subscription = Subscription.objects.create(
            user=self.user,
            stripe_customer_id='cus_recon',
            stripe_subscription_id='sub_recon',
            status='active',
            current_period_end=timezone.now() + timedelta(days=20),
        )

    def _post(self, event):
        with patch.object(stripe.Webhook, 'construct_event', return_value=event):
            return self.client.post(
                reverse('stripe_webhook'),
                data=b'{}',
                content_type='application/json',
                HTTP_STRIPE_SIGNATURE='t=1,v=test',
            )

    def test_subscription_updated_cancel_at_period_end_keeps_access(self):
        period_end = 1893456000
        event = _subscription_event(
            'evt_cancel_sched',
            'customer.subscription.updated',
            {
                'id': 'sub_recon',
                'customer': 'cus_recon',
                'status': 'active',
                'cancel_at_period_end': True,
                'current_period_end': period_end,
                'items': {'data': []},
            },
        )
        with patch('overslot.auth.MailgunEmailer.send_email') as send_email, patch.object(
            stripe.Invoice,
            'list',
            return_value=SimpleNamespace(
                data=[SimpleNamespace(hosted_invoice_url='https://pay.stripe.com/receipt/1', charge=None)]
            ),
        ):
            response = self._post(event)
        self.assertEqual(response.status_code, 200)
        row = Subscription.objects.get(pk=self.subscription.pk)
        self.assertTrue(row.cancel_at_period_end)
        self.assertEqual(row.status, 'active')
        self.assertTrue(row.can_access_premium_content())
        self.assertEqual(send_email.call_count, 1)
        self.assertEqual(
            SubscriptionNotice.objects.filter(subscription=row, notice_type='cancel_scheduled').count(),
            1,
        )

    def test_subscription_updated_pause_collection_removes_access_and_emails_once(self):
        event = _subscription_event(
            'evt_pause_1',
            'customer.subscription.updated',
            {
                'id': 'sub_recon',
                'customer': 'cus_recon',
                'status': 'active',
                'pause_collection': {'behavior': 'void', 'resumes_at': 1893456000},
                'items': {'data': []},
            },
        )
        with patch('overslot.auth.MailgunEmailer.send_email') as send_email:
            response = self._post(event)
        self.assertEqual(response.status_code, 200)
        row = Subscription.objects.get(pk=self.subscription.pk)
        self.assertTrue(row.collection_paused)
        self.assertEqual(row.status, 'active')
        self.assertFalse(row.can_access_premium_content())
        self.assertEqual(send_email.call_count, 1)
        self.assertIn('paused', send_email.call_args[0][1].lower())

    def test_subscription_paused_event_removes_access(self):
        event = _subscription_event(
            'evt_paused_event',
            'customer.subscription.paused',
            {
                'id': 'sub_recon',
                'customer': 'cus_recon',
                'status': 'active',
                'pause_collection': {'behavior': 'mark_uncollectible'},
                'items': {'data': []},
            },
        )
        with patch('overslot.auth.MailgunEmailer.send_email') as send_email:
            response = self._post(event)
        self.assertEqual(response.status_code, 200)
        row = Subscription.objects.get(pk=self.subscription.pk)
        self.assertTrue(row.collection_paused)
        self.assertFalse(row.can_access_premium_content())
        self.assertEqual(send_email.call_count, 1)

    def test_subscription_deleted_cancels_and_emails_once(self):
        event = _subscription_event(
            'evt_deleted_1',
            'customer.subscription.deleted',
            {
                'id': 'sub_recon',
                'customer': 'cus_recon',
                'status': 'canceled',
                'items': {'data': []},
            },
        )
        with patch('overslot.auth.MailgunEmailer.send_email') as send_email, patch.object(
            stripe.Invoice,
            'list',
            return_value=SimpleNamespace(data=[]),
        ):
            response = self._post(event)
        self.assertEqual(response.status_code, 200)
        row = Subscription.objects.get(pk=self.subscription.pk)
        self.assertEqual(row.status, 'canceled')
        self.assertFalse(row.can_access_premium_content())
        self.assertEqual(send_email.call_count, 1)
        self.assertEqual(
            SubscriptionNotice.objects.filter(subscription=row, notice_type='canceled').count(),
            1,
        )

    def test_same_event_id_does_not_send_a_second_email(self):
        event = _subscription_event(
            'evt_deleted_once',
            'customer.subscription.deleted',
            {
                'id': 'sub_recon',
                'customer': 'cus_recon',
                'status': 'canceled',
                'items': {'data': []},
            },
        )
        with patch('overslot.auth.MailgunEmailer.send_email') as send_email, patch.object(
            stripe.Invoice,
            'list',
            return_value=SimpleNamespace(data=[]),
        ):
            first = self._post(event)
            second = self._post(event)
        self.assertEqual(first.status_code, 200)
        self.assertEqual(second.status_code, 200)
        self.assertEqual(send_email.call_count, 1)
        self.assertEqual(
            StripeWebhookEvent.objects.filter(stripe_event_id='evt_deleted_once', status='processed').count(),
            1,
        )

    def test_invoice_payment_succeeded_does_not_revive_canceled_subscription(self):
        self.subscription.status = 'canceled'
        self.subscription.save(update_fields=['status', 'last_modified'])
        event = _subscription_event(
            'evt_invoice_paid_late',
            'invoice.payment_succeeded',
            {
                'id': 'in_1',
                'subscription': 'sub_recon',
                'customer': 'cus_recon',
            },
        )
        with patch('overslot.auth.MailgunEmailer.send_email') as send_email:
            response = self._post(event)
        self.assertEqual(response.status_code, 200)
        row = Subscription.objects.get(pk=self.subscription.pk)
        self.assertEqual(row.status, 'canceled')
        self.assertFalse(row.can_access_premium_content())
        self.assertEqual(send_email.call_count, 0)

    def test_invoice_paid_promotes_past_due_to_active(self):
        self.subscription.status = 'past_due'
        self.subscription.save(update_fields=['status', 'last_modified'])
        event = _subscription_event(
            'evt_invoice_paid',
            'invoice.paid',
            {
                'id': 'in_2',
                'subscription': 'sub_recon',
                'customer': 'cus_recon',
            },
        )
        response = self._post(event)
        self.assertEqual(response.status_code, 200)
        row = Subscription.objects.get(pk=self.subscription.pk)
        self.assertEqual(row.status, 'active')
        self.assertTrue(row.can_access_premium_content())

    def test_resumed_clears_pause_and_restores_access(self):
        self.subscription.collection_paused = True
        self.subscription.save(update_fields=['collection_paused', 'last_modified'])
        self.assertFalse(self.subscription.can_access_premium_content())
        event = _subscription_event(
            'evt_resume_1',
            'customer.subscription.resumed',
            {
                'id': 'sub_recon',
                'customer': 'cus_recon',
                'status': 'active',
                'pause_collection': None,
                'items': {'data': []},
            },
        )
        with patch('overslot.auth.MailgunEmailer.send_email') as send_email:
            response = self._post(event)
        self.assertEqual(response.status_code, 200)
        row = Subscription.objects.get(pk=self.subscription.pk)
        self.assertFalse(row.collection_paused)
        self.assertEqual(row.status, 'active')
        self.assertTrue(row.can_access_premium_content())
        self.assertEqual(send_email.call_count, 1)
        self.assertEqual(
            SubscriptionNotice.objects.filter(subscription=row, notice_type='resumed').count(),
            1,
        )

    def test_reconcile_command_updates_stale_local_row(self):
        self.subscription.status = 'inactive'
        self.subscription.save(update_fields=['status', 'last_modified'])
        remote = stripe_bagify(
            {
                'id': 'sub_recon',
                'customer': 'cus_recon',
                'status': 'active',
                'cancel_at_period_end': False,
                'current_period_end': 1893456000,
                'items': {'data': []},
            }
        )
        with patch.object(stripe.Subscription, 'retrieve', return_value=remote):
            call_command('reconcile_stripe_subscriptions')
        row = Subscription.objects.get(pk=self.subscription.pk)
        self.assertEqual(row.status, 'active')
        self.assertTrue(row.can_access_premium_content())
        self.assertEqual(row.stripe_subscription_id, 'sub_recon')

    def test_reconcile_dry_run_does_not_save_or_email(self):
        self.subscription.status = 'inactive'
        self.subscription.save(update_fields=['status', 'last_modified'])
        remote = stripe_bagify(
            {
                'id': 'sub_recon',
                'status': 'active',
                'cancel_at_period_end': True,
                'current_period_end': 1893456000,
                'items': {'data': []},
            }
        )
        with patch.object(stripe.Subscription, 'retrieve', return_value=remote), patch(
            'overslot.auth.MailgunEmailer.send_email'
        ) as send_email:
            call_command('reconcile_stripe_subscriptions', '--dry-run')
        row = Subscription.objects.get(pk=self.subscription.pk)
        self.assertEqual(row.status, 'inactive')
        self.assertFalse(row.cancel_at_period_end)
        self.assertEqual(send_email.call_count, 0)

    def test_process_stripe_events_replays_pending_payload(self):
        StripeWebhookEvent.objects.create(
            stripe_event_id='evt_replay_1',
            event_type='customer.subscription.updated',
            status='pending',
            payload={
                'id': 'evt_replay_1',
                'type': 'customer.subscription.updated',
                'data': {
                    'object': {
                        'id': 'sub_recon',
                        'customer': 'cus_recon',
                        'status': 'past_due',
                        'items': {'data': []},
                    }
                },
            },
        )
        call_command('process_stripe_events')
        row = Subscription.objects.get(pk=self.subscription.pk)
        self.assertEqual(row.status, 'past_due')
        self.assertTrue(row.can_access_premium_content())
        stored = StripeWebhookEvent.objects.get(stripe_event_id='evt_replay_1')
        self.assertEqual(stored.status, 'processed')
        call_command('process_stripe_events')
        self.assertEqual(StripeWebhookEvent.objects.get(stripe_event_id='evt_replay_1').status, 'processed')

    def test_webhook_queues_until_worker_runs(self):
        """Production webhooks only store the event. The worker applies it."""
        self.subscription.status = 'inactive'
        self.subscription.save(update_fields=['status', 'last_modified'])
        event = _subscription_event(
            'evt_queued_1',
            'customer.subscription.updated',
            {
                'id': 'sub_recon',
                'customer': 'cus_recon',
                'status': 'past_due',
                'items': {'data': []},
            },
        )
        with patch.object(sub_views, '_stripe_webhook_runs_inline', return_value=False):
            response = self._post(event)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(Subscription.objects.get(pk=self.subscription.pk).status, 'inactive')
        stored = StripeWebhookEvent.objects.get(stripe_event_id='evt_queued_1')
        self.assertEqual(stored.status, 'pending')

        with patch.object(stripe.Subscription, 'retrieve') as retrieve:
            call_command('run_stripe_worker', '--once', '--skip-reconcile')
        retrieve.assert_not_called()
        row = Subscription.objects.get(pk=self.subscription.pk)
        self.assertEqual(row.status, 'past_due')
        self.assertEqual(
            StripeWebhookEvent.objects.get(stripe_event_id='evt_queued_1').status,
            'processed',
        )

    def test_worker_waits_before_retrying_a_failed_event(self):
        record = StripeWebhookEvent.objects.create(
            stripe_event_id='evt_failed_recent',
            event_type='customer.subscription.updated',
            status='failed',
            payload={
                'id': 'evt_failed_recent',
                'type': 'customer.subscription.updated',
                'data': {
                    'object': {
                        'id': 'sub_recon',
                        'customer': 'cus_recon',
                        'status': 'past_due',
                        'items': {'data': []},
                    }
                },
            },
        )
        call_command('run_stripe_worker', '--once', '--skip-reconcile', '--retry-failed-after', '60')
        record.refresh_from_db()
        self.assertEqual(record.status, 'failed')
        self.assertEqual(Subscription.objects.get(pk=self.subscription.pk).status, 'active')

        StripeWebhookEvent.objects.filter(pk=record.pk).update(
            last_modified=timezone.now() - timedelta(seconds=120),
        )
        call_command('run_stripe_worker', '--once', '--skip-reconcile', '--retry-failed-after', '60')
        record.refresh_from_db()
        self.assertEqual(record.status, 'processed')
        self.assertEqual(Subscription.objects.get(pk=self.subscription.pk).status, 'past_due')


@override_settings(
    STRIPE_SECRET_KEY='sk_test_dummy',
    STRIPE_PUBLISHABLE_KEY='pk_test_dummy',
)
class SubscriptionDashboardStateTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username='dash@example.com',
            email='dash@example.com',
            password='pwd',
        )
        self.client = Client()
        self.client.force_login(self.user)

    def _subscription(self, **kwargs):
        defaults = {
            'user': self.user,
            'stripe_customer_id': 'cus_dash',
            'stripe_subscription_id': 'sub_dash',
            'status': 'active',
            'current_period_end': timezone.now() + timedelta(days=10),
        }
        defaults.update(kwargs)
        return Subscription.objects.create(**defaults)

    def test_cancel_at_period_end_copy(self):
        self._subscription(cancel_at_period_end=True)
        response = self.client.get(reverse('subscription_dashboard'))
        self.assertEqual(response.status_code, 200)
        body = response.content.decode()
        self.assertIn('Cancellation scheduled', body)
        self.assertIn('keep premium access until then', body)
        self.assertNotIn('You are cleared for subscriber content', body)

    def test_collection_paused_has_no_premium_banner(self):
        self._subscription(collection_paused=True)
        response = self.client.get(reverse('subscription_dashboard'))
        body = response.content.decode()
        self.assertIn('Billing is paused', body)
        self.assertNotIn('You are cleared for subscriber content', body)
        self.assertNotIn('Premium access', body)

    def test_canceled_does_not_promise_continued_access(self):
        self._subscription(
            status='canceled',
            current_period_end=timezone.now() + timedelta(days=5),
        )
        response = self.client.get(reverse('subscription_dashboard'))
        body = response.content.decode()
        self.assertNotIn('continue to have access', body)
        self.assertIn('premium access has ended', body)
