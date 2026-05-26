import re

from django.core.management.base import BaseCommand, CommandError
from django.db.models import Q

from overslot import models, utils

# Mock draft source spreadsheet (tabs named like "2026 Mock 1.0", "2026 Mock 2.0", …).
MOCK_DRAFT_SPREADSHEET_ID = "1n91_DpIkNKncmTpRWgnCdVrEF_eVjA_NTGZJUYSKqbU"

# Tab titles: "<YEAR> Mock <NUMBER>" — YEAR is the draft year; NUMBER is a release label (e.g. 1.0, 2.0).
_MOCK_TAB_TITLE_RE = re.compile(r"^(\d{4})\s+mock\s+(.+)$", re.IGNORECASE)


def _parse_mock_tab_title(tab_title):
    """
    If tab_title matches "<YEAR> Mock <VERSION>", return (year, version) with whitespace trimmed.
    Otherwise return None.
    """
    if not tab_title or not isinstance(tab_title, str):
        return None
    normalized = " ".join(tab_title.split())
    m = _MOCK_TAB_TITLE_RE.match(normalized)
    if not m:
        return None
    year, version = m.group(1), (m.group(2) or "").strip()
    if not version:
        return None
    return year, version


def _mock_version_sort_key(version):
    """Sort key so numeric releases (1.0, 2.0) order before non-numeric labels like Final."""
    v = (version or "").strip()
    if v.lower() == "final":
        return (2, 0.0, v.lower())
    try:
        return (0, float(v), v.lower())
    except (TypeError, ValueError):
        return (1, 0.0, v.lower())


class Command(BaseCommand):
    help = (
        "Load mock drafts from the Google Sheet: each tab named like "
        '"2026 Mock 1.0" becomes one Ranking (unique by draft year + version). '
        "With no arguments, all matching tabs are discovered and imported. "
        "Re-running updates the same mock for the same tab."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            '--clear',
            action='store_true',
            help='Clear all existing players, rankings, and player rankings before loading (DESTRUCTIVE)',
        )
        parser.add_argument(
            '--year',
            type=str,
            help='Draft year to load (e.g. 2026). Must be used with --mock-version.',
        )
        parser.add_argument(
            '--mock-version',
            dest='mock_version',
            type=str,
            help='Mock release label from the tab (e.g. 1.0 or 2.0). Must be used with --year.',
        )
        parser.add_argument(
            'tab',
            nargs='?',
            help='Only load one tab by title (e.g. "2026 Mock 1.0"). Must match a sheet tab name.',
        )

    def handle(self, *args, **options):
        # Only delete if explicitly requested
        if options['clear']:
            self.stdout.write(self.style.WARNING('DESTRUCTIVE MODE: Clearing existing MOCK DRAFT data...'))
            models.PlayerRanking.objects.filter(ranking__is_mock_draft=True).delete()
            models.Ranking.objects.filter(is_mock_draft=True).delete()
            self.stdout.write(self.style.SUCCESS('Cleared existing mock draft data'))
        else:
            self.stdout.write('Running in non-destructive mode. Use --clear to delete existing data.')

        def get_primary_player(player):
            """
            Check if this player has been merged into another player.
            If so, return the primary player. Otherwise, return the original player.
            """
            # Check if this player was merged into another (it would be inactive)
            if not player.active:
                # Look for a merge decision where this player was the secondary
                merge_decision = models.DuplicateDecision.objects.filter(
                    decision='merged',
                    primary_player__isnull=False
                ).filter(
                    Q(player1=player) | Q(player2=player)
                ).exclude(
                    primary_player=player  # Don't match if this player was the primary
                ).first()
                
                if merge_decision and merge_decision.primary_player.active:
                    print(f"  → Player {player.name} was merged into {merge_decision.primary_player.name}")
                    return merge_decision.primary_player
            
            return player
        
        def get_primary_team(team):
            """
            Check if this team has been merged into another team.
            If so, return the primary team. Otherwise, return the original team.
            """
            # Check if this team was merged into another (it would be inactive)
            if not team.active:
                # Look for a merge decision where this team was the secondary
                merge_decision = models.TeamDuplicateDecision.objects.filter(
                    decision='merged',
                    primary_team__isnull=False
                ).filter(
                    Q(team1=team) | Q(team2=team)
                ).exclude(
                    primary_team=team  # Don't match if this team was the primary
                ).first()
                
                if merge_decision and merge_decision.primary_team.active:
                    print(f"  → Team {team.name} was merged into {merge_decision.primary_team.name}")
                    return merge_decision.primary_team
            
            return team
        
        def get_or_create_team_with_merge_check(school_name):
            """
            Get or create a team by name, and return the primary team if it has been merged.
            """
            team, created = models.Team.objects.get_or_create(
                name=school_name,
                defaults={'active': True}
            )
            # Check if this team has been merged
            primary_team = get_primary_team(team)
            return primary_team, created

        def transform_level(level):
            if level:
                if level.lower() == "h":
                    return "High School"

                if level.lower() == "c":
                    return "College"

            return None

        def to_int_or_none(value):
            """Coerce sheet values to int or None (handles '', None, numeric strings)."""
            if value is None:
                return None
            if isinstance(value, str):
                stripped = value.strip()
                if stripped == "" or stripped.lower() in {"na", "n/a", "null"}:
                    return None
                value = stripped
            try:
                # Some sheets store numbers as '1.0'; convert safely
                return int(float(value))
            except Exception:
                return None

        explicit_year = options.get('year')
        explicit_version = options.get('mock_version')
        tab = options.get('tab')

        if (explicit_year or explicit_version) and not (explicit_year and explicit_version):
            raise CommandError('Use --year and --mock-version together (e.g. --year 2026 --mock-version 1.0).')

        tab_jobs = []

        if explicit_year and explicit_version:
            year = str(explicit_year).strip()
            version = str(explicit_version).strip()
            tab_title = f"{year} Mock {version}"
            tab_jobs.append({"tab_title": tab_title, "year": year, "version": version})
            self.stdout.write(self.style.WARNING(f'Only loading: {tab_title}'))
        elif tab:
            tab_normalized = ' '.join(str(tab).split())
            parsed = _parse_mock_tab_title(tab_normalized)
            if not parsed:
                raise CommandError(
                    'Tab title must look like "<YEAR> Mock <NUMBER>", e.g. "2026 Mock 1.0".'
                )
            year, version = parsed
            tab_jobs.append({"tab_title": tab_normalized, "year": year, "version": version})
            self.stdout.write(self.style.WARNING(f'Only loading tab: {tab_normalized}'))
        else:
            try:
                all_titles = utils.list_spreadsheet_sheet_titles(MOCK_DRAFT_SPREADSHEET_ID)
            except Exception as exc:
                raise CommandError(f'Could not list spreadsheet tabs: {exc}') from exc
            for raw_title in all_titles:
                parsed = _parse_mock_tab_title(raw_title)
                if not parsed:
                    continue
                y, ver = parsed
                tab_jobs.append({"tab_title": raw_title, "year": y, "version": ver})
            tab_jobs.sort(
                key=lambda job: (int(job['year']), _mock_version_sort_key(job['version']))
            )
            if not tab_jobs:
                self.stdout.write(
                    self.style.WARNING(
                        'No tabs matching "<YEAR> Mock <NUMBER>" (e.g. "2026 Mock 1.0"). '
                        'Add tabs to the sheet, or pass a tab name / --year and --mock-version.'
                    )
                )
                return
            self.stdout.write(
                self.style.NOTICE(
                    f'Discovered {len(tab_jobs)} mock tab(s): '
                    + ', '.join(j['tab_title'] for j in tab_jobs)
                )
            )

        for job in tab_jobs:
                tab_title = job['tab_title']
                year = job['year']
                mock_number = job['version']

                print(year, mock_number)

                sheet = None
                range_a1 = utils.sheet_tab_a1_range(tab_title)

                try:
                    sheet = utils.get_sheet(MOCK_DRAFT_SPREADSHEET_ID, range_a1, value_cutoff=None)
                except Exception as exc:
                    self.stderr.write(
                        self.style.ERROR(f'Error reading sheet tab {tab_title!r} ({range_a1}): {exc}')
                    )
                    continue

                if sheet:
                    # Normalize version and final flag
                    version_display = str(mock_number).strip()
                    is_final_version = version_display.lower() == "final"

                    # Create/update the mock draft ranking
                    r, r_created = models.Ranking.objects.get_or_create(
                        year=year,
                        is_mock_draft=True,
                        mock_draft_version=version_display,
                        ranking_type=None,
                        is_draft=True,
                        defaults={
                            'is_final': False,
                        }
                    )
                    # Update mutable fields
                    r.is_final = is_final_version
                    r.ranking_length = len(sheet)

                    r.save()

                    # Deactivate existing player rankings for this mock ranking
                    models.PlayerRanking.objects.filter(ranking=r).update(rank=None, active=False)

                    for row in sheet:
                        # player object
                        p, created = models.Player.objects.get_or_create(name=row['name'], position = row['position'])
                        
                        # Check if this player has been merged into another player
                        p = get_primary_player(p)
                        
                        p.school=row.get('school')

                        if row.get('bat_throw', None):
                            
                            if "-" in row['bat_throw']:
                                p.bats = row['bat_throw'].split('-')[0]
                                p.throws = row['bat_throw'].split('-')[1]
                            elif "/" in row['bat_throw']:
                                p.bats = row['bat_throw'].split('/')[0]
                                p.throws = row['bat_throw'].split('/')[1]
            
                        p.height = row.get('height', None)
                        p.weight = row.get('weight', None)
                        p.hometown = row.get('hometown', None)

                        p.state = row.get('state', None)
                        if p.state:
                            if len(p.state) >3:
                                try:
                                    p.state = utils.STATE_NAME_TO_ABBREV[p.state.strip()]
                                except:
                                    pass

                        p.photo_url = row.get('photo_url', None)
                        spotlight = row.get('draft_spotlight')
                        if spotlight and str(spotlight).strip():
                            p.video_url = str(spotlight).strip()

                        p.save()

                        # player_ranking object
                        pr, pr_created = models.PlayerRanking.objects.get_or_create(
                            ranking=r,
                            player=p,
                            defaults={}
                        )

                        # Update fields from the sheet
                        pr.school = row.get('school')
                        pr.position = row.get('position')
                        pr.rank = to_int_or_none(row.get('rank'))
                        pr.level = transform_level(row.get('class', None))
                        pr.commitment = row.get('commitment', None)
                        pr.raw_carrying_tools = row.get('carrying_tool', None)
                        pr.role = row.get('role', None)
                        pr.risk = row.get('risk', None)
                        pr.scouting_report = ''  # Will set below after processing blurb
                        pr.mock_pick_number = to_int_or_none(row.get('mock_pick_number'))
                        pr.mock_team = row.get('mock_team', None)
                        pr.mock_team_logo_url = row.get('mock_team_photo_url', None)
                        pr.active = True
                        
                        # Link to Team object if this is a college player
                        if pr.level == "College" and pr.school:
                            school_name = pr.school.strip()
                            if school_name:
                                team, created = get_or_create_team_with_merge_check(school_name)
                                pr.school_team = team

                        # Save now so we can work with M2M relationships
                        pr.save()

                        # Process carrying tools
                        pr.carrying_tools.clear()
                        raw_tools = pr.raw_carrying_tools
                        if raw_tools:
                            for line in str(raw_tools).splitlines():
                                if not line.strip():
                                    continue
                                if ":" in line:
                                    tool_part, score_part = line.split(":", 1)
                                    tool_name = tool_part.strip()
                                    score_val = score_part.strip()
                                    if tool_name and score_val:
                                        ct_obj = models.PlayerRankingCarryingTool.objects.filter(tool=tool_name, score=score_val).first()
                                        if ct_obj:
                                            pr.carrying_tools.add(ct_obj)
                                        else:
                                            print(f"Warning: Carrying tool '{tool_name}:{score_val}' not found for player {p.name}")

                        # Update scouting report with formatted blurb
                        blurb = row.get('blurb', None)
                        if blurb:
                            paragraphs = []
                            for paragraph in blurb.split('\n\n'):
                                if paragraph.strip():
                                    paragraph_html = paragraph.strip().replace('\n', '<br>')
                                    paragraphs.append(f'<p>{paragraph_html}</p>')
                            pr.scouting_report = ''.join(paragraphs) if paragraphs else blurb
                        else:
                            pr.scouting_report = None

                        pr.save()