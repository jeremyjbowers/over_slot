"""Replay Stripe webhook events that are still pending or failed."""

import logging

from django.core.management.base import BaseCommand

from overslot.models import StripeWebhookEvent
from overslot.subscription_views import process_stripe_webhook_event

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Process pending and failed Stripe webhook events. Safe to run repeatedly.'

    def handle(self, *args, **options):
        qs = StripeWebhookEvent.objects.filter(
            status__in=[
                StripeWebhookEvent.STATUS_PENDING,
                StripeWebhookEvent.STATUS_FAILED,
            ]
        ).order_by('id')
        processed = 0
        failed = 0
        for record in qs.iterator():
            try:
                process_stripe_webhook_event(record)
                record.refresh_from_db()
                if record.status == StripeWebhookEvent.STATUS_PROCESSED:
                    processed += 1
                else:
                    failed += 1
            except Exception:
                failed += 1
                logger.exception('process_stripe_events failed for %s', record.stripe_event_id)
        self.stdout.write(f'processed={processed} failed={failed}')
