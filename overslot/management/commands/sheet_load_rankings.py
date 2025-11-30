from django.core.management.base import BaseCommand, CommandError
from django.conf import settings
from django.db.models import Q
import traceback

from overslot import models, utils


class Command(BaseCommand):
    help = 'Load rankings, players and player rankings from Google Sheets'

    def add_arguments(self, parser):
        parser.add_argument(
            '--clear',
            action='store_true',
            help='Clear all existing players, rankings, and player rankings before loading (DESTRUCTIVE)',
        )
        parser.add_argument(
            '--debug',
            action='store_true',
            help='Print detailed progress information while loading',
        )
        parser.add_argument(
            'tab',
            nargs='?',
            help='Only load a specific tab (e.g., "2027 High School")',
        )

    def handle(self, *args, **options):
        debug = options.get('debug', False)
        # Only delete if explicitly requested
        if options['clear']:
            self.stdout.write(self.style.WARNING('DESTRUCTIVE MODE: Clearing all existing data...'))
            models.PlayerRanking.objects.all().delete()
            models.Ranking.objects.all().delete()
            self.stdout.write(self.style.SUCCESS('Cleared existing data'))
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
                    if debug:
                        self.stdout.write(f"  → Player {player.name} was merged into {merge_decision.primary_player.name}")
                    return merge_decision.primary_player
            
            return player

        def transform_level(level):
            if level:
                if level.lower() == "h":
                    return "High School"

                if level.lower() == "c":
                    return "College"

            return None

        default_years = ["2026", "2027", "2028"]
        default_levels = ["Overall", "High School", "College"]

        tab = options.get('tab')
        if tab:
            tab_normalized = ' '.join(str(tab).split())
            if ' ' not in tab_normalized:
                raise CommandError('Tab must be in the format "YYYY Level", e.g., "2027 High School"')
            year, level = tab_normalized.split(' ', 1)
            year_level_pairs = [(year, level)]
            self.stdout.write(self.style.WARNING(f'Only loading tab: {year} {level}'))
        else:
            year_level_pairs = [(y, l) for y in default_years for l in default_levels]

        for (year, level) in year_level_pairs:
                try:
                    if debug:
                        self.stdout.write(self.style.WARNING(f"Starting load for tab: {year} {level}"))
                    sheet = utils.get_sheet("15kLgnYACmlcrYV3QI5TECb2Vzkz-9jkrc8kc_IG6rkE", f"{year} {level}!A:Z", value_cutoff=None)
                    if debug:
                        self.stdout.write(f"Fetched sheet with {len(sheet)} rows for {year} {level}")
                    r, r_created = models.Ranking.objects.get_or_create(year=year, ranking_type=None, is_mock_draft=False, is_draft=True, is_final=True, draft_level=level)
                    if debug:
                        self.stdout.write(f"Ranking {'created' if r_created else 'loaded'}: id={r.pk} year={year} level={level}")
                    r.ranking_length = len(sheet)
                    r.save()

                    # Deactivate all existing player rankings for this ranking, blank their rank
                    deactivated = models.PlayerRanking.objects.filter(ranking=r).update(rank=None, active=False)
                    if debug:
                        self.stdout.write(f"Deactivated {deactivated} existing PlayerRanking rows for ranking id={r.pk}")

                    processed_rows = 0
                    for idx, row in enumerate(sheet, start=1):
                        processed_rows += 1
                        if debug:
                            self.stdout.write(f"Row {idx}/{len(sheet)}: name={row.get('name')} position={row.get('position')}")
                        # player object
                        p, created = models.Player.objects.get_or_create(name=row['name'], position = row['position'])
                        if debug:
                            self.stdout.write(f"  Player {'created' if created else 'found'}: id={p.pk} name={p.name}")
                        
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
                            if debug:
                                self.stdout.write(f"  Bat/Throw parsed: bats={getattr(p, 'bats', None)} throws={getattr(p, 'throws', None)}")
            
                        p.height = row.get('height', None)
                        p.weight = row.get('weight', None)
                        p.hometown = row.get('hometown', None)

                        p.state = row.get('state', None)
                        if p.state:
                            if len(p.state) >3:
                                try:
                                    p.state = utils.STATE_NAME_TO_ABBREV[p.state.strip()]
                                    if debug:
                                        self.stdout.write(f"  State normalized to {p.state}")
                                except:
                                    if debug:
                                        self.stdout.write(f"  State normalization failed for value: {row.get('state')}")
                                    pass

                        p.photo_url = row.get('photo_url', None)
                        p.video_url = row.get('draft_spotlight', None)

                        p.save()
                        if debug:
                            self.stdout.write(f"  Player saved: id={p.pk}")

                        # Find existing player ranking for this player+ranking or create if missing
                        pr, pr_created = models.PlayerRanking.objects.get_or_create(
                            ranking=r,
                            player=p,
                            defaults={}
                        )
                        if debug:
                            self.stdout.write(f"  PlayerRanking {'created' if pr_created else 'found'}: id={pr.pk}")

                        # Update fields from the sheet
                        pr.school = row.get('school')
                        pr.position = row.get('position')
                        pr.rank = row.get('rank', None)
                        pr.level = transform_level(row.get('class', None))
                        pr.commitment = row.get('commitment', None)
                        pr.raw_carrying_tools = row.get('carrying_tool', None)
                        pr.role = row.get('role', None)
                        pr.risk = row.get('risk', None)
                        pr.age_at_draft = row.get('age_at_draft', None)
                        pr.active = True
                        pr.scouting_report = ''  # Will set below after processing blurb

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
                                            if debug:
                                                self.stdout.write(f"    Carrying tool added: {tool_name}:{score_val}")
                                        else:
                                            if debug:
                                                self.stdout.write(self.style.WARNING(f"    Carrying tool not found: {tool_name}:{score_val} for player {p.name}"))

                        # Update scouting report with formatted blurb
                        blurb = row.get('blurb', None)
                        if blurb:
                            paragraphs = []
                            for paragraph in blurb.split('\n\n'):
                                if paragraph.strip():
                                    paragraph_html = paragraph.strip().replace('\n', '<br>')
                                    paragraphs.append(f'<p>{paragraph_html}</p>')
                            pr.scouting_report = ''.join(paragraphs) if paragraphs else blurb
                            if debug:
                                self.stdout.write("  Scouting report updated (HTML paragraphs)")
                        else:
                            pr.scouting_report = None
                            if debug:
                                self.stdout.write("  Scouting report cleared")

                        pr.save()
                    if debug:
                        self.stdout.write(self.style.SUCCESS(f"Completed load for {year} {level}: {processed_rows} rows processed"))
                except Exception as e:
                    if debug:
                        self.stderr.write(self.style.ERROR(f"Error processing {year} {level}: {e}"))
                        self.stderr.write(traceback.format_exc())
                    continue