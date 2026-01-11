from django.core.management.base import BaseCommand
from googleapiclient.errors import HttpError

from overslot import models, utils


class Command(BaseCommand):
    help = 'Load College Pitchers Trackman data from Google Sheets'

    def add_arguments(self, parser):
        parser.add_argument(
            '--debug',
            action='store_true',
            help='Enable verbose logging for player matching and saves'
        )
        parser.add_argument(
            '--tab',
            type=str,
            default=None,
            help='Load a specific tab name (e.g., "2025 Fourseam" or "2024 Changeups/Splitters"). If not specified, loads all tabs.'
        )

    def handle(self, *args, **options):
        """
        Load college pitchers data from sheets named like "{YEAR} {PITCH_TYPE}"
        Pitch types: Fourseam, Sinkers, Sliders, Sweepers, Curveballs, Changeups/Splitters
        """
        debug = options.get('debug', False)
        specific_tab = options.get('tab')
        
        # If a specific tab is requested, load only that tab
        if specific_tab:
            # Determine year and tab_type from the tab name for processing
            import re
            match = re.match(r'(\d{4})\s+(.+)', specific_tab)
            if match:
                year = match.group(1)
                tab_type_raw = match.group(2).strip()
                # Map to internal tab_type
                if 'Changeup' in tab_type_raw or 'Splitter' in tab_type_raw:
                    tab_type = "Changeups/Splitters"
                else:
                    tab_type = tab_type_raw.split()[0] if tab_type_raw.split() else tab_type_raw
            else:
                self.stdout.write(self.style.ERROR(f"Could not parse tab name '{specific_tab}'. Expected format: '2025 Fourseam' or '2024 Changeups/Splitters'"))
                return
            
            # Process just this one tab
            years = [year]
            tab_types = [tab_type]
        else:
            years = ['2025', '2024']
            tab_types = ["Fourseam", "Sinkers", "Sliders", "Sweepers", "Curveballs", "Changeups/Splitters"]

        for year in years:
            for tab_type in tab_types:
                # Handle Changeups/Splitters tab name
                if specific_tab:
                    # Use the exact tab name provided
                    tab_candidates = [specific_tab]
                elif tab_type == "Changeups/Splitters":
                    tab_candidates = [f"{year} Changeups/Splitters"]
                else:
                    tab_candidates = [f"{year} {tab_type}"]

                sheet = None
                tab = None
                for candidate_tab in tab_candidates:
                    print(f"[load] Reading tab: {candidate_tab}")
                    try:
                        sheet = utils.get_sheet("1KJwXOxOKZvk50bP186klB_YXUdWVylJwEHvHUBorULA", f"{candidate_tab}!A:Z", value_cutoff=None)
                        if sheet:
                            tab = candidate_tab
                            break
                    except HttpError as e:
                        # 400 error means the sheet tab doesn't exist, try next candidate
                        if e.resp.status == 400:
                            if debug:
                                self.stdout.write(f"[load] Tab '{candidate_tab}' not found (400 error), trying next option...")
                            continue
                        else:
                            # Re-raise other HTTP errors
                            raise
                    except Exception as e:
                        print(e)
                        continue

                if sheet is None:
                    print(f"No sheet found for any of: {', '.join(tab_candidates)}")
                    continue

                min_pitches = 5
                total_sheet_rows = len(sheet)
                rows = [utils.fix_blanks(row) for row in sheet if int(row.get('Pitches', 0)) >= min_pitches]
                if debug:
                    self.stdout.write(f"[load] Tab '{tab}': loaded {total_sheet_rows} rows; min_pitches={min_pitches}; processing {len(rows)} rows")

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
                    distribution = utils.calculate_percentile_distribution(rows, metric)
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
                        raw_value = utils.parse_value(row.get(metric))
                        distribution = metric_distributions[metric]['distribution']
                        should_invert = metric_distributions[metric]['invert']
                        percentile_result = utils.get_percentile_rank(raw_value, distribution, invert=should_invert)
                        row_percentiles[metric] = percentile_result
                    
                    # Calculate weighted composite score for this pitch type
                    pitch_percentile = utils.calculate_weighted_percentile_score(row_percentiles, pitch_weights)
                    
                    # Show progress
                    if (original_index + 1) % 10 == 0 or original_index == total_rows - 1:
                        progress = ((original_index + 1) / total_rows) * 100
                        print(f"Processing {tab_type.lower()}: {progress:.1f}% complete ({original_index + 1}/{total_rows})")
                    
                    # Extract break data (x,y coordinates)
                    vert_break = utils.parse_value(row.get('Induced Vertical Break'))
                    horiz_break = utils.parse_value(row.get('Horizontal Break'))
                    
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
                        obj = utils.fuzzy_find_player(row['Name'], debug=debug, stdout=self.stdout)
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
