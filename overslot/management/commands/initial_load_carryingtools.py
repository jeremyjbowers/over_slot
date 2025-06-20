from django.core.management.base import BaseCommand, CommandError
from django.conf import settings

from overslot import models

class Command(BaseCommand):
    help = 'Load initial carrying tools data. By default, runs in non-destructive mode (preserves existing data).'
    
    def add_arguments(self, parser):
        parser.add_argument(
            '--clear',
            action='store_true',
            help='Delete all existing PlayerRankingCarryingTool objects before loading',
        )
    
    def handle(self, *args, **options):
        clear_existing = options['clear']
        
        if clear_existing:
            self.stdout.write(
                self.style.WARNING('DESTRUCTIVE MODE: Clearing all existing carrying tools data...')
            )
            deleted_count = models.PlayerRankingCarryingTool.objects.all().delete()[0]
            self.stdout.write(
                self.style.WARNING(f'Deleted {deleted_count} existing carrying tool records.')
            )
        else:
            self.stdout.write(
                self.style.SUCCESS('NON-DESTRUCTIVE MODE: Preserving existing data (use --clear to delete existing records)')
            )
        
        tools = ["Hit", "Power", "Run", "Arm", "Field", "Fastball", "Slider", "Curveball", "Changeup", "Command", "Arm Action", "Splitter", "Sinker", "Cutter"]
        scores = ["30", "35", "40", "45", "50", "55", "60", "65", "70", "75", "80"]
        
        created_count = 0
        existing_count = 0
        
        for tool in tools:
            for score in scores:
                ts, created = models.PlayerRankingCarryingTool.objects.get_or_create(tool=tool, score=score)
                if created:
                    created_count += 1
                    self.stdout.write(f"+ Created {tool}: {score}")
                else:
                    existing_count += 1
                    self.stdout.write(f"* Found existing {tool}: {score}")
        
        # Summary
        self.stdout.write(
            self.style.SUCCESS(f'\nSummary: Created {created_count} new records, found {existing_count} existing records.')
        )