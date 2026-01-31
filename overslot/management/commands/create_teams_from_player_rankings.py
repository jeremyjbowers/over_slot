from django.core.management.base import BaseCommand, CommandError
from django.db.models import Q
from django.utils import timezone
from datetime import datetime

from overslot import models


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
            return merge_decision.primary_team
    
    return team


def get_or_create_team_with_merge_check(school_name):
    """
    Get or create a team by name, and return the primary team if it has been merged.
    Ensures the team has a slug.
    """
    team, created = models.Team.objects.get_or_create(
        name=school_name,
        defaults={'active': True}
    )
    # Ensure team has a slug (for existing teams that might not have one)
    if not team.slug:
        team.save()  # Auto-generates slug
        team.refresh_from_db()
    # Check if this team has been merged
    primary_team = get_primary_team(team)
    # Ensure primary team also has a slug
    if primary_team and not primary_team.slug:
        primary_team.save()
        primary_team.refresh_from_db()
    return primary_team, created


class Command(BaseCommand):
    help = 'Create Team objects for schools from all college-level player rankings. Optionally roll over rankings from one year to another.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--source-year',
            type=str,
            help='Optional: Source year to copy rankings from (e.g., "2025"). If provided with --target-year, will roll over rankings.',
        )
        parser.add_argument(
            '--target-year',
            type=str,
            help='Optional: Target year to copy rankings to (e.g., "2026"). If provided with --source-year, will roll over rankings.',
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be done without actually making changes',
        )

    def handle(self, *args, **options):
        dry_run = options.get('dry_run', False)
        
        if dry_run:
            self.stdout.write(self.style.WARNING("DRY RUN MODE - No changes will be made"))
        
        # Collect all unique school names from ALL college player rankings (across all years)
        self.stdout.write("Collecting school names from all college-level player rankings...")
        player_rankings = models.PlayerRanking.objects.filter(
            level="College",
            active=True,
            school__isnull=False
        ).exclude(school="")
        
        school_names = set()
        for pr in player_rankings:
            if pr.school:
                school_names.add(pr.school.strip())
        
        self.stdout.write(f"Found {len(school_names)} unique school names from {player_rankings.count()} college player rankings")
        
        # Create Team objects for schools that don't exist
        teams_created = 0
        teams_existing = 0
        
        for school_name in sorted(school_names):
            if not dry_run:
                team, created = get_or_create_team_with_merge_check(school_name)
            else:
                # In dry-run, just check if team exists (don't create or update)
                try:
                    team = models.Team.objects.get(name=school_name, active=True)
                    created = False
                except models.Team.DoesNotExist:
                    created = True
            
            if created:
                teams_created += 1
                if not dry_run:
                    self.stdout.write(f"  ✓ Created Team: {school_name}")
                else:
                    self.stdout.write(f"  [DRY RUN] Would create Team: {school_name}")
            else:
                teams_existing += 1
                # Check if team was merged
                if team.name != school_name:
                    if not dry_run:
                        self.stdout.write(f"  ↻ Team '{school_name}' merged into '{team.name}'")
        
        self.stdout.write(f"\nTeams: {teams_created} created, {teams_existing} already existed")
        
        # Roll over rankings if years are provided
        source_year = options.get('source_year')
        target_year = options.get('target_year')
        
        if source_year or target_year:
            # Determine source and target years
            current_year = datetime.now().year
            if not source_year:
                source_year = str(current_year - 1)
            
            if not target_year:
                target_year = str(current_year)
            
            self.stdout.write(f"\nRolling over college rankings from {source_year} to {target_year}")
            
            if dry_run:
                self.stdout.write(self.style.WARNING("DRY RUN - No rankings were rolled over"))
                return
            
            # Find all college rankings from source year
            source_rankings = models.Ranking.objects.filter(
                year=source_year,
                draft_level="College",
                active=True
            )
            
            if not source_rankings.exists():
                self.stdout.write(
                    self.style.WARNING(f"No college rankings found for year {source_year}")
                )
            else:
                self.stdout.write(f"Found {source_rankings.count()} college ranking(s) from {source_year}")
                
                # Roll over rankings and player rankings
                rankings_created = 0
                player_rankings_created = 0
                
                for source_ranking in source_rankings:
                    # Create new ranking for target year
                    # Use similar attributes but update year
                    target_ranking, ranking_created = models.Ranking.objects.get_or_create(
                        year=target_year,
                        ranking_type=source_ranking.ranking_type,
                        ranking_length=source_ranking.ranking_length,
                        is_final=source_ranking.is_final,
                        is_draft=source_ranking.is_draft,
                        is_mock_draft=source_ranking.is_mock_draft,
                        mock_draft_version=source_ranking.mock_draft_version,
                        draft_level=source_ranking.draft_level,
                        defaults={
                            'headline': source_ranking.headline,
                            'subhead': source_ranking.subhead,
                            'blurb': source_ranking.blurb,
                            'current': source_ranking.current,
                            'publish': False,  # Don't auto-publish rolled over rankings
                            'active': True,
                        }
                    )
                    
                    if ranking_created:
                        rankings_created += 1
                        self.stdout.write(f"  ✓ Created Ranking: {target_ranking.get_computed_title()}")
                    else:
                        self.stdout.write(f"  ↻ Ranking already exists: {target_ranking.get_computed_title()}")
                    
                    # Copy player rankings
                    source_player_rankings = models.PlayerRanking.objects.filter(
                        ranking=source_ranking,
                        level="College",
                        active=True
                    )
                    
                    for source_pr in source_player_rankings:
                        # Create or get existing player ranking for target year
                        target_pr, pr_created = models.PlayerRanking.objects.get_or_create(
                            ranking=target_ranking,
                            player=source_pr.player,
                            defaults={'active': True}
                        )
                        
                        if pr_created:
                            player_rankings_created += 1
                        
                        # Copy all fields from source to target
                        target_pr.rank = source_pr.rank
                        target_pr.position = source_pr.position
                        target_pr.school = source_pr.school
                        target_pr.country = source_pr.country
                        target_pr.commitment = source_pr.commitment
                        target_pr.raw_carrying_tools = source_pr.raw_carrying_tools
                        target_pr.age_at_draft = source_pr.age_at_draft
                        target_pr.level = source_pr.level
                        target_pr.role = source_pr.role
                        target_pr.risk = source_pr.risk
                        target_pr.scouting_report = source_pr.scouting_report
                        target_pr.active = True
                        
                        # Link to Team object if this is a college player
                        if target_pr.level == "College" and target_pr.school:
                            school_name = target_pr.school.strip()
                            if school_name:
                                team, created = get_or_create_team_with_merge_check(school_name)
                                target_pr.school_team = team
                        
                        # Copy carrying tools
                        target_pr.carrying_tools.set(source_pr.carrying_tools.all())
                        
                        # Copy all Trackman/metrics fields
                        metric_fields = [
                            'hitter_percentile', 'game_power_percentile', 'raw_power_percentile',
                            'approach_percentile', 'hitter_score', 'game_power_score',
                            'raw_power_score', 'approach_score',
                            'whiff_pct', 'whiff_pct_percentile', 'whiff_pct_points_above_median',
                            'iz_whiff_pct', 'iz_whiff_pct_percentile', 'iz_whiff_pct_points_above_median',
                            'ooz_whiff_pct', 'ooz_whiff_pct_percentile', 'ooz_whiff_pct_points_above_median',
                            'chase_pct', 'chase_pct_percentile', 'chase_pct_points_above_median',
                            'k_pct', 'k_pct_percentile', 'k_pct_points_above_median',
                            'bb_pct', 'bb_pct_percentile', 'bb_pct_points_above_median',
                            'avg_exit_velocity', 'avg_exit_velocity_percentile', 'avg_exit_velocity_points_above_median',
                            'ev_90th', 'ev_90th_percentile', 'ev_90th_points_above_median',
                            'barrel_pct', 'barrel_pct_percentile', 'barrel_pct_points_above_median',
                            'pull_air_pct', 'pull_air_pct_percentile', 'pull_air_pct_points_above_median',
                            'xwoba', 'xwoba_percentile', 'xwoba_points_above_median',
                            'fourseam_percentile', 'sinker_percentile', 'slider_percentile',
                            'sweeper_percentile', 'curveball_percentile', 'changeup_percentile',
                            'fourseam_score', 'sinker_score', 'slider_score',
                            'sweeper_score', 'curveball_score', 'changeup_score',
                            'confidence',
                        ]
                        
                        for field_name in metric_fields:
                            if hasattr(source_pr, field_name):
                                setattr(target_pr, field_name, getattr(source_pr, field_name))
                        
                        target_pr.save()
                
                # Summary for rollover
                self.stdout.write("")
                self.stdout.write(self.style.SUCCESS(
                    f'\nRollover Summary:\n'
                    f'  Rankings created: {rankings_created}\n'
                    f'  Player rankings created: {player_rankings_created}'
                ))
        
        # Final summary
        self.stdout.write("")
        self.stdout.write(self.style.SUCCESS(
            f'\nFinal Summary:\n'
            f'  Teams created: {teams_created}\n'
            f'  Teams already existed: {teams_existing}'
        ))
