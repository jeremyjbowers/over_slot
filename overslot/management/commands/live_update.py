from django.core.management import call_command
from django.core.management.base import BaseCommand

# Pitch tracking, 643 live stats, ESPN games, the coaches poll, and the
# podcast feed do not update again until the season. Rankings and mocks keep
# loading. Set this to False to run every loader again.
OFFSEASON = True

OFFSEASON_SKIP = (
    "load_podcast_episodes",
    "load_college_hitters",
    "load_college_pitchers",
    "load_hs_hitters",
    "load_643_stats",
    "load_games",
    "load_coaches_poll",
)


class Command(BaseCommand):
    help = (
        "Refresh site data. While OFFSEASON is True, only rankings, mocks, "
        "and the player-duplicate scan run."
    )

    def handle(self, *args, **options):
        self._run("load_podcast_episodes")

        self._run("generate_player_duplicates")
        self._run("sheet_load_rankings")
        self._run("sheet_load_mocks")
        self._run("load_college_hitters")
        self._run("load_college_pitchers")
        self._run("load_hs_hitters")
        self._run("generate_player_duplicates")

        self._run("load_643_stats")
        self._run("load_games")
        self._run("load_coaches_poll")

    def _run(self, name):
        if OFFSEASON and name in OFFSEASON_SKIP:
            self.stdout.write(f"Skipping {name} until the season starts")
            return
        call_command(name)
