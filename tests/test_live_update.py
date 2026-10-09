from io import StringIO
from unittest.mock import patch

from django.core.management import call_command
from django.test import SimpleTestCase

from overslot.management.commands.live_update import OFFSEASON_SKIP


class LiveUpdateOffseasonTestCase(SimpleTestCase):
    def test_offseason_keeps_rankings_mocks_and_duplicate_scan(self):
        with patch("overslot.management.commands.live_update.call_command") as mocked:
            out = StringIO()
            call_command("live_update", stdout=out)

        self.assertEqual(
            [call.args[0] for call in mocked.call_args_list],
            [
                "generate_player_duplicates",
                "sheet_load_rankings",
                "sheet_load_mocks",
                "generate_player_duplicates",
            ],
        )
        logged = out.getvalue()
        for name in OFFSEASON_SKIP:
            self.assertIn(f"Skipping {name} until the season starts", logged)

    def test_season_runs_every_loader(self):
        with patch("overslot.management.commands.live_update.OFFSEASON", False), patch(
            "overslot.management.commands.live_update.call_command"
        ) as mocked:
            call_command("live_update", stdout=StringIO())

        self.assertEqual(
            [call.args[0] for call in mocked.call_args_list],
            [
                "load_podcast_episodes",
                "generate_player_duplicates",
                "sheet_load_rankings",
                "sheet_load_mocks",
                "load_college_hitters",
                "load_college_pitchers",
                "load_hs_hitters",
                "generate_player_duplicates",
                "load_643_stats",
                "load_games",
                "load_coaches_poll",
            ],
        )
