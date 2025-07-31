from django.core.management.base import BaseCommand, CommandError
from django.conf import settings
from django.db.models import Q

from overslot import models, utils


class Command(BaseCommand):
    help = 'Load rankings, players and player rankings from Google Sheets'

    def add_arguments(self, parser):
        parser.add_argument(
            '--clear',
            action='store_true',
            help='Clear all existing players, rankings, and player rankings before loading (DESTRUCTIVE)',
        )

    def handle(self, *args, **options):
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
                    print(f"  → Player {player.name} was merged into {merge_decision.primary_player.name}")
                    return merge_decision.primary_player
            
            return player

        def transform_level(level):
            if level:
                if level.lower() == "h":
                    return "High School"

                if level.lower() == "c":
                    return "College"

            return None

        for year in ["2020", "2021", "2022", "2023", "2024", "2025", "2026", "2027"]:
            levels = ["Overall", "High School", "College"]
            for level in levels:
                try:
                    sheet = utils.get_sheet("15kLgnYACmlcrYV3QI5TECb2Vzkz-9jkrc8kc_IG6rkE", f"{year} {level}!A:Z", value_cutoff=None)
                    r, r_created = models.Ranking.objects.get_or_create(year=year, ranking_type=None, is_mock_draft=False, is_draft=True, is_final=True, draft_level=level)
                    r.ranking_length = len(sheet)
                    r.save()

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
                        p.video_url = row.get('draft_spotlight', None)

                        p.save()

                        # player_ranking object
                        pr, pr_created = models.PlayerRanking.objects.get_or_create(ranking=r, player=p, rank=row['rank'], school=row['school'], position=row['position'])

                        pr.level = transform_level(row.get('class', None))
                        pr.commitment = row.get('commitment', None)
                        pr.raw_carrying_tools = row.get('carrying_tool', None)
                        pr.role = row.get('role', None)
                        pr.risk = row.get('risk', None)
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
                except Exception as e:
                    # print(f"Error processing {year} {level}: {e}")
                    continue