from django.core.management.base import BaseCommand, CommandError
from django.conf import settings
from django.core.management import call_command

from overslot import models, utils


class Command(BaseCommand):
    def handle(self, *args, **options):
        call_command('load_podcast_episodes')

        call_command('generate_player_duplicates')
        call_command('sheet_load_rankings')
        # call_command('sheet_load_mocks')
        call_command('load_college_hitters')
        call_command('load_college_pitchers')
        call_command('load_hs_hitters')
        call_command('generate_player_duplicates')

        call_command('load_643_stats')
        call_command('load_games')
        call_command('load_coaches_poll')
