import json
import os
import requests
from pathlib import Path
from django.core.management.base import BaseCommand, CommandError

from overslot import models
from overslot.utils import fuzzy_find_player


# API Configuration
TOKEN_URL = "https://api.643charts.com/token"
PLAYER_MAPPINGS_URL = "https://api.643charts.com/overslot/player-mappings"
STATS_URL_TEMPLATE = "https://api.643charts.com/overslot/stats/{overslot_player_id}"


class Command(BaseCommand):
    help = 'Load player stats from 6-4-3 Charts API and create/update Player643StatSeason records. Processes all players (hitters and pitchers, college and high school).'

    def add_arguments(self, parser):
        parser.add_argument(
            '--local-dir',
            type=str,
            help='Read from local directory instead of making API calls (faster for testing)',
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be created/updated without actually saving',
        )
        parser.add_argument(
            '--player-id',
            type=str,
            help='Process only a specific player ID (for testing)',
        )

    def handle(self, *args, **options):
        local_dir = options.get('local_dir')
        dry_run = options.get('dry_run', False)
        player_id_filter = options.get('player_id')
        verbosity = options.get('verbosity', 1)

        if dry_run:
            self.stdout.write(self.style.WARNING('DRY RUN MODE - No changes will be saved'))

        # Determine if we're reading from local files or making API calls
        if local_dir:
            self.stdout.write(f"Reading from local directory: {local_dir}")
            if not os.path.isdir(local_dir):
                raise CommandError(f"Local directory does not exist: {local_dir}")
            player_mappings = self._load_local_player_mappings(local_dir)
            stats_data_list = self._load_local_stats_files(local_dir, player_id_filter)
            # If no mappings file, we'll match by name from stats files
            if not player_mappings:
                self.stdout.write(self.style.WARNING("No player_mappings.json found - will match players by name from stats files"))
        else:
            self.stdout.write("Fetching data from 6-4-3 Charts API...")
            # Get credentials from environment
            client_id = os.environ.get('SIXFORTYTHREE_CLIENT_ID')
            client_secret = os.environ.get('SIXFORTYTHREE_CLIENT_SECRET')
            
            if not client_id or not client_secret:
                self.stdout.write(self.style.ERROR(
                    "\nMissing required environment variables!\n"
                    "Please export the following before running this command:\n"
                    "  export SIXFORTYTHREE_CLIENT_ID='Partner - Over-Slot'\n"
                    "  export SIXFORTYTHREE_CLIENT_SECRET='your-secret-here'\n\n"
                    "Alternatively, use --local-dir to read from local files instead."
                ))
                raise CommandError("Missing required environment variables")
            
            try:
                # Get token and fetch data
                token = self._get_bearer_token(client_id, client_secret)
                player_mappings = self._get_player_mappings(token)
                
                # Fetch stats directly from API
                stats_data_list = self._fetch_stats_from_api(token, player_mappings, player_id_filter, verbosity=verbosity)
                
            except requests.exceptions.RequestException as e:
                self.stdout.write(self.style.ERROR(f"\nAPI request failed: {str(e)}"))
                if hasattr(e, 'response') and e.response is not None:
                    try:
                        error_detail = e.response.json()
                        self.stdout.write(self.style.ERROR(f"API response: {error_detail}"))
                    except:
                        self.stdout.write(self.style.ERROR(f"API response status: {e.response.status_code}"))
                        self.stdout.write(self.style.ERROR(f"API response text: {e.response.text[:500]}"))
                raise CommandError("Failed to fetch data from 6-4-3 Charts API")
            except CommandError:
                # Re-raise CommandError as-is
                raise
            except Exception as e:
                self.stdout.write(self.style.ERROR(f"\nUnexpected error: {str(e)}"))
                if verbosity >= 2:
                    import traceback
                    traceback.print_exc()
                raise CommandError(f"Failed to fetch data: {str(e)}")

        # Check if we have any stats to process
        if not stats_data_list:
            self.stdout.write(self.style.WARNING("\nNo stats found to process."))
            if not local_dir:
                self.stdout.write("This could mean:")
                self.stdout.write("  - No players matched the filter criteria")
                self.stdout.write("  - All players returned 404 (no stats available)")
                self.stdout.write("  - All API requests failed")
                self.stdout.write("  - The API returned no data")
                self.stdout.write("\nNote: It's normal for some players (especially HS players) to not have stats.")
            return
        
        # Process stats and create/update records
        self.stdout.write(f"\nProcessing {len(stats_data_list)} players...")
        created_count = 0
        updated_count = 0
        error_count = 0
        skipped_count = 0

        # Create a lookup dict for player mappings by ID for faster access
        mappings_by_id = {}
        if player_mappings:
            for pm in player_mappings:
                pid = pm.get('overslot_player_id')
                if pid:
                    mappings_by_id[pid] = pm

        for overslot_player_id, stats_data in stats_data_list:
            try:
                # Get player mapping
                player_mapping = mappings_by_id.get(overslot_player_id)
                
                # If no mapping found, try to extract player name from stats data
                if not player_mapping:
                    batting = stats_data.get('batting', [])
                    pitching = stats_data.get('pitching', [])
                    first_record = (batting + pitching)[0] if (batting + pitching) else None
                    if first_record:
                        player_name = first_record.get('player_name', '').strip()
                        if player_name:
                            name_parts = player_name.split(' ', 1)
                            player_mapping = {
                                'first_name': name_parts[0] if len(name_parts) > 0 else '',
                                'last_name': name_parts[1] if len(name_parts) > 1 else '',
                                'overslot_player_id': overslot_player_id,
                            }
                
                if not player_mapping:
                    if verbosity >= 2:
                        self.stdout.write(self.style.WARNING(f"No player mapping found for {overslot_player_id}"))
                    skipped_count += 1
                    continue
                
                # Find the Player in our database (must already exist)
                player = self._find_player_simple(player_mapping, verbosity=verbosity)
                if not player:
                    skipped_count += 1
                    continue
                
                # Process stats
                stats_created, stats_updated = self._process_player_stats(
                    player, stats_data, dry_run=dry_run
                )
                created_count += stats_created
                updated_count += stats_updated
                
            except Exception as e:
                self.stdout.write(self.style.ERROR(f"Error processing {overslot_player_id}: {str(e)}"))
                error_count += 1
                import traceback
                if verbosity >= 2:
                    traceback.print_exc()

        # Summary
        self.stdout.write(self.style.SUCCESS(f"\n{'[DRY RUN] ' if dry_run else ''}Summary:"))
        self.stdout.write(f"  Created: {created_count}")
        self.stdout.write(f"  Updated: {updated_count}")
        self.stdout.write(f"  Skipped: {skipped_count}")
        
        if error_count > 0:
            self.stdout.write(self.style.ERROR(f"  Errors: {error_count}"))
            self.stdout.write(self.style.WARNING(
                "\nSome files failed to process. Run with --verbosity 2 for detailed error messages."
            ))
        else:
            self.stdout.write(f"  Errors: {error_count}")
        
        if created_count == 0 and updated_count == 0 and error_count == 0:
            self.stdout.write(self.style.WARNING("\nNo records were created or updated."))

    def _get_bearer_token(self, client_id, client_secret):
        """Get a Bearer token from the API."""
        self.stdout.write("Fetching Bearer token...")
        try:
            response = requests.post(
                TOKEN_URL,
                headers={"Content-Type": "application/json"},
                json={
                    "client_id": client_id,
                    "client_secret": client_secret,
                },
                timeout=30,  # 30 second timeout
            )
            response.raise_for_status()
        except requests.exceptions.Timeout:
            raise CommandError("Request to 6-4-3 Charts API timed out. Please try again.")
        except requests.exceptions.ConnectionError as e:
            raise CommandError(f"Could not connect to 6-4-3 Charts API: {str(e)}")
        except requests.exceptions.HTTPError as e:
            if e.response.status_code == 401:
                raise CommandError(
                    "Authentication failed. Please check your SIXFORTYTHREE_CLIENT_ID and "
                    "SIXFORTYTHREE_CLIENT_SECRET environment variables."
                )
            else:
                raise CommandError(f"HTTP error from 6-4-3 Charts API: {e.response.status_code} - {str(e)}")
        
        try:
            token_data = response.json()
        except ValueError as e:
            raise CommandError(f"Invalid JSON response from API: {str(e)}")
        
        token = token_data.get("access_token") or token_data.get("token")
        if not token:
            self.stdout.write(self.style.ERROR(f"Unexpected token response format: {token_data}"))
            raise CommandError("API did not return a valid access token")
        
        self.stdout.write(self.style.SUCCESS("✓ Token obtained"))
        return token

    def _get_player_mappings(self, token):
        """Get all player mappings from the API."""
        self.stdout.write("Fetching player mappings...")
        try:
            response = requests.get(
                PLAYER_MAPPINGS_URL,
                headers={"Authorization": f"Bearer {token}"},
                timeout=60,  # 60 second timeout for potentially large response
            )
            response.raise_for_status()
        except requests.exceptions.Timeout:
            raise CommandError("Request to fetch player mappings timed out. Please try again.")
        except requests.exceptions.ConnectionError as e:
            raise CommandError(f"Could not connect to 6-4-3 Charts API: {str(e)}")
        except requests.exceptions.HTTPError as e:
            if e.response.status_code == 401:
                raise CommandError("Authentication token expired or invalid. Please try again.")
            else:
                raise CommandError(f"HTTP error fetching player mappings: {e.response.status_code} - {str(e)}")
        
        try:
            data = response.json()
        except ValueError as e:
            raise CommandError(f"Invalid JSON response from API: {str(e)}")
        
        # Handle different response structures
        if isinstance(data, dict):
            players = data.get("data") or data.get("players") or data.get("results") or list(data.values())[0]
        elif isinstance(data, list):
            players = data
        else:
            raise CommandError(f"Unexpected response type: {type(data)}")
        
        if not isinstance(players, list):
            players = [players] if players else []
        
        if len(players) == 0:
            self.stdout.write(self.style.WARNING("No player mappings found in API response"))
        
        self.stdout.write(self.style.SUCCESS(f"✓ Found {len(players)} player mappings"))
        return players

    def _fetch_stats_from_api(self, token, player_mappings, player_id_filter=None, verbosity=1):
        """Fetch stats directly from API and return list of (player_id, stats_data) tuples.
        Processes ALL players (hitters and pitchers, college and high school).
        """
        stats_list = []
        total = len(player_mappings)
        
        self.stdout.write(f"Processing {total} players (all hitters and pitchers)...")
        
        for idx, player_mapping in enumerate(player_mappings, 1):
            overslot_player_id = player_mapping.get('overslot_player_id')
            if not overslot_player_id:
                continue
            
            # Filter by player ID if specified (for testing)
            if player_id_filter and overslot_player_id != player_id_filter:
                continue
            
            if idx % 100 == 0:
                self.stdout.write(f"Fetching stats... {idx}/{total}")
            
            try:
                # Fetch stats
                url = STATS_URL_TEMPLATE.format(overslot_player_id=overslot_player_id)
                try:
                    response = requests.get(
                        url,
                        headers={"Authorization": f"Bearer {token}"},
                        timeout=30,
                    )
                    response.raise_for_status()
                except requests.exceptions.Timeout:
                    self.stdout.write(self.style.WARNING(f"Timeout fetching stats for {overslot_player_id}"))
                    continue
                except requests.exceptions.ConnectionError as e:
                    self.stdout.write(self.style.WARNING(f"Connection error for {overslot_player_id}: {str(e)}"))
                    continue
                except requests.exceptions.HTTPError as e:
                    if e.response.status_code == 404:
                        # Gracefully handle players without stats (common for HS players or players not yet in system)
                        if verbosity >= 2:
                            player_name = player_mapping.get('first_name', '') + ' ' + player_mapping.get('last_name', '')
                            self.stdout.write(self.style.WARNING(f"No stats found for {overslot_player_id} ({player_name.strip()})"))
                        continue
                    elif e.response.status_code == 401:
                        self.stdout.write(self.style.ERROR("Authentication token expired during fetch"))
                        raise CommandError("Token expired - please run the command again")
                    else:
                        self.stdout.write(self.style.WARNING(
                            f"HTTP error {e.response.status_code} for {overslot_player_id}: {str(e)}"
                        ))
                        continue
                
                try:
                    stats_data = response.json()
                    stats_list.append((overslot_player_id, stats_data))
                except ValueError as e:
                    self.stdout.write(self.style.WARNING(f"Invalid JSON response for {overslot_player_id}: {str(e)}"))
                    continue
                
            except CommandError:
                # Re-raise CommandError (like token expiration)
                raise
            except Exception as e:
                self.stdout.write(self.style.WARNING(f"Unexpected error fetching stats for {overslot_player_id}: {str(e)}"))
                if verbosity >= 2:
                    import traceback
                    traceback.print_exc()
                continue
        
        self.stdout.write(self.style.SUCCESS(f"✓ Fetched stats for {len(stats_list)} players"))
        return stats_list

    def _load_local_player_mappings(self, local_dir):
        """Load player mappings from a local JSON file if it exists."""
        mappings_file = os.path.join(local_dir, 'player_mappings.json')
        if os.path.exists(mappings_file):
            with open(mappings_file, 'r') as f:
                data = json.load(f)
                if isinstance(data, list):
                    return data
                elif isinstance(data, dict):
                    return data.get("data") or data.get("players") or data.get("results") or []
        return []

    def _load_local_stats_files(self, local_dir, player_id_filter=None):
        """Load stats from local JSON files and return list of (player_id, stats_data) tuples."""
        stats_list = []
        for filepath in Path(local_dir).glob('*.json'):
            # Skip player_mappings.json if it exists
            if filepath.name == 'player_mappings.json':
                continue
            
            # Extract player ID from filename
            filename = filepath.stem
            if '-' in filename:
                # Extract UUID (everything after the first dash, or everything if no year prefix)
                parts = filename.split('-', 1)
                if len(parts) == 2:
                    # Check if first part looks like a year (4 digits)
                    if parts[0].isdigit() and len(parts[0]) == 4:
                        overslot_player_id = parts[1]  # UUID is everything after year
                    else:
                        overslot_player_id = filename  # Use full filename as ID
                else:
                    overslot_player_id = filename
            else:
                overslot_player_id = filename
            
            # Filter by player ID if specified
            if player_id_filter and overslot_player_id != player_id_filter:
                continue
            
            try:
                with open(filepath, 'r') as f:
                    stats_data = json.load(f)
                stats_list.append((overslot_player_id, stats_data))
            except IOError as e:
                self.stdout.write(self.style.WARNING(f"Could not read file {filepath}: {str(e)}"))
                continue
            except json.JSONDecodeError as e:
                self.stdout.write(self.style.WARNING(f"Invalid JSON in {filepath}: {str(e)}"))
                continue
        
        return stats_list

    def _find_player_simple(self, player_mapping, verbosity=1):
        """Find a Player object from the player mapping. Simple matching - uses fuzzy_find_player
        which already handles merge decisions. Does not create new players.
        """
        first_name = player_mapping.get('first_name', '').strip()
        last_name = player_mapping.get('last_name', '').strip()
        full_name = f"{first_name} {last_name}".strip()
        
        if not full_name:
            return None
        
        # Use fuzzy_find_player which handles duplicates and merge decisions
        player = fuzzy_find_player(full_name, debug=(verbosity >= 2), stdout=self.stdout)
        
        if not player:
            if verbosity >= 1:
                overslot_id = player_mapping.get('overslot_player_id', 'unknown')
                self.stdout.write(self.style.WARNING(
                    f"Could not find player '{full_name}' (643 ID: {overslot_id}) - skipping stats"
                ))
        
        return player

    def _process_player_stats(self, player, stats_data, dry_run=False):
        """Process stats data and create/update Player643StatSeason records."""
        created_count = 0
        updated_count = 0
        
        # Group stats by year and team_name to merge batting and pitching for same season
        stats_by_season = {}
        
        # Process batting stats
        batting_stats = stats_data.get('batting', [])
        for stat_record in batting_stats:
            season_year = stat_record.get('season_year', '')
            team_name = stat_record.get('team_name', '')
            
            # Skip "Career" records for now (or handle them separately if needed)
            if season_year == 'Career':
                continue
            
            key = (season_year, team_name or None)
            if key not in stats_by_season:
                stats_by_season[key] = {'batting': None, 'pitching': None}
            stats_by_season[key]['batting'] = stat_record
        
        # Process pitching stats
        pitching_stats = stats_data.get('pitching', [])
        for stat_record in pitching_stats:
            season_year = stat_record.get('season_year', '')
            team_name = stat_record.get('team_name', '')
            
            # Skip "Career" records for now
            if season_year == 'Career':
                continue
            
            key = (season_year, team_name or None)
            if key not in stats_by_season:
                stats_by_season[key] = {'batting': None, 'pitching': None}
            stats_by_season[key]['pitching'] = stat_record
        
        # Create/update records for each season
        for (year, team_name), stats in stats_by_season.items():
            stat_season, created = self._create_or_update_stat_season(
                player=player,
                year=year,
                team_name=team_name,
                batting_data=stats['batting'],
                pitching_data=stats['pitching'],
                dry_run=dry_run,
            )
            
            if created:
                created_count += 1
            else:
                updated_count += 1
        
        return created_count, updated_count

    def _create_or_update_stat_season(self, player, year, team_name, batting_data=None, pitching_data=None, dry_run=False):
        """Create or update a Player643StatSeason record."""
        # Normalize team_name (handle "---" as None)
        if team_name == '---' or not team_name:
            team_name = None
        
        # Try to get existing record
        try:
            stat_season = models.Player643StatSeason.objects.get(
                player=player,
                year=year,
                team_name=team_name,
            )
            created = False
        except models.Player643StatSeason.DoesNotExist:
            stat_season = models.Player643StatSeason(
                player=player,
                year=year,
                team_name=team_name,
            )
            created = True
        
        # Update hitting stats if provided
        if batting_data:
            stat_season.hit_at_bats = batting_data.get('at_bats')
            stat_season.hit_ba = batting_data.get('ba')
            stat_season.hit_babip = batting_data.get('babip')
            stat_season.hit_base_on_balls = batting_data.get('base_on_balls')
            stat_season.hit_caught_stealing = batting_data.get('caught_stealing')
            stat_season.hit_doubles = batting_data.get('doubles')
            stat_season.hit_games_played = batting_data.get('games_played')
            stat_season.hit_hit_by_pitch = batting_data.get('hit_by_pitch')
            stat_season.hit_hits = batting_data.get('hits')
            stat_season.hit_hrs = batting_data.get('hrs')
            stat_season.hit_iso = batting_data.get('iso')
            stat_season.hit_obp = batting_data.get('obp')
            stat_season.hit_ops = batting_data.get('ops')
            stat_season.hit_plate_appearances = batting_data.get('plate_appearances')
            stat_season.hit_runs = batting_data.get('runs')
            stat_season.hit_singles = batting_data.get('singles')
            stat_season.hit_slg = batting_data.get('slg')
            stat_season.hit_stolen_bases = batting_data.get('stolen_bases')
            stat_season.hit_strikeout_rate = batting_data.get('strikeout_rate')
            stat_season.hit_strikeouts = batting_data.get('strikeouts')
            stat_season.hit_triples = batting_data.get('triples')
            stat_season.hit_walk_rate = batting_data.get('walk_rate')
            stat_season.hit_walk_to_strikeout = batting_data.get('walk_to_strikeout')
            stat_season.hit_woba = batting_data.get('woba')
        
        # Update pitching stats if provided
        if pitching_data:
            stat_season.pitch_appearances = pitching_data.get('appearances')
            stat_season.pitch_ba = pitching_data.get('ba')
            stat_season.pitch_babip = pitching_data.get('babip')
            stat_season.pitch_base_on_balls = pitching_data.get('base_on_balls')
            stat_season.pitch_batters_faced = pitching_data.get('batters_faced')
            stat_season.pitch_fip = pitching_data.get('fip')
            stat_season.pitch_games_started = pitching_data.get('games_started')
            stat_season.pitch_hit_by_pitch = pitching_data.get('hit_by_pitch')
            stat_season.pitch_hits = pitching_data.get('hits')
            stat_season.pitch_innings_pitched = pitching_data.get('innings_pitched')
            stat_season.pitch_obp = pitching_data.get('obp')
            stat_season.pitch_ops = pitching_data.get('ops')
            stat_season.pitch_runs = pitching_data.get('runs')
            stat_season.pitch_siera = pitching_data.get('siera')
            stat_season.pitch_slg = pitching_data.get('slg')
            stat_season.pitch_strikeout_rate = pitching_data.get('strikeout_rate')
            stat_season.pitch_strikeouts = pitching_data.get('strikeouts')
            stat_season.pitch_walk_rate = pitching_data.get('walk_rate')
            stat_season.pitch_walk_to_strikeout = pitching_data.get('walk_to_strikeout')
            stat_season.pitch_whip = pitching_data.get('whip')
            stat_season.pitch_xfip = pitching_data.get('xfip')
        
        if not dry_run:
            stat_season.save()
        
        return stat_season, created
