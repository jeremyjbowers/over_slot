from django.contrib.sitemaps import Sitemap
from django.urls import reverse
from django.contrib.sites.models import Site

from overslot import models


class BaseForcedDomainSitemap(Sitemap):
    protocol = "https"

    def get_urls(self, page=1, site=None, protocol=None):
        forced_site = Site(domain="overslotbaseball.com", name="overslotbaseball.com")
        return super().get_urls(page=page, site=forced_site, protocol="https")


class StaticViewSitemap(BaseForcedDomainSitemap):
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


class ArticleSitemap(BaseForcedDomainSitemap):
    priority = 0.7
    changefreq = "daily"

    def items(self):
        return models.Article.objects.filter(publish=True)

    def location(self, obj):
        return reverse("articles_detail", kwargs={"slug": obj.slug})

    def lastmod(self, obj):
        return obj.last_modified or obj.created


class RankingSitemap(BaseForcedDomainSitemap):
    priority = 0.7
    changefreq = "daily"

    def items(self):
        return models.Ranking.objects.filter(publish=True)

    def location(self, obj):
        return reverse("rankings_detail", kwargs={"slug": obj.slug})

    def lastmod(self, obj):
        return obj.last_modified or obj.created


class PlayerSitemap(BaseForcedDomainSitemap):
    priority = 0.6
    changefreq = "weekly"

    def items(self):
        return models.Player.objects.filter(active=True)

    def location(self, obj):
        return reverse("players_detail", kwargs={"slug": obj.slug})

    def lastmod(self, obj):
        return obj.last_modified or obj.created


class PodcastEpisodeSitemap(BaseForcedDomainSitemap):
    priority = 0.5
    changefreq = "weekly"

    def items(self):
        return models.PodcastEpisode.objects.filter(publish=True)

    def location(self, obj):
        # No dedicated detail route yet; use external URL for now
        return obj.external_url

    def lastmod(self, obj):
        return obj.published_at


