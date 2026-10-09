"""Replay Stripe webhook events that are still pending or failed."""

import logging
from datetime import timedelta

from django.core.management.base import BaseCommand
from django.db.models import Q
from django.utils import timezone

from overslot.models import StripeWebhookEvent
from overslot.subscription_views import process_stripe_webhook_event

logger = logging.getLogger(__name__)


def drain_stripe_webhook_events(*, retry_failed_after_seconds=None):
    """
    Apply pending StripeWebhookEvent rows.

    Failed rows are included. When retry_failed_after_seconds is set, a failed
    row is skipped until that many seconds have passed since it was last saved,
    so a long-running worker does not hammer a poison event.
    Returns (processed, failed).
    """
    pending = Q(status=StripeWebhookEvent.STATUS_PENDING)
    if retry_failed_after_seconds is None:
        failed = Q(status=StripeWebhookEvent.STATUS_FAILED)
    else:
        cutoff = timezone.now() - timedelta(seconds=retry_failed_after_seconds)
        failed = Q(status=StripeWebhookEvent.STATUS_FAILED, last_modified__lt=cutoff)
    qs = StripeWebhookEvent.objects.filter(pending | failed).order_by('id')
    processed = 0
    failed_count = 0
    for record in qs.iterator():
        try:
            process_stripe_webhook_event(record)
            record.refresh_from_db()
            if record.status == StripeWebhookEvent.STATUS_PROCESSED:
                processed += 1
            else:
                failed_count += 1
        except Exception:
            failed_count += 1
            logger.exception('process_stripe_events failed for %s', record.stripe_event_id)
    return processed, failed_count


class Command(BaseCommand):
    help = 'Process pending and failed Stripe webhook events once. Safe to run repeatedly.'

    def handle(self, *args, **options):
        processed, failed = drain_stripe_webhook_events()
        self.stdout.write(f'processed={processed} failed={failed}')
