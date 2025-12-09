from django.core.management.base import BaseCommand, CommandError
from django.conf import settings
from django.core.management import call_command

from overslot import models, utils


class Command(BaseCommand):
    def handle(self, *args, **options):
        call_command('generate_duplicates')
        call_command('sheet_load_rankings')
        call_command('sheet_load_trackman')
        call_command('generate_duplicates')
        call_command('sheet_load_mocks')
        call_command('load_podcast_episodes')