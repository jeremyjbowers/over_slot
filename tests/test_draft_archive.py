from unittest.mock import patch

from django.contrib.auth.models import AnonymousUser
from django.contrib.messages.storage.fallback import FallbackStorage
from django.contrib.sessions.backends.signed_cookies import SessionStore
from django.template.loader import render_to_string
from django.test import RequestFactory, SimpleTestCase
from django.urls import reverse

from overslot.sitemaps import StaticViewSitemap
from overslot.views import draft_archive


def _page_context(user, request):
    return {
        "user": user,
        "request": request,
        "messages": [],
        "has_published_mock_drafts": False,
        "has_live_games": False,
        "cache_backend": None,
        "settings": {"SUBSCRIPTION_PRICE_MONTHLY": 9.99},
        "has_monthly_price": False,
        "has_annual_price": False,
        "has_any_price": False,
        "pitch_shapes_base_url": "",
    }


class DraftArchivePageTests(SimpleTestCase):
    def setUp(self):
        self.factory = RequestFactory()

    def test_url_and_sitemap(self):
        self.assertEqual(reverse("draft_archive"), "/draft-archive/")
        self.assertIn("draft_archive", StaticViewSitemap().items())

    def test_nav_puts_draft_archive_under_data(self):
        request = self.factory.get("/draft-archive/")
        request.user = AnonymousUser()
        html = render_to_string("includes/nav.html", _page_context(request.user, request))
        rankings = html.split(">Rankings<", 1)[1].split(">Data<", 1)[0]
        data = html.split(">Data<", 1)[1].split(">Videos<", 1)[0]
        self.assertNotIn('href="/draft-archive/"', rankings)
        self.assertIn('href="/draft-archive/"', data)
        self.assertIn(">Draft archive<", data)
        self.assertLess(data.index('href="/draft-archive/"'), data.index('href="/stats/"'))

    def test_homepage_banner_promotes_draft_archive(self):
        request = self.factory.get("/")
        request.user = AnonymousUser()
        ctx = _page_context(request.user, request)
        ctx.update({
            "latest_articles": [],
            "latest_rankings": [],
            "latest_stock_watch": [],
            "latest_games": [],
            "scouting_articles": [],
            "non_scouting_articles": [],
            "draft_highlight_reels": [],
            "draft_highlight_reels_playlist_url": "",
            "featured_games": [],
            "latest_podcasts": [],
            "current_rankings": [],
            "archived_rankings": [],
            "rankings_count": 0,
            "player_videos": [],
            "videos_count": 0,
            "homepage_collections": [],
        })
        html = render_to_string("index.html", ctx)
        self.assertIn(">Draft Archive<", html)
        self.assertIn("MLB Draft Archive, <span class=\"home-feature-banner-years\">1977", html)
        self.assertIn("Open the archive", html)
        self.assertIn('href="/draft-archive/"', html)
        self.assertNotIn("Start a mock draft", html)
        self.assertNotIn('href="/my-mock-draft/"', html)

    def test_anonymous_page_uses_site_nav_and_keeps_overslot_paths(self):
        request = self.factory.get("/draft-archive/")
        request.user = AnonymousUser()
        html = render_to_string("draft_archive.html", _page_context(request.user, request))
        self.assertIn("<title>MLB Draft Archive - Over Slot</title>", html)
        self.assertIn('id="navMenu"', html)
        self.assertIn("Get started", html)
        self.assertIn('href="/draft-archive/"', html)
        self.assertIn('id="dz-data"', html)
        self.assertIn('id="view"', html)
        self.assertIn('href="${OSURL[y]||"/rankings/"}"', html)
        self.assertIn("o.ou ? o.ou", html)
        self.assertIn('document.querySelector(".draft-archive").appendChild', html)
        self.assertNotIn("https://overslotbaseball.com", html)
        self.assertNotIn('class="wordmark"', html)

    def test_signed_in_nav_shows_the_account(self):
        request = self.factory.get("/draft-archive/")

        class SignedIn:
            is_authenticated = True
            is_staff = False
            email = "reader@example.com"

        html = render_to_string("draft_archive.html", _page_context(SignedIn(), request))
        self.assertIn("reader@example.com", html)
        self.assertNotIn("Get started", html)

    def test_view_is_public(self):
        request = self.factory.get("/draft-archive/")
        request.user = AnonymousUser()
        request.session = SessionStore()
        request._messages = FallbackStorage(request)
        with patch(
            "overslot.context_processors.settings_context",
            return_value=_page_context(request.user, request),
        ):
            response = draft_archive(request)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "MLB Draft Archive")
        self.assertContains(response, "Get started")
