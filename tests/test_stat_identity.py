from django.contrib.auth.models import User
from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse

from overslot import models, stat_identity, utils


def _player(name, school, position="OF"):
    return models.Player.objects.create(name=name, school=school, position=position)


def _rank(player, year, level, school, commitment=None):
    ranking, _ = models.Ranking.objects.get_or_create(
        year=str(year), is_draft=True, draft_level=level, defaults={"publish": True}
    )
    return models.PlayerRanking.objects.create(
        player=player, ranking=ranking, level=level, school=school, commitment=commitment, active=True
    )


class SchoolNormalizationTests(TestCase):
    def test_common_spellings_match(self):
        pairs = [
            ("NC State", "North Carolina State"),
            ("USF", "University of South Florida"),
            ("FGCU", "Florida Gulf Coast University"),
            ("Saint Mary's (CA)", "St. Mary's"),
            ("Cal Baptist", "California Baptist"),
            ("St. Louis", "Saint Louis University"),
            ("LSU", "Louisiana State"),
            ("Ole Miss", "Mississippi"),
            ("SIUE", "Southern Illinois Univ.-Edwardsville"),
            ("USC Upstate", "South Carolina Upstate"),
        ]
        for a, b in pairs:
            self.assertTrue(stat_identity.schools_match(a, b), f"{a} vs {b}")

    def test_different_schools_do_not_match(self):
        pairs = [
            ("South Carolina", "USC Upstate"),
            ("Texas", "Texas Tech"),
            ("NC State", "UNC Asheville"),
            ("South Alabama", "Alabama"),
        ]
        for a, b in pairs:
            self.assertFalse(stat_identity.schools_match(a, b), f"{a} vs {b}")


class ResolveCollegeStatPlayerTests(TestCase):
    def setUp(self):
        self.rett = _player("Rett Johnson", "NC State")
        _rank(self.rett, 2027, "College", "NC State")

    def resolve(self, name, year, team, source="trackman"):
        return utils.resolve_college_stat_player(name, year, team=team, source=source)

    def test_same_school_attaches(self):
        self.assertEqual(self.resolve("Rett Johnson", "2026", "North Carolina State"), self.rett)

    def test_other_school_is_held_and_queued(self):
        self.assertIsNone(self.resolve("Rett Johnson", "2025", "South Alabama"))
        link = models.StatTeamLink.objects.get(player=self.rett)
        self.assertEqual(link.status, models.StatTeamLink.PENDING)
        self.assertEqual(link.team_key, stat_identity.normalize_school("South Alabama"))
        self.assertIn("trackman:2025", link.seasons)

    def test_accepted_link_attaches_transfer(self):
        self.resolve("Rett Johnson", "2025", "South Alabama")
        models.StatTeamLink.objects.filter(player=self.rett).update(status=models.StatTeamLink.ACCEPTED)
        self.assertEqual(self.resolve("Rett Johnson", "2025", "South Alabama"), self.rett)

    def test_rejected_link_is_remembered(self):
        self.resolve("Rett Johnson", "2025", "South Alabama")
        models.StatTeamLink.objects.filter(player=self.rett).update(status=models.StatTeamLink.REJECTED)
        self.assertIsNone(self.resolve("Rett Johnson", "2026", "South Alabama"))
        self.assertFalse(
            models.StatTeamLink.objects.filter(player=self.rett, status=models.StatTeamLink.PENDING).exists()
        )

    def test_two_players_same_name_pick_by_school(self):
        other = _player("Rett Johnson", "South Alabama")
        _rank(other, 2025, "College", "South Alabama")
        self.assertEqual(self.resolve("Rett Johnson", "2025", "South Alabama"), other)
        self.assertEqual(self.resolve("Rett Johnson", "2026", "NC State"), self.rett)

    def test_hs_commitment_counts_as_known_school(self):
        hs = _player("Aiden Barrientes", "Katy", position="RHP")
        _rank(hs, 2025, "High School", "Katy", commitment="TCU")
        self.assertEqual(self.resolve("Aiden Barrientes", "2026", "Texas Christian"), hs)

    def test_643_career_corroborates_transfer(self):
        models.Player643StatSeason.objects.create(player=self.rett, year="2024", team_name="Clemson")
        self.assertEqual(self.resolve("Rett Johnson", "2024", "Clemson"), self.rett)
        self.assertEqual(self.resolve("Rett Johnson", "2023", "Clemson"), self.rett)

    def test_trackman_same_season_corroborates_643_name_match(self):
        models.PlayerStatSeason.objects.create(player=self.rett, year="2024", level="College", school="Clemson")
        self.assertTrue(stat_identity.team_fits_player(self.rett, "Clemson", "2024", source="643"))
        self.assertFalse(stat_identity.team_fits_player(self.rett, "Clemson", "2023", source="643"))

    def test_last_first_names(self):
        self.assertEqual(self.resolve("Johnson, Rett", "2026", "NC State"), self.rett)

    def test_name_only_call_keeps_old_behavior(self):
        self.assertEqual(utils.resolve_college_stat_player("Rett Johnson", "2025"), self.rett)


class StatLinkReviewViewTests(TestCase):
    def setUp(self):
        self.staff = User.objects.create_user("staff", password="pw", is_staff=True)
        self.client.force_login(self.staff)
        self.rett = _player("Rett Johnson", "NC State")
        _rank(self.rett, 2027, "College", "NC State")
        models.PlayerStatSeason.objects.create(player=self.rett, year="2025", level="College", school="South Alabama")
        models.PlayerStatSeason.objects.create(player=self.rett, year="2026", level="College", school="NC State")
        models.Player643StatSeason.objects.create(player=self.rett, year="2025", team_name="South Alabama")

    def decide(self, action, team="South Alabama", **extra):
        return self.client.post(
            reverse("stat_link_decide", args=[self.rett.uuid]),
            {"team_key": stat_identity.normalize_school(team), "raw_team": team, "action": action, **extra},
        )

    def test_queue_and_player_pages_render(self):
        # Without 6-4-3 backing it up, the South Alabama season needs review.
        models.Player643StatSeason.objects.filter(player=self.rett).delete()
        call_command("find_stat_melts", stdout=open("/dev/null", "w"))
        r = self.client.get(reverse("stat_link_queue"))
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "South Alabama")
        r = self.client.get(reverse("stat_link_player", args=[self.rett.uuid]))
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "on his record")

    def test_reject_removes_that_teams_seasons(self):
        self.decide("reject")
        self.assertEqual(
            list(models.PlayerStatSeason.objects.filter(player=self.rett).values_list("school", flat=True)),
            ["NC State"],
        )
        self.assertFalse(models.Player643StatSeason.objects.filter(player=self.rett).exists())
        link = models.StatTeamLink.objects.get(player=self.rett)
        self.assertEqual(link.status, models.StatTeamLink.REJECTED)
        self.assertEqual(link.decided_by, self.staff)

    def test_move_to_other_player(self):
        other = _player("Rett Johnson", "South Alabama")
        self.decide("move", target=f"https://overslotbaseball.com/players/{other.slug}/")
        self.assertEqual(models.PlayerStatSeason.objects.get(player=other).school, "South Alabama")
        self.assertTrue(models.Player643StatSeason.objects.filter(player=other).exists())
        self.assertEqual(
            models.StatTeamLink.objects.get(player=other).status, models.StatTeamLink.ACCEPTED
        )
        # Next load sends South Alabama rows to the right player.
        self.assertEqual(
            utils.resolve_college_stat_player("Rett Johnson", "2025", team="South Alabama", source="trackman"),
            other,
        )

    def test_accept_keeps_seasons(self):
        self.decide("accept")
        self.assertEqual(models.PlayerStatSeason.objects.filter(player=self.rett).count(), 2)
        self.assertEqual(models.StatTeamLink.objects.get(player=self.rett).status, models.StatTeamLink.ACCEPTED)

    def test_requires_staff(self):
        self.client.logout()
        r = self.client.get(reverse("stat_link_queue"))
        self.assertNotEqual(r.status_code, 200)


class FindStatMeltsTests(TestCase):
    def test_flags_conflicts_and_unknown_schools_only(self):
        rett = _player("Rett Johnson", "NC State")
        _rank(rett, 2027, "College", "NC State")
        models.PlayerStatSeason.objects.create(player=rett, year="2026", level="College", school="NC State")
        models.PlayerStatSeason.objects.create(player=rett, year="2025", level="College", school="South Alabama")
        transfer = _player("Liam Doyle", "Tennessee", position="LHP")
        _rank(transfer, 2025, "College", "Tennessee")
        # 6-4-3 career history alone (no conflict) is trusted.
        models.Player643StatSeason.objects.create(player=transfer, year="2024", team_name="Ole Miss")
        # Trackman and 6-4-3 disagree in the same season.
        davis = _player("Davis Rivers", "Texas Tech")
        _rank(davis, 2026, "College", "Texas Tech")
        models.PlayerStatSeason.objects.create(player=davis, year="2025", level="College", school="Wofford College")
        models.Player643StatSeason.objects.create(player=davis, year="2025", team_name="Texas Tech")

        call_command("find_stat_melts", "--dry-run", stdout=open("/dev/null", "w"))
        self.assertFalse(models.StatTeamLink.objects.exists())

        call_command("find_stat_melts", stdout=open("/dev/null", "w"))
        links = {(l.player.name, l.raw_team, l.reason) for l in models.StatTeamLink.objects.all()}
        self.assertEqual(
            links,
            {
                ("Rett Johnson", "South Alabama", models.StatTeamLink.REASON_UNKNOWN_SCHOOL),
                ("Davis Rivers", "Wofford College", models.StatTeamLink.REASON_CONFLICT),
            },
        )
        # Running again doesn't duplicate.
        call_command("find_stat_melts", stdout=open("/dev/null", "w"))
        self.assertEqual(models.StatTeamLink.objects.count(), 2)


class MergeMovesStatsTests(TestCase):
    def setUp(self):
        self.staff = User.objects.create_user("staff", password="pw", is_staff=True)
        self.client.force_login(self.staff)
        self.keeper = _player("Joey McLaughlin III", "Arkansas State")
        self.removed = _player("Joey McLaughlin", "Arkansas State")
        models.PlayerStatSeason.objects.create(player=self.removed, year="2026", level="College", school="Arkansas State")
        models.PlayerStatSeason.objects.create(player=self.removed, year="2025", level="College", school="Arkansas State")
        models.PlayerStatSeason.objects.create(player=self.keeper, year="2025", level="College", school="Arkansas State")
        models.Player643StatSeason.objects.create(player=self.removed, year="2026", team_name="Arkansas State")

    def test_merge_moves_stat_seasons(self):
        self.client.post(
            reverse("merge_players", args=[self.keeper.uuid, self.removed.uuid]),
            {"primary_player": str(self.keeper.uuid)},
        )
        self.assertEqual(
            sorted(models.PlayerStatSeason.objects.filter(player=self.keeper).values_list("year", flat=True)),
            ["2025", "2026"],
        )
        self.assertTrue(models.Player643StatSeason.objects.filter(player=self.keeper).exists())
        # The keeper's own 2025 season wins; the duplicate stays behind.
        self.assertEqual(models.PlayerStatSeason.objects.filter(player=self.removed).count(), 1)

    def test_find_stat_melts_moves_stranded_seasons(self):
        self.removed.active = False
        self.removed.save()
        models.DuplicateDecision.objects.create(
            player1=self.keeper, player2=self.removed, decision="merged", primary_player=self.keeper
        )
        call_command("find_stat_melts", "--move-merged", stdout=open("/dev/null", "w"))
        self.assertEqual(models.PlayerStatSeason.objects.filter(player=self.keeper, year="2026").count(), 1)
        self.assertTrue(models.Player643StatSeason.objects.filter(player=self.keeper).exists())
