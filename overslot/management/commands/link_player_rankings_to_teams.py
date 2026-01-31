from django.core.management.base import BaseCommand
from django.db.models import Q
from overslot import models
from overslot import utils


class Command(BaseCommand):
    help = 'Link PlayerRanking records to Team objects by matching school field to team names'

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be updated without actually updating',
        )
        parser.add_argument(
            '--force',
            action='store_true',
            help='Update even if school_team is already set',
        )

    def handle(self, *args, **options):
        dry_run = options.get('dry_run', False)
        force = options.get('force', False)
        
        # Get PlayerRankings that need team linking (only college players)
        if force:
            player_rankings = models.PlayerRanking.objects.filter(
                level="College",
                school__isnull=False
            ).exclude(school='')
        else:
            player_rankings = models.PlayerRanking.objects.filter(
                level="College",
                school__isnull=False,
                school_team__isnull=True
            ).exclude(school='')
        
        total_count = player_rankings.count()
        self.stdout.write(f"Found {total_count} PlayerRanking records to process")
        
        if total_count == 0:
            self.stdout.write(self.style.SUCCESS("No records to process."))
            return
        
        matched_count = 0
        unmatched_count = 0
        errors = []
        
        # Group by school for efficiency
        schools = player_rankings.values_list('school', flat=True).distinct()
        self.stdout.write(f"Processing {len(schools)} unique schools...")
        
        for school in schools:
            if not school or not school.strip():
                continue
            
            # Find matching team
            matched_team = utils.find_team_by_school_name(school)
            
            # Get all PlayerRankings with this school
            rankings_with_school = player_rankings.filter(school=school)
            
            if matched_team:
                matched_count += rankings_with_school.count()
                if not dry_run:
                    rankings_with_school.update(school_team=matched_team)
                self.stdout.write(
                    f"  ✓ Matched '{school}' -> '{matched_team.name}' ({rankings_with_school.count()} records)"
                )
            else:
                unmatched_count += rankings_with_school.count()
                unmatched_schools = list(rankings_with_school.values_list('school', flat=True).distinct())
                if unmatched_schools:
                    errors.append(f"  ✗ No match for '{school}' ({rankings_with_school.count()} records)")
        
        # Summary
        self.stdout.write("")
        self.stdout.write(self.style.SUCCESS(
            f"Summary:\n"
            f"  Matched: {matched_count}\n"
            f"  Unmatched: {unmatched_count}"
        ))
        
        if dry_run:
            self.stdout.write(self.style.WARNING("\nDRY RUN - No changes were made"))
        else:
            self.stdout.write(self.style.SUCCESS(f"\nUpdated {matched_count} PlayerRanking records"))
        
        if errors:
            self.stdout.write("")
            self.stdout.write(self.style.WARNING("Unmatched schools:"))
            for error in errors[:20]:  # Show first 20
                self.stdout.write(error)
            if len(errors) > 20:
                self.stdout.write(f"  ... and {len(errors) - 20} more")
