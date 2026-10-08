"""Pull Stripe subscription state for local rows webhooks may have missed."""

import logging

import stripe
from django.core.management.base import BaseCommand
from django.db.models import Q

from overslot.models import Subscription
from overslot.subscription_views import (
    retrieve_stripe_subscription_for_local,
    sync_local_subscription_from_stripe,
)

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = (
        'Retrieve each local subscription from Stripe, apply the same sync used by webhooks, '
        'and email on a real cancel, pause, or resume transition. Safe to run repeatedly.'
    )

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Print field changes without saving or sending email.',
        )

    def handle(self, *args, **options):
        dry_run = options['dry_run']
        qs = (
            Subscription.objects.filter(
                Q(stripe_subscription_id__gt='') | Q(stripe_customer_id__gt='')
            )
            .select_related('user')
            .order_by('id')
        )
        seen = 0
        updated = 0
        for local in qs.iterator():
            seen += 1
            try:
                remote = retrieve_stripe_subscription_for_local(local)
            except stripe.error.StripeError:
                logger.exception(
                    'reconcile_stripe_subscriptions Stripe error subscription=%s',
                    local.pk,
                )
                self.stderr.write(f'subscription {local.pk}: Stripe error')
                continue
            except Exception:
                logger.exception(
                    'reconcile_stripe_subscriptions failed subscription=%s',
                    local.pk,
                )
                self.stderr.write(f'subscription {local.pk}: error')
                continue
            if remote is None:
                self.stdout.write(f'subscription {local.pk}: no Stripe subscription found')
                continue
            try:
                changes = sync_local_subscription_from_stripe(
                    local,
                    remote,
                    dry_run=dry_run,
                )
            except Exception:
                logger.exception(
                    'reconcile_stripe_subscriptions sync failed subscription=%s',
                    local.pk,
                )
                self.stderr.write(f'subscription {local.pk}: sync error')
                continue
            if changes:
                updated += 1
                summary = '; '.join(changes)
            else:
                summary = 'no changes'
            prefix = 'dry-run' if dry_run else 'updated'
            self.stdout.write(f'subscription {local.pk}: {prefix} {summary}')
        self.stdout.write(f'seen={seen} changed={updated} dry_run={dry_run}')
