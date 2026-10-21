from django.core.management import call_command
from django.core.management.base import BaseCommand

# 643 live stats, ESPN games, the coaches poll, and the podcast feed do not
# update again until the season. Trackman (college/HS hitters + pitchers) is
# re-enabled for a few weeks of sheet updates, then should go back in
# OFFSEASON_SKIP until February. Rankings and mocks keep loading. Set
# OFFSEASON to False to run every loader again.
OFFSEASON = True

OFFSEASON_SKIP = (
    "load_podcast_episodes",
    "load_643_stats",
    "load_games",
    "load_coaches_poll",
)


class Command(BaseCommand):
    help = (
        "Refresh site data. While OFFSEASON is True, rankings, mocks, "
        "Trackman loaders, the highlight playlist, and the player-duplicate "
        "scan run; 643/games/poll/podcast stay skipped."
    )

    def handle(self, *args, **options):
        self._run("load_podcast_episodes")
        self._run("load_highlight_playlist")

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
