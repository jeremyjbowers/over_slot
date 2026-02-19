from django.contrib.sitemaps import Sitemap
from django.urls import reverse
from django.contrib.sites.models import Site
from django.utils import timezone
from django.conf import settings
from django.db.models.functions import TruncDate
from dateutil import parser
from datetime import timedelta, datetime, date

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
            "games_list",  # Live games main page
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


class StockWatchArticleSitemap(BaseForcedDomainSitemap):
    priority = 0.7
    changefreq = "weekly"

    def items(self):
        return models.StockWatchArticle.objects.filter(publish=True, active=True)

    def location(self, obj):
        return reverse("stock_watch_detail", kwargs={"slug": obj.slug})

    def lastmod(self, obj):
        return obj.last_modified or obj.created


class MockDraftSitemap(BaseForcedDomainSitemap):
    """
    High-priority sitemap for mock drafts - these are important for SEO.
    """
    priority = 0.9
    changefreq = "weekly"

    def items(self):
        return models.Ranking.objects.filter(publish=True, is_mock_draft=True)

    def location(self, obj):
        return reverse("mock_drafts_detail", kwargs={"slug": obj.slug})

    def lastmod(self, obj):
        return obj.last_modified or obj.created


class RankingSitemap(BaseForcedDomainSitemap):
    """
    Regular rankings (excluding mock drafts, which are in MockDraftSitemap).
    """
    priority = 0.7
    changefreq = "daily"

    def items(self):
        return models.Ranking.objects.filter(publish=True, is_mock_draft=False)

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


class GamesSitemap(BaseForcedDomainSitemap):
    """
    High-priority sitemap for live games pages.
    Includes the main games page and date-specific pages for dates with games
    or upcoming dates within a reasonable window.
    """
    priority = 0.9
    changefreq = "hourly"  # Games update frequently

    def items(self):
        """
        Generate list of game date URLs to include in sitemap.
        Strategy: Include dates from opening day forward, prioritizing:
        1. Dates that have games scheduled
        2. Dates within the next 7 days (even if no games yet)
        3. Dates up to 30 days out (only if they have games)
        """
        # Get season opening day
        try:
            season_opening_day = parser.parse(getattr(settings, 'SEASON_OPENING_DAY', '2025-02-13')).date()
        except (ValueError, TypeError):
            season_opening_day = date(2026, 2, 13)
        
        today = timezone.now().date()
        start_date = max(today, season_opening_day)
        
        # Get all dates that have games
        # Use TruncDate to efficiently extract dates from datetime fields
        games_qs = models.Game.objects.filter(
            active=True,
            start_datetime__gte=timezone.make_aware(datetime.combine(start_date, datetime.min.time()))
        ).annotate(
            game_date=TruncDate('start_datetime')
        ).values_list('game_date', flat=True).distinct()
        
        # Filter dates and convert to date objects if needed
        dates_with_games = set()
        for d in games_qs:
            if d:
                # TruncDate returns a date, but handle both date and datetime
                game_date = d.date() if isinstance(d, datetime) else d
                if game_date >= start_date:
                    dates_with_games.add(game_date)
        
        # Build list of dates to include
        dates_to_include = []
        
        # Always include the next 7 days (even if no games yet)
        for i in range(7):
            check_date = start_date + timedelta(days=i)
            if check_date >= season_opening_day:
                dates_to_include.append(check_date)
        
        # Include all dates with games up to 30 days out
        for game_date in dates_with_games:
            if game_date >= start_date and game_date <= start_date + timedelta(days=30):
                if game_date not in dates_to_include:
                    dates_to_include.append(game_date)
        
        # Sort and return as tuples (year, month, day) for URL generation
        dates_to_include = sorted(set(dates_to_include))
        return [(d.year, d.month, d.day) for d in dates_to_include]

    def location(self, item):
        year, month, day = item
        return reverse("games_list_date", kwargs={"year": year, "month": month, "day": day})

    def lastmod(self, item):
        # Return current time since game schedules update frequently
        return timezone.now()


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


