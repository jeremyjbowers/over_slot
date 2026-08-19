from django.core.management.base import BaseCommand
from googleapiclient.errors import HttpError
import json
import os
from django.conf import settings

from overslot import utils


def _movement_stats(data):
    if not data:
        return {'count': 0, 'horiz_min': None, 'horiz_max': None, 'vert_min': None, 'vert_max': None}
    horiz_breaks = [d['horiz_break'] for d in data]
    vert_breaks = [d['vert_break'] for d in data]
    return {
        'count': len(data),
        'horiz_min': min(horiz_breaks),
        'horiz_max': max(horiz_breaks),
        'vert_min': min(vert_breaks),
        'vert_max': max(vert_breaks),
    }


def _split_movement_by_handedness(rows):
    movement_data_lh = []
    movement_data_rh = []
    for row in rows:
        vert_break = utils.parse_value(row.get('Induced Vertical Break'))
        horiz_break = utils.parse_value(row.get('Horizontal Break'))
        handedness = str(row.get('Handedness') or '').strip().upper()
        if vert_break is None or horiz_break is None:
            continue
        movement_point = {
            'vert_break': vert_break,
            'horiz_break': horiz_break,
        }
        if handedness == 'L':
            movement_data_lh.append(movement_point)
        elif handedness == 'R':
            movement_data_rh.append(movement_point)
        else:
            movement_data_lh.append(movement_point)
            movement_data_rh.append(movement_point)
    return movement_data_lh, movement_data_rh


class Command(BaseCommand):
    help = (
        'Generate JSON files with movement plot data for all pitchers by pitch type and year. '
        'Upload outputs to Spaces prefix pitch-shapes/ (served at PITCH_SHAPES_BASE_URL). '
        'College files: {year}_{lh|rh}_{pitch}.json. '
        'HS files: {year}_hs_{lh|rh}_{pitch}.json.'
    )

    def add_arguments(self, parser):
        parser.add_argument(
            '--output-dir',
            type=str,
            default=None,
            help='Output directory for JSON files (defaults to static directory)',
        )
        parser.add_argument(
            '--level',
            choices=['all', 'college', 'hs'],
            default='all',
            help='Which pitch-shape universes to generate (default: all)',
        )

    def handle(self, *args, **options):
        output_dir = options.get('output_dir')
        if output_dir is None:
            project_root = os.path.dirname(settings.BASE_DIR)
            output_dir = os.path.join(project_root, 'static')
        os.makedirs(output_dir, exist_ok=True)

        level = options.get('level') or 'all'
        if level in ('all', 'college'):
            self._generate_college(output_dir)
        if level in ('all', 'hs'):
            self._generate_hs(output_dir)

        self.stdout.write(self.style.SUCCESS("Completed generating all pitch movement data files"))

    def _write_handedness_files(self, output_dir, year, filename_base, movement_lh, movement_rh, hs=False):
        prefix = f"{year}_hs_" if hs else f"{year}_"
        for hand, data in (('lh', movement_lh), ('rh', movement_rh)):
            filename = f"{prefix}{hand}_{filename_base}.json"
            filepath = os.path.join(output_dir, filename)
            with open(filepath, 'w') as f:
                json.dump(data, f, indent=2)
            stats = _movement_stats(data)
            if stats['count']:
                self.stdout.write(
                    self.style.SUCCESS(
                        f"Generated {filepath}: {stats['count']} data points "
                        f"(horiz: {stats['horiz_min']:.1f} to {stats['horiz_max']:.1f}, "
                        f"vert: {stats['vert_min']:.1f} to {stats['vert_max']:.1f})"
                    )
                )
            else:
                self.stdout.write(self.style.WARNING(f"Generated {filepath}: 0 data points"))

    def _read_tab(self, tab_name):
        self.stdout.write(f"[generate] Reading tab: {tab_name}")
        try:
            sheet = utils.get_sheet(
                utils.TRACKMAN_SHEET_ID,
                utils.sheet_tab_a1_range(tab_name, "A:Z"),
                value_cutoff=None,
            )
            return sheet
        except HttpError as e:
            if e.resp.status == 400:
                self.stdout.write(f"[generate] Tab '{tab_name}' not found (400 error)")
                return None
            raise
        except Exception as e:
            self.stdout.write(self.style.WARNING(f"[generate] Error reading tab '{tab_name}': {e}"))
            return None

    def _generate_college(self, output_dir):
        years = ['2026', '2025', '2024']
        tab_types = ["Fourseam", "Sinkers", "Sliders", "Sweepers", "Curveballs", "Changeups/Splitters", "Cutters"]
        tab_type_to_filename = {
            "Fourseam": "fourseam",
            "Sinkers": "sinkers",
            "Sliders": "sliders",
            "Sweepers": "sweepers",
            "Curveballs": "curveballs",
            "Changeups/Splitters": "changeup_splitters",
            "Cutters": "cutters",
        }

        for year in years:
            for tab_type in tab_types:
                tab_candidates = (
                    [f"{year} Changeups/Splitters"]
                    if tab_type == "Changeups/Splitters"
                    else [f"{year} {tab_type}"]
                )
                sheet = None
                for candidate_tab in tab_candidates:
                    sheet = self._read_tab(candidate_tab)
                    if sheet:
                        break
                if sheet is None:
                    self.stdout.write(
                        self.style.WARNING(f"No sheet found for any of: {', '.join(tab_candidates)}")
                    )
                    continue
                rows = [utils.fix_blanks(row) for row in sheet]
                movement_lh, movement_rh = _split_movement_by_handedness(rows)
                self._write_handedness_files(
                    output_dir, year, tab_type_to_filename[tab_type], movement_lh, movement_rh, hs=False
                )

    def _generate_hs(self, output_dir):
        try:
            titles = utils.list_spreadsheet_sheet_titles(utils.TRACKMAN_SHEET_ID)
        except Exception as e:
            self.stdout.write(self.style.WARNING(f"[generate] Could not list HS pitcher tabs: {e}"))
            return

        tabs = utils.discover_hs_pitcher_tabs(titles)
        if not tabs:
            self.stdout.write(self.style.WARNING("No HS pitcher tabs found."))
            return

        for tab, year, pitch_key, tab_type in tabs:
            sheet = self._read_tab(tab)
            if not sheet:
                continue
            filename_base = utils.HS_PITCH_SHAPE_FILENAMES.get(pitch_key)
            if not filename_base:
                self.stdout.write(self.style.WARNING(f"[generate] No HS filename mapping for {tab_type}"))
                continue
            rows = [utils.fix_blanks(row) for row in sheet]
            movement_lh, movement_rh = _split_movement_by_handedness(rows)
            self._write_handedness_files(
                output_dir, year, filename_base, movement_lh, movement_rh, hs=True
            )
