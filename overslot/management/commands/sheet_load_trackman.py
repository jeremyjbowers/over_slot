import numpy as np
from django.core.management.base import BaseCommand, CommandError
from django.conf import settings
from thefuzz import fuzz

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
            n = n.lower()
            for suffix in [' jr.', ' sr.', ' ii', ' iii', ' iv']:
                if n.endswith(suffix):
                    n = n[:-len(suffix)]
            return n

        normalized_input = normalize_name(name)
        
        # Basic filtering to reduce candidate pool
        candidates = models.Player.objects.filter(name__icontains=normalized_input.split()[-1])
        
        high_confidence_matches = []
        for player in candidates:
            normalized_candidate = normalize_name(player.name)
            score = fuzz.ratio(normalized_input, normalized_candidate)
            if score >= 95:
                high_confidence_matches.append(player)
        
        if len(high_confidence_matches) == 1:
            return high_confidence_matches[0]
        
        return None

    def handle(self, *args, **options):
        """
        Four scores are calculated:
        Hitter Percentile
        Game Power Percentile
        Raw Power Percentile
        Approach Percentile

        Each score is a weighted average of the following columns and then a percentile is calculated from the distribution of all scores.

        Hitter Percentile
            40% Contact % (column I)
            25% Contact% IZ (column O)
            15% Contact% Out-of-Zone (Column P)
            10% SliderMiss% (Column N)
            10% Elevated FB Contact% (Column M)

        Game Power Percentile
            33% 90th Percentile EV (Column R)
            33% EV 95+ % (Column K)
            33% Pull AIR% (Column X)

        Raw Power Percentile
            50% Average EV (Column Q)
            50% 90th Percentile EV (Column R)

        Approach Percentile
            50% Chase% (Column J)
            50% Walk% (Column AA)
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

        def _calculate_weighted_score(row, weights_info):
            score = 0
            total_weight = 0
            for col_name, weight in weights_info:
                value = _parse_value(row.get(col_name))
                if value is not None:
                    score += value * weight
                    total_weight += weight
            if total_weight == 0:
                return None
            return score / total_weight

        def _calculate_percentiles(scores):
            valid_scores = [s for s in scores if s is not None]
            if not valid_scores:
                return [None] * len(scores)
            
            percentiles = np.percentile(valid_scores, np.arange(101))
            
            results = []
            for score in scores:
                if score is None:
                    results.append(None)
                    continue
                
                percentile_rank = np.interp(score, percentiles, np.arange(101))
                results.append(percentile_rank / 100.0)
            return results

        def create_hitter_percentile(row):
            weights = [
                ('Contact %', 0.40),
                ('Contact% IZ', 0.25),
                ('Contact% Out-of-Zone', 0.15),
                ('SliderMiss%', 0.10),
                ('Elevated FB Contact%', 0.10),
            ]
            return _calculate_weighted_score(row, weights)

        def create_game_power_percentile(row):
            weights = [
                ('90th Percentile EV', 0.33),
                ('EV 95+ %', 0.33),
                ('Pull AIR%', 0.33),
            ]
            return _calculate_weighted_score(row, weights)

        def create_raw_power_percentile(row):
            weights = [
                ('Average EV', 0.50),
                ('90th Percentile EV', 0.50),
            ]
            return _calculate_weighted_score(row, weights)

        def create_approach_percentile(row):
            weights = [
                ('Chase%', 0.50),
                ('Walk%', 0.50),
            ]
            return _calculate_weighted_score(row, weights)

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

                rows = [self.fix_blanks(row) for row in sheet]

                # Calculate raw scores
                hitter_scores = [create_hitter_percentile(row) for row in rows]
                game_power_scores = [create_game_power_percentile(row) for row in rows]
                raw_power_scores = [create_raw_power_percentile(row) for row in rows]
                approach_scores = [create_approach_percentile(row) for row in rows]
                
                # Calculate percentiles
                hitter_percentiles = _calculate_percentiles(hitter_scores)
                game_power_percentiles = _calculate_percentiles(game_power_scores)
                raw_power_percentiles = _calculate_percentiles(raw_power_scores)
                approach_percentiles = _calculate_percentiles(approach_scores)

                for i, row in enumerate([r for r in rows if int(r['Pitches']) > 74]):
                    row['hitter_score'] = hitter_scores[i]
                    row['game_power_score'] = game_power_scores[i]
                    row['raw_power_score'] = raw_power_scores[i]
                    row['approach_score'] = approach_scores[i]
                    row['hitter_percentile'] = hitter_percentiles[i]
                    row['game_power_percentile'] = game_power_percentiles[i]
                    row['raw_power_percentile'] = raw_power_percentiles[i]
                    row['approach_percentile'] = approach_percentiles[i]

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

                            pr.confidence = None

                            if int(row['Pitches']) > 400:
                                pr.confidence = 10
                            elif int(row['Pitches']) > 250:
                                pr.confidence = 5                                  

                            if pr.confidence is None:
                                pr.confidence = 0

                            print(pr)
                            pr.save()
