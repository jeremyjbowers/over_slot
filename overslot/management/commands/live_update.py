import time
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
        
        # Load 643 stats and games only every 4 hours (6 times per day)
        # Only run if we're in the first 5 minutes of the 4-hour interval
        current_time = int(time.time())
        interval_seconds = 4 * 60 * 60  # 4 hours
        if (current_time % interval_seconds) < 300:
            call_command('load_games')
            call_command('load_coaches_poll')
            call_command('load_643_stats')
        else:
            self.stdout.write("Skipping 643 stats and games update (not in update window - runs every 4 hours)")
