from django.contrib.sitemaps import Sitemap
from django.urls import reverse

from overslot import models


class StaticViewSitemap(Sitemap):
    priority = 0.8
    changefreq = "daily"

    def items(self):
        return [
            "index",
            "articles_list",
            "rankings_list",
            "mock_drafts_list",
            "videos_list",
        ]

    def location(self, item):
        return reverse(item)


class ArticleSitemap(Sitemap):
    priority = 0.7
    changefreq = "daily"

    def items(self):
        return models.Article.objects.filter(publish=True)

    def location(self, obj):
        return reverse("articles_detail", kwargs={"slug": obj.slug})

    def lastmod(self, obj):
        return obj.last_modified or obj.created


class RankingSitemap(Sitemap):
    priority = 0.7
    changefreq = "daily"

    def items(self):
        return models.Ranking.objects.filter(publish=True)

    def location(self, obj):
        return reverse("rankings_detail", kwargs={"slug": obj.slug})

    def lastmod(self, obj):
        return obj.last_modified or obj.created


class PlayerSitemap(Sitemap):
    priority = 0.6
    changefreq = "weekly"

    def items(self):
        return models.Player.objects.filter(active=True)

    def location(self, obj):
        return reverse("players_detail", kwargs={"slug": obj.slug})

    def lastmod(self, obj):
        return obj.last_modified or obj.created


class PodcastEpisodeSitemap(Sitemap):
    priority = 0.5
    changefreq = "weekly"

    def items(self):
        return models.PodcastEpisode.objects.filter(publish=True)

    def location(self, obj):
        # No dedicated detail route yet; use external URL for now
        return obj.external_url

    def lastmod(self, obj):
        return obj.published_at


