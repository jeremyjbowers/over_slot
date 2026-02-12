import re
import requests
from django.core.management.base import BaseCommand
from django.utils import timezone
from django.conf import settings
from datetime import timedelta
from dateutil import parser
import pytz
from django.db.models import Q

from overslot import models


class Command(BaseCommand):
    help = 'Load games from ESPN GraphQL API and create Game objects'

    def add_arguments(self, parser):
        parser.add_argument(
            '--date',
            type=str,
            help='Start date to fetch games for (YYYY-MM-DD format). Will load 4 weeks from this date. Defaults to today.',
        )
        parser.add_argument(
            '--clear',
            action='store_true',
            help='Clear all existing games before loading (DESTRUCTIVE)',
        )
        parser.add_argument(
            '--max-weeks-ahead',
            type=int,
            default=4,
            help='Maximum number of weeks in the future to fetch games (default: 4). ESPN typically only loads games 3-4 weeks ahead.',
        )

    def handle(self, *args, **options):
        if options.get('clear'):
            self.stdout.write(self.style.WARNING('Clearing all existing games...'))
            try:
                deleted_count = models.Game.objects.all().delete()[0]
                self.stdout.write(self.style.SUCCESS(f'Cleared {deleted_count} games.'))
            except Exception as e:
                self.stdout.write(self.style.ERROR(f"Error clearing games: {str(e)}"))
                return

        # Get season opening day from settings
        try:
            season_opening_day = parser.parse(getattr(settings, 'SEASON_OPENING_DAY', '2026-02-13')).date()
        except (ValueError, TypeError) as e:
            self.stdout.write(self.style.ERROR(f"Invalid SEASON_OPENING_DAY setting: {str(e)}"))
            return

        today = timezone.now().date()
        
        # Determine start date - use max of today and season opening day
        # (in case someone manually sets a date before opening day)
        if options.get('date'):
            try:
                start_date = parser.parse(options['date']).date()
                if start_date < season_opening_day:
                    self.stdout.write(
                        self.style.WARNING(
                            f"Specified date {start_date} is before the season opening day ({season_opening_day}). "
                            f"Using season opening day instead."
                        )
                    )
                    start_date = season_opening_day
            except (ValueError, TypeError) as e:
                self.stdout.write(self.style.ERROR(f"Invalid date format: {options['date']}. Use YYYY-MM-DD. Error: {str(e)}"))
                return
        else:
            # Default: start from season opening day if today is before it, otherwise start from today
            start_date = max(today, season_opening_day)
            if today < season_opening_day:
                self.stdout.write(
                    self.style.SUCCESS(
                        f"Today ({today}) is before the season opening day ({season_opening_day}). "
                        f"Loading games starting from opening day."
                    )
                )

        # Load 4 weeks (28 days) of games
        end_date = start_date + timedelta(days=27)  # 28 days total (start_date + 27 more days)

        # Check if date range is too far in the future
        max_weeks_ahead = options.get('max_weeks_ahead', 4)
        max_future_date = timezone.now().date() + timedelta(weeks=max_weeks_ahead)
        
        if start_date > max_future_date:
            self.stdout.write(
                self.style.WARNING(
                    f"Start date {start_date} is more than {max_weeks_ahead} weeks in the future. "
                    f"ESPN typically only loads games up to {max_future_date}. "
                    f"Skipping to avoid empty results."
                )
            )
            return

        est = pytz.timezone('US/Eastern')
        now = timezone.now()
        if now.tzinfo is None:
            now = est.localize(now.replace(tzinfo=None))

        # Deactivate all future ESPN games; they will be reactivated if found in the API feed.
        # Games no longer in the feed (canceled or moved) will remain inactive.
        # Exclude FloBaseball games (espn_id starts with 'flo_') - those are managed by load_flocollege_games.
        if not options.get('clear'):
            deactivated = models.Game.objects.filter(
                start_datetime__gt=now
            ).exclude(
                espn_id__startswith='flo_'
            ).update(active=False)
            if deactivated > 0:
                self.stdout.write(self.style.WARNING(f'Deactivated {deactivated} future ESPN game(s) (will reactivate if found in feed).'))

        self.stdout.write(f"Loading games from {start_date} to {end_date} (4 weeks)...")

        # Track totals across all days
        total_created_count = 0
        total_updated_count = 0
        total_skipped_count = 0
        all_error_details = []

        # Loop through each day in the 2-week range
        current_date = start_date
        while current_date <= end_date:
            # Format date for URL
            z_month = f"{current_date.month}".zfill(2)
            z_day = f"{current_date.day}".zfill(2)
            url_date = f"{current_date.year}-{z_month}-{z_day}"

            self.stdout.write(f"\nFetching games for {url_date}...")

            # Fetch games from ESPN API
            try:
                games_data = self.get_espn_games(url_date)
            except Exception as e:
                self.stdout.write(self.style.ERROR(f"Fatal error fetching games for {url_date}: {str(e)}"))
                current_date += timedelta(days=1)
                continue
            
            if not games_data:
                self.stdout.write(self.style.WARNING(f'No games found for {url_date}.'))
                current_date += timedelta(days=1)
                continue

            # Filter to only actual games (not studio shows, etc.)
            actual_games = [g for g in games_data if self.is_actual_game(g)]
            if not actual_games:
                self.stdout.write(self.style.WARNING(f'No actual games found for {url_date} (only non-game content).'))
                current_date += timedelta(days=1)
                continue

            # Filter to only NCAA games
            ncaa_games = [g for g in actual_games if self.is_ncaa_game(g)]
            if not ncaa_games:
                self.stdout.write(self.style.WARNING(f'No NCAA games found for {url_date} (only non-NCAA games).'))
                current_date += timedelta(days=1)
                continue

            self.stdout.write(f"Found {len(ncaa_games)} NCAA games for {url_date}. Processing...")

            created_count = 0
            updated_count = 0
            skipped_count = 0
            error_details = []

            for game_data in ncaa_games:
                try:
                    game, created = self.create_or_update_game(game_data, now)
                    if created:
                        created_count += 1
                        total_created_count += 1
                        self.stdout.write(f"  ✓ Created: {game.name}")
                    else:
                        updated_count += 1
                        total_updated_count += 1
                        self.stdout.write(f"  ↻ Updated: {game.name}")
                except ValueError as e:
                    # Missing required data - skip gracefully
                    game_name = game_data.get('name', 'Unknown')
                    espn_id = game_data.get('id', 'N/A')
                    error_msg = f"{game_name} (ID: {espn_id}): {str(e)}"
                    error_details.append(error_msg)
                    all_error_details.append(f"{url_date} - {error_msg}")
                    skipped_count += 1
                    total_skipped_count += 1
                except Exception as e:
                    # Other errors - log but continue
                    game_name = game_data.get('name', 'Unknown')
                    espn_id = game_data.get('id', 'N/A')
                    error_msg = f"{game_name} (ID: {espn_id}): {str(e)}"
                    error_details.append(error_msg)
                    all_error_details.append(f"{url_date} - {error_msg}")
                    skipped_count += 1
                    total_skipped_count += 1

            self.stdout.write(f"  {url_date}: Created: {created_count}, Updated: {updated_count}, Skipped: {skipped_count}")

            # Move to next day
            current_date += timedelta(days=1)

        # Summary across all days
        self.stdout.write("")
        self.stdout.write(self.style.SUCCESS(
            f'\nOverall Summary ({start_date} to {end_date}):\n'
            f'  Created: {total_created_count}\n'
            f'  Updated: {total_updated_count}\n'
            f'  Skipped: {total_skipped_count}'
        ))
        
        if all_error_details and total_skipped_count > 0:
            self.stdout.write("")
            self.stdout.write(self.style.WARNING("Skipped games (errors):"))
            for detail in all_error_details[:10]:  # Show first 10 errors
                self.stdout.write(f"  - {detail}")
            if len(all_error_details) > 10:
                self.stdout.write(f"  ... and {len(all_error_details) - 10} more errors")

    def is_actual_game(self, game_data):
        """Check if this is an actual game (not a studio show or other content)."""
        name = game_data.get('name', '')
        # Must have "vs." to be a game
        if " vs. " not in name:
            return False
        
        # Check if it's marked as a studio show
        program = game_data.get('program', {})
        if program.get('isStudio'):
            return False
        
        return True

    def get_espn_games(self, url_date):
        """Fetch games from ESPN GraphQL API for both live and upcoming games."""
        headers = {
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.5 Safari/605.1.15',
            'Content-Type': 'application/json',
            'Accept': 'application/json',
        }

        live_url = (
            "https://watch.graph.api.espn.com/api?apiKey=0dbf88e8-cc6d-41da-aa83-18b5c630bc5c&query=query%20Airings%20(%20%24countryCode%3A%20String!%2C%20%24deviceType%3A%20DeviceType!%2C%20%24tz%3A%20String!%2C%20%24type%3A%20AiringType%2C%20%24types%3A%20%5BAiringType%5D%2C%20%24categories%3A%20%5BString%5D%2C%20%24networks%3A%20%5BString%5D%2C%20%24packages%3A%20%5BString%5D%2C%20%24eventId%3A%20String%2C%20%24packageId%3A%20String%2C%20%24start%3A%20String%2C%20%24end%3A%20String%2C%20%24day%3A%20String%2C%20%24limit%3A%20Int%20)%20%7B%20airings(%20countryCode%3A%20%24countryCode%2C%20deviceType%3A%20%24deviceType%2C%20tz%3A%20%24tz%2C%20type%3A%20%24type%2C%20types%3A%20%24types%2C%20categories%3A%20%24categories%2C%20networks%3A%20%24networks%2C%20packages%3A%20%24packages%2C%20eventId%3A%20%24eventId%2C%20packageId%3A%20%24packageId%2C%20start%3A%20%24start%2C%20end%3A%20%24end%2C%20day%3A%20%24day%2C%20limit%3A%20%24limit%20)%20%7B%20id%20airingId%20simulcastAiringId%20name%20shortName%20type%20startDateTime%20endDateTime%20shortDate%3A%20startDate(style%3A%20SHORT)%20authTypes%20adobeRSS%20duration%20feedName%20purchaseImage%20%7B%20url%20%7D%20image%20%7B%20url%20%7D%20network%20%7B%20id%20type%20abbreviation%20name%20shortName%20adobeResource%20isIpAuth%20%7D%20source%20%7B%20url%20authorizationType%20hasPassThroughAds%20hasNielsenWatermarks%20hasEspnId3Heartbeats%20commercialReplacement%20%7D%20packages%20%7B%20name%20%7D%20category%20%7B%20id%20name%20%7D%20subcategory%20%7B%20id%20name%20%7D%20sport%20%7B%20id%20name%20abbreviation%20code%20%7D%20league%20%7B%20id%20name%20abbreviation%20code%20%7D%20franchise%20%7B%20id%20name%20%7D%20program%20%7B%20id%20code%20categoryCode%20isStudio%20%7D%20tracking%20%7B%20nielsenCrossId1%20nielsenCrossId2%20comscoreC6%20trackingId%20%7D%20%7D%20%7D&variables=%7B%22deviceType%22%3A%22DESKTOP%22%2C%22countryCode%22%3A%22US%22%2C%22tz%22%3A%22UTC-0500%22%2C%22type%22%3A%22LIVE%22%2C%22packages%22%3Anull%2C%22categories%22%3A%5B%22e364bfcd-493d-3bfb-ac83-bd27d66fedd0%22%5D%2C%22limit%22%3A1000%7D"
        )

        upcoming_url = (
            f"https://watch.graph.api.espn.com/api?apiKey=0dbf88e8-cc6d-41da-aa83-18b5c630bc5c&query=query%20Airings%20(%20%24countryCode%3A%20String!%2C%20%24deviceType%3A%20DeviceType!%2C%20%24tz%3A%20String!%2C%20%24type%3A%20AiringType%2C%20%24types%3A%20%5BAiringType%5D%2C%20%24categories%3A%20%5BString%5D%2C%20%24networks%3A%20%5BString%5D%2C%20%24packages%3A%20%5BString%5D%2C%20%24eventId%3A%20String%2C%20%24packageId%3A%20String%2C%20%24start%3A%20String%2C%20%24end%3A%20String%2C%20%24day%3A%20String%2C%20%24limit%3A%20Int%20)%20%7B%20airings(%20countryCode%3A%20%24countryCode%2C%20deviceType%3A%20%24deviceType%2C%20tz%3A%20%24tz%2C%20type%3A%20%24type%2C%20types%3A%20%24types%2C%20categories%3A%20%24categories%2C%20networks%3A%20%24networks%2C%20packages%3A%20%24packages%2C%20eventId%3A%20%24eventId%2C%20packageId%3A%20%24packageId%2C%20start%3A%20%24start%2C%20end%3A%20%24end%2C%20day%3A%20%24day%2C%20limit%3A%20%24limit%20)%20%7B%20id%20airingId%20simulcastAiringId%20name%20shortName%20type%20startDateTime%20endDateTime%20shortDate%3A%20startDate(style%3A%20SHORT)%20authTypes%20adobeRSS%20duration%20feedName%20purchaseImage%20%7B%20url%20%7D%20image%20%7B%20url%20%7D%20network%20%7B%20id%20type%20abbreviation%20name%20shortName%20adobeResource%20isIpAuth%20%7D%20source%20%7B%20url%20authorizationType%20hasPassThroughAds%20hasNielsenWatermarks%20hasEspnId3Heartbeats%20commercialReplacement%20%7D%20packages%20%7B%20name%20%7D%20category%20%7B%20id%20name%20%7D%20subcategory%20%7B%20id%20name%20%7D%20sport%20%7B%20id%20name%20abbreviation%20code%20%7D%20league%20%7B%20id%20name%20abbreviation%20code%20%7D%20franchise%20%7B%20id%20name%20%7D%20program%20%7B%20id%20code%20categoryCode%20isStudio%20%7D%20tracking%20%7B%20nielsenCrossId1%20nielsenCrossId2%20comscoreC6%20trackingId%20%7D%20%7D%20%7D&variables=%7B%22deviceType%22%3A%22DESKTOP%22%2C%22countryCode%22%3A%22US%22%2C%22tz%22%3A%22UTC-0500%22%2C%22type%22%3A%22UPCOMING%22%2C%22packages%22%3Anull%2C%22categories%22%3A%5B%22e364bfcd-493d-3bfb-ac83-bd27d66fedd0%22%5D%2C%22day%22%3A%22{url_date}%22%2C%22limit%22%3A1000%7D"
        )

        all_games = []
        
        # Fetch live games (gracefully handle failures)
        try:
            live_response = requests.get(live_url, headers=headers, timeout=30)
            live_response.raise_for_status()
            live_data = live_response.json()
            
            if isinstance(live_data, dict) and 'data' in live_data:
                live_games = live_data.get("data", {}).get("airings", [])
                if isinstance(live_games, list):
                    for game in live_games:
                        if isinstance(game, dict):
                            game['_status'] = 'live'
                            all_games.append(game)
        except requests.Timeout:
            self.stdout.write(self.style.WARNING("Timeout fetching live games (continuing with upcoming games)..."))
        except requests.RequestException as e:
            self.stdout.write(self.style.WARNING(f"Error fetching live games: {str(e)} (continuing with upcoming games)..."))
        except (KeyError, ValueError, TypeError) as e:
            self.stdout.write(self.style.WARNING(f"Error parsing live games response: {str(e)} (continuing with upcoming games)..."))
        
        # Fetch upcoming games (gracefully handle failures)
        try:
            upcoming_response = requests.get(upcoming_url, headers=headers, timeout=30)
            upcoming_response.raise_for_status()
            upcoming_data = upcoming_response.json()
            
            if isinstance(upcoming_data, dict) and 'data' in upcoming_data:
                upcoming_games = upcoming_data.get("data", {}).get("airings", [])
                if isinstance(upcoming_games, list):
                    for game in upcoming_games:
                        if isinstance(game, dict):
                            game['_status'] = 'upcoming'
                            all_games.append(game)
        except requests.Timeout:
            self.stdout.write(self.style.WARNING("Timeout fetching upcoming games..."))
        except requests.RequestException as e:
            self.stdout.write(self.style.WARNING(f"Error fetching upcoming games: {str(e)}..."))
        except (KeyError, ValueError, TypeError) as e:
            self.stdout.write(self.style.WARNING(f"Error parsing upcoming games response: {str(e)}..."))
        
        return all_games

    def extract_teams_from_name(self, game_name):
        """Extract team names and rankings from game name string (e.g., '#15 UCLA vs. #25 South Florida').
        
        Returns a list of tuples: [(team_name, ranking), ...] where ranking is an int or None.
        """
        teams = []
        
        # Clean up game name
        if "(Baseball)" in game_name:
            game_name = game_name.replace("(Baseball)", "").strip()
        
        if "vs." in game_name:
            for team_name in game_name.split("vs."):
                team_name = team_name.strip()
                ranking = None
                
                # Extract ranking if present (e.g., "#5 Team Name" or "#15 Team Name")
                if "#" in team_name:
                    rank_pattern = re.compile(r"#(\d{1,})")
                    rank_match = rank_pattern.search(team_name)
                    if rank_match:
                        try:
                            ranking = int(rank_match.group(1))
                        except (ValueError, AttributeError):
                            ranking = None
                        # Remove ranking from team name
                        team_name = rank_pattern.sub('', team_name).strip()
                
                if team_name:
                    teams.append((team_name, ranking))
        
        return teams

    def get_primary_team(self, team):
        """
        Check if this team has been merged into another team.
        If so, return the primary team. Otherwise, return the original team.
        """
        # Check if this team was merged into another (it would be inactive)
        if not team.active:
            # Look for a merge decision where this team was the secondary
            merge_decision = models.TeamDuplicateDecision.objects.filter(
                decision='merged',
                primary_team__isnull=False
            ).filter(
                Q(team1=team) | Q(team2=team)
            ).exclude(
                primary_team=team  # Don't match if this team was the primary
            ).first()
            
            if merge_decision and merge_decision.primary_team.active:
                return merge_decision.primary_team
        
        return team
    
    def get_or_create_team(self, team_name):
        """Get or create a Team object by name, returning the primary team if merged."""
        team, created = models.Team.objects.get_or_create(
            name=team_name,
            defaults={'active': True}
        )
        # Ensure team has a slug (for existing teams that might not have one)
        if not team.slug:
            team.save()  # This will auto-generate the slug
            team.refresh_from_db()
        # Check if this team has been merged
        primary_team = self.get_primary_team(team)
        # Ensure primary team also has a slug
        if primary_team and not primary_team.slug:
            primary_team.save()
            primary_team.refresh_from_db()
        return primary_team

    def is_ncaa_game(self, game_data):
        """Determine if a game is an NCAA game."""
        if game_data.get('subcategory'):
            if game_data['subcategory'].get('name') == "NCAA Baseball":
                return True
        
        if game_data.get('league'):
            if game_data['league'].get('name') == "NCAA Baseball":
                return True
        
        return False

    def create_or_update_game(self, game_data, now):
        """Create or update a Game object from ESPN API data.
        
        This method is idempotent - running it multiple times with the same espn_id
        will update the existing game rather than creating duplicates.
        """
        # Validate required fields
        espn_id = game_data.get('id')
        if not espn_id:
            raise ValueError("Game data missing required 'id' field (espn_id)")
        
        if not isinstance(espn_id, str) and not isinstance(espn_id, (int, float)):
            raise ValueError(f"Invalid espn_id type: {type(espn_id)}")

        # Parse datetime (required field)
        start_datetime_str = game_data.get('startDateTime')
        if not start_datetime_str:
            raise ValueError(f"Game data missing required 'startDateTime' field (espn_id: {espn_id})")
        
        try:
            start_datetime = parser.parse(start_datetime_str)
            if start_datetime.tzinfo is None:
                est = pytz.timezone('US/Eastern')
                start_datetime = est.localize(start_datetime)
        except (ValueError, TypeError) as e:
            raise ValueError(f"Invalid startDateTime format '{start_datetime_str}': {str(e)}")
        
        # Parse end datetime (optional)
        end_datetime = None
        if game_data.get('endDateTime'):
            try:
                end_datetime = parser.parse(game_data['endDateTime'])
                if end_datetime.tzinfo is None:
                    est = pytz.timezone('US/Eastern')
                    end_datetime = est.localize(end_datetime)
            except (ValueError, TypeError):
                # End datetime is optional, so we'll just skip it if invalid
                pass

        # Extract teams (rankings come from load_coaches_poll - USA Today poll, not ESPN)
        game_name = game_data.get('name', '')
        team_data = self.extract_teams_from_name(game_name)
        
        home_team = None
        away_team = None
        home_team_ranking = None  # Use team.current_ranking from load_coaches_poll
        away_team_ranking = None
        
        if len(team_data) >= 2:
            # First team is away, second is home (typical "Away vs. Home" format)
            away_team_name, _ = team_data[0]
            home_team_name, _ = team_data[1]
            away_team = self.get_or_create_team(away_team_name)
            home_team = self.get_or_create_team(home_team_name)
        elif len(team_data) == 1:
            away_team_name, _ = team_data[0]
            away_team = self.get_or_create_team(away_team_name)

        # Extract video URL from API response
        # Prefer source.url (actual video stream URL) over constructed ESPN+ URL
        streaming_url = None
        if game_data.get('source') and game_data['source'].get('url'):
            streaming_url = game_data['source']['url']
        
        # Fallback to ESPN+ player URL if source URL not available
        if not streaming_url:
            streaming_url = f"https://www.espn.com/espnplus/player/_/id/{espn_id}"

        # Determine initial status
        initial_status = game_data.get('_status', 'future')
        if initial_status == 'live':
            status = 'live'
        elif initial_status == 'upcoming':
            status = 'future'
        else:
            # Fallback: determine from datetime
            if end_datetime and now > end_datetime:
                status = 'past'
            elif start_datetime and now >= start_datetime:
                status = 'live'
            else:
                status = 'future'

        # Get image URL
        image_url = None
        if game_data.get('image') and game_data['image'].get('url'):
            image_url = game_data['image']['url']

        # Get network name
        network_name = None
        if game_data.get('network') and game_data['network'].get('name'):
            network_name = game_data['network']['name']

        # Get sport and league names
        sport_name = None
        if game_data.get('sport') and game_data['sport'].get('name'):
            sport_name = game_data['sport']['name']

        league_name = None
        if game_data.get('league') and game_data['league'].get('name'):
            league_name = game_data['league']['name']

        # Create or update game using espn_id as unique identifier
        # This makes the operation idempotent - same espn_id will update existing game
        try:
            game, created = models.Game.objects.update_or_create(
                espn_id=str(espn_id),  # Ensure string for consistency
                defaults={
                    'name': game_name,
                    'short_name': game_data.get('shortName'),
                    'home_team': home_team,
                    'away_team': away_team,
                    'home_team_ranking': home_team_ranking,
                    'away_team_ranking': away_team_ranking,
                    'start_datetime': start_datetime,
                    'end_datetime': end_datetime,
                    'short_date': game_data.get('shortDate'),
                    'status': status,
                    'streaming_url': streaming_url,
                    'image_url': image_url,
                    'network_name': network_name,
                    'sport_name': sport_name,
                    'league_name': league_name,
                    'is_ncaa': self.is_ncaa_game(game_data),
                    'active': True,
                }
            )
            return game, created
        except Exception as e:
            # Database errors (e.g., constraint violations)
            raise ValueError(f"Database error creating/updating game (espn_id: {espn_id}): {str(e)}")
