"""
Ingest 2027 draft highlight reels from the Over-Slot YouTube playlist.

Fetches YouTube's public Atom feed for the playlist, caches the catalog, and
busts the homepage random-sample cache so the tray reshuffles from fresh data.
"""
from django.core.management.base import BaseCommand, CommandError

from overslot.cache_utils import KEY_HOMEPAGE, _safe_delete
from overslot.youtube_playlist import (
    DRAFT_HIGHLIGHT_PLAYLIST_FEED_URL,
    DRAFT_HIGHLIGHT_PLAYLIST_URL,
    refresh_playlist_catalog,
)


class Command(BaseCommand):
    help = (
        'Load 2027 draft highlight-reel video IDs from the YouTube playlist '
        f'({DRAFT_HIGHLIGHT_PLAYLIST_URL}) into cache.'
    )

    def add_arguments(self, parser):
        parser.add_argument(
            '--feed-url',
            dest='feed_url',
            default=DRAFT_HIGHLIGHT_PLAYLIST_FEED_URL,
            help='YouTube playlist Atom feed URL',
        )

    def handle(self, *args, **options):
        feed_url = options['feed_url']
        videos = refresh_playlist_catalog(feed_url=feed_url)
        if not videos:
            raise CommandError(
                f'No videos ingested from playlist feed: {feed_url}'
            )

        # Force homepage tray to resample from the refreshed catalog.
        _safe_delete(f'{KEY_HOMEPAGE}:draft_highlight_reels')

        self.stdout.write(self.style.SUCCESS(
            f'Ingested {len(videos)} highlight reel(s) from playlist'
        ))
        for video in videos[:5]:
            self.stdout.write(f"  - {video['video_id']}: {video['title']}")
        if len(videos) > 5:
            self.stdout.write(f'  … and {len(videos) - 5} more')
