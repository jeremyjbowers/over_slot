"""
Fetch and cache YouTube playlist videos for the homepage highlight-reels tray.

Uses YouTube's public Atom feed (no API key). The feed returns the most recent
~15 videos in the playlist, which is enough for a random sample of four.
"""
from __future__ import annotations

import logging
import re
from typing import List, Optional
from xml.etree import ElementTree as ET

import requests

from overslot.cache_utils import get_cached, _safe_delete

logger = logging.getLogger(__name__)

DRAFT_HIGHLIGHT_PLAYLIST_ID = 'PLHOPM8dszvhA'
DRAFT_HIGHLIGHT_PLAYLIST_URL = (
    f'https://www.youtube.com/playlist?list={DRAFT_HIGHLIGHT_PLAYLIST_ID}'
)
DRAFT_HIGHLIGHT_PLAYLIST_FEED_URL = (
    f'https://www.youtube.com/feeds/videos.xml?playlist_id={DRAFT_HIGHLIGHT_PLAYLIST_ID}'
)

# Full playlist catalog (refreshed by management command / on cold miss).
KEY_DRAFT_HIGHLIGHT_PLAYLIST = (
    f'overslot:youtube_playlist:{DRAFT_HIGHLIGHT_PLAYLIST_ID}'
)
# Longer TTL than homepage sample — ingest command refreshes; fallback fetch on miss.
PLAYLIST_CATALOG_TIMEOUT = 60 * 60 * 24  # 24 hours

_VIDEO_ID_RE = re.compile(r'^[a-zA-Z0-9_-]{11}$')
_ATOM_NS = {
    'atom': 'http://www.w3.org/2005/Atom',
    'yt': 'http://www.youtube.com/xml/schemas/2015',
}


def embed_url_for_video_id(video_id: str) -> str:
    return f'https://www.youtube.com/embed/{video_id}'


def parse_playlist_feed_xml(xml_bytes: bytes) -> List[dict]:
    """
    Parse a YouTube playlist Atom feed into a list of video dicts.

    Each item: video_id, title, embed_url.
    """
    root = ET.fromstring(xml_bytes)
    videos: List[dict] = []
    seen = set()

    for entry in root.findall('atom:entry', _ATOM_NS):
        video_el = entry.find('yt:videoId', _ATOM_NS)
        title_el = entry.find('atom:title', _ATOM_NS)
        if video_el is None or not (video_el.text or '').strip():
            continue
        video_id = video_el.text.strip()
        if not _VIDEO_ID_RE.match(video_id) or video_id in seen:
            continue
        seen.add(video_id)
        title = (title_el.text or '').strip() if title_el is not None else ''
        videos.append({
            'video_id': video_id,
            'title': title,
            'embed_url': embed_url_for_video_id(video_id),
        })
    return videos


def fetch_playlist_videos(
    feed_url: str = DRAFT_HIGHLIGHT_PLAYLIST_FEED_URL,
    timeout: int = 30,
) -> List[dict]:
    """HTTP-fetch and parse the playlist Atom feed. Raises on network/parse errors."""
    response = requests.get(feed_url, timeout=timeout)
    response.raise_for_status()
    return parse_playlist_feed_xml(response.content)


def refresh_playlist_catalog(
    feed_url: str = DRAFT_HIGHLIGHT_PLAYLIST_FEED_URL,
) -> List[dict]:
    """
    Fetch playlist videos and write them into the catalog cache.
    Returns the ingested list (possibly empty on failure).
    """
    from django.core.cache import cache

    try:
        videos = fetch_playlist_videos(feed_url=feed_url)
    except Exception:
        logger.exception('Failed to fetch YouTube playlist feed: %s', feed_url)
        return []

    try:
        cache.set(KEY_DRAFT_HIGHLIGHT_PLAYLIST, videos, PLAYLIST_CATALOG_TIMEOUT)
    except Exception:
        logger.exception('Failed to cache YouTube playlist catalog')
    return videos


def get_playlist_videos(
    *,
    fetch_if_missing: bool = True,
) -> List[dict]:
    """
    Return the cached playlist catalog. Optionally fetch from YouTube on miss.
    """
    if not fetch_if_missing:
        try:
            from django.core.cache import cache
            cached = cache.get(KEY_DRAFT_HIGHLIGHT_PLAYLIST)
            return list(cached) if cached else []
        except Exception:
            return []

    def _compute():
        try:
            return fetch_playlist_videos()
        except Exception:
            logger.exception('Failed to fetch YouTube playlist on cache miss')
            return []

    return get_cached(
        KEY_DRAFT_HIGHLIGHT_PLAYLIST,
        _compute,
        PLAYLIST_CATALOG_TIMEOUT,
    )


def bust_playlist_catalog() -> None:
    _safe_delete(KEY_DRAFT_HIGHLIGHT_PLAYLIST)
