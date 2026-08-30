import json

from django.contrib.auth.models import User
from django.test import SimpleTestCase, TestCase
from django.urls import reverse

from overslot.management.commands.load_hs_hitters import hs_hitter_tabs
from overslot.models import Player, PlayerStatSeason
from overslot.views import group_stat_charts_by_year


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


class StatYearGroupTests(SimpleTestCase):
    def test_two_way_same_year_shares_one_group(self):
        charts = [
            {"year": "2026", "level": "High School", "hitter_json": "{}", "pitcher_json": "{}"},
            {"year": "2025", "level": "High School", "hitter_json": "{}", "pitcher_json": None},
        ]
        groups = group_stat_charts_by_year(charts)
        self.assertEqual([g["year"] for g in groups], ["2026", "2025"])
        self.assertTrue(groups[0]["has_hitting"])
        self.assertTrue(groups[0]["has_pitching"])
        self.assertTrue(groups[1]["has_hitting"])
        self.assertFalse(groups[1]["has_pitching"])


class TwoWayPlayerPageTests(TestCase):
    def setUp(self):
        self.staff = User.objects.create_user(
            username="staff@example.com",
            email="staff@example.com",
            password="pass",
            is_staff=True,
        )
        self.client.force_login(self.staff)
        self.player = Player.objects.create(name="Two Way Kid")
        PlayerStatSeason.objects.create(
            player=self.player,
            year="2026",
            level="High School",
            hs_contact_pct_percentile=55.0,
            fourseam_percentile=0.72,
            fourseam_stuff_plus=108,
            fourseam_vert_break=16.0,
            fourseam_horiz_break=-8.0,
        )
        PlayerStatSeason.objects.create(
            player=self.player,
            year="2025",
            level="High School",
            hs_contact_pct_percentile=48.0,
            slider_percentile=0.61,
            slider_stuff_plus=99,
        )

    def test_year_tabs_show_hitting_and_pitching_together(self):
        response = self.client.get(
            reverse("players_detail", kwargs={"slug": self.player.slug})
        )
        self.assertEqual(response.status_code, 200)
        groups = response.context["stat_year_groups"]
        self.assertEqual([g["year"] for g in groups], ["2026", "2025"])
        self.assertTrue(groups[0]["has_hitting"] and groups[0]["has_pitching"])
        self.assertTrue(groups[1]["has_hitting"] and groups[1]["has_pitching"])
        self.assertContains(response, 'id="stat-year-tabs"')
        self.assertContains(response, "2026 Hitter Performance")
        self.assertContains(response, "2026 Pitch Design")
        self.assertContains(response, "2026 Stuff+")
        # Two-way seasons must render both chart types (not hitter-only via elif)
        self.assertContains(response, "renderHitterChart")
        self.assertContains(response, "renderPitcherChart")
        self.assertContains(response, "renderPitchMovementChart")

