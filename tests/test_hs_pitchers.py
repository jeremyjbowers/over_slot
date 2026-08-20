from django.test import SimpleTestCase, TestCase

from overslot import models, utils


class SheetPlayerNameTests(SimpleTestCase):
    def test_flips_last_first(self):
        self.assertEqual(utils.normalize_sheet_player_name("Pence, Striker"), "Striker Pence")

    def test_strips_quoted_nickname(self):
        self.assertEqual(
            utils.normalize_sheet_player_name('Jones Jr., Harry "Chubb"'),
            "Harry Jones Jr.",
        )

    def test_keeps_first_last(self):
        self.assertEqual(utils.normalize_sheet_player_name("Colin Linder"), "Colin Linder")

    def test_handles_blank(self):
        self.assertEqual(utils.normalize_sheet_player_name(""), "")
        self.assertEqual(utils.normalize_sheet_player_name(None), "")


class HsPitcherTabTests(SimpleTestCase):
    def test_parses_expected_tabs(self):
        self.assertEqual(
            utils.parse_hs_pitcher_tab("HS Fourseam 2026"),
            ("2026", "fourseam", "Fourseam"),
        )
        self.assertEqual(
            utils.parse_hs_pitcher_tab("HS Changeup 2026"),
            ("2026", "changeup", "Changeup"),
        )
        self.assertEqual(
            utils.parse_hs_pitcher_tab("HS Splitter 2026"),
            ("2026", "splitter", "Splitter"),
        )

    def test_ignores_non_pitch_tabs(self):
        self.assertIsNone(utils.parse_hs_pitcher_tab("2026 Fourseam"))
        self.assertIsNone(utils.parse_hs_pitcher_tab("2027 HS Hitters - 2026"))
        self.assertIsNone(utils.parse_hs_pitcher_tab("2025 HS Pitching"))

    def test_discover_filters_and_keeps_order(self):
        titles = [
            "2026 Fourseam",
            "HS Fourseam 2026",
            "HS Sinker 2026",
            "2027 HS Hitters - 2026",
            "HS Splitter 2026",
        ]
        self.assertEqual(
            utils.discover_hs_pitcher_tabs(titles),
            [
                ("HS Fourseam 2026", "2026", "fourseam", "Fourseam"),
                ("HS Sinker 2026", "2026", "sinker", "Sinker"),
                ("HS Splitter 2026", "2026", "splitter", "Splitter"),
            ],
        )


class PitchTypeFieldTests(TestCase):
    def test_set_pitch_type_fields_writes_stuff_plus_and_splitter(self):
        player = models.Player.objects.create(name="Test Arm", position="RHP")
        season = models.PlayerStatSeason.objects.create(
            player=player, year="2026", level="High School"
        )
        utils.set_pitch_type_fields(
            season,
            "splitter",
            percentile=0.72,
            vert_break=-1.4,
            horiz_break=11.8,
            stuff_plus=107,
        )
        season.save()
        season.refresh_from_db()
        self.assertAlmostEqual(season.splitter_percentile, 0.72)
        self.assertAlmostEqual(season.splitter_score, 0.72)
        self.assertAlmostEqual(season.splitter_vert_break, -1.4)
        self.assertAlmostEqual(season.splitter_horiz_break, 11.8)
        self.assertEqual(season.splitter_stuff_plus, 107)

    def test_parse_stuff_plus(self):
        self.assertEqual(utils.parse_stuff_plus({"Stuff+": "111"}), 111.0)
        self.assertEqual(utils.parse_stuff_plus({"Stuff Plus": "99.5"}), 99.5)
        self.assertIsNone(utils.parse_stuff_plus({"Name": "Nobody"}))

    def test_second_best_stuff_plus_ranks_near_top_of_class(self):
        rows = [{"Stuff+": str(v)} for v in (65, 80, 86, 90, 94, 100, 107, 111)]
        distribution = utils.calculate_percentile_distribution(rows, "Stuff+")
        second_best = utils.get_percentile_rank(107, distribution, invert=False)
        mid = utils.get_percentile_rank(90, distribution, invert=False)
        self.assertGreaterEqual(second_best, 0.8)
        self.assertGreater(second_best, mid)
