import numpy as np
from django.core.management.base import BaseCommand
from googleapiclient.errors import HttpError

from overslot import models, utils


_COLLEGE_HITTER_TRACKMAN_FIELDS = (
    "hitter_percentile",
    "game_power_percentile",
    "raw_power_percentile",
    "approach_percentile",
    "hitter_score",
    "game_power_score",
    "raw_power_score",
    "approach_score",
    "whiff_pct",
    "whiff_pct_percentile",
    "whiff_pct_points_above_median",
    "iz_whiff_pct",
    "iz_whiff_pct_percentile",
    "iz_whiff_pct_points_above_median",
    "ooz_whiff_pct",
    "ooz_whiff_pct_percentile",
    "ooz_whiff_pct_points_above_median",
    "chase_pct",
    "chase_pct_percentile",
    "chase_pct_points_above_median",
    "k_pct",
    "k_pct_percentile",
    "k_pct_points_above_median",
    "bb_pct",
    "bb_pct_percentile",
    "bb_pct_points_above_median",
    "avg_exit_velocity",
    "avg_exit_velocity_percentile",
    "avg_exit_velocity_points_above_median",
    "ev_90th",
    "ev_90th_percentile",
    "ev_90th_points_above_median",
    "barrel_pct",
    "barrel_pct_percentile",
    "barrel_pct_points_above_median",
    "pull_air_pct",
    "pull_air_pct_percentile",
    "pull_air_pct_points_above_median",
    "xwoba",
    "xwoba_percentile",
    "xwoba_points_above_median",
)


def _clear_college_hitter_trackman_fields(season):
    """Clear college hitter TrackMan columns only (pitcher & HS fields unchanged)."""
    for name in _COLLEGE_HITTER_TRACKMAN_FIELDS:
        setattr(season, name, None)
    season.save()


class Command(BaseCommand):
    help = 'Load College Hitters Trackman data from Google Sheets'

    def add_arguments(self, parser):
        parser.add_argument(
            '--debug',
            action='store_true',
            help='Enable verbose logging for player matching and saves'
        )

    def handle(self, *args, **options):
        """
        Load college hitters data from sheets named like "{YEAR} Hitters" (e.g. 2026 Hitters).
        """
        debug = options.get('debug', False)
        years = ['2026', '2025', '2024']
        tab_type = "Hitters"

        for year in years:
            tab = f"{year} {tab_type}"

            sheet = None
            print(f"[load] Reading tab: {tab}")

            try:
                # Include AB to capture K % column as requested
                sheet = utils.get_sheet("1KJwXOxOKZvk50bP186klB_YXUdWVylJwEHvHUBorULA", f"{tab}!A:AB", value_cutoff=None)
            except HttpError as e:
                # 400 error means the sheet tab doesn't exist
                if e.resp.status == 400:
                    if debug:
                        self.stdout.write(f"[load] Tab '{tab}' not found (400 error)")
                    print(f"No sheet found for {tab}")
                    continue
                else:
                    # Re-raise other HTTP errors
                    raise
            except Exception as e:
                print(e)
                continue

            if sheet is None:
                print(f"No sheet found for {tab}")
                continue

            # 2026: higher minimum stabilizes contact-rate-driven percentiles and visuals (Statcast-style charts).
            min_pitches = 300 if year == "2026" else 250
            total_sheet_rows = len(sheet)
            rows = [utils.fix_blanks(row) for row in sheet if int(row.get('Pitches', 0)) >= min_pitches]
            if debug:
                self.stdout.write(f"[load] Tab '{tab}': loaded {total_sheet_rows} rows; min_pitches={min_pitches}; processing {len(rows)} rows")

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
                distribution = utils.calculate_percentile_distribution(rows, metric)
                metric_distributions[metric] = {
                    'distribution': distribution,
                    'invert': should_invert
                }

            # Build medians for points-above-median calculations (college metrics)
            def median_points_for_metric(metric_name_list):
                values = []
                for row in rows:
                    for metric_name in metric_name_list:
                        raw = utils.parse_value(row.get(metric_name))
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

            contact_median_pts = median_points_for_metric(['Contact %'])
            iz_contact_median_pts = median_points_for_metric(['Contact% IZ'])
            ooz_contact_median_pts = median_points_for_metric(['Contact% Out-Of-Zone'])
            chase_median_pts = median_points_for_metric(['Chase%'])
            bb_median_pts = median_points_for_metric(['BB%'])
            k_median_pts = median_points_for_metric([k_col_for_sheet])
            avg_ev_median = median_points_for_metric(['Average EV'])
            ev90_median = median_points_for_metric(['90th Percentile EV'])
            barrel_median_pts = median_points_for_metric(['Barrel%'])
            pull_air_median_pts = median_points_for_metric(['Pull AIR%'])
            xwoba_median = median_points_for_metric(['xWOBA'])

            # Process each row and calculate composite scores
            total_rows = len(rows)
            for original_index, row in enumerate(rows):
                if debug and row.get('Name'):
                    self.stdout.write(f"[hitters] Matching '{row.get('Name')}'")
                
                # Calculate percentiles for this row using the high-volume distributions
                row_percentiles = {}
                for metric in all_metrics:
                    raw_value = utils.parse_value(row.get(metric))
                    distribution = metric_distributions[metric]['distribution']
                    should_invert = metric_distributions[metric]['invert']
                    percentile_result = utils.get_percentile_rank(raw_value, distribution, invert=should_invert)
                    row_percentiles[metric] = percentile_result
                
                # Calculate weighted composite scores
                row['hitter_percentile'] = utils.calculate_weighted_percentile_score(row_percentiles, hitter_weights)
                row['game_power_percentile'] = utils.calculate_weighted_percentile_score(row_percentiles, game_power_weights)
                row['raw_power_percentile'] = utils.calculate_weighted_percentile_score(row_percentiles, raw_power_weights)
                row['approach_percentile'] = utils.calculate_weighted_percentile_score(row_percentiles, approach_weights)
                
                # Derive and store requested hitter metrics (raw and percentiles)
                # Helper for percent raw conversion (handles decimals vs percent values)
                def pct_to_raw(val):
                    if val is None:
                        return None
                    return val * 100.0 if val <= 1.0 else val
                
                # Whiff % (inverse of Contact %) - percentile should reflect better = higher, so use Contact % percentile directly
                contact = utils.parse_value(row.get('Contact %'))
                row['whiff_pct'] = pct_to_raw(None if contact is None else (1.0 - contact))
                row['whiff_pct_percentile'] = None if row_percentiles.get('Contact %') is None else row_percentiles['Contact %'] * 100.0
                # points above median (percentage points)
                row['whiff_pct_points_above_median'] = None
                if row['whiff_pct'] is not None and contact_median_pts is not None:
                    whiff_median_pts = None if contact_median_pts is None else (100.0 - contact_median_pts)
                    if whiff_median_pts is not None:
                        row['whiff_pct_points_above_median'] = row['whiff_pct'] - whiff_median_pts
                
                # In-Zone Whiff % (inverse of Contact% IZ) - percentile mirrors Contact% IZ percentile
                contact_iz = utils.parse_value(row.get('Contact% IZ'))
                row['iz_whiff_pct'] = pct_to_raw(None if contact_iz is None else (1.0 - contact_iz))
                row['iz_whiff_pct_percentile'] = None if row_percentiles.get('Contact% IZ') is None else row_percentiles['Contact% IZ'] * 100.0
                row['iz_whiff_pct_points_above_median'] = None
                if row['iz_whiff_pct'] is not None and iz_contact_median_pts is not None:
                    iz_whiff_median_pts = 100.0 - iz_contact_median_pts
                    row['iz_whiff_pct_points_above_median'] = row['iz_whiff_pct'] - iz_whiff_median_pts
                
                # Out-of-Zone Whiff % (inverse of Contact% Out-Of-Zone) - percentile mirrors Contact% Out-Of-Zone percentile
                contact_ooz = utils.parse_value(row.get('Contact% Out-Of-Zone'))
                row['ooz_whiff_pct'] = pct_to_raw(None if contact_ooz is None else (1.0 - contact_ooz))
                row['ooz_whiff_pct_percentile'] = None if row_percentiles.get('Contact% Out-Of-Zone') is None else row_percentiles['Contact% Out-Of-Zone'] * 100.0
                row['ooz_whiff_pct_points_above_median'] = None
                if row['ooz_whiff_pct'] is not None and ooz_contact_median_pts is not None:
                    ooz_whiff_median_pts = 100.0 - ooz_contact_median_pts
                    row['ooz_whiff_pct_points_above_median'] = row['ooz_whiff_pct'] - ooz_whiff_median_pts
                
                # Chase % (lower is better - we already inverted percentiles in row_percentiles)
                chase = utils.parse_value(row.get('Chase%'))
                row['chase_pct'] = pct_to_raw(chase)
                row['chase_pct_percentile'] = None if row_percentiles.get('Chase%') is None else row_percentiles['Chase%'] * 100.0
                row['chase_pct_points_above_median'] = None if (row['chase_pct'] is None or chase_median_pts is None) else (row['chase_pct'] - chase_median_pts)
                
                # K % (lower is better) - handle header variants 'K %' and 'K%'
                k_col = 'K %' if any(r.get('K %') is not None for r in rows) else 'K%'
                k_rate = utils.parse_value(row.get(k_col))
                # Ensure distribution exists for whichever column is present
                if k_col not in metric_distributions:
                    metric_distributions[k_col] = {
                        'distribution': utils.calculate_percentile_distribution(rows, k_col),
                        'invert': True
                    }
                k_distribution = metric_distributions.get(k_col, {}).get('distribution')
                k_percentile = utils.get_percentile_rank(k_rate, k_distribution, invert=True) if k_distribution is not None else None
                row['k_pct'] = pct_to_raw(k_rate)
                row['k_pct_percentile'] = None if k_percentile is None else k_percentile * 100.0
                row['k_pct_points_above_median'] = None if (row['k_pct'] is None or k_median_pts is None) else (row['k_pct'] - k_median_pts)
                
                # BB % (higher is better)
                bb_rate = utils.parse_value(row.get('BB%'))
                row['bb_pct'] = pct_to_raw(bb_rate)
                row['bb_pct_percentile'] = None if row_percentiles.get('BB%') is None else row_percentiles['BB%'] * 100.0
                row['bb_pct_points_above_median'] = None if (row['bb_pct'] is None or bb_median_pts is None) else (row['bb_pct'] - bb_median_pts)
                
                # Avg Exit Velocity (Q)
                avg_ev = utils.parse_value(row.get('Average EV'))
                row['avg_exit_velocity'] = avg_ev
                row['avg_exit_velocity_percentile'] = None if row_percentiles.get('Average EV') is None else row_percentiles['Average EV'] * 100.0
                row['avg_exit_velocity_points_above_median'] = None if (row['avg_exit_velocity'] is None or avg_ev_median is None) else (row['avg_exit_velocity'] - avg_ev_median)
                
                # 90th % Exit Velocity (R)
                ev90 = utils.parse_value(row.get('90th Percentile EV'))
                row['ev_90th'] = ev90
                row['ev_90th_percentile'] = None if row_percentiles.get('90th Percentile EV') is None else row_percentiles['90th Percentile EV'] * 100.0
                row['ev_90th_points_above_median'] = None if (row['ev_90th'] is None or ev90_median is None) else (row['ev_90th'] - ev90_median)
                
                # Barrel % (T)
                barrel = utils.parse_value(row.get('Barrel%'))
                row['barrel_pct'] = pct_to_raw(barrel)
                row['barrel_pct_percentile'] = None if row_percentiles.get('Barrel%') is None else row_percentiles['Barrel%'] * 100.0
                row['barrel_pct_points_above_median'] = None if (row['barrel_pct'] is None or barrel_median_pts is None) else (row['barrel_pct'] - barrel_median_pts)
                
                # Pull AIR % (X)
                pull_air = utils.parse_value(row.get('Pull AIR%'))
                row['pull_air_pct'] = pct_to_raw(pull_air)
                row['pull_air_pct_percentile'] = None if row_percentiles.get('Pull AIR%') is None else row_percentiles['Pull AIR%'] * 100.0
                row['pull_air_pct_points_above_median'] = None if (row['pull_air_pct'] is None or pull_air_median_pts is None) else (row['pull_air_pct'] - pull_air_median_pts)
                
                # xWOBA (U)
                xwoba_val = utils.parse_value(row.get('xWOBA'))
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
                    obj = utils.resolve_college_stat_player(
                        row['Name'], year, debug=debug, stdout=self.stdout
                    )
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

            # Remove college hitter TrackMan data when sheet row is below min_pitches (avoids stale visuals after thresholds move).
            for sheet_row in [utils.fix_blanks(r) for r in sheet]:
                try:
                    p_seen = int(sheet_row.get("Pitches", 0))
                except (TypeError, ValueError):
                    continue
                if p_seen >= min_pitches:
                    continue
                name = sheet_row.get("Name")
                if not name:
                    continue
                obj = utils.fuzzy_find_player(name, debug=debug, stdout=self.stdout)
                if not obj:
                    continue
                season = models.PlayerStatSeason.objects.filter(
                    player=obj, year=str(year), level="College"
                ).first()
                if season and any(getattr(season, f) is not None for f in _COLLEGE_HITTER_TRACKMAN_FIELDS):
                    _clear_college_hitter_trackman_fields(season)
                    if debug:
                        self.stdout.write(
                            f"[hitters] Cleared college hitter TrackMan metrics for '{obj.name}' "
                            f"({year}, pitches={p_seen} < {min_pitches})"
                        )

            print(f"Completed processing {total_rows} players for {tab}")
