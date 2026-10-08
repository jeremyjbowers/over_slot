"""Long-running process that applies stored Stripe webhooks and reconciles subscriptions."""

import logging
import signal
import time

from django.core.management.base import BaseCommand
from django.db import close_old_connections

from overslot.management.commands.process_stripe_events import drain_stripe_webhook_events
from overslot.management.commands.reconcile_stripe_subscriptions import (
    reconcile_stripe_subscriptions,
)

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = (
        'Run until stopped. Applies stored Stripe webhook events, and on an interval '
        're-reads each local subscription from Stripe. Start this as a long-running process. '
        'Stop it with SIGINT or SIGTERM.'
    )

    def add_arguments(self, parser):
        parser.add_argument(
            '--sleep',
            type=float,
            default=2,
            help='Seconds to wait between queue drains (default 2).',
        )
        parser.add_argument(
            '--reconcile-every',
            type=float,
            default=300,
            help='Seconds between full Stripe subscription reconciles (default 300).',
        )
        parser.add_argument(
            '--retry-failed-after',
            type=float,
            default=60,
            help='Seconds to wait before retrying a failed webhook event (default 60).',
        )
        parser.add_argument(
            '--once',
            action='store_true',
            help='Drain the queue once, reconcile once, and exit.',
        )
        parser.add_argument(
            '--skip-reconcile',
            action='store_true',
            help='Do not call Stripe to reconcile local subscriptions.',
        )
        parser.add_argument(
            '--no-email',
            action='store_true',
            help='Reconcile Stripe state without sending cancel, pause, or resume email.',
        )

    def handle(self, *args, **options):
        sleep_seconds = max(0.1, options['sleep'])
        reconcile_every = max(0, options['reconcile_every'])
        retry_after = max(0, options['retry_failed_after'])
        once = options['once']
        skip_reconcile = options['skip_reconcile']
        send_notices = not options['no_email']

        stopping = False

        def request_stop(signum, frame):
            nonlocal stopping
            stopping = True
            self.stdout.write('stripe worker stopping')

        previous_handlers = {}
        for sig in (signal.SIGINT, signal.SIGTERM):
            try:
                previous_handlers[sig] = signal.signal(sig, request_stop)
            except ValueError:
                # signal() is only available on the main thread.
                pass

        self.stdout.write(
            'stripe worker started '
            f'sleep={sleep_seconds} reconcile_every={reconcile_every} once={once}'
        )
        next_reconcile = time.monotonic()
        try:
            while not stopping:
                # A one-shot run shares the caller's database connection (tests).
                # The long-running loop must drop idle connections between passes.
                if not once:
                    close_old_connections()
                try:
                    processed, failed = drain_stripe_webhook_events(
                        retry_failed_after_seconds=retry_after,
                    )
                except Exception:
                    logger.exception('stripe worker failed while draining webhook events')
                    processed, failed = 0, 0
                if processed or failed:
                    self.stdout.write(f'events processed={processed} failed={failed}')

                now = time.monotonic()
                if not skip_reconcile and now >= next_reconcile:
                    try:
                        seen, changed = reconcile_stripe_subscriptions(
                            send_notices=send_notices,
                            write=self.stdout.write,
                        )
                    except Exception:
                        logger.exception('stripe worker failed while reconciling subscriptions')
                        seen, changed = 0, 0
                    self.stdout.write(f'reconcile seen={seen} changed={changed}')
                    next_reconcile = time.monotonic() + reconcile_every

                if once or stopping:
                    break
                close_old_connections()
                deadline = time.monotonic() + sleep_seconds
                while not stopping and time.monotonic() < deadline:
                    time.sleep(min(0.25, max(0, deadline - time.monotonic())))
        finally:
            for sig, old in previous_handlers.items():
                signal.signal(sig, old)
            self.stdout.write('stripe worker stopped')
