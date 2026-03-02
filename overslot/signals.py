from django.contrib.auth.models import User
from django.db.models.signals import pre_save, post_save, m2m_changed
from django.dispatch import receiver

from overslot.cache_utils import (
    bust_homepage,
    bust_articles_list,
    bust_article,
    bust_stock_watch,
    bust_rankings_list,
    bust_ranking,
)


@receiver(pre_save, sender=User)
def normalize_user_email_and_username(sender, instance: User, **kwargs):
    email = getattr(instance, "email", None)
    if email:
        instance.email = email.strip().lower()
    username = getattr(instance, "username", None)
    if username:
        instance.username = username.strip().lower()


def _bust_article_caches(article):
    """Bust caches affected by article save."""
    bust_article(article.slug)
    bust_articles_list()
    # Articles appear on homepage: carousel, scouting, non-scouting
    bust_homepage()


@receiver(post_save)
def bust_cache_on_article_save(sender, instance, **kwargs):
    from overslot.models import Article
    if sender is Article:
        _bust_article_caches(instance)


@receiver(m2m_changed)
def bust_cache_on_article_m2m_changed(sender, instance, action, **kwargs):
    """When article's players or teams M2M changes, bust article and list caches."""
    from overslot.models import Article
    if sender in (Article.players.through, Article.teams.through) and action in ('post_add', 'post_remove', 'post_clear'):
        if hasattr(instance, 'slug') and instance.slug:
            bust_article(instance.slug)
            bust_articles_list()
            bust_homepage()


@receiver(post_save)
def bust_cache_on_stock_watch_save(sender, instance, **kwargs):
    from overslot.models import StockWatchArticle
    if sender is StockWatchArticle:
        bust_stock_watch(instance.slug)
        bust_articles_list()
        bust_homepage()


@receiver(post_save)
def bust_cache_on_stock_watch_player_save(sender, instance, **kwargs):
    from overslot.models import StockWatchPlayer
    if sender is StockWatchPlayer:
        article = getattr(instance, 'stock_watch_article', None)
        if article and article.slug:
            bust_stock_watch(article.slug)


@receiver(post_save)
def bust_cache_on_ranking_save(sender, instance, **kwargs):
    from overslot.models import Ranking
    if sender is Ranking:
        bust_ranking(instance.slug, is_mock_draft=instance.is_mock_draft)
        bust_rankings_list()
        bust_articles_list()
        bust_homepage()


@receiver(post_save)
def bust_cache_on_player_ranking_save(sender, instance, **kwargs):
    from overslot.models import PlayerRanking
    if sender is PlayerRanking:
        ranking = getattr(instance, 'ranking', None)
        if ranking and ranking.slug:
            bust_ranking(ranking.slug, is_mock_draft=ranking.is_mock_draft)


@receiver(post_save)
def bust_cache_on_game_save(sender, instance, **kwargs):
    from overslot.models import Game
    if sender is Game:
        bust_homepage()


@receiver(post_save)
def bust_cache_on_player_save(sender, instance, **kwargs):
    from overslot.models import Player
    if sender is Player:
        bust_homepage()


@receiver(post_save)
def bust_cache_on_podcast_save(sender, instance, **kwargs):
    from overslot.models import PodcastEpisode
    if sender is PodcastEpisode:
        bust_homepage()


