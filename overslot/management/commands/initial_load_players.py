from django.core.management.base import BaseCommand, CommandError
from django.conf import settings

from overslot import models, utils


class Command(BaseCommand):
    def handle(self, *args, **options):
        for year in ["2020", "2021", "2022", "2023", "2024", "2025"]:
            sheet = utils.get_sheet("15kLgnYACmlcrYV3QI5TECb2Vzkz-9jkrc8kc_IG6rkE", f"{year}!A:D", value_cutoff=None)
            r, r_created = models.Ranking.objects.get_or_create(year=year, ranking_type=None, ranking_length=len(sheet), is_draft=True, is_final=True)

            for row in sheet:
                p, created = models.Player.objects.get_or_create(name=row['name'], current_position = row['position'])
                p.current_school=row['school']
                p.save()

                payload = f"*"
                if created:
                    payload = f"+"

                payload += f" {p.name} {p.current_position} {p.current_school}"

                pr, pr_created = models.PlayerRanking.objects.get_or_create(ranking=r, player=p, rank=row['rank'], ranking_school=row['school'], ranking_position=row['position'])