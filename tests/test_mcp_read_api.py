# Read API keys, the JSON read API, and the paywall around published content.
import hashlib
from io import StringIO

from django.contrib.auth.models import User
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import Client, TestCase
from django.urls import reverse

from overslot.models import (
    Article,
    Player,
    Player643StatSeason,
    PlayerRanking,
    PlayerRankingCarryingTool,
    PlayerStatSeason,
    Ranking,
    ReadAPIKey,
    Subscription,
)


def _paid_user(username, email, **extra):
    user = User.objects.create_user(username=username, email=email, password="x", **extra)
    Subscription.objects.create(user=user, status="active")
    return user


class ReadAPIKeyModelTestCase(TestCase):
    def setUp(self):
        self.user = _paid_user("reader", "reader@example.com")

    def test_create_key_stores_hash_and_secret(self):
        raw, key = ReadAPIKey.create_key(self.user, label="laptop")
        self.assertTrue(raw.startswith("overslot_"))
        self.assertEqual(key.token_hash, hashlib.sha256(raw.encode("utf-8")).hexdigest())
        self.assertNotEqual(key.token_hash, raw)
        self.assertEqual(key.token_secret, raw)
        self.assertTrue(raw.startswith(key.token_prefix))
        self.assertEqual(key.label, "laptop")

    def test_authorize_and_revoke(self):
        raw, key = ReadAPIKey.create_key(self.user, label="laptop")
        found, reason = ReadAPIKey.authorize(raw)
        self.assertIsNone(reason)
        self.assertEqual(found.pk, key.pk)
        found.refresh_from_db()
        self.assertIsNotNone(found.last_used_at)

        found.revoke()
        self.assertEqual(ReadAPIKey.authorize(raw), (None, "unauthorized"))
        self.assertEqual(ReadAPIKey.authorize("overslot_not-a-real-key"), (None, "unauthorized"))
        self.assertEqual(ReadAPIKey.authorize(""), (None, "unauthorized"))
        self.assertEqual(ReadAPIKey.authorize(None), (None, "unauthorized"))
        self.assertEqual(ReadAPIKey.authorize("ulmg_something"), (None, "unauthorized"))

    def test_unpaid_account_cannot_create_or_use_a_key(self):
        free = User.objects.create_user(username="free-model", email="free-model@example.com", password="x")
        with self.assertRaises(PermissionError):
            ReadAPIKey.create_key(free)
        staff = User.objects.create_user(
            username="staff-model", email="staff-model@example.com", password="x", is_staff=True
        )
        with self.assertRaises(PermissionError):
            ReadAPIKey.create_key(staff)

        raw, _key = ReadAPIKey.create_key(self.user)
        self.user.subscription.status = "canceled"
        self.user.subscription.save(update_fields=["status"])
        self.assertEqual(ReadAPIKey.authorize(raw)[1], "unpaid")

    def test_inactive_user_cannot_authenticate(self):
        raw, _key = ReadAPIKey.create_key(self.user)
        self.user.is_active = False
        self.user.save(update_fields=["is_active"])
        self.assertEqual(ReadAPIKey.authorize(raw), (None, "unauthorized"))


class CreateReadAPIKeyCommandTestCase(TestCase):
    def setUp(self):
        self.user = _paid_user("cmd", "cmd@example.com")

    def test_command_prints_the_key(self):
        out = StringIO()
        call_command(
            "create_read_api_key",
            "--email",
            "cmd@example.com",
            "--label",
            "cursor",
            stdout=out,
        )
        text = out.getvalue()
        self.assertIn("overslot_", text)
        raw = [line.strip() for line in text.splitlines() if line.strip().startswith("overslot_")][0]
        self.assertIsNone(ReadAPIKey.authorize(raw)[1])
        self.assertEqual(ReadAPIKey.objects.get(user=self.user).label, "cursor")

    def test_command_refuses_an_unpaid_account(self):
        User.objects.create_user(username="cmd-free", email="cmd-free@example.com", password="x")
        with self.assertRaises(CommandError):
            call_command("create_read_api_key", "--email", "cmd-free@example.com")
        self.assertEqual(ReadAPIKey.objects.count(), 0)


class APIKeyPageTestCase(TestCase):
    def setUp(self):
        self.user = _paid_user("page", "page@example.com")
        self.other = _paid_user("other", "other@example.com")
        self.free = User.objects.create_user(
            username="page-free", email="page-free@example.com", password="x"
        )
        self.client = Client()

    def test_page_requires_login(self):
        response = self.client.get(reverse("account_api_keys"))
        self.assertEqual(response.status_code, 302)
        self.assertIn("/accounts/login/", response.url)

    def test_owner_can_create_and_revoke_only_their_keys(self):
        self.client.force_login(self.user)
        response = self.client.post(
            reverse("account_api_keys"),
            {"action": "create", "label": "claude"},
            follow=True,
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "overslot_")
        self.assertContains(response, "claude")
        key = ReadAPIKey.objects.get(user=self.user)
        self.assertEqual(key.label, "claude")

        other_key_raw, other_key = ReadAPIKey.create_key(self.other, label="secret")
        response = self.client.post(
            reverse("account_api_keys"),
            {"action": "revoke", "key_id": other_key.pk},
        )
        self.assertEqual(response.status_code, 404)
        other_key.refresh_from_db()
        self.assertIsNone(other_key.revoked_at)
        self.assertIsNone(ReadAPIKey.authorize(other_key_raw)[1])

        response = self.client.post(
            reverse("account_api_keys"),
            {"action": "revoke", "key_id": key.pk},
            follow=True,
        )
        self.assertContains(response, "Revoked")
        self.assertEqual(ReadAPIKey.authorize(key.token_secret)[1], "unauthorized")

        self.client.force_login(self.other)
        response = self.client.get(reverse("account_api_keys"))
        self.assertNotContains(response, key.token_secret)
        self.assertContains(response, other_key.token_secret)

    def test_unpaid_account_sees_no_create_form(self):
        self.client.force_login(self.free)
        response = self.client.get(reverse("account_api_keys"))
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "Generate key")
        self.assertContains(response, "active subscription")
        response = self.client.post(
            reverse("account_api_keys"),
            {"action": "create", "label": "nope"},
            follow=True,
        )
        self.assertEqual(ReadAPIKey.objects.filter(user=self.free).count(), 0)
        self.assertContains(response, "active subscription")


class MCPReadAPITestCase(TestCase):
    def setUp(self):
        self.member = _paid_user("member", "member@example.com")
        self.member_raw, _key = ReadAPIKey.create_key(self.member, label="member")
        # A key minted while the account was paid. Staff without a subscription
        # never get one of their own.
        self.lapsed_user = _paid_user("lapsed", "lapsed@example.com")
        self.lapsed_raw, self.lapsed_key = ReadAPIKey.create_key(self.lapsed_user, label="lapsed")
        self.lapsed_user.subscription.status = "canceled"
        self.lapsed_user.subscription.save(update_fields=["status"])

        self.player = Player.objects.create(name="Ada Prospect", position="SS", school="State U")
        self.hidden_player = Player.objects.create(name="Hidden Prospect", position="OF")
        self.tool = PlayerRankingCarryingTool.objects.create(tool="Hit", score="60")

        self.article = Article.objects.create(
            headline="Ada's swing",
            article_type="scouting",
            body=" ".join(["detail"] * 200),
            publish=True,
            active=True,
        )
        self.article.players.add(self.player)
        self.free_article = Article.objects.create(
            headline="Free note",
            body=" ".join(["open"] * 180),
            publish=True,
            active=True,
            is_free=True,
        )
        self.draft_article = Article.objects.create(
            headline="Unpublished note",
            body="do not leak",
            publish=False,
            active=True,
        )

        self.ranking = Ranking.objects.create(
            year="2027",
            draft_level="College",
            headline="2027 College",
            publish=True,
            active=True,
            is_mock_draft=False,
            current=True,
            is_free=False,
            free_number_to_show=1,
        )
        PlayerRanking.objects.create(
            player=self.player,
            ranking=self.ranking,
            rank=1,
            position="SS",
            school="State U",
            level="High School",
            role="60",
            scouting_report="<p>Plus bat speed.</p>",
        ).carrying_tools.add(self.tool)
        PlayerRanking.objects.create(
            player=self.hidden_player,
            ranking=self.ranking,
            rank=2,
            position="OF",
            level="High School",
            scouting_report="<p>Second report stays behind the paywall.</p>",
        )
        self.mock = Ranking.objects.create(
            year="2027",
            draft_level="Overall",
            mock_draft_version="1.0",
            publish=True,
            active=True,
            is_mock_draft=True,
            is_free=False,
            free_number_to_show=5,
        )
        PlayerRanking.objects.create(
            player=self.player,
            ranking=self.mock,
            rank=1,
            mock_pick_number=4,
            mock_team="Baltimore Orioles",
            level="High School",
            scouting_report="<p>Mock blurb.</p>",
        )
        Ranking.objects.create(
            year="2026",
            publish=False,
            active=True,
            is_mock_draft=False,
            headline="Hidden board",
        )

        PlayerStatSeason.objects.create(
            player=self.player,
            year="2026",
            level="College",
            school="State U",
            hitter_percentile=88.5,
        )
        Player643StatSeason.objects.create(
            player=self.player,
            year="2026",
            team_name="State U",
            hit_ba=0.312,
            hit_plate_appearances=180,
        )

    def _get(self, path, raw, **params):
        return self.client.get(
            path,
            data=params,
            HTTP_AUTHORIZATION=f"Bearer {raw}",
        )

    def test_requires_a_key(self):
        response = self.client.get("/api/mcp/v1/articles/")
        self.assertEqual(response.status_code, 401)
        response = self.client.get(
            "/api/mcp/v1/articles/",
            HTTP_X_OVERSLOT_TOKEN=self.member_raw,
        )
        self.assertEqual(response.status_code, 200)
        unpaid = self.client.get(
            "/api/mcp/v1/articles/",
            HTTP_AUTHORIZATION=f"Bearer {self.lapsed_raw}",
        )
        self.assertEqual(unpaid.status_code, 403)
        self.assertEqual(unpaid.json()["error"], "Subscription required")

    def test_article_returns_the_full_body(self):
        member = self._get(f"/api/mcp/v1/articles/{self.article.slug}/", self.member_raw)
        self.assertEqual(member.status_code, 200)
        body = member.json()
        self.assertEqual(body["access"], "full")
        self.assertEqual(len(body["body"]["text"].split()), 200)
        self.assertEqual(body["players"][0]["name"], "Ada Prospect")

        opened = self._get(f"/api/mcp/v1/articles/{self.free_article.slug}/", self.member_raw)
        self.assertEqual(opened.json()["access"], "full")
        self.assertEqual(len(opened.json()["body"]["text"].split()), 180)

        missing = self._get(f"/api/mcp/v1/articles/{self.draft_article.slug}/", self.member_raw)
        self.assertEqual(missing.status_code, 404)

        listing = self._get("/api/mcp/v1/articles/", self.member_raw, query="Ada")
        headlines = [row["headline"] for row in listing.json()["articles"]]
        self.assertIn("Ada's swing", headlines)
        self.assertNotIn("Unpublished note", headlines)
        self.assertNotIn("body", listing.json()["articles"][0])

    def test_ranking_returns_every_player_and_report(self):
        full = self._get(f"/api/mcp/v1/rankings/{self.ranking.slug}/", self.member_raw)
        self.assertEqual(full.status_code, 200)
        data = full.json()
        self.assertEqual(data["access"], "full")
        self.assertEqual(data["players_total"], 2)
        self.assertEqual(data["players_returned"], 2)
        by_name = {row["player"]["name"]: row for row in data["players"]}
        self.assertIn("Plus bat speed.", by_name["Ada Prospect"]["scouting_report"]["text"])
        self.assertEqual(by_name["Ada Prospect"]["carrying_tools"][0]["tool"], "Hit")
        self.assertIn("paywall", by_name["Hidden Prospect"]["scouting_report"]["text"])

        listing = self._get("/api/mcp/v1/rankings/", self.member_raw)
        titles = [row["title"] for row in listing.json()["rankings"]]
        self.assertTrue(any("2027" in title for title in titles))
        self.assertFalse(any("Hidden" in title for title in titles))
        self.assertFalse(any(row.get("is_mock_draft") for row in listing.json()["rankings"]))

        wrong = self._get(f"/api/mcp/v1/rankings/{self.mock.slug}/", self.member_raw)
        self.assertEqual(wrong.status_code, 404)
        self.assertIn("mock draft", wrong.json()["detail"])

    def test_mock_draft_pick(self):
        response = self._get(f"/api/mcp/v1/mock-drafts/{self.mock.slug}/", self.member_raw)
        self.assertEqual(response.status_code, 200)
        row = response.json()["players"][0]
        self.assertEqual(row["mock_pick_number"], 4)
        self.assertEqual(row["mock_team"], "Baltimore Orioles")
        self.assertIn("Mock blurb.", row["scouting_report"]["text"])

        listing = self._get("/api/mcp/v1/mock-drafts/", self.member_raw)
        self.assertEqual(listing.json()["total"], 1)
        wrong = self._get(f"/api/mcp/v1/mock-drafts/{self.ranking.slug}/", self.member_raw)
        self.assertEqual(wrong.status_code, 404)

    def test_player_and_stat_seasons_follow_the_subscription(self):
        found = self._get("/api/mcp/v1/players/", self.member_raw, query="Ada")
        self.assertEqual(found.status_code, 200)
        self.assertEqual(found.json()["players"][0]["slug"], self.player.slug)

        short = self._get("/api/mcp/v1/players/", self.member_raw, query="A")
        self.assertEqual(short.status_code, 400)

        full = self._get(f"/api/mcp/v1/players/{self.player.slug}/", self.member_raw)
        self.assertEqual(full.json()["access"], "full")
        reports = " ".join(
            row["scouting_report"]["text"]
            for row in full.json()["rankings"]
            if row.get("scouting_report")
        )
        self.assertIn("Plus bat speed.", reports)
        self.assertEqual(full.json()["trackman_stat_seasons"][0]["hitter_percentile"], 88.5)
        self.assertAlmostEqual(full.json()["counting_stat_seasons"][0]["hit_ba"], 0.312)

        locked = self._get(
            "/api/mcp/v1/player-stat-seasons/",
            self.lapsed_raw,
            player=self.player.slug,
        )
        self.assertEqual(locked.status_code, 403)

        seasons = self._get(
            "/api/mcp/v1/player-stat-seasons/",
            self.member_raw,
            player=self.player.slug,
            year="2026",
        )
        self.assertEqual(seasons.status_code, 200)
        self.assertEqual(seasons.json()["trackman_stat_seasons"][0]["level"], "College")
        self.assertEqual(seasons.json()["counting_stat_seasons"][0]["hit_plate_appearances"], 180)

        bad_level = self._get(
            "/api/mcp/v1/player-stat-seasons/",
            self.member_raw,
            year="2026",
            kind="counting",
            level="College",
        )
        self.assertEqual(bad_level.status_code, 400)

    def test_revoked_key_is_rejected(self):
        key = ReadAPIKey.objects.get(user=self.member)
        raw = key.token_secret
        key.revoke()
        response = self._get("/api/mcp/v1/articles/", raw)
        self.assertEqual(response.status_code, 401)
