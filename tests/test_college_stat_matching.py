from django.test import TestCase

from overslot import models, utils


def _make_player(name, school="Some HS", position="SS"):
    return models.Player.objects.create(name=name, school=school, position=position)


def _make_ranking(year, draft_level="High School"):
    return models.Ranking.objects.create(
        year=str(year),
        is_draft=True,
        draft_level=draft_level,
        publish=True,
    )


def _rank_player(player, ranking, level, school=None, commitment=None, active=True):
    return models.PlayerRanking.objects.create(
        player=player,
        ranking=ranking,
        level=level,
        school=player.school if school is None else school,
        commitment=commitment,
        active=active,
    )


class CollegeStatMatchingTestCase(TestCase):
    def test_hs_prospect_rejects_college_season_before_draft_year(self):
        player = _make_player("Jack Leeper", school="St. Francis")
        ranking = _make_ranking(2027)
        _rank_player(player, ranking, "High School", commitment="Stanford")

        self.assertFalse(utils.player_accepts_college_season(player, "2025"))
        self.assertFalse(utils.player_accepts_college_season(player, "2027"))
        self.assertTrue(utils.player_accepts_college_season(player, "2028"))

    def test_inactive_hs_ranking_still_blocks(self):
        player = _make_player("Kellen Rogers", school="Wake Forest")
        ranking = _make_ranking(2027)
        _rank_player(player, ranking, "High School", commitment="NC State", active=False)

        self.assertFalse(utils.player_accepts_college_season(player, "2022"))

    def test_former_hs_player_accepts_later_college_season(self):
        player = _make_player("A.J. Evasco", school="Lincoln East")
        ranking = _make_ranking(2024)
        _rank_player(player, ranking, "High School", commitment="Kansas State")

        self.assertFalse(utils.player_accepts_college_season(player, "2024"))
        self.assertTrue(utils.player_accepts_college_season(player, "2025"))

    def test_college_ranking_allows_college_stats_even_with_prior_hs(self):
        player = _make_player("Andrew Costello", school="Wake Forest")
        hs = _make_ranking(2026, draft_level="High School")
        college = _make_ranking(2028, draft_level="College")
        _rank_player(player, hs, "High School", school="Cathedral Prep", active=False)
        _rank_player(player, college, "College", school="")

        self.assertTrue(utils.player_accepts_college_season(player, "2025"))

    def test_unranked_player_is_allowed(self):
        player = _make_player("Mystery College Guy")
        self.assertTrue(utils.player_accepts_college_season(player, "2025"))

    def test_resolve_college_stat_player_skips_hs_collision(self):
        player = _make_player("Jake Turner", school="Centennial")
        ranking = _make_ranking(2027)
        _rank_player(player, ranking, "High School", commitment="TCU")

        self.assertIsNone(utils.resolve_college_stat_player("Jake Turner", "2025"))
        self.assertEqual(
            utils.resolve_college_stat_player("Jake Turner", "2028").pk,
            player.pk,
        )

    def test_find_mismatched_college_stats(self):
        hs_player = _make_player("Jack Leeper", school="St. Francis")
        ranking = _make_ranking(2027)
        _rank_player(hs_player, ranking, "High School")
        bad = models.PlayerStatSeason.objects.create(
            player=hs_player, year="2025", level="College", school="Jacksonville State University"
        )
        ok_hs = models.PlayerStatSeason.objects.create(
            player=hs_player, year="2025", level="High School", school="St. Francis"
        )
        bad_643 = models.Player643StatSeason.objects.create(
            player=hs_player, year="2022", team_name="Prairie View"
        )

        college_player = _make_player("Real College Hitter", school="Clemson")
        college_ranking = _make_ranking(2026, draft_level="College")
        _rank_player(college_player, college_ranking, "College", school="")
        models.PlayerStatSeason.objects.create(
            player=college_player, year="2025", level="College", school="Clemson"
        )

        trackman, stats_643 = utils.find_mismatched_college_stats()
        self.assertEqual({s.id for s in trackman}, {bad.id})
        self.assertEqual({s.id for s in stats_643}, {bad_643.id})
        self.assertTrue(models.PlayerStatSeason.objects.filter(id=ok_hs.id).exists())
