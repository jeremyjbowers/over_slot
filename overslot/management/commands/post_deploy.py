from django.core.management.base import BaseCommand, CommandError
from django.conf import settings
from django.core.management import call_command

from overslot import models, utils


class Command(BaseCommand):
    def handle(self, *args, **options):
        call_command('migrate')
        call_command('collectstatic', '--noinput')
        call_command('create_teams_from_player_rankings')
        call_command('link_player_rankings_to_teams')