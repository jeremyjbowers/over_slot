import xml.etree.ElementTree as ET

from django.test import TestCase
from django.urls import reverse

from overslot.feeds import first_paragraph, rss_item_description
from overslot.models import Article, Author, Ranking


PAYWALL_BODY = (
    "<p>This is the public-facing first paragraph of the piece.</p>"
    "<p>SECRET_FULL_TEXT_SHOULD_NOT_APPEAR in any RSS description.</p>"
    "<p>Another subscriber-only paragraph with extra detail.</p>"
)


class RssPreviewHelperTestCase(TestCase):
    def test_first_paragraph_uses_only_the_opening_p(self):
        self.assertEqual(
            first_paragraph(PAYWALL_BODY),
            "This is the public-facing first paragraph of the piece.",
        )
        self.assertNotIn("SECRET_FULL_TEXT_SHOULD_NOT_APPEAR", first_paragraph(PAYWALL_BODY))

    def test_first_paragraph_strips_tags_and_truncates_when_no_p(self):
        html = "<div><strong>Deck-like lead</strong> without a p tag. " + ("x" * 500) + "</div>"
        preview = first_paragraph(html)
        self.assertTrue(preview.startswith("Deck-like lead without a p tag."))
        self.assertLessEqual(len(preview), 400)

    def test_description_prefers_deck_over_body(self):
        desc = rss_item_description(
            deck="The deck.",
            blurb="",
            body=PAYWALL_BODY,
            item_url="https://overslotbaseball.com/articles/example/",
        )
        self.assertIn("The deck.", desc)
        self.assertNotIn("SECRET_FULL_TEXT_SHOULD_NOT_APPEAR", desc)
        self.assertNotIn("first paragraph of the piece", desc)
        self.assertIn("Continue reading on Over Slot:", desc)
        self.assertIn("https://overslotbaseball.com/articles/example/", desc)

    def test_description_falls_back_to_first_paragraph(self):
        desc = rss_item_description(body=PAYWALL_BODY, item_url="https://example.com/a/")
        self.assertIn("This is the public-facing first paragraph of the piece.", desc)
        self.assertNotIn("SECRET_FULL_TEXT_SHOULD_NOT_APPEAR", desc)


class RssFeedViewTestCase(TestCase):
    def setUp(self):
        self.author = Author.objects.create(name="Jane Scout", display_name="Jane Scout")
        self.article = Article.objects.create(
            headline="Big Board Shakeup",
            subhead="A closer look at the top of the class.",
            blurb="Why the 1-1 conversation changed this week.",
            body=PAYWALL_BODY,
            publish=True,
            slug="big-board-shakeup",
            article_type="analysis",
        )
        self.article.authors.add(self.author)

        self.unpublished = Article.objects.create(
            headline="Draft embargo",
            subhead="Not yet live",
            body="<p>Unpublished body</p>",
            publish=False,
            slug="draft-embargo",
        )
        self.inactive = Article.objects.create(
            headline="Inactive piece",
            subhead="Should not syndicate",
            body="<p>Inactive body</p>",
            publish=True,
            active=False,
            slug="inactive-piece",
        )

        self.ranking = Ranking.objects.create(
            year="2026",
            ranking_type="Overall",
            ranking_length="100",
            headline="2026 Top 100",
            subhead="The latest overall board.",
            body=PAYWALL_BODY,
            publish=True,
            is_mock_draft=False,
            slug="2026-top-100",
        )
        self.mock = Ranking.objects.create(
            year="2026",
            is_mock_draft=True,
            mock_draft_version="3.0",
            headline="2026 Mock Draft 3.0",
            subhead="Version 3.0 of the mock.",
            body=PAYWALL_BODY,
            publish=True,
            slug="2026-mock-3",
        )
        self.unpublished_ranking = Ranking.objects.create(
            year="2026",
            headline="Hidden ranking",
            body="<p>Not public</p>",
            publish=False,
            is_mock_draft=False,
            slug="hidden-ranking",
        )

    def _feed_xml(self, url_name):
        response = self.client.get(reverse(url_name))
        self.assertEqual(response.status_code, 200)
        self.assertIn("xml", response["Content-Type"])
        return response, ET.fromstring(response.content)

    def _channel_items(self, root):
        channel = root.find("channel")
        self.assertIsNotNone(channel)
        return channel.findall("item")

    def test_articles_feed_teaser_not_full_text(self):
        response, root = self._feed_xml("articles_rss")
        items = self._channel_items(root)
        self.assertEqual(len(items), 1)

        item = items[0]
        self.assertEqual(item.findtext("title"), "Big Board Shakeup")
        desc = item.findtext("description") or ""
        self.assertIn("A closer look at the top of the class.", desc)
        self.assertIn("Why the 1-1 conversation changed this week.", desc)
        self.assertIn("/articles/big-board-shakeup/", item.findtext("link") or "")
        self.assertIn("Continue reading on Over Slot:", desc)
        self.assertNotIn("SECRET_FULL_TEXT_SHOULD_NOT_APPEAR", desc)
        self.assertNotIn("SECRET_FULL_TEXT_SHOULD_NOT_APPEAR", response.content.decode())
        self.assertNotIn("Draft embargo", response.content.decode())
        self.assertNotIn("Inactive piece", response.content.decode())
        self.assertIn("Jane Scout", response.content.decode())

    def test_rankings_feed_excludes_mocks_and_full_body(self):
        response, root = self._feed_xml("rankings_rss")
        titles = [item.findtext("title") for item in self._channel_items(root)]
        self.assertTrue(any("2026" in (t or "") and "Top 100" in (t or "") for t in titles))
        self.assertFalse(any("Mock Draft" in (t or "") for t in titles))
        self.assertNotIn("SECRET_FULL_TEXT_SHOULD_NOT_APPEAR", response.content.decode())
        self.assertNotIn("Hidden ranking", response.content.decode())
        self.assertIn("/rankings/2026-top-100/", response.content.decode())
        desc = self._channel_items(root)[0].findtext("description") or ""
        self.assertIn("The latest overall board.", desc)

    def test_mock_drafts_feed_excludes_regular_rankings(self):
        response, root = self._feed_xml("mock_drafts_rss")
        titles = [item.findtext("title") for item in self._channel_items(root)]
        self.assertTrue(any("Mock Draft" in (t or "") for t in titles))
        self.assertFalse(any("Top 100" in (t or "") for t in titles))
        self.assertNotIn("SECRET_FULL_TEXT_SHOULD_NOT_APPEAR", response.content.decode())
        self.assertIn("/mock-drafts/2026-mock-3/", response.content.decode())

    def test_homepage_advertises_feeds(self):
        response = self.client.get(reverse("index"))
        self.assertContains(response, reverse("articles_rss"))
        self.assertContains(response, reverse("rankings_rss"))
        self.assertContains(response, reverse("mock_drafts_rss"))
        self.assertContains(response, 'type="application/rss+xml"')
