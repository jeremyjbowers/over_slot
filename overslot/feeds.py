"""RSS feeds for published articles, rankings, and mock drafts.

Items are teasers only (headline lives in <title>; description is the deck /
blurb, or the first paragraph of the body as a fallback) plus a permalink.
Full subscriber content is never included.
"""

from __future__ import annotations

import re
from html import unescape

from django.contrib.syndication.views import Feed
from django.urls import reverse
from django.utils.html import strip_tags
from django.utils.text import Truncator

from overslot import models

CANONICAL_ORIGIN = "https://overslotbaseball.com"
FEED_ITEM_LIMIT = 30
FEED_PREVIEW_CHARS = 400

_P_RE = re.compile(r"<p\b[^>]*>(.*?)</p>", re.IGNORECASE | re.DOTALL)


def _canonical(path: str) -> str:
    if path.startswith("http://") or path.startswith("https://"):
        return path
    if not path.startswith("/"):
        path = f"/{path}"
    return f"{CANONICAL_ORIGIN}{path}"


def first_paragraph(html: str | None) -> str:
    """Plain-text first paragraph (or truncated leftover text) from HTML body."""
    if not html or not str(html).strip():
        return ""
    match = _P_RE.search(html)
    chunk = match.group(1) if match else html
    text = " ".join(unescape(strip_tags(chunk)).split())
    if not text:
        return ""
    return Truncator(text).chars(FEED_PREVIEW_CHARS)


def rss_item_description(*, deck="", blurb="", body="", item_url="") -> str:
    """Subscriber-safe RSS description: deck/blurb, else first paragraph + link."""
    deck = (deck or "").strip()
    blurb = (blurb or "").strip()
    parts = []
    if deck:
        parts.append(deck)
    if blurb and blurb != deck:
        parts.append(blurb)
    if not parts:
        para = first_paragraph(body)
        if para:
            parts.append(para)
    if item_url:
        parts.append(f"Continue reading on Over Slot: {item_url}")
    return "\n\n".join(parts)


class _CanonicalFeed(Feed):
    author_name = "Over Slot"
    author_link = CANONICAL_ORIGIN

    def item_guid_is_permalink(self, item):
        return True

    def item_pubdate(self, item):
        return item.created

    def item_updateddate(self, item):
        return item.last_modified or item.created


class ArticlesFeed(_CanonicalFeed):
    title = "Over Slot Articles"
    description = (
        "Headlines and decks from Over Slot — scouting, news, and analysis. "
        "Full articles are on the site (subscription may be required)."
    )

    def link(self):
        return _canonical(reverse("articles_list"))

    def feed_url(self):
        return _canonical(reverse("articles_rss"))

    def items(self):
        return (
            models.Article.objects.filter(publish=True, active=True)
            .prefetch_related("authors")
            .order_by("-created")[:FEED_ITEM_LIMIT]
        )

    def item_title(self, item):
        return item.headline or "Article"

    def item_link(self, item):
        return _canonical(reverse("articles_detail", kwargs={"slug": item.slug}))

    def item_description(self, item):
        return rss_item_description(
            deck=item.subhead,
            blurb=item.blurb,
            body=item.body,
            item_url=self.item_link(item),
        )

    def item_author_name(self, item):
        names = []
        for author in item.authors.all():
            name = author.display_name or author.name
            if name:
                names.append(name)
        return ", ".join(names) or None

    def item_categories(self, item):
        if item.article_type:
            return [item.article_type]
        return None


class RankingsFeed(_CanonicalFeed):
    title = "Over Slot Rankings"
    description = (
        "Prospect ranking updates from Over Slot. Full boards are on the site "
        "(subscription may be required)."
    )

    def link(self):
        return _canonical(reverse("rankings_list"))

    def feed_url(self):
        return _canonical(reverse("rankings_rss"))

    def items(self):
        return models.Ranking.objects.filter(
            publish=True, is_mock_draft=False
        ).order_by("-created")[:FEED_ITEM_LIMIT]

    def item_title(self, item):
        return item.get_computed_title() or item.headline or "Ranking"

    def item_link(self, item):
        return _canonical(reverse("rankings_detail", kwargs={"slug": item.slug}))

    def item_description(self, item):
        return rss_item_description(
            deck=item.subhead,
            blurb=item.blurb,
            body=item.body,
            item_url=self.item_link(item),
        )

    def item_categories(self, item):
        cats = ["Ranking"]
        if item.ranking_type:
            cats.append(item.ranking_type)
        elif item.draft_level:
            cats.append(item.draft_level)
        return cats


class MockDraftsFeed(_CanonicalFeed):
    title = "Over Slot Mock Drafts"
    description = (
        "Mock draft updates from Over Slot. Full boards are on the site "
        "(subscription may be required)."
    )

    def link(self):
        return _canonical(reverse("mock_drafts_list"))

    def feed_url(self):
        return _canonical(reverse("mock_drafts_rss"))

    def items(self):
        return models.Ranking.objects.filter(
            publish=True, is_mock_draft=True
        ).order_by("-created")[:FEED_ITEM_LIMIT]

    def item_title(self, item):
        return item.get_computed_title() or item.headline or "Mock Draft"

    def item_link(self, item):
        return _canonical(reverse("mock_drafts_detail", kwargs={"slug": item.slug}))

    def item_description(self, item):
        return rss_item_description(
            deck=item.subhead,
            blurb=item.blurb,
            body=item.body,
            item_url=self.item_link(item),
        )

    def item_categories(self, item):
        return ["Mock Draft"]
