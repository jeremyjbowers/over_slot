from django.core.management.base import BaseCommand, CommandError
from django.conf import settings

from overslot import models, utils


class Command(BaseCommand):
    def handle(self, *args, **options):

        # models.Player.objects.all().delete()
        # models.PlayerRanking.objects.all().delete()
        # models.Ranking.objects.all().delete()

        def transform_level(level):
            if level:
                if level.lower() == "h":
                    return "High School"

                if level.lower() == "c":
                    return "College"

            return None

        # for year in ["2024", "2025"]:
        for year in ["2020", "2021", "2022", "2023", "2024", "2025"]:
            print(year)
            sheet = utils.get_sheet("15kLgnYACmlcrYV3QI5TECb2Vzkz-9jkrc8kc_IG6rkE", f"{year}!A:Z", value_cutoff=None)
            r, r_created = models.Ranking.objects.get_or_create(year=year, ranking_type=None, ranking_length=len(sheet), is_draft=True, is_final=True)

            for row in sheet:
                # player object
                p, created = models.Player.objects.get_or_create(name=row['name'], position = row['position'])
                p.school=row.get('school')

                print(row['name'], row.get('bat_throw'))
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
                pr.scouting_report = row.get('blurb', None)

                pr.save()