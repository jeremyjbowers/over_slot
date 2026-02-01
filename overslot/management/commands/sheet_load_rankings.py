from django.core.management.base import BaseCommand, CommandError
from django.conf import settings
from django.db.models import Q, Count
from django.core.exceptions import MultipleObjectsReturned
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
                    if debug:
                        self.stdout.write(f"  → Team {team.name} was merged into {merge_decision.primary_team.name}")
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
                    
                    # Delete any duplicate inactive PlayerRankings for this ranking to avoid get_or_create conflicts
                    # Keep only one inactive record per player+ranking combination
                    duplicate_inactive_prs = models.PlayerRanking.objects.filter(
                        ranking=r, 
                        active=False
                    ).values('player').annotate(
                        count=Count('id')
                    ).filter(count__gt=1)
                    
                    if duplicate_inactive_prs.exists():
                        deleted_count = 0
                        for dup_info in duplicate_inactive_prs:
                            # Get all inactive PlayerRankings for this player+ranking
                            prs_to_clean = models.PlayerRanking.objects.filter(
                                ranking=r,
                                player_id=dup_info['player'],
                                active=False
                            ).order_by('id')
                            # Keep the first one, delete the rest
                            if prs_to_clean.count() > 1:
                                to_delete = prs_to_clean[1:]
                                deleted_count += to_delete.count()
                                for pr in to_delete:
                                    if debug:
                                        self.stdout.write(f"  Deleting duplicate inactive PlayerRanking: id={pr.pk} player={pr.player.name if pr.player else 'None'}")
                                    pr.delete()
                        if deleted_count > 0:
                            self.stdout.write(self.style.WARNING(f"Deleted {deleted_count} duplicate inactive PlayerRanking records for ranking id={r.pk}"))

                    processed_rows = 0
                    for idx, row in enumerate(sheet, start=1):
                        processed_rows += 1
                        player_name = row.get('name', '')
                        player_position = row.get('position', '')
                        if debug:
                            self.stdout.write(f"Row {idx}/{len(sheet)}: name={player_name} position={player_position}")
                        
                        # player object - handle duplicate case
                        try:
                            p, created = models.Player.objects.get_or_create(name=player_name, position=player_position)
                            if debug:
                                self.stdout.write(f"  Player {'created' if created else 'found'}: id={p.pk} name={p.name} position={p.position}")
                        except MultipleObjectsReturned as e:
                            # Multiple players found with same name/position
                            self.stderr.write(self.style.ERROR(f"\n{'='*80}"))
                            self.stderr.write(self.style.ERROR(f"DUPLICATE PLAYER ERROR at Row {idx}/{len(sheet)}"))
                            self.stderr.write(self.style.ERROR(f"  Name: '{player_name}'"))
                            self.stderr.write(self.style.ERROR(f"  Position: '{player_position}'"))
                            matching_players = models.Player.objects.filter(name=player_name, position=player_position)
                            self.stderr.write(self.style.ERROR(f"  Found {matching_players.count()} matching players:"))
                            for mp in matching_players:
                                self.stderr.write(f"    - id={mp.pk} name='{mp.name}' position='{mp.position}' active={mp.active} school='{mp.school}'")
                            
                            # Try to get the first active one, or just the first one
                            p = matching_players.filter(active=True).first()
                            if not p:
                                p = matching_players.first()
                                self.stderr.write(self.style.WARNING(f"  → Using inactive player: id={p.pk}"))
                            else:
                                self.stderr.write(self.style.SUCCESS(f"  → Using active player: id={p.pk}"))
                            self.stderr.write(self.style.ERROR(f"{'='*80}\n"))
                            created = False
                        
                        # Check if this player has been merged into another player
                        if debug:
                            self.stdout.write(f"  Checking for merged player: id={p.pk} name={p.name} active={p.active}")
                        p_original = p
                        p = get_primary_player(p)
                        if p != p_original:
                            self.stdout.write(self.style.WARNING(f"  → Player was merged: {p_original.name} (id={p_original.pk}) -> {p.name} (id={p.pk})"))
                        elif debug:
                            self.stdout.write(f"  No merge found, using original player: id={p.pk}")
                        
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
                        # First check if there's an active one, if not check for inactive ones
                        pr = models.PlayerRanking.objects.filter(ranking=r, player=p, active=True).first()
                        if pr:
                            pr_created = False
                            if debug:
                                self.stdout.write(f"  PlayerRanking found (active): id={pr.pk}")
                        else:
                            # Check for inactive ones
                            inactive_prs = models.PlayerRanking.objects.filter(ranking=r, player=p, active=False)
                            if inactive_prs.exists():
                                # Use the first inactive one and reactivate it
                                pr = inactive_prs.first()
                                pr_created = False
                                if debug:
                                    self.stdout.write(f"  PlayerRanking found (inactive, reactivating): id={pr.pk}")
                                # If there are multiple inactive ones, delete the extras
                                if inactive_prs.count() > 1:
                                    extras = inactive_prs[1:]
                                    deleted_count = extras.count()
                                    for extra_pr in extras:
                                        if debug:
                                            self.stdout.write(f"    Deleting duplicate inactive PlayerRanking: id={extra_pr.pk}")
                                        extra_pr.delete()
                                    self.stderr.write(self.style.WARNING(f"  Deleted {deleted_count} duplicate inactive PlayerRanking(s) for {p.name}"))
                            else:
                                # Create a new one
                                pr = models.PlayerRanking.objects.create(ranking=r, player=p)
                                pr_created = True
                                if debug:
                                    self.stdout.write(f"  PlayerRanking created: id={pr.pk}")

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
                        
                        # Link to Team object if this is a college player
                        if pr.level == "College" and pr.school:
                            school_name = pr.school.strip()
                            if school_name:
                                team, created = get_or_create_team_with_merge_check(school_name)
                                pr.school_team = team
                                if debug:
                                    if created:
                                        self.stdout.write(f"  Created Team: {school_name}")
                                    elif team.name != school_name:
                                        self.stdout.write(f"  Linked to merged Team: {school_name} -> {team.name}")
                                    else:
                                        self.stdout.write(f"  Linked to Team: {school_name}")

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