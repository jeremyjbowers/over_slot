from django.core.management.base import BaseCommand, CommandError
from django.conf import settings

from overslot import models

class Command(BaseCommand):
    def handle(self, *args, **options):
        for tool in ["Hit", "Game Power", "Run", "Throw", "Field", "Fastball", "Breaking Ball", "Changeup", "Command"]:
            for score in ["30", "35", "40", "45", "50", "55", "60", "65", "70", "75", "80"]:
                ts, created = models.PlayerRankingCarryingTool.objects.get_or_create(tool=tool, score=score)
                if created:
                    payload = f"+"
                else:
                    payload = f"*"
                payload += f" {tool}: {score}"
                print(payload)