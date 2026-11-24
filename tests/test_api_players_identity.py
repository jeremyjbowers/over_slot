import csv
import io
import os
from unittest import mock

from django.test import TestCase
from django.urls import reverse

from overslot import models


@mock.patch.dict(os.environ, {"OVERSLOT_API_KEY": "k"})
class ApiPlayersIdentityTests(TestCase):
    def setUp(self):
        self.keeper = models.Player.objects.create(name="Rett Johnson", position="OF")
        self.middle = models.Player.objects.create(name="Rett Johnson", position="SS", active=False)
        self.gone = models.Player.objects.create(name="Rett Johnsen", position="OF", active=False)
        # gone -> middle -> keeper
        models.DuplicateDecision.objects.create(
            player1=self.middle, player2=self.keeper, decision="merged", primary_player=self.keeper
        )
        models.DuplicateDecision.objects.create(
            player1=self.gone, player2=self.middle, decision="merged", primary_player=self.middle
        )
        hs, _ = models.Ranking.objects.get_or_create(year="2024", is_draft=True, draft_level="High School")
        col, _ = models.Ranking.objects.get_or_create(year="2027", is_draft=True, draft_level="College")
        overall, _ = models.Ranking.objects.get_or_create(year="2027", is_draft=True, draft_level="Overall")
        mock_r = models.Ranking.objects.create(year="2027", is_draft=True, is_mock_draft=True)
        models.PlayerRanking.objects.create(player=self.keeper, ranking=hs, level="High School", school="Some HS", commitment="NC State")
        models.PlayerRanking.objects.create(player=self.keeper, ranking=col, level="College", school="NC State")
        models.PlayerRanking.objects.create(player=self.keeper, ranking=overall, level="College", school="NC State")
        models.PlayerRanking.objects.create(player=self.keeper, ranking=mock_r, level="College", school="Mock U")

    def get(self, **params):
        return self.client.get(reverse("api_players"), {"overslot_api_key": "k", **params})

    def test_json_has_merged_into_and_schools(self):
        data = {r["uuid"]: r for r in self.get().json()}
        self.assertEqual(len(data), 3)
        k = str(self.keeper.pk)
        self.assertIsNone(data[k]["merged_into"])
        self.assertEqual(data[str(self.middle.pk)]["merged_into"], k)
        self.assertEqual(data[str(self.gone.pk)]["merged_into"], k)
        schools = data[k]["schools"]
        self.assertEqual([(s["year"], s["school"]) for s in schools], [("2027", "NC State"), ("2024", "Some HS")])
        self.assertEqual(schools[1]["commitment"], "NC State")

    def test_active_filter(self):
        data = self.get(active="1").json()
        self.assertEqual([r["uuid"] for r in data], [str(self.keeper.pk)])

    def test_csv_columns(self):
        rows = list(csv.DictReader(io.StringIO(self.get(format="csv").content.decode())))
        by_id = {r["uuid"]: r for r in rows}
        self.assertEqual(by_id[str(self.gone.pk)]["merged_into"], str(self.keeper.pk))
        self.assertEqual(by_id[str(self.keeper.pk)]["schools"], "2027 College: NC State | 2024 High School: Some HS")

    def test_key_still_required(self):
        self.assertEqual(self.client.get(reverse("api_players")).status_code, 401)
