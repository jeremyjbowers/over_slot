import numpy as np
from django.core.management.base import BaseCommand, CommandError
from django.conf import settings
from thefuzz import fuzz
from nicknames import NickNamer

from overslot import models, utils


class Command(BaseCommand):
    help = 'Load Trackman data from Google Sheets'

    def fix_blanks(self, row):
        for k,v in row.items():
            if v == "":
                row[k] = None
        return row

    def _fuzzy_find_player(self, name):
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
        
        # Get all players to check against
        all_players = models.Player.objects.all()
        
        exact_matches = []
        nickname_matches = []
        fuzzy_matches = []
        
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
            if score >= 95:
                fuzzy_matches.append(player)
        
        # Return the best match based on priority
        if len(exact_matches) == 1:
            return exact_matches[0]
        elif len(nickname_matches) == 1:
            return nickname_matches[0]
        elif len(fuzzy_matches) == 1:
            return fuzzy_matches[0]
        
        return None

    def handle(self, *args, **options):
        """
        Four scores are calculated:
        Hitter Percentile
        Game Power Percentile
        Raw Power Percentile
        Approach Percentile

        Each score is calculated by first determining percentiles for individual metrics across all players, 
        then taking a weighted average of those percentiles.

        Hitter Percentile
            40% Contact % (column I) POSITIVE
            25% Contact% IZ (column O) POSITIVE
            15% Contact% Out-of-Zone (Column P) POSITIVE
            10% SliderMiss% (Column N) NEGATIVE
            10% Elevated FB Contact% (Column M) POSITIVE

        Game Power Percentile
            33% 90th Percentile EV (Column R) POSITIVE
            33% EV 95+ % (Column K) POSITIVE
            33% Pull AIR% (Column X) POSITIVE

        Raw Power Percentile
            50% Average EV (Column Q) POSITIVE
            50% 90th Percentile EV (Column R) POSITIVE

        Approach Percentile
            50% Chase% (Column J) NEGATIVE
            50% Walk% (Column AA) POSITIVE
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

        years = ['2025']
        tab_types = ["Hitters"]

        for year in years:
            for tab_type in tab_types:
                tab = f"{year} {tab_type}"

                sheet = None

                try:
                    sheet = utils.get_sheet("1KJwXOxOKZvk50bP186klB_YXUdWVylJwEHvHUBorULA", f"{tab}!A:AA", value_cutoff=None)
                except Exception as e:
                    print(e)

                if sheet is None:
                    print(f"No sheet found for {tab}")
                    continue

                rows = [self.fix_blanks(row) for row in sheet if int(row.get('Pitches', 0)) >= 250]

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
                
                # Calculate percentile distributions using only high-volume players (250+ pitches)
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
                    
                    # Show progress
                    if (original_index + 1) % 10 == 0 or original_index == total_rows - 1:
                        progress = ((original_index + 1) / total_rows) * 100
                        print(f"Processing players: {progress:.1f}% complete ({original_index + 1}/{total_rows})")
                    
                    # For backward compatibility, also set the "score" fields (these are now the same as percentiles)
                    row['hitter_score'] = row['hitter_percentile']
                    row['game_power_score'] = row['game_power_percentile']
                    row['raw_power_score'] = row['raw_power_percentile']
                    row['approach_score'] = row['approach_percentile']

                    if row.get('Name'):
                        obj = self._fuzzy_find_player(row['Name'])

                    if obj:
                        prs = models.PlayerRanking.objects.filter(player=obj)
                        for pr in prs:
                            pr.hitter_score = row['hitter_score']
                            pr.game_power_score = row['game_power_score']
                            pr.raw_power_score = row['raw_power_score']
                            pr.approach_score = row['approach_score']
                            pr.hitter_percentile = row['hitter_percentile']
                            pr.game_power_percentile = row['game_power_percentile']
                            pr.raw_power_percentile = row['raw_power_percentile']
                            pr.approach_percentile = row['approach_percentile']

                            pr.confidence = 10
                            pr.save()
                
                print(f"Completed processing {total_rows} players for {tab}")
