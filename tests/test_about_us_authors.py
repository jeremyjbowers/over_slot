from django.test import TestCase
from django.urls import reverse

from overslot.models import Article, Author


class AboutUsAuthorVisibilityTestCase(TestCase):
    def setUp(self):
        self.active_author = Author.objects.create(
            name="Active Writer",
            display_name="Active Writer",
            active=True,
            bio="Still on staff.",
        )
        self.inactive_author = Author.objects.create(
            name="Former Writer",
            display_name="Former Writer",
            active=False,
            bio="No longer on the authors page.",
        )
        self.article = Article.objects.create(
            headline="Shared byline piece",
            body="<p>Body</p>",
            publish=True,
            active=True,
            slug="shared-byline-piece",
        )
        self.article.authors.add(self.active_author, self.inactive_author)

    def test_about_us_lists_only_active_authors(self):
        response = self.client.get(reverse("about_us"))
        self.assertEqual(response.status_code, 200)
        content = response.content.decode()
        self.assertIn("Active Writer", content)
        self.assertNotIn("Former Writer", content)

    def test_article_page_still_shows_inactive_author_name(self):
        response = self.client.get(reverse("articles_detail", kwargs={"slug": self.article.slug}))
        self.assertEqual(response.status_code, 200)
        content = response.content.decode()
        self.assertIn("Active Writer", content)
        self.assertIn("Former Writer", content)
