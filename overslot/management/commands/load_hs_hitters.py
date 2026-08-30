import numpy as np
from django.core.management.base import BaseCommand
from googleapiclient.errors import HttpError

from overslot import models, utils


def hs_hitter_tabs():
    """Tab titles to try: "{DRAFT_YEAR} HS Hitters - {STATS_YEAR}" where draft > stats."""
    # Draft years: 2028-2023; Data years: 2026-2022; constraint: draft > data.
    draft_years = [str(y) for y in range(2028, 2022, -1)]
    data_years = [str(y) for y in range(2026, 2021, -1)]
    tabs = []
    seen = set()
    for draft_year in draft_years:
        for stats_year in data_years:
            if int(draft_year) > int(stats_year):
                title = f"{draft_year} HS Hitters - {stats_year}"
                if title not in seen:
                    seen.add(title)
                    tabs.append(title)
    return tabs


class Command(BaseCommand):
    help = 'Load High School Hitters Trackman data from Google Sheets'

    def add_arguments(self, parser):
        parser.add_argument(
            '--debug',
            action='store_true',
            help='Enable verbose logging for player matching and saves'
        )

    def handle(self, *args, **options):
        """
        Load high school hitters data from sheets named like "{DRAFT_YEAR} HS Hitters - {STATS_YEAR}"
        """
        debug = options.get('debug', False)
        hs_tabs = hs_hitter_tabs()

        for hs_tab in hs_tabs:
            sheet = None
            try:
                print(f"[load] Reading tab: {hs_tab}")
                sheet = utils.get_sheet("1KJwXOxOKZvk50bP186klB_YXUdWVylJwEHvHUBorULA", f"{hs_tab}!A:AZ", value_cutoff=None)
            except HttpError as e:
                # 400 error means the sheet tab doesn't exist
                if e.resp.status == 400:
                    if debug:
                        self.stdout.write(f"[load] Tab '{hs_tab}' not found (400 error)")
                    print(f"No sheet found for {hs_tab}")
                    continue
                else:
                    # Re-raise other HTTP errors
                    raise
            except Exception as e:
                print(e)
                continue

            if sheet is None:
                print(f"No sheet found for {hs_tab}")
                continue

            rows = [utils.fix_blanks(row) for row in sheet]

            # Helpers
            RAW_METRIC_HEADERS = {"RSI"}

            def pct_or_number(val, header=None):
                v = utils.parse_value(val)
                if v is None:
                    return None
                # RSI is a raw athletic index (often 0.5–3); never treat it as a proportion.
                if header in RAW_METRIC_HEADERS:
                    return v
                # If value seems like a proportion (0-1), scale to percent space for deltas
                return v * 100.0 if 0.0 <= v <= 1.0 else v

            def collect_values(rows, keys):
                collected = []
                for r in rows:
                    for k in keys:
                        if k in r and r.get(k) is not None:
                            parsed = pct_or_number(r.get(k), header=k)
                            if parsed is not None:
                                collected.append(parsed)
                            break
                return collected

            def row_value(row, keys):
                for k in keys:
                    if k in row and row.get(k) is not None:
                        return pct_or_number(row.get(k), header=k)
                return None

            # Raw numeric (no percent scaling) — for BA/OBP/SLG/OPS/ISO actuals
            def row_value_raw(row, keys):
                for k in keys:
                    if k in row and row.get(k) is not None:
                        return utils.parse_value(row.get(k))
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
                (["RSI"], False, "hs_twitch_percentile", "hs_twitch_points_above_median"),
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
                obj = utils.fuzzy_find_player(row.get('Name') or row.get('Player') or row.get('Player Name') or "", debug=debug, stdout=self.stdout)
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
                        prc = utils.get_percentile_rank(raw_val if (not (keys == ["PG 60 Yard", "60 Yard", "60 yd", "PG 60yd"])) else raw_val, dist, invert=invert)
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
                season.hs_twitch_percentile = computed.get('hs_twitch_percentile')
                season.hs_twitch_points_above_median = computed.get('hs_twitch_points_above_median')

                season.confidence = 10
                season.save()
                if debug:
                    self.stdout.write(f"[hs_hitters] Saved PlayerStatSeason {season.year} High School for '{obj.name}' from '{hs_tab}'")
