import requests
from django.core.management.base import BaseCommand
from django.utils import timezone
from django.conf import settings
from datetime import datetime, timedelta
from dateutil import parser


class Command(BaseCommand):
    help = 'Find dates that have games available from ESPN API (debugging/discovery tool). Uses SEASON_OPENING_DAY from settings.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--start-date',
            type=str,
            help='Start date (YYYY-MM-DD format). Defaults to SEASON_OPENING_DAY from settings.',
        )
        parser.add_argument(
            '--end-date',
            type=str,
            help='End date (YYYY-MM-DD format). Defaults to end of June 2026.',
        )
        parser.add_argument(
            '--max-weeks-ahead',
            type=int,
            default=4,
            help='Maximum number of weeks in the future to check for games (default: 4). ESPN typically only loads games 3-4 weeks ahead.',
        )
        parser.add_argument(
            '--load',
            action='store_true',
            help='Also load games using load_games command (loads 2 weeks at a time, respecting SEASON_OPENING_DAY)',
        )

    def handle(self, *args, **options):
        # Get season opening day from settings
        try:
            season_opening_day = parser.parse(getattr(settings, 'SEASON_OPENING_DAY', '2026-02-13')).date()
        except (ValueError, TypeError) as e:
            self.stdout.write(self.style.ERROR(f"Invalid SEASON_OPENING_DAY setting: {str(e)}"))
            return

        today = timezone.now().date()
        
        # Parse start date or default to season opening day
        if options.get('start_date'):
            try:
                start_date = datetime.strptime(options['start_date'], '%Y-%m-%d').date()
                if start_date < season_opening_day:
                    self.stdout.write(
                        self.style.WARNING(
                            f"Start date {start_date} is before season opening day ({season_opening_day}). "
                            f"Using season opening day instead."
                        )
                    )
                    start_date = season_opening_day
            except ValueError:
                self.stdout.write(self.style.ERROR(f"Invalid start date format: {options['start_date']}. Use YYYY-MM-DD"))
                return
        else:
            start_date = season_opening_day

        # Parse end date or default to end of June
        if options.get('end_date'):
            try:
                end_date = datetime.strptime(options['end_date'], '%Y-%m-%d').date()
            except ValueError:
                self.stdout.write(self.style.ERROR(f"Invalid end date format: {options['end_date']}. Use YYYY-MM-DD"))
                return
        else:
            # Default to June 30, 2026 (College World Series typically ends late June)
            end_date = datetime(2026, 6, 30).date()

        # Limit end date based on max weeks ahead (ESPN typically only loads 3-4 weeks ahead)
        max_weeks_ahead = options.get('max_weeks_ahead', 4)
        max_future_date = today + timedelta(weeks=max_weeks_ahead)
        
        if end_date > max_future_date:
            self.stdout.write(
                self.style.WARNING(
                    f"End date {end_date} is more than {max_weeks_ahead} weeks in the future. "
                    f"Limiting scan to {max_future_date} (ESPN typically only loads games 3-4 weeks ahead)."
                )
            )
            end_date = max_future_date
        
        if start_date > max_future_date:
            self.stdout.write(
                self.style.WARNING(
                    f"Start date {start_date} is more than {max_weeks_ahead} weeks in the future. "
                    f"ESPN typically only loads games up to {max_future_date}. No dates to scan."
                )
            )
            return

        # Check if we're before the season opening day
        if today < season_opening_day:
            self.stdout.write(
                self.style.WARNING(
                    f"Today ({today}) is before the season opening day ({season_opening_day}). "
                    f"Scanning will still proceed, but load_games will skip dates before opening day."
                )
            )

        self.stdout.write(f"Season opening day: {season_opening_day}")
        self.stdout.write(f"Scanning dates from {start_date} to {end_date}...")
        self.stdout.write(f"(Limited to {max_weeks_ahead} weeks ahead from today: {today})")
        self.stdout.write("")

        dates_with_games = []
        current_date = start_date

        while current_date <= end_date:
            try:
                game_count = self.check_date_for_games(current_date)
                if game_count > 0:
                    dates_with_games.append((current_date, game_count))
                    self.stdout.write(
                        self.style.SUCCESS(f"✓ {current_date.strftime('%Y-%m-%d (%A)')}: {game_count} games")
                    )
                else:
                    self.stdout.write(f"  {current_date.strftime('%Y-%m-%d (%A)')}: No games")
            except Exception as e:
                # Continue scanning even if one date fails
                self.stdout.write(
                    self.style.WARNING(f"  ⚠ {current_date.strftime('%Y-%m-%d (%A)')}: Error checking - {str(e)}")
                )

            current_date += timedelta(days=1)

        self.stdout.write("")
        self.stdout.write(self.style.SUCCESS(f"\nFound {len(dates_with_games)} dates with games:"))
        for date, count in dates_with_games:
            self.stdout.write(f"  {date.strftime('%Y-%m-%d')}: {count} games")

        # Optionally load games using load_games command (which loads 2 weeks at a time)
        if options.get('load') and dates_with_games:
            self.stdout.write("")
            self.stdout.write("Loading games using load_games command (loads 2 weeks at a time)...")
            self.stdout.write("Note: load_games respects SEASON_OPENING_DAY and loads 2 weeks from each start date.")
            from django.core.management import call_command
            
            # Group dates into 2-week chunks to avoid redundant API calls
            # Since load_games loads 2 weeks at once, we'll call it for unique 2-week windows
            loaded_chunks = set()
            loaded_count = 0
            failed_count = 0
            
            for date, count in dates_with_games:
                # Calculate which 2-week chunk this date belongs to
                # Use the start of the 2-week period (date - (date - season_opening_day) % 14)
                days_since_opening = (date - season_opening_day).days
                chunk_start_days = (days_since_opening // 14) * 14
                chunk_start_date = season_opening_day + timedelta(days=chunk_start_days)
                
                # Skip if we've already loaded this chunk
                if chunk_start_date in loaded_chunks:
                    continue
                
                loaded_chunks.add(chunk_start_date)
                
                try:
                    self.stdout.write(f"Loading games starting from {chunk_start_date} (2-week chunk)...")
                    call_command('load_games', date=chunk_start_date.strftime('%Y-%m-%d'))
                    loaded_count += 1
                except Exception as e:
                    self.stdout.write(
                        self.style.ERROR(f"Failed to load games for chunk starting {chunk_start_date}: {str(e)}")
                    )
                    failed_count += 1
                    continue
            
            self.stdout.write("")
            self.stdout.write(self.style.SUCCESS(
                f"Loaded games for {loaded_count} 2-week chunks. Failed: {failed_count}"
            ))
            self.stdout.write(f"(Note: Each chunk covers 14 days, so this may cover more dates than were found in the scan)")

    def check_date_for_games(self, target_date):
        """Check if a specific date has games available from ESPN API."""
        headers = {
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.5 Safari/605.1.15',
            'Content-Type': 'application/json',
            'Accept': 'application/json',
        }

        # Format date for URL
        z_month = f"{target_date.month}".zfill(2)
        z_day = f"{target_date.day}".zfill(2)
        url_date = f"{target_date.year}-{z_month}-{z_day}"

        # Check upcoming games for this date
        upcoming_url = (
            f"https://watch.graph.api.espn.com/api?apiKey=0dbf88e8-cc6d-41da-aa83-18b5c630bc5c&query=query%20Airings%20(%20%24countryCode%3A%20String!%2C%20%24deviceType%3A%20DeviceType!%2C%20%24tz%3A%20String!%2C%20%24type%3A%20AiringType%2C%20%24types%3A%20%5BAiringType%5D%2C%20%24categories%3A%20%5BString%5D%2C%20%24networks%3A%20%5BString%5D%2C%20%24packages%3A%20%5BString%5D%2C%20%24eventId%3A%20String%2C%20%24packageId%3A%20String%2C%20%24start%3A%20String%2C%20%24end%3A%20String%2C%20%24day%3A%20String%2C%20%24limit%3A%20Int%20)%20%7B%20airings(%20countryCode%3A%20%24countryCode%2C%20deviceType%3A%20%24deviceType%2C%20tz%3A%20%24tz%2C%20type%3A%20%24type%2C%20types%3A%20%24types%2C%20categories%3A%20%24categories%2C%20networks%3A%20%24networks%2C%20packages%3A%20%24packages%2C%20eventId%3A%20%24eventId%2C%20packageId%3A%20%24packageId%2C%20start%3A%20%24start%2C%20end%3A%20%24end%2C%20day%3A%20%24day%2C%20limit%3A%20%24limit%20)%20%7B%20id%20airingId%20simulcastAiringId%20name%20shortName%20type%20startDateTime%20endDateTime%20shortDate%3A%20startDate(style%3A%20SHORT)%20authTypes%20adobeRSS%20duration%20feedName%20purchaseImage%20%7B%20url%20%7D%20image%20%7B%20url%20%7D%20network%20%7B%20id%20type%20abbreviation%20name%20shortName%20adobeResource%20isIpAuth%20%7D%20source%20%7B%20url%20authorizationType%20hasPassThroughAds%20hasNielsenWatermarks%20hasEspnId3Heartbeats%20commercialReplacement%20%7D%20packages%20%7B%20name%20%7D%20category%20%7B%20id%20name%20%7D%20subcategory%20%7B%20id%20name%20%7D%20sport%20%7B%20id%20name%20abbreviation%20code%20%7D%20league%20%7B%20id%20name%20abbreviation%20code%20%7D%20franchise%20%7B%20id%20name%20%7D%20program%20%7B%20id%20code%20categoryCode%20isStudio%20%7D%20tracking%20%7B%20nielsenCrossId1%20nielsenCrossId2%20comscoreC6%20trackingId%20%7D%20%7D%20%7D&variables=%7B%22deviceType%22%3A%22DESKTOP%22%2C%22countryCode%22%3A%22US%22%2C%22tz%22%3A%22UTC-0500%22%2C%22type%22%3A%22UPCOMING%22%2C%22packages%22%3Anull%2C%22categories%22%3A%5B%22e364bfcd-493d-3bfb-ac83-bd27d66fedd0%22%5D%2C%22day%22%3A%22{url_date}%22%2C%22limit%22%3A1000%7D"
        )

        try:
            response = requests.get(upcoming_url, headers=headers, timeout=10)
            response.raise_for_status()
            
            # Parse JSON response
            try:
                data = response.json()
            except ValueError as e:
                raise ValueError(f"Invalid JSON response: {str(e)}")
            
            # Safely extract games
            if not isinstance(data, dict):
                return 0
            
            games = data.get("data", {}).get("airings", [])
            if not isinstance(games, list):
                return 0
            
            # Filter to only games with "vs." in the name (actual games, not studio shows)
            actual_games = [
                g for g in games 
                if isinstance(g, dict) and " vs. " in g.get("name", "")
            ]
            
            return len(actual_games)
        except requests.Timeout:
            # Timeout - return 0 but don't raise exception
            return 0
        except requests.RequestException as e:
            # Network/HTTP errors - return 0 but don't raise exception
            return 0
        except (KeyError, ValueError, TypeError) as e:
            # Parsing errors - return 0 but don't raise exception
            return 0
