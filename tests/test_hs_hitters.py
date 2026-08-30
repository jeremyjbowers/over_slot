import json

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from overslot.management.commands.load_hs_hitters import hs_hitter_tabs
from overslot.models import Player, PlayerStatSeason


class HsHitterTabTests(TestCase):
    def test_includes_2026_summer_tabs(self):
        tabs = hs_hitter_tabs()
        self.assertIn("2027 HS Hitters - 2026", tabs)
        self.assertIn("2028 HS Hitters - 2026", tabs)
        self.assertNotIn("2026 HS Hitters - 2026", tabs)


class HsHittersYearViewTests(TestCase):
    def setUp(self):
        self.staff = User.objects.create_user(
            username="staff@example.com",
            email="staff@example.com",
            password="pass",
            is_staff=True,
        )
        self.client.force_login(self.staff)

    def _season(self, year, name, **kwargs):
        player = Player.objects.create(name=name)
        defaults = {
            "player": player,
            "year": str(year),
            "level": "High School",
            "hs_contact_pct_percentile": 60.0,
        }
        defaults.update(kwargs)
        return PlayerStatSeason.objects.create(**defaults)

    def test_twitch_column_shown_when_rsi_present(self):
        self._season("2026", "Ada Twitch", hs_twitch_percentile=72.0)
        response = self.client.get(reverse("hs_hitters_year", kwargs={"year": 2026}))
        self.assertEqual(response.status_code, 200)
        self.assertIn(("hs_twitch_percentile", "Twitch"), response.context["columns"])
        self.assertContains(response, "Twitch")
        self.assertEqual(response.context["hs_years"][0], 2026)

    def test_twitch_column_hidden_when_rsi_absent(self):
        self._season("2025", "Bea NoRsi")
        response = self.client.get(reverse("hs_hitters_year", kwargs={"year": 2025}))
        self.assertEqual(response.status_code, 200)
        self.assertNotIn(("hs_twitch_percentile", "Twitch"), response.context["columns"])

    def test_player_page_includes_twitch_axis(self):
        season = self._season(
            "2026",
            "Cara Hitter",
            hs_twitch_percentile=80.0,
            hs_twitch_points_above_median=0.4,
        )
        response = self.client.get(
            reverse("players_detail", kwargs={"slug": season.player.slug})
        )
        self.assertEqual(response.status_code, 200)
        payload = json.loads(response.context["hitter_seasons"][0]["hitter_json"])
        self.assertEqual(payload["items"][-1]["axis"], "Twitch")
