from django.core.management.base import BaseCommand, CommandError
from django.conf import settings
from django.core.management import call_command

from overslot import models, utils


class Command(BaseCommand):
    def handle(self, *args, **options):
        call_command('migrate')
        call_command('collectstatic', '--noinput')
        call_command('initial_load_carryingtools')
        call_command('sheet_load_rankings', '--clear')