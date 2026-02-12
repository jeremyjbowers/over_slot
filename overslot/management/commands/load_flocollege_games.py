"""
Load games from FloCollege API (e.g. Shriners Classic, FloBaseball events).

Can either fetch from the API or load from a local JSON file.
Uses flo_{id} as the game identifier to avoid collisions with ESPN games.
"""
import re
import requests
from django.core.management.base import BaseCommand
from django.utils import timezone
from django.conf import settings
from dateutil import parser
from django.db.models import Q
import pytz

from overslot import models


DEFAULT_API_URL = (
    "https://api.flocollege.com/api/collections/14995438/nodes"
    "?fields=data%3C2%3E&limit=35&sort=recent&view=live-and-upcoming&type=event"
)


class Command(BaseCommand):
    help = "Load games from FloCollege API (e.g. Shriners Classic) and create Game objects"

    def add_arguments(self, parser):
        parser.add_argument(
            "--file",
            type=str,
            metavar="PATH",
            help="Load from local JSON file instead of API (e.g. flocollege/nodes.json). Default: fetch from API.",
        )
        parser.add_argument(
            "--url",
            type=str,
            default=DEFAULT_API_URL,
            help=f"API URL to fetch from (default: Shriners Classic collection)",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Don't save to database, just show what would be created",
        )
        parser.add_argument(
            "--limit",
            type=int,
            default=100,
            help="Maximum number of games to process (default: 100)",
        )

    def handle(self, *args, **options):
        dry_run = options.get("dry_run", False)
        limit = options.get("limit", 100)

        if options.get("file"):
            self.stdout.write(f"Loading from file: {options['file']}")
            try:
                with open(options["file"]) as f:
                    import json

                    response_data = json.load(f)
            except FileNotFoundError:
                self.stdout.write(self.style.ERROR(f"File not found: {options['file']}"))
                return
            except json.JSONDecodeError as e:
                self.stdout.write(self.style.ERROR(f"Invalid JSON: {e}"))
                return
        else:
            self.stdout.write(f"Fetching from API: {options['url'][:80]}...")
            try:
                response = self.fetch_api(options["url"])
                response_data = response
            except Exception as e:
                self.stdout.write(self.style.ERROR(f"API request failed: {e}"))
                return

        nodes = response_data.get("data", [])
        if not nodes:
            self.stdout.write(self.style.WARNING("No games found in response."))
            return

        self.stdout.write(f"Found {len(nodes)} nodes. Processing up to {limit}...")

        now = timezone.now()
        created_count = 0
        updated_count = 0
        skipped_count = 0
        errors = []

        for node in nodes[:limit]:
            if node.get("type") != "event":
                skipped_count += 1
                continue

            try:
                game, created = self.create_or_update_game(node, now, dry_run)
                if dry_run:
                    self.stdout.write(
                        f"  [DRY RUN] Would {'create' if created else 'update'}: {game.name}"
                    )
                elif created:
                    created_count += 1
                    self.stdout.write(self.style.SUCCESS(f"  Created: {game.name}"))
                else:
                    updated_count += 1
                    self.stdout.write(f"  Updated: {game.name}")
            except Exception as e:
                skipped_count += 1
                errors.append(f"{node.get('title', 'Unknown')}: {e}")
                self.stdout.write(self.style.ERROR(f"  Error: {e}"))

        self.stdout.write("")
        if dry_run:
            self.stdout.write(self.style.WARNING("DRY RUN - no changes saved."))
        else:
            self.stdout.write(
                self.style.SUCCESS(
                    f"Done. Created: {created_count}, Updated: {updated_count}, Skipped: {skipped_count}"
                )
            )
        if errors:
            self.stdout.write(self.style.WARNING(f"Errors: {len(errors)}"))
            for err in errors[:5]:
                self.stdout.write(f"  {err}")
            if len(errors) > 5:
                self.stdout.write(f"  ... and {len(errors) - 5} more")

    def fetch_api(self, url):
        """Fetch data from FloCollege API."""
        headers = {}
        if hasattr(settings, "FLOCOLLEGE_API_KEY") and settings.FLOCOLLEGE_API_KEY:
            headers["Authorization"] = f"Bearer {settings.FLOCOLLEGE_API_KEY}"
        if hasattr(settings, "FLOCOLLEGE_COOKIE") and settings.FLOCOLLEGE_COOKIE:
            headers["Cookie"] = settings.FLOCOLLEGE_COOKIE

        response = requests.get(url, headers=headers if headers else None, timeout=30)
        response.raise_for_status()
        return response.json()

    def extract_teams_from_name(self, game_name):
        """Extract team names and rankings from game name.
        Handles both 'vs.' (ESPN) and 'vs' (FloCollege) formats.
        """
        teams = []
        # Normalize FloCollege " vs " to " vs. " for consistent parsing
        game_name = game_name.replace(" vs ", " vs. ")
        if "(Baseball)" in game_name:
            game_name = game_name.replace("(Baseball)", "").strip()

        if "vs." in game_name:
            for team_name in game_name.split("vs."):
                team_name = team_name.strip()
                ranking = None
                if "#" in team_name:
                    rank_pattern = re.compile(r"#(\d{1,})")
                    rank_match = rank_pattern.search(team_name)
                    if rank_match:
                        try:
                            ranking = int(rank_match.group(1))
                        except (ValueError, AttributeError):
                            ranking = None
                        team_name = rank_pattern.sub("", team_name).strip()
                if team_name:
                    teams.append((team_name, ranking))
        return teams

    def get_primary_team(self, team):
        """Return primary team if this one was merged."""
        if not team.active:
            merge_decision = (
                models.TeamDuplicateDecision.objects.filter(
                    decision="merged",
                    primary_team__isnull=False,
                )
                .filter(Q(team1=team) | Q(team2=team))
                .exclude(primary_team=team)
                .first()
            )
            if merge_decision and merge_decision.primary_team.active:
                return merge_decision.primary_team
        return team

    def get_or_create_team(self, team_name):
        """Get or create a Team by name, returning primary if merged."""
        team, created = models.Team.objects.get_or_create(
            name=team_name,
            defaults={"active": True},
        )
        if not team.slug:
            team.save()
            team.refresh_from_db()
        primary_team = self.get_primary_team(team)
        if primary_team and not primary_team.slug:
            primary_team.save()
            primary_team.refresh_from_db()
        return primary_team

    def is_ncaa_event(self, node):
        """Check if event is NCAA (from aggregated_category_slugs)."""
        slugs = node.get("aggregated_category_slugs") or []
        return "ncaa" in slugs or "college" in slugs

    def create_or_update_game(self, node, now, dry_run=False):
        """Create or update a Game from FloCollege node data."""
        node_id = node.get("id")
        if not node_id:
            raise ValueError("Node missing required 'id' field")

        espn_id = f"flo_{node_id}"

        # Parse start datetime
        start_str = node.get("start_date_time")
        if not start_str:
            raise ValueError(f"Node missing start_date_time (id: {node_id})")

        start_datetime = parser.parse(start_str)
        if start_datetime.tzinfo is None:
            from pytz import timezone as tz

            tz_name = node.get("timezone", "America/Chicago")
            try:
                tz_obj = tz(tz_name)
                start_datetime = tz_obj.localize(start_datetime.replace(tzinfo=None))
            except Exception:
                start_datetime = timezone.make_aware(start_datetime)

        # Parse end datetime
        end_datetime = None
        if node.get("end_date_time"):
            try:
                end_datetime = parser.parse(node["end_date_time"])
                if end_datetime.tzinfo is None:
                    end_datetime = timezone.make_aware(end_datetime)
            except (ValueError, TypeError):
                pass

        # Determine status from times
        if end_datetime and now > end_datetime:
            status = "past"
        elif start_datetime and now >= start_datetime:
            status = "live"
        else:
            status = "future"

        # Extract teams
        game_name = node.get("short_title") or node.get("title", "")
        team_data = self.extract_teams_from_name(game_name)

        home_team = None
        away_team = None
        home_team_ranking = None
        away_team_ranking = None

        if len(team_data) >= 2:
            away_team_name, away_team_ranking = team_data[0]
            home_team_name, home_team_ranking = team_data[1]
            away_team = self.get_or_create_team(away_team_name)
            home_team = self.get_or_create_team(home_team_name)
        elif len(team_data) == 1:
            away_team_name, away_team_ranking = team_data[0]
            away_team = self.get_or_create_team(away_team_name)

        # Streaming URL - shareable_link points to the watch page
        streaming_url = node.get("shareable_link") or ""
        if not streaming_url:
            streaming_url = f"https://www.flobaseball.tv/events/{node_id}-{node.get('slug', '')}"

        # Image
        image_url = node.get("asset_url") or node.get("thumbnail_url")

        # League name from categories (e.g. big-12, sec)
        league_name = None
        slugs = node.get("aggregated_category_slugs") or []
        for slug in slugs:
            if slug in ("ncaa", "college", "division-i", "flosports"):
                continue
            # Convert big-12 -> Big 12
            league_name = slug.replace("-", " ").title()
            break

        defaults = {
            "name": game_name,
            "short_name": node.get("short_title"),
            "home_team": home_team,
            "away_team": away_team,
            "home_team_ranking": home_team_ranking,
            "away_team_ranking": away_team_ranking,
            "start_datetime": start_datetime,
            "end_datetime": end_datetime,
            "short_date": node.get("start_date"),
            "status": status,
            "streaming_url": streaming_url,
            "image_url": image_url,
            "network_name": "FloBaseball",
            "sport_name": "Baseball",
            "league_name": league_name,
            "is_ncaa": self.is_ncaa_event(node),
            "active": True,
        }

        if dry_run:
            # Return a mock game for dry-run display
            class MockGame:
                pass

            mock = MockGame()
            mock.name = game_name
            return mock, True

        game, created = models.Game.objects.update_or_create(
            espn_id=espn_id,
            defaults=defaults,
        )
        return game, created
