from io import StringIO
from unittest.mock import patch

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import SimpleTestCase

from overslot.youtube_playlist import (
    DRAFT_HIGHLIGHT_PLAYLIST_ID,
    embed_url_for_video_id,
    parse_playlist_feed_xml,
)


SAMPLE_FEED = b"""<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns:yt="http://www.youtube.com/xml/schemas/2015"
      xmlns="http://www.w3.org/2005/Atom">
  <title>2027 MLB Draft Prospect Highlights</title>
  <entry>
    <yt:videoId>IvyRbadv-AI</yt:videoId>
    <title>2025/2026 Jack Leeper Highlights - St. Francis</title>
  </entry>
  <entry>
    <yt:videoId>Y80eWgmftUg</yt:videoId>
    <title>Caden Nelson 2026 Highlights</title>
  </entry>
  <entry>
    <yt:videoId>bad</yt:videoId>
    <title>Should be skipped</title>
  </entry>
  <entry>
    <yt:videoId>IvyRbadv-AI</yt:videoId>
    <title>Duplicate should be skipped</title>
  </entry>
</feed>
"""


class YoutubePlaylistParseTests(SimpleTestCase):
    def test_parse_playlist_feed_xml(self):
        videos = parse_playlist_feed_xml(SAMPLE_FEED)
        self.assertEqual(len(videos), 2)
        self.assertEqual(videos[0]['video_id'], 'IvyRbadv-AI')
        self.assertEqual(
            videos[0]['title'],
            '2025/2026 Jack Leeper Highlights - St. Francis',
        )
        self.assertEqual(
            videos[0]['embed_url'],
            embed_url_for_video_id('IvyRbadv-AI'),
        )
        self.assertEqual(videos[1]['video_id'], 'Y80eWgmftUg')

    def test_embed_url_for_video_id(self):
        self.assertEqual(
            embed_url_for_video_id('abcdefghijk'),
            'https://www.youtube.com/embed/abcdefghijk',
        )


class LoadHighlightPlaylistCommandTests(SimpleTestCase):
    @patch('overslot.management.commands.load_highlight_playlist.refresh_playlist_catalog')
    @patch('overslot.management.commands.load_highlight_playlist._safe_delete')
    def test_command_caches_catalog_and_busts_homepage_sample(
        self, mock_delete, mock_refresh
    ):
        mock_refresh.return_value = [
            {
                'video_id': 'IvyRbadv-AI',
                'title': 'Jack Leeper',
                'embed_url': 'https://www.youtube.com/embed/IvyRbadv-AI',
            },
            {
                'video_id': 'Y80eWgmftUg',
                'title': 'Caden Nelson',
                'embed_url': 'https://www.youtube.com/embed/Y80eWgmftUg',
            },
        ]
        out = StringIO()
        call_command('load_highlight_playlist', stdout=out)
        mock_refresh.assert_called_once()
        mock_delete.assert_called_once_with('overslot:homepage:draft_highlight_reels')
        self.assertIn('Ingested 2 highlight reel(s)', out.getvalue())

    @patch('overslot.management.commands.load_highlight_playlist.refresh_playlist_catalog')
    def test_command_errors_when_feed_empty(self, mock_refresh):
        mock_refresh.return_value = []
        with self.assertRaises(CommandError):
            call_command('load_highlight_playlist', stdout=StringIO())


class DraftHighlightPlaylistConstantsTests(SimpleTestCase):
    def test_playlist_id(self):
        self.assertEqual(DRAFT_HIGHLIGHT_PLAYLIST_ID, 'PLHOPM8dszvhA')
