"""
DEPRECATED: This command has been split into three separate loaders:
- load_college_hitters: Load college hitters data
- load_pitchers: Load pitchers data  
- load_hs_hitters: Load high school hitters data

This file is kept for backward compatibility but should not be used for new cron jobs.
Use the individual loaders instead for better maintenance and separate scheduling.
"""

import numpy as np
from django.core.management.base import BaseCommand, CommandError
from django.conf import settings
from django.db.models import Q
from thefuzz import fuzz
from nicknames import NickNamer

from overslot import models, utils


class Command(BaseCommand):
    help = 'Load Trackman data from Google Sheets (DEPRECATED - use load_college_hitters, load_pitchers, or load_hs_hitters instead)'

    def add_arguments(self, parser):
        parser.add_argument(
            '--group',
            choices=['all', 'hitters', 'pitchers'],
            default='all',
            help='Choose which group to load: hitters, pitchers, or all (default)'
        )
        parser.add_argument(
            '--debug',
            action='store_true',
            help='Enable verbose logging for player matching and saves'
        )

    def fix_blanks(self, row):
        for k,v in row.items():
            if v == "":
                row[k] = None
        return row

    def _fuzzy_find_player(self, name, debug=False):
        def normalize_name(n):
            n = n.lower().strip()
            for suffix in [' jr.', ' sr.', ' ii', ' iii', ' iv']:
                if n.endswith(suffix):
                    n = n[:-len(suffix)]
            return n

        def extract_first_names(full_name):
            """Extract first and middle names from a full name"""
            parts = full_name.split()
            if len(parts) <= 1:
                return [full_name] if parts else []
            # Return all parts except the last (assuming last is surname)
            return parts[:-1]

        normalized_input = normalize_name(name)
        input_parts = normalized_input.split()
        
        if not input_parts:
            return None

        # Initialize nickname handler
        nn = NickNamer()
        
        # Get all players to check against (prefer active records)
        all_players = models.Player.objects.filter(active=True)
        
        exact_matches = []
        nickname_matches = []
        fuzzy_matches = []
        best_fuzzy_score = -1
        best_fuzzy_player = None
        
        for player in all_players:
            normalized_player = normalize_name(player.name)
            player_parts = normalized_player.split()
            
            # 1. Try exact matching (normalized)
            if normalized_input == normalized_player:
                exact_matches.append(player)
                continue
            
            # 2. Try nickname/canonical name variations
            input_first_names = extract_first_names(normalized_input)
            player_first_names = extract_first_names(normalized_player)
            
            # Check if any first name matches through nickname relationships
            name_variations_match = False
            for input_name in input_first_names:
                for player_name in player_first_names:
                    # Check if input_name is a nickname of player_name
                    if input_name in nn.nicknames_of(player_name):
                        name_variations_match = True
                        break
                    # Check if player_name is a nickname of input_name  
                    if player_name in nn.nicknames_of(input_name):
                        name_variations_match = True
                        break
                    # Check if they share a canonical name
                    input_canonicals = nn.canonicals_of(input_name)
                    player_canonicals = nn.canonicals_of(player_name)
                    if input_canonicals and player_canonicals and input_canonicals & player_canonicals:
                        name_variations_match = True
                        break
                if name_variations_match:
                    break
            
            # If names match through nickname relationships, check if surname matches too
            if name_variations_match:
                # Check if surnames match (fuzzy matching for surnames)
                if len(input_parts) > 1 and len(player_parts) > 1:
                    input_surname = input_parts[-1]
                    player_surname = player_parts[-1]
                    surname_score = fuzz.ratio(input_surname, player_surname)
                    if surname_score >= 90:  # High threshold for surname matching
                        nickname_matches.append(player)
                        continue
                elif len(input_parts) == 1 or len(player_parts) == 1:
                    # If one of them only has one name, consider it a match
                    nickname_matches.append(player)
                    continue
            
            # 3. Fall back to fuzzy matching
            score = fuzz.ratio(normalized_input, normalized_player)
            if score > best_fuzzy_score:
                best_fuzzy_score = score
                best_fuzzy_player = player
            if score >= 95:
                fuzzy_matches.append(player)
        
        # Return the best match based on priority
        if len(exact_matches) == 1:
            if debug:
                self.stdout.write(f"[match] Exact: '{name}' -> '{exact_matches[0].name}' (pk={exact_matches[0].pk})")
            return exact_matches[0]
        elif len(exact_matches) > 1:
            # Multiple exact matches — attempt to resolve using merge decisions to find the primary
            try:
                merges = models.DuplicateDecision.objects.filter(
                    decision='merged',
                    primary_player__isnull=False
                ).filter(
                    Q(player1__in=exact_matches) | Q(player2__in=exact_matches)
                )
                primary_candidates = [m.primary_player for m in merges if m.primary_player in exact_matches]
                unique_primary_candidates = list({p.pk: p for p in primary_candidates}.values())
                if len(unique_primary_candidates) == 1:
                    primary = unique_primary_candidates[0]
                    if debug:
                        self.stdout.write(f"[match] Exact (resolved via merge): '{name}' -> '{primary.name}' (pk={primary.pk})")
                    return primary
            except Exception as e:
                if debug:
                    self.stdout.write(f"[match] Error resolving merges for '{name}': {e}")
        elif len(nickname_matches) == 1:
            if debug:
                self.stdout.write(f"[match] Nickname: '{name}' -> '{nickname_matches[0].name}' (pk={nickname_matches[0].pk})")
            return nickname_matches[0]
        elif len(fuzzy_matches) == 1:
            if debug:
                self.stdout.write(f"[match] Fuzzy: '{name}' -> '{fuzzy_matches[0].name}' (pk={fuzzy_matches[0].pk})")
            return fuzzy_matches[0]
        else:
            if debug:
                self.stdout.write(
                    f"[match] No unique match for '{name}'. exact={len(exact_matches)}, nickname={len(nickname_matches)}, "
                    f"fuzzy={len(fuzzy_matches)}; best_fuzzy={(best_fuzzy_player.name if best_fuzzy_player else None)}({best_fuzzy_score})"
                )
        
        return None

    def handle(self, *args, **options):
        """
        Here are the columns from the sheet for hitters.
        Name	Position	Team	Draft Year	Bats	Throws	Pitches	Swing%	Contact %	Chase%	EV 95+ %	Contact%v92+	Elevated FB Contact%	SliderMiss%	Contact% IZ	Contact% Out-Of-Zone	Average EV	90th Percentile EV	Max EV	Barrel%	xWOBA	Ground%	Fly Ball%	Pull AIR%	FBLD%
        What Joe wants:
            "Whiff %" -- (inverse of column I)
            "In-Zone Whiff %" -- (inverse of column O)
            "Out-of-Zone Whiff %" -- (inverse of column P)
            "Chase %" -- (Column J)
            "K %" -- (Column AB)
            "BB %" -- (Column AA)
            "Avg Exit Velocity" -- (Column Q)
            "90th % Exit Velocity" -- (Column R)
            "Barrel %" -- (Column T)
            "Pull AIR %" -- (Column X)
            "xWOBA" -- (Column U)
        """

        def _parse_value(val):
            if val is None:
                return None
            if isinstance(val, (int, float)):
                return float(val)
            if isinstance(val, str):
                val = val.strip()
                if not val:
                    return None
                try:
                    if val.endswith('%'):
                        return float(val.rstrip('%')) / 100.0
                    return float(val)
                except (ValueError, TypeError):
                    return None
            return None

        def _calculate_percentile_distribution(rows, column_name):
            """Calculate the percentile distribution for a column
            
            Returns the percentile thresholds that can be used to rank any value
            """
            values = []
            for row in rows:
                value = _parse_value(row.get(column_name))
                if value is not None:
                    values.append(value)
            
            if not values:
                return None
            
            # Calculate percentiles for this column (0th to 100th percentile)
            percentiles = np.percentile(values, np.arange(101))
            return percentiles
        
        def _get_percentile_rank(value, percentile_distribution, invert=False):
            """Get the percentile rank for a single value based on a percentile distribution"""
            if value is None or percentile_distribution is None:
                return None
            
            percentile_rank = np.interp(value, percentile_distribution, np.arange(101))
            percentile_value = percentile_rank / 100.0
            
            # Invert percentile for negative metrics (lower values = better performance)
            if invert:
                percentile_value = 1.0 - percentile_value
            
            return percentile_value

        def _calculate_weighted_percentile_score(row_percentiles, weights_info):
            """Calculate weighted average of percentiles"""
            score = 0
            total_weight = 0
            for weight_tuple in weights_info:
                # Handle both old format (col_name, weight) and new format (col_name, weight, invert)
                col_name = weight_tuple[0]
                weight = weight_tuple[1]
                
                percentile = row_percentiles.get(col_name)
                if percentile is not None:
                    score += percentile * weight
                    total_weight += weight
            if total_weight == 0:
                return None
            return score / total_weight

        # Load current and prior college seasons named like "{YEAR} Hitters"
        years = ['2025', '2024']
        all_tab_types = ["Hitters", "Fourseam", "Sinkers", "Sliders", "Sweepers", "Curveballs", "Changeups/Splitters"]

        group = options.get('group', 'all')
        if group == 'hitters':
            tab_types = ["Hitters"]
        elif group == 'pitchers':
            tab_types = ["Fourseam", "Sinkers", "Sliders", "Sweepers", "Curveballs", "Changeups/Splitters"]
        else:
            tab_types = all_tab_types

        debug = options.get('debug', False)

        for year in years:
            for tab_type in tab_types:
                # Handle Changeups/Splitters tab name
                if tab_type == "Changeups/Splitters":
                    tab_candidates = [f"{year} Changeups/Splitters"]
                else:
                    tab_candidates = [f"{year} {tab_type}"]
                
                sheet = None
                tab = None
                for candidate_tab in tab_candidates:
                    print(f"[load] Reading tab: {candidate_tab}")
                    try:
                        # Quote tab name if it contains spaces or special characters
                        if ' ' in candidate_tab or '/' in candidate_tab:
                            range_str = f"'{candidate_tab}'!A:Z"
                        else:
                            range_str = f"{candidate_tab}!A:Z"
                        # For hitters, use A:AB to capture K % column; for pitchers use A:Z
                        if tab_type == "Hitters":
                            range_str = range_str.replace('!A:Z', '!A:AB')
                        sheet = utils.get_sheet("1KJwXOxOKZvk50bP186klB_YXUdWVylJwEHvHUBorULA", range_str, value_cutoff=None)
                        if sheet:
                            tab = candidate_tab
                            break
                    except HttpError as e:
                        # 400 error means the sheet tab doesn't exist, try next candidate
                        if e.resp.status == 400:
                            print(f"Tab '{candidate_tab}' not found (400 error), trying next option...")
                            continue
                        else:
                            # Re-raise other HTTP errors
                            raise
                    except Exception as e:
                        print(f"Error reading tab '{candidate_tab}': {e}")
                        continue
                
                if sheet is None:
                    print(f"No sheet found for any of: {', '.join(tab_candidates)}")
                    continue
                
                # Use the found tab name for the rest of the processing
                if tab is None:
                    tab = tab_candidates[0]  # Fallback, though this shouldn't happen

                # Different minimum pitches for hitters vs pitchers
                min_pitches = 250 if tab_type == "Hitters" else 100
                total_sheet_rows = len(sheet)
                rows = [self.fix_blanks(row) for row in sheet if int(row.get('Pitches', 0)) >= min_pitches]
                if debug:
                    self.stdout.write(f"[load] Tab '{tab}': loaded {total_sheet_rows} rows; min_pitches={min_pitches}; processing {len(rows)} rows")

                if tab_type == "Hitters":
                    # Hitter processing logic
                    # Define metric weights for each composite score
                    # Format: (metric_name, weight, invert_percentile)
                    # invert_percentile=True for negative metrics where lower values are better
                    hitter_weights = [
                        ('Contact %', 0.40, False),           # POSITIVE
                        ('Contact% IZ', 0.25, False),         # POSITIVE
                        ('Contact% Out-Of-Zone', 0.15, False), # POSITIVE
                        ('SliderMiss%', 0.10, True),          # NEGATIVE (lower is better)
                        ('Elevated FB Contact%', 0.10, False), # POSITIVE
                    ]
                    
                    game_power_weights = [
                        ('90th Percentile EV', 0.33, False),  # POSITIVE
                        ('EV 95+ %', 0.33, False),            # POSITIVE
                        ('Pull AIR%', 0.33, False),           # POSITIVE
                    ]
                    
                    raw_power_weights = [
                        ('Average EV', 0.50, False),          # POSITIVE
                        ('90th Percentile EV', 0.50, False),  # POSITIVE
                    ]
                    
                    approach_weights = [
                        ('Chase%', 0.50, True),               # NEGATIVE (lower is better)
                        ('BB%', 0.50, False),               # POSITIVE
                    ]
                    
                    # Calculate individual percentiles for each metric using only high-volume players
                    all_metrics = {}  # metric_name -> invert_flag
                    for weights in [hitter_weights, game_power_weights, raw_power_weights, approach_weights]:
                        for metric, _, invert in weights:
                            all_metrics[metric] = invert
                    # Also include additional metrics we store
                    all_metrics['K %'] = True
                    all_metrics['Barrel%'] = False
                    all_metrics['xWOBA'] = False
                    
                    # Calculate percentile distributions using only high-volume players
                    metric_distributions = {}
                    for metric, should_invert in all_metrics.items():
                        distribution = _calculate_percentile_distribution(rows, metric)
                        metric_distributions[metric] = {
                            'distribution': distribution,
                            'invert': should_invert
                        }

                    # Build medians for points-above-median calculations (college metrics)
                    def _median_points_for_metric(metric_name_list):
                        values = []
                        for row in rows:
                            for metric_name in metric_name_list:
                                raw = _parse_value(row.get(metric_name))
                                if raw is None:
                                    continue
                                # Convert proportion to percentage points when appropriate
                                scaled = raw * 100.0 if raw <= 1.0 else raw
                                values.append(scaled)
                                break
                        if not values:
                            return None
                        return float(np.median(values))

                    k_col_for_sheet = 'K %' if any(r.get('K %') is not None for r in rows) else 'K%'

                    contact_median_pts = _median_points_for_metric(['Contact %'])
                    iz_contact_median_pts = _median_points_for_metric(['Contact% IZ'])
                    ooz_contact_median_pts = _median_points_for_metric(['Contact% Out-Of-Zone'])
                    chase_median_pts = _median_points_for_metric(['Chase%'])
                    bb_median_pts = _median_points_for_metric(['BB%'])
                    k_median_pts = _median_points_for_metric([k_col_for_sheet])
                    avg_ev_median = _median_points_for_metric(['Average EV'])
                    ev90_median = _median_points_for_metric(['90th Percentile EV'])
                    barrel_median_pts = _median_points_for_metric(['Barrel%'])
                    pull_air_median_pts = _median_points_for_metric(['Pull AIR%'])
                    xwoba_median = _median_points_for_metric(['xWOBA'])

                    # Process each row and calculate composite scores
                    total_rows = len(rows)
                    for original_index, row in enumerate(rows):
                        if debug and row.get('Name'):
                            self.stdout.write(f"[hitters] Matching '{row.get('Name')}'")
                        
                        # Calculate percentiles for this row using the high-volume distributions
                        row_percentiles = {}
                        for metric in all_metrics:
                            raw_value = _parse_value(row.get(metric))
                            distribution = metric_distributions[metric]['distribution']
                            should_invert = metric_distributions[metric]['invert']
                            percentile_result = _get_percentile_rank(raw_value, distribution, invert=should_invert)
                            row_percentiles[metric] = percentile_result
                        
                        # Calculate weighted composite scores
                        row['hitter_percentile'] = _calculate_weighted_percentile_score(row_percentiles, hitter_weights)
                        row['game_power_percentile'] = _calculate_weighted_percentile_score(row_percentiles, game_power_weights)
                        row['raw_power_percentile'] = _calculate_weighted_percentile_score(row_percentiles, raw_power_weights)
                        row['approach_percentile'] = _calculate_weighted_percentile_score(row_percentiles, approach_weights)
                        
                        # Derive and store requested hitter metrics (raw and percentiles)
                        # Helper for percent raw conversion (handles decimals vs percent values)
                        def pct_to_raw(val):
                            if val is None:
                                return None
                            return val * 100.0 if val <= 1.0 else val
                        
                        # Whiff % (inverse of Contact %) - percentile should reflect better = higher, so use Contact % percentile directly
                        contact = _parse_value(row.get('Contact %'))
                        row['whiff_pct'] = pct_to_raw(None if contact is None else (1.0 - contact))
                        row['whiff_pct_percentile'] = None if row_percentiles.get('Contact %') is None else row_percentiles['Contact %'] * 100.0
                        # points above median (percentage points)
                        row['whiff_pct_points_above_median'] = None
                        if row['whiff_pct'] is not None and contact_median_pts is not None:
                            whiff_median_pts = None if contact_median_pts is None else (100.0 - contact_median_pts)
                            if whiff_median_pts is not None:
                                row['whiff_pct_points_above_median'] = row['whiff_pct'] - whiff_median_pts
                        
                        # In-Zone Whiff % (inverse of Contact% IZ) - percentile mirrors Contact% IZ percentile
                        contact_iz = _parse_value(row.get('Contact% IZ'))
                        row['iz_whiff_pct'] = pct_to_raw(None if contact_iz is None else (1.0 - contact_iz))
                        row['iz_whiff_pct_percentile'] = None if row_percentiles.get('Contact% IZ') is None else row_percentiles['Contact% IZ'] * 100.0
                        row['iz_whiff_pct_points_above_median'] = None
                        if row['iz_whiff_pct'] is not None and iz_contact_median_pts is not None:
                            iz_whiff_median_pts = 100.0 - iz_contact_median_pts
                            row['iz_whiff_pct_points_above_median'] = row['iz_whiff_pct'] - iz_whiff_median_pts
                        
                        # Out-of-Zone Whiff % (inverse of Contact% Out-Of-Zone) - percentile mirrors Contact% Out-Of-Zone percentile
                        contact_ooz = _parse_value(row.get('Contact% Out-Of-Zone'))
                        row['ooz_whiff_pct'] = pct_to_raw(None if contact_ooz is None else (1.0 - contact_ooz))
                        row['ooz_whiff_pct_percentile'] = None if row_percentiles.get('Contact% Out-Of-Zone') is None else row_percentiles['Contact% Out-Of-Zone'] * 100.0
                        row['ooz_whiff_pct_points_above_median'] = None
                        if row['ooz_whiff_pct'] is not None and ooz_contact_median_pts is not None:
                            ooz_whiff_median_pts = 100.0 - ooz_contact_median_pts
                            row['ooz_whiff_pct_points_above_median'] = row['ooz_whiff_pct'] - ooz_whiff_median_pts
                        
                        # Chase % (lower is better - we already inverted percentiles in row_percentiles)
                        chase = _parse_value(row.get('Chase%'))
                        row['chase_pct'] = pct_to_raw(chase)
                        row['chase_pct_percentile'] = None if row_percentiles.get('Chase%') is None else row_percentiles['Chase%'] * 100.0
                        row['chase_pct_points_above_median'] = None if (row['chase_pct'] is None or chase_median_pts is None) else (row['chase_pct'] - chase_median_pts)
                        
                        # K % (lower is better) - handle header variants 'K %' and 'K%'
                        k_col = 'K %' if any(r.get('K %') is not None for r in rows) else 'K%'
                        k_rate = _parse_value(row.get(k_col))
                        # Ensure distribution exists for whichever column is present
                        if k_col not in metric_distributions:
                            metric_distributions[k_col] = {
                                'distribution': _calculate_percentile_distribution(rows, k_col),
                                'invert': True
                            }
                        k_distribution = metric_distributions.get(k_col, {}).get('distribution')
                        k_percentile = _get_percentile_rank(k_rate, k_distribution, invert=True) if k_distribution is not None else None
                        row['k_pct'] = pct_to_raw(k_rate)
                        row['k_pct_percentile'] = None if k_percentile is None else k_percentile * 100.0
                        row['k_pct_points_above_median'] = None if (row['k_pct'] is None or k_median_pts is None) else (row['k_pct'] - k_median_pts)
                        
                        # BB % (higher is better)
                        bb_rate = _parse_value(row.get('BB%'))
                        row['bb_pct'] = pct_to_raw(bb_rate)
                        row['bb_pct_percentile'] = None if row_percentiles.get('BB%') is None else row_percentiles['BB%'] * 100.0
                        row['bb_pct_points_above_median'] = None if (row['bb_pct'] is None or bb_median_pts is None) else (row['bb_pct'] - bb_median_pts)
                        
                        # Avg Exit Velocity (Q)
                        avg_ev = _parse_value(row.get('Average EV'))
                        row['avg_exit_velocity'] = avg_ev
                        row['avg_exit_velocity_percentile'] = None if row_percentiles.get('Average EV') is None else row_percentiles['Average EV'] * 100.0
                        row['avg_exit_velocity_points_above_median'] = None if (row['avg_exit_velocity'] is None or avg_ev_median is None) else (row['avg_exit_velocity'] - avg_ev_median)
                        
                        # 90th % Exit Velocity (R)
                        ev90 = _parse_value(row.get('90th Percentile EV'))
                        row['ev_90th'] = ev90
                        row['ev_90th_percentile'] = None if row_percentiles.get('90th Percentile EV') is None else row_percentiles['90th Percentile EV'] * 100.0
                        row['ev_90th_points_above_median'] = None if (row['ev_90th'] is None or ev90_median is None) else (row['ev_90th'] - ev90_median)
                        
                        # Barrel % (T)
                        barrel = _parse_value(row.get('Barrel%'))
                        row['barrel_pct'] = pct_to_raw(barrel)
                        row['barrel_pct_percentile'] = None if row_percentiles.get('Barrel%') is None else row_percentiles['Barrel%'] * 100.0
                        row['barrel_pct_points_above_median'] = None if (row['barrel_pct'] is None or barrel_median_pts is None) else (row['barrel_pct'] - barrel_median_pts)
                        
                        # Pull AIR % (X)
                        pull_air = _parse_value(row.get('Pull AIR%'))
                        row['pull_air_pct'] = pct_to_raw(pull_air)
                        row['pull_air_pct_percentile'] = None if row_percentiles.get('Pull AIR%') is None else row_percentiles['Pull AIR%'] * 100.0
                        row['pull_air_pct_points_above_median'] = None if (row['pull_air_pct'] is None or pull_air_median_pts is None) else (row['pull_air_pct'] - pull_air_median_pts)
                        
                        # xWOBA (U)
                        xwoba_val = _parse_value(row.get('xWOBA'))
                        row['xwoba'] = xwoba_val
                        row['xwoba_percentile'] = None if row_percentiles.get('xWOBA') is None else row_percentiles['xWOBA'] * 100.0
                        row['xwoba_points_above_median'] = None if (row['xwoba'] is None or xwoba_median is None) else (row['xwoba'] - xwoba_median)
                        
                        # Show progress
                        if (original_index + 1) % 10 == 0 or original_index == total_rows - 1:
                            progress = ((original_index + 1) / total_rows) * 100
                            print(f"Processing hitters: {progress:.1f}% complete ({original_index + 1}/{total_rows})")
                        
                        # For backward compatibility, also set the "score" fields (these are now the same as percentiles)
                        row['hitter_score'] = row['hitter_percentile']
                        row['game_power_score'] = row['game_power_percentile']
                        row['raw_power_score'] = row['raw_power_percentile']
                        row['approach_score'] = row['approach_percentile']

                        if row.get('Name'):
                            obj = self._fuzzy_find_player(row['Name'], debug=debug)
                        else:
                            obj = None

                        if obj:
                            # Upsert PlayerStatSeason (College)
                            season, _created = models.PlayerStatSeason.objects.get_or_create(
                                player=obj, year=str(year), level="College"
                            )
                            # Extract draft year and school from row data
                            draft_year = row.get('Draft Year')
                            if draft_year:
                                season.draft_year = str(draft_year).strip()
                            else:
                                # If blank, use the year from the tab name (e.g., "2025" from "2025 Hitters")
                                season.draft_year = str(year)
                            season.school = row.get('Team')  # Column C for college hitters
                            season.hitter_score = row['hitter_score']
                            season.game_power_score = row['game_power_score']
                            season.raw_power_score = row['raw_power_score']
                            season.approach_score = row['approach_score']
                            season.hitter_percentile = row['hitter_percentile']
                            season.game_power_percentile = row['game_power_percentile']
                            season.raw_power_percentile = row['raw_power_percentile']
                            season.approach_percentile = row['approach_percentile']

                            # Save requested hitter metrics
                            season.whiff_pct = row.get('whiff_pct')
                            season.whiff_pct_percentile = row.get('whiff_pct_percentile')
                            season.whiff_pct_points_above_median = row.get('whiff_pct_points_above_median')
                            season.iz_whiff_pct = row.get('iz_whiff_pct')
                            season.iz_whiff_pct_percentile = row.get('iz_whiff_pct_percentile')
                            season.iz_whiff_pct_points_above_median = row.get('iz_whiff_pct_points_above_median')
                            season.ooz_whiff_pct = row.get('ooz_whiff_pct')
                            season.ooz_whiff_pct_percentile = row.get('ooz_whiff_pct_percentile')
                            season.ooz_whiff_pct_points_above_median = row.get('ooz_whiff_pct_points_above_median')
                            season.chase_pct = row.get('chase_pct')
                            season.chase_pct_percentile = row.get('chase_pct_percentile')
                            season.chase_pct_points_above_median = row.get('chase_pct_points_above_median')
                            season.k_pct = row.get('k_pct')
                            season.k_pct_percentile = row.get('k_pct_percentile')
                            season.k_pct_points_above_median = row.get('k_pct_points_above_median')
                            season.bb_pct = row.get('bb_pct')
                            season.bb_pct_percentile = row.get('bb_pct_percentile')
                            season.bb_pct_points_above_median = row.get('bb_pct_points_above_median')
                            season.avg_exit_velocity = row.get('avg_exit_velocity')
                            season.avg_exit_velocity_percentile = row.get('avg_exit_velocity_percentile')
                            season.avg_exit_velocity_points_above_median = row.get('avg_exit_velocity_points_above_median')
                            season.ev_90th = row.get('ev_90th')
                            season.ev_90th_percentile = row.get('ev_90th_percentile')
                            season.ev_90th_points_above_median = row.get('ev_90th_points_above_median')
                            season.barrel_pct = row.get('barrel_pct')
                            season.barrel_pct_percentile = row.get('barrel_pct_percentile')
                            season.barrel_pct_points_above_median = row.get('barrel_pct_points_above_median')
                            season.pull_air_pct = row.get('pull_air_pct')
                            season.pull_air_pct_percentile = row.get('pull_air_pct_percentile')
                            season.pull_air_pct_points_above_median = row.get('pull_air_pct_points_above_median')
                            season.xwoba = row.get('xwoba')
                            season.xwoba_percentile = row.get('xwoba_percentile')
                            season.xwoba_points_above_median = row.get('xwoba_points_above_median')

                            season.confidence = 10
                            season.save()
                            if debug:
                                self.stdout.write(f"[hitters] Saved PlayerStatSeason {season.year} College for '{obj.name}'")
                        else:
                            if debug and row.get('Name'):
                                self.stdout.write(f"[hitters] No Player match for '{row.get('Name')}' — skipping updates")
                
                else:
                    # Pitcher processing logic
                    # Define weights for each pitch type based on documentation
                    if tab_type == "Curveballs":
                        # Special case: Curveballs use Contact% (inverse) instead of Whiff%
                        pitch_weights = [
                            ('Strike%', 0.15, False),     # POSITIVE 
                            ('Chase%', 0.35, False),      # POSITIVE
                            ('Contact%', 0.50, True),     # NEGATIVE (inverse - lower is better)
                        ]
                    else:
                        # All other pitch types use the same weights
                        pitch_weights = [
                            ('Strike%', 0.15, False),     # POSITIVE
                            ('Chase%', 0.35, False),      # POSITIVE
                            ('Whiff%', 0.50, False),      # POSITIVE
                        ]
                    
                    # Calculate individual percentiles for pitch metrics
                    all_metrics = {}  # metric_name -> invert_flag
                    for metric, _, invert in pitch_weights:
                        all_metrics[metric] = invert
                    
                    # Calculate percentile distributions using only high-volume players (100+ pitches)
                    metric_distributions = {}
                    for metric, should_invert in all_metrics.items():
                        distribution = _calculate_percentile_distribution(rows, metric)
                        metric_distributions[metric] = {
                            'distribution': distribution,
                            'invert': should_invert
                        }

                    # Process each row and calculate composite scores
                    total_rows = len(rows)
                    for original_index, row in enumerate(rows):
                        if debug and row.get('Name'):
                            self.stdout.write(f"[pitchers:{tab_type}] Matching '{row.get('Name')}'")
                        
                        # Calculate percentiles for this row using the high-volume distributions
                        row_percentiles = {}
                        for metric in all_metrics:
                            raw_value = _parse_value(row.get(metric))
                            distribution = metric_distributions[metric]['distribution']
                            should_invert = metric_distributions[metric]['invert']
                            percentile_result = _get_percentile_rank(raw_value, distribution, invert=should_invert)
                            row_percentiles[metric] = percentile_result
                        
                        # Calculate weighted composite score for this pitch type
                        pitch_percentile = _calculate_weighted_percentile_score(row_percentiles, pitch_weights)
                        
                        # Show progress
                        if (original_index + 1) % 10 == 0 or original_index == total_rows - 1:
                            progress = ((original_index + 1) / total_rows) * 100
                            print(f"Processing {tab_type.lower()}: {progress:.1f}% complete ({original_index + 1}/{total_rows})")
                        
                        # Extract break data (x,y coordinates)
                        vert_break = _parse_value(row.get('Induced Vertical Break'))
                        horiz_break = _parse_value(row.get('Horizontal Break'))
                        
                        # Store the composite score for this pitch type
                        if tab_type == "Fourseam":
                            row['fourseam_percentile'] = pitch_percentile
                            row['fourseam_score'] = pitch_percentile
                            row['fourseam_vert_break'] = vert_break
                            row['fourseam_horiz_break'] = horiz_break
                        elif tab_type == "Sinkers":
                            row['sinker_percentile'] = pitch_percentile
                            row['sinker_score'] = pitch_percentile
                            row['sinker_vert_break'] = vert_break
                            row['sinker_horiz_break'] = horiz_break
                        elif tab_type == "Sliders":
                            row['slider_percentile'] = pitch_percentile
                            row['slider_score'] = pitch_percentile
                            row['slider_vert_break'] = vert_break
                            row['slider_horiz_break'] = horiz_break
                        elif tab_type == "Sweepers":
                            row['sweeper_percentile'] = pitch_percentile
                            row['sweeper_score'] = pitch_percentile
                            row['sweeper_vert_break'] = vert_break
                            row['sweeper_horiz_break'] = horiz_break
                        elif tab_type == "Curveballs":
                            row['curveball_percentile'] = pitch_percentile
                            row['curveball_score'] = pitch_percentile
                            row['curveball_vert_break'] = vert_break
                            row['curveball_horiz_break'] = horiz_break
                        elif tab_type == "Changeups/Splitters":
                            row['changeup_percentile'] = pitch_percentile
                            row['changeup_score'] = pitch_percentile
                            row['changeup_vert_break'] = vert_break
                            row['changeup_horiz_break'] = horiz_break

                        if row.get('Name'):
                            obj = self._fuzzy_find_player(row['Name'], debug=debug)
                        else:
                            obj = None

                        if obj:
                            season, _created = models.PlayerStatSeason.objects.get_or_create(
                                player=obj, year=str(year), level="College"
                            )
                            # Extract draft year and school from row data
                            draft_year = row.get('Draft Year')
                            if draft_year:
                                season.draft_year = str(draft_year).strip()
                            else:
                                # If blank, use the year from the tab name (e.g., "2025" from "2025 Fourseam")
                                season.draft_year = str(year)
                            season.school = row.get('School')  # Column B for college pitchers
                            if tab_type == "Fourseam":
                                season.fourseam_percentile = row['fourseam_percentile']
                                season.fourseam_score = row['fourseam_score']
                                season.fourseam_vert_break = row.get('fourseam_vert_break')
                                season.fourseam_horiz_break = row.get('fourseam_horiz_break')
                            elif tab_type == "Sinkers":
                                season.sinker_percentile = row['sinker_percentile']
                                season.sinker_score = row['sinker_score']
                                season.sinker_vert_break = row.get('sinker_vert_break')
                                season.sinker_horiz_break = row.get('sinker_horiz_break')
                            elif tab_type == "Sliders":
                                season.slider_percentile = row['slider_percentile']
                                season.slider_score = row['slider_score']
                                season.slider_vert_break = row.get('slider_vert_break')
                                season.slider_horiz_break = row.get('slider_horiz_break')
                            elif tab_type == "Sweepers":
                                season.sweeper_percentile = row['sweeper_percentile']
                                season.sweeper_score = row['sweeper_score']
                                season.sweeper_vert_break = row.get('sweeper_vert_break')
                                season.sweeper_horiz_break = row.get('sweeper_horiz_break')
                            elif tab_type == "Curveballs":
                                season.curveball_percentile = row['curveball_percentile']
                                season.curveball_score = row['curveball_score']
                                season.curveball_vert_break = row.get('curveball_vert_break')
                                season.curveball_horiz_break = row.get('curveball_horiz_break')
                            elif tab_type == "Changeups/Splitters":
                                season.changeup_percentile = row['changeup_percentile']
                                season.changeup_score = row['changeup_score']
                                season.changeup_vert_break = row.get('changeup_vert_break')
                                season.changeup_horiz_break = row.get('changeup_horiz_break')

                            season.confidence = 10
                            season.save()
                            if debug:
                                self.stdout.write(f"[pitchers:{tab_type}] Saved PlayerStatSeason {season.year} College for '{obj.name}'")
                        else:
                            if debug and row.get('Name'):
                                self.stdout.write(f"[pitchers:{tab_type}] No Player match for '{row.get('Name')}' — skipping updates")
                
                print(f"Completed processing {total_rows} players for {tab}")

        # Additional processing for High School Hitters tabs (skip if only loading pitchers)
        if group != 'pitchers':
            # Supported patterns:
            #   "{DRAFT_YEAR} HS Hitters - {STATS_YEAR}"
            #   "{DRAFT_YEAR} HS Hitters {STATS_YEAR}"
            # The stat season should be STATS_YEAR.
            # Discover all HS Hitters tabs across the requested ranges.
            # Draft years: 2027-2023; Data years: 2025-2022; constraint: draft > data.
            draft_years = [str(y) for y in range(2027, 2022, -1)]
            data_years = [str(y) for y in range(2025, 2021, -1)]
            hs_tabs = []
            for draft_year in draft_years:
                for stats_year in data_years:
                    if int(draft_year) > int(stats_year):
                        # Only support dash-separated naming pattern created by editor
                        hs_tabs.append(f"{draft_year} HS Hitters - {stats_year}")
            # De-duplicate while preserving order
            seen = set()
            hs_tabs = [t for t in hs_tabs if not (t in seen or seen.add(t))]

            for hs_tab in hs_tabs:
                sheet = None
                try:
                    print(f"[load] Reading tab: {hs_tab}")
                    sheet = utils.get_sheet("1KJwXOxOKZvk50bP186klB_YXUdWVylJwEHvHUBorULA", f"{hs_tab}!A:AZ", value_cutoff=None)
                except Exception as e:
                    print(e)

                if sheet is None:
                    print(f"No sheet found for {hs_tab}")
                    continue

                rows = [self.fix_blanks(row) for row in sheet]
                debug = options.get('debug', False)

                # Helpers
                def pct_or_number(val):
                    v = _parse_value(val)
                    if v is None:
                        return None
                    # If value seems like a proportion (0-1), scale to percent space for deltas
                    return v * 100.0 if 0.0 <= v <= 1.0 else v

                def collect_values(rows, keys):
                    collected = []
                    for r in rows:
                        for k in keys:
                            if k in r and r.get(k) is not None:
                                parsed = pct_or_number(r.get(k))
                                if parsed is not None:
                                    collected.append(parsed)
                                break
                    return collected

                def row_value(row, keys):
                    for k in keys:
                        if k in row and row.get(k) is not None:
                            return pct_or_number(row.get(k))
                    return None

                # Raw numeric (no percent scaling) — for BA/OBP/SLG/OPS/ISO actuals
                def row_value_raw(row, keys):
                    for k in keys:
                        if k in row and row.get(k) is not None:
                            return _parse_value(row.get(k))
                    return None

                # Define metric mappings: ([possible header names], invert_percentile, percentile_field, points_delta_field)
                metric_map = [
                (["Contact%", "Contact %"], False, "hs_contact_pct_percentile", "hs_contact_pct_points_above_median"),
                (["Chase%", "Chase %"], True, "hs_chase_pct_percentile", "hs_chase_pct_points_above_median"),
                (["IZ Contact%", "Contact% IZ", "In-Zone Contact%"], False, "hs_iz_contact_pct_percentile", "hs_iz_contact_pct_points_above_median"),
                (["OOZ Contact%", "Contact% Out-Of-Zone", "Out-Of-Zone Contact%"], False, "hs_ooz_contact_pct_percentile", "hs_ooz_contact_pct_points_above_median"),
                (["K%", "K %"], True, "hs_k_pct_percentile", "hs_k_pct_points_above_median"),
                (["GB%", "Ground%", "GB %"], True, "hs_gb_pct_percentile", "hs_gb_pct_points_above_median"),
                (["FB%", "Fly Ball%", "FB %"], False, "hs_fb_pct_percentile", "hs_fb_pct_points_above_median"),
                (["Air PULL%", "Pull AIR%", "Air Pull%"], False, "hs_air_pull_pct_percentile", "hs_air_pull_pct_points_above_median"),
                (["PG 60 Yard", "60 Yard", "60 yd", "PG 60yd"], True, "hs_sprint_speed_percentile", "hs_sprint_speed_points_above_median"),
                (["Bat Speed"], False, "hs_bat_speed_percentile", "hs_bat_speed_points_above_median"),
                (["Avg Rot. Acc.", "Average Rot. Acc.", "Avg Rot Acc"], False, "hs_avg_rot_acc_percentile", "hs_avg_rot_acc_points_above_median"),
                (["Peak Hand Speed", "Peak HandSpeed"], False, "hs_peak_hand_speed_percentile", "hs_peak_hand_speed_points_above_median"),
                (["Peak Power"], False, "hs_force_plate_explosiveness_percentile", "hs_force_plate_explosiveness_points_above_median"),
                ]

                # Build distributions and medians
                distributions = {}
                medians = {}
                for keys, invert, _, _ in metric_map:
                    values = collect_values(rows, keys)
                    if values:
                        distributions[tuple(keys)] = {
                            'distribution': np.percentile(values, np.arange(101)),
                            'invert': invert,
                        }
                        medians[tuple(keys)] = float(np.median(values))
                    else:
                        distributions[tuple(keys)] = {'distribution': None, 'invert': invert}
                        medians[tuple(keys)] = None

                # Actual stat columns for HS hitters
                actual_map = {
                    'hs_pa': ["PA"],
                    'hs_ba': ["BA"],
                    'hs_obp': ["OBP"],
                    'hs_slg': ["SLG"],
                    'hs_ops': ["OPS"],
                    'hs_iso': ["ISO"],
                }

                total_rows = len(rows)
                for idx, row in enumerate(rows):
                    # Find player
                    obj = self._fuzzy_find_player(row.get('Name') or row.get('Player') or row.get('Player Name') or "", debug=debug)
                    if not obj:
                        if debug and (row.get('Name') or row.get('Player') or row.get('Player Name')):
                            self.stdout.write(f"[hs_hitters] No Player match for '{row.get('Name') or row.get('Player') or row.get('Player Name')}' — skipping updates")
                        continue
                    # infer stats year from tab label after the dash if present, else fallback to first token
                    stats_year = None
                    draft_year = None
                    if " - " in hs_tab:
                        try:
                            parts = hs_tab.split(" - ", 1)
                            draft_year = parts[0].split()[0].strip()  # First token is draft year (e.g., "2027" from "2027 HS Hitters")
                            stats_year = parts[1].strip()
                        except Exception:
                            stats_year = None
                    if not stats_year:
                        # Fallback: last token
                        stats_year = hs_tab.split()[-1]
                    if not draft_year:
                        # Fallback: first token
                        draft_year = hs_tab.split()[0].strip()
                    if debug:
                        self.stdout.write(f"[hs_hitters] Saving PlayerStatSeason for '{obj.name}' year={stats_year} draft_year={draft_year}")

                    # Prepare computed values for this row
                    computed = {}
                    for keys, _, percentile_field, delta_field in metric_map:
                        dist = distributions.get(tuple(keys), {}).get('distribution')
                        invert = distributions.get(tuple(keys), {}).get('invert')
                        median_val = medians.get(tuple(keys))
                        raw_val = row_value(row, keys)
                        if raw_val is not None and dist is not None:
                            prc = _get_percentile_rank(raw_val if (not (keys == ["PG 60 Yard", "60 Yard", "60 yd", "PG 60yd"])) else raw_val, dist, invert=invert)
                            computed[percentile_field] = None if prc is None else prc * 100.0
                        else:
                            computed[percentile_field] = None
                        computed[delta_field] = None if (raw_val is None or median_val is None) else (raw_val - median_val)

                    # Actuals
                    for field_name, keys in actual_map.items():
                        # Keep actual statline values as decimals (e.g., 0.247).
                        # If sheet provides percent-style numbers (e.g., 24.7), normalize to decimal.
                        val = row_value_raw(row, keys)
                        # Never normalize PA; it is a raw count
                        # For SLG and OPS, values may legitimately exceed 1.000 — do not scale.
                        # Only normalize BA/OBP/ISO if someone entered percent-style numbers.
                        if field_name in ('hs_ba', 'hs_obp', 'hs_iso') and val is not None and val > 1.0:
                            val = val / 100.0
                        computed[field_name] = val

                    # Save onto PlayerStatSeason for this player/year at High School level
                    season, _created = models.PlayerStatSeason.objects.get_or_create(
                        player=obj, year=str(stats_year), level="High School"
                    )
                    # Extract draft year and school
                    if draft_year:
                        season.draft_year = str(draft_year).strip()
                    season.school = row.get('School')  # Column C for high school hitters
                    # Actuals
                    season.hs_pa = computed.get('hs_pa')
                    season.hs_ba = computed.get('hs_ba')
                    season.hs_obp = computed.get('hs_obp')
                    season.hs_slg = computed.get('hs_slg')
                    season.hs_ops = computed.get('hs_ops')
                    season.hs_iso = computed.get('hs_iso')

                    # Percentiles and above-median deltas
                    season.hs_contact_pct_percentile = computed.get('hs_contact_pct_percentile')
                    season.hs_contact_pct_points_above_median = computed.get('hs_contact_pct_points_above_median')
                    season.hs_chase_pct_percentile = computed.get('hs_chase_pct_percentile')
                    season.hs_chase_pct_points_above_median = computed.get('hs_chase_pct_points_above_median')
                    season.hs_iz_contact_pct_percentile = computed.get('hs_iz_contact_pct_percentile')
                    season.hs_iz_contact_pct_points_above_median = computed.get('hs_iz_contact_pct_points_above_median')
                    season.hs_ooz_contact_pct_percentile = computed.get('hs_ooz_contact_pct_percentile')
                    season.hs_ooz_contact_pct_points_above_median = computed.get('hs_ooz_contact_pct_points_above_median')
                    season.hs_k_pct_percentile = computed.get('hs_k_pct_percentile')
                    season.hs_k_pct_points_above_median = computed.get('hs_k_pct_points_above_median')
                    season.hs_gb_pct_percentile = computed.get('hs_gb_pct_percentile')
                    season.hs_gb_pct_points_above_median = computed.get('hs_gb_pct_points_above_median')
                    season.hs_fb_pct_percentile = computed.get('hs_fb_pct_percentile')
                    season.hs_fb_pct_points_above_median = computed.get('hs_fb_pct_points_above_median')
                    season.hs_air_pull_pct_percentile = computed.get('hs_air_pull_pct_percentile')
                    season.hs_air_pull_pct_points_above_median = computed.get('hs_air_pull_pct_points_above_median')
                    season.hs_sprint_speed_percentile = computed.get('hs_sprint_speed_percentile')
                    season.hs_sprint_speed_points_above_median = computed.get('hs_sprint_speed_points_above_median')
                    season.hs_bat_speed_percentile = computed.get('hs_bat_speed_percentile')
                    season.hs_bat_speed_points_above_median = computed.get('hs_bat_speed_points_above_median')
                    season.hs_avg_rot_acc_percentile = computed.get('hs_avg_rot_acc_percentile')
                    season.hs_avg_rot_acc_points_above_median = computed.get('hs_avg_rot_acc_points_above_median')
                    season.hs_peak_hand_speed_percentile = computed.get('hs_peak_hand_speed_percentile')
                    season.hs_peak_hand_speed_points_above_median = computed.get('hs_peak_hand_speed_points_above_median')
                    season.hs_force_plate_explosiveness_percentile = computed.get('hs_force_plate_explosiveness_percentile')
                    season.hs_force_plate_explosiveness_points_above_median = computed.get('hs_force_plate_explosiveness_points_above_median')

                    season.confidence = 10
                    season.save()
                    if debug:
                        self.stdout.write(f"[hs_hitters] Saved PlayerStatSeason {season.year} High School for '{obj.name}' from '{hs_tab}'")
