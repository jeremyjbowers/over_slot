from django.core.management.base import BaseCommand

from overslot import models, utils


class Command(BaseCommand):
    help = (
        "Remove college Trackman (PlayerStatSeason) and 643 (Player643StatSeason) rows "
        "attached to high-school-only players whose draft class year is >= the stat season. "
        "Those rows are name-collision junk from college loaders matching by name only. "
        "Dry-run by default; pass --commit to delete."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--commit",
            action="store_true",
            help="Actually delete the mismatched rows. Default is a dry-run.",
        )

    def handle(self, *args, **options):
        commit = options.get("commit", False)
        trackman, stats_643 = utils.find_mismatched_college_stats()

        self.stdout.write(
            f"{'[DRY RUN] ' if not commit else ''}Mismatched college Trackman seasons: {len(trackman)}"
        )
        for s in sorted(trackman, key=lambda x: (x.player.name, x.year)):
            self.stdout.write(
                f"  Trackman id={s.id} {s.player.name} {s.year} College "
                f"school={s.school!r} draft_year={s.draft_year}"
            )

        self.stdout.write(
            f"{'[DRY RUN] ' if not commit else ''}Mismatched 643 seasons: {len(stats_643)}"
        )
        for s in sorted(stats_643, key=lambda x: (x.player.name, x.year)):
            self.stdout.write(
                f"  643 id={s.id} {s.player.name} {s.year} team={s.team_name!r}"
            )

        if not trackman and not stats_643:
            self.stdout.write(self.style.SUCCESS("No mismatched college stats found."))
            return

        if not commit:
            self.stdout.write(
                self.style.WARNING(
                    "Dry-run only. Re-run with --commit to delete these rows on this database."
                )
            )
            return

        trackman_ids = [s.id for s in trackman]
        stats_643_ids = [s.id for s in stats_643]
        deleted_tm, _ = models.PlayerStatSeason.objects.filter(id__in=trackman_ids).delete()
        deleted_643, _ = models.Player643StatSeason.objects.filter(id__in=stats_643_ids).delete()
        self.stdout.write(
            self.style.SUCCESS(
                f"Deleted {deleted_tm} Trackman row(s) and {deleted_643} 643 row(s)."
            )
        )
