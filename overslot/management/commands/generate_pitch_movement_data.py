from django.core.management.base import BaseCommand
from googleapiclient.errors import HttpError
import json
import os
from django.conf import settings

from overslot import utils


class Command(BaseCommand):
    help = 'Generate JSON files with movement plot data for all pitchers by pitch type and year'

    def add_arguments(self, parser):
        parser.add_argument(
            '--output-dir',
            type=str,
            default=None,
            help='Output directory for JSON files (defaults to static directory)'
        )

    def handle(self, *args, **options):
        """
        Generate JSON files with movement plot data for all pitchers.
        Files are named like: {year}_{pitchtype}.json
        """
        years = ['2025', '2024']
        tab_types = ["Fourseam", "Sinkers", "Sliders", "Sweepers", "Curveballs", "Changeups/Splitters", "Cutters"]
        
        # Map tab types to file-safe names
        pitch_type_to_filename = {
            "Fourseam": "fourseam",
            "Sinkers": "sinkers",
            "Sliders": "sliders",
            "Sweepers": "sweepers",
            "Curveballs": "curveballs",
            "Changeups/Splitters": "changeup_splitters",
            "Cutters": "cutters"
        }
        
        # Determine output directory
        output_dir = options.get('output_dir')
        if output_dir is None:
            # Default to static directory (BASE_DIR is config/, so go up one level to project root)
            project_root = os.path.dirname(settings.BASE_DIR)
            output_dir = os.path.join(project_root, 'static')
        
        # Ensure output directory exists
        os.makedirs(output_dir, exist_ok=True)
        
        sheet_id = "1KJwXOxOKZvk50bP186klB_YXUdWVylJwEHvHUBorULA"
        
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
                    self.stdout.write(f"[generate] Reading tab: {candidate_tab}")
                    try:
                        # Quote tab name if it contains spaces or special characters
                        if ' ' in candidate_tab or '/' in candidate_tab:
                            range_str = f"'{candidate_tab}'!A:Z"
                        else:
                            range_str = f"{candidate_tab}!A:Z"
                        sheet = utils.get_sheet(sheet_id, range_str, value_cutoff=None)
                        if sheet:
                            tab = candidate_tab
                            break
                    except HttpError as e:
                        # 400 error means the sheet tab doesn't exist, try next candidate
                        if e.resp.status == 400:
                            self.stdout.write(f"[generate] Tab '{candidate_tab}' not found (400 error), trying next option...")
                            continue
                        else:
                            # Re-raise other HTTP errors
                            raise
                    except Exception as e:
                        self.stdout.write(self.style.WARNING(f"[generate] Error reading tab '{candidate_tab}': {e}"))
                        continue
                
                if sheet is None:
                    self.stdout.write(self.style.WARNING(f"No sheet found for any of: {', '.join(tab_candidates)}"))
                    continue
                
                # Process all rows (no minimum pitch filter for universe data)
                rows = [utils.fix_blanks(row) for row in sheet]
                total_rows = len(rows)
                
                # Group movement data by handedness (L/R)
                movement_data_lh = []
                movement_data_rh = []
                
                for row in rows:
                    vert_break = utils.parse_value(row.get('Induced Vertical Break'))
                    horiz_break = utils.parse_value(row.get('Horizontal Break'))
                    handedness_raw = row.get('Handedness') or ''
                    handedness = str(handedness_raw).strip().upper() if handedness_raw else ''
                    
                    # Only include rows with valid movement data
                    if vert_break is not None and horiz_break is not None:
                        movement_point = {
                            'vert_break': vert_break,
                            'horiz_break': horiz_break
                        }
                        
                        # Group by handedness (R or L)
                        if handedness == 'L':
                            movement_data_lh.append(movement_point)
                        elif handedness == 'R':
                            movement_data_rh.append(movement_point)
                        else:
                            # If handedness is unclear, include in both (fallback)
                            movement_data_lh.append(movement_point)
                            movement_data_rh.append(movement_point)
                
                # Generate filenames for both handedness
                filename_base = pitch_type_to_filename[tab_type]
                
                # Calculate stats for debugging
                def get_stats(data):
                    if not data:
                        return {'count': 0, 'horiz_min': None, 'horiz_max': None, 'vert_min': None, 'vert_max': None}
                    horiz_breaks = [d['horiz_break'] for d in data]
                    vert_breaks = [d['vert_break'] for d in data]
                    return {
                        'count': len(data),
                        'horiz_min': min(horiz_breaks),
                        'horiz_max': max(horiz_breaks),
                        'vert_min': min(vert_breaks),
                        'vert_max': max(vert_breaks)
                    }
                
                stats_lh = get_stats(movement_data_lh)
                stats_rh = get_stats(movement_data_rh)
                
                # Left-handed pitchers
                filename_lh = f"{year}_lh_{filename_base}.json"
                filepath_lh = os.path.join(output_dir, filename_lh)
                with open(filepath_lh, 'w') as f:
                    json.dump(movement_data_lh, f, indent=2)
                self.stdout.write(
                    self.style.SUCCESS(
                        f"Generated {filepath_lh}: {stats_lh['count']} data points "
                        f"(horiz: {stats_lh['horiz_min']:.1f} to {stats_lh['horiz_max']:.1f}, "
                        f"vert: {stats_lh['vert_min']:.1f} to {stats_lh['vert_max']:.1f})"
                    )
                )
                
                # Right-handed pitchers
                filename_rh = f"{year}_rh_{filename_base}.json"
                filepath_rh = os.path.join(output_dir, filename_rh)
                with open(filepath_rh, 'w') as f:
                    json.dump(movement_data_rh, f, indent=2)
                self.stdout.write(
                    self.style.SUCCESS(
                        f"Generated {filepath_rh}: {stats_rh['count']} data points "
                        f"(horiz: {stats_rh['horiz_min']:.1f} to {stats_rh['horiz_max']:.1f}, "
                        f"vert: {stats_rh['vert_min']:.1f} to {stats_rh['vert_max']:.1f})"
                    )
                )
        
        self.stdout.write(self.style.SUCCESS("Completed generating all pitch movement data files"))
