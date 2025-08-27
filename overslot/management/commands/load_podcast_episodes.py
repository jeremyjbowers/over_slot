import re
from datetime import timezone

import requests
from dateutil import parser as dateutil_parser
from defusedxml import ElementTree as ET
from django.core.management.base import BaseCommand, CommandError

from overslot.models import PodcastEpisode


def _find_child(element, name):
    """
    Find a direct child by tag localname. Handles namespaced tags by matching the
    localname (text after the final '}').
    """
    for child in element:
        tag = child.tag
        local = tag[tag.rfind('}') + 1 :] if '}' in tag else tag
        if local == name:
            return child
    return None


def _find_children(element, name):
    for child in element:
        tag = child.tag
        local = tag[tag.rfind('}') + 1 :] if '}' in tag else tag
        if local == name:
            yield child


def _get_text(element, name):
    found = _find_child(element, name)
    return (found.text or '').strip() if found is not None and found.text else None


class Command(BaseCommand):
    help = "Load podcast episodes from a Patreon RSS feed and upsert by GUID."

    def add_arguments(self, parser):
        parser.add_argument(
            '--feed-url',
            dest='feed_url',
            default='https://www.patreon.com/rss/Overslot?auth=W-2rI6cVQ5TQ_sMBz2E_3rYVquLr7ETU',
            help='Patreon RSS feed URL',
        )
        # Episodes are always published; flag retained for backwards compatibility
        parser.add_argument('--publish', action='store_true', dest='publish', help='(Deprecated) Episodes are now always published')

    def handle(self, *args, **options):
        feed_url = options['feed_url']
        # Always publish imported episodes
        auto_publish = True

        try:
            response = requests.get(feed_url, timeout=30)
            response.raise_for_status()
        except Exception as exc:
            raise CommandError(f"Failed to fetch feed: {exc}")

        try:
            root = ET.fromstring(response.content)
        except Exception as exc:
            raise CommandError(f"Failed to parse RSS XML: {exc}")

        channel = _find_child(root, 'channel') or root
        items = list(_find_children(channel, 'item'))

        created_count = 0
        updated_count = 0

        for item in items:
            title = _get_text(item, 'title') or ''
            link = _get_text(item, 'link')
            description_html = _get_text(item, 'description')
            guid = _get_text(item, 'guid') or link or title
            pub_date_text = _get_text(item, 'pubDate')

            # itunes:image href
            image_url = None
            for child in item:
                tag = child.tag
                local = tag[tag.rfind('}') + 1 :] if '}' in tag else tag
                if local == 'image':
                    href = child.attrib.get('href') or child.attrib.get('url')
                    if href:
                        image_url = href
                        break

            # enclosure
            enclosure = _find_child(item, 'enclosure')
            audio_url = None
            audio_bytes = None
            audio_mime_type = None
            if enclosure is not None:
                audio_url = enclosure.attrib.get('url')
                length_value = enclosure.attrib.get('length')
                try:
                    audio_bytes = int(length_value) if length_value else None
                except Exception:
                    audio_bytes = None
                audio_mime_type = enclosure.attrib.get('type')

            # published date
            published_at = None
            if pub_date_text:
                try:
                    dt = dateutil_parser.parse(pub_date_text)
                    if dt.tzinfo is None:
                        dt = dt.replace(tzinfo=timezone.utc)
                    published_at = dt.astimezone(timezone.utc)
                except Exception:
                    published_at = None

            # episode number heuristic from title
            episode_number = None
            match = re.search(r"\bEp\.?\s*(\d+)", title, flags=re.IGNORECASE)
            if not match:
                match = re.search(r"\bEpisode\s*(\d+)", title, flags=re.IGNORECASE)
            if match:
                try:
                    episode_number = int(match.group(1))
                except Exception:
                    episode_number = None

            defaults = {
                'title': title[:255],
                'external_url': link or '',
                'image_url': image_url,
                'description_html': description_html,
                'audio_url': audio_url or '',
                'audio_bytes': audio_bytes,
                'audio_mime_type': audio_mime_type,
                'published_at': published_at or dateutil_parser.parse('1970-01-01T00:00:00Z'),
                'publish': auto_publish,
                'episode_number': episode_number,
            }

            obj, created = PodcastEpisode.objects.update_or_create(
                guid=guid,
                defaults=defaults,
            )
            if created:
                created_count += 1
            else:
                updated_count += 1

        self.stdout.write(self.style.SUCCESS(
            f"Processed {len(items)} items: created={created_count}, updated={updated_count}"
        ))


