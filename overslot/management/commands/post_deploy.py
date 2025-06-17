from django.core.management.base import BaseCommand, CommandError
from django.conf import settings
from django.core.management import call_command

from overslot import models, utils


class Command(BaseCommand):
    def handle(self, *args, **options):
        call_command('migrate')
        call_command('collectstatic', '--noinput')
        
        # Set up cache table for multi-pod deployment
        try:
            call_command('createcachetable')
            self.stdout.write('Cache table created/verified')
        except Exception as e:
            self.stdout.write(f'Cache table setup: {e}')