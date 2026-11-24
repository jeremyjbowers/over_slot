"""
Queue existing college stat seasons whose school doesn't fit the player.

Before school-aware matching, stat loaders attached rows by name alone, so some
players carry another person's seasons (e.g. Rett Johnson). This command scans
what is already in the database and opens a pending StatTeamLink for each
(player, team) that needs a human look, so it shows up on the review page.

    django-admin find_stat_melts --dry-run   # report only
    django-admin find_stat_melts             # queue for review

Rules, per player and college team:
* the team is a ranking school, an HS commitment, or an accepted link: fine
* Trackman and 6-4-3 put him at different schools in the same season: queued
  as a conflict (highest priority)
* a Trackman season at a school not on his record: queued for review
* 6-4-3 seasons are only queued when they conflict with Trackman. 6-4-3 rows
  normally arrive through 6-4-3's own mapping to our UUIDs, and its career
  history is how most transfers show up.
"""

from collections import defaultdict

from django.core.management.base import BaseCommand

from overslot import models
from overslot.stat_identity import normalize_school, queue_link


class Command(BaseCommand):
    help = "Queue college stat seasons whose school doesn't match the player for review"

    def add_arguments(self, parser):
        parser.add_argument("--dry-run", action="store_true", help="Report without creating review items")
        parser.add_argument("--limit", type=int, default=40, help="How many examples to print")
        parser.add_argument(
            "--move-merged",
            action="store_true",
            help="First move stat seasons left on merged-away players to the player they were merged into",
        )

    def handle(self, *args, **options):
        dry = options["dry_run"]

        stranded = models.Player.objects.filter(active=False).filter(
            pk__in=set(models.PlayerStatSeason.objects.values_list("player_id", flat=True))
            | set(models.Player643StatSeason.objects.values_list("player_id", flat=True))
        )
        if stranded.exists():
            if options["move_merged"] and not dry:
                from overslot.duplicate_views import move_stat_seasons
                from overslot.stat_identity import follow_merges

                moved = 0
                for p in stranded:
                    keeper = follow_merges(p)
                    if keeper is not None and keeper.pk != p.pk and keeper.active:
                        moved += move_stat_seasons(p, keeper)
                self.stdout.write(f"Moved {moved} stat season(s) from merged-away players to their survivors")
            else:
                self.stdout.write(
                    f"{stranded.count()} merged-away players still hold stat seasons "
                    f"(run with --move-merged to move them)"
                )

        known = defaultdict(set)
        for pid, school, commitment in models.PlayerRanking.objects.values_list(
            "player_id", "school", "commitment"
        ):
            for v in (school, commitment):
                k = normalize_school(v)
                if k:
                    known[pid].add(k)
        decided = defaultdict(set)
        for pid, team_key in models.StatTeamLink.objects.exclude(
            status=models.StatTeamLink.PENDING
        ).values_list("player_id", "team_key"):
            decided[pid].add(team_key)

        by_season = defaultdict(list)  # (player_id, year) -> [(team, source)]
        for pid, year, school in models.PlayerStatSeason.objects.filter(level="College", player__active=True).values_list(
            "player_id", "year", "school"
        ):
            if school:
                by_season[(pid, str(year))].append((school, "trackman"))
        for pid, year, team in models.Player643StatSeason.objects.filter(player__active=True).exclude(year="Career").values_list(
            "player_id", "year", "team_name"
        ):
            if team and team != "---":
                by_season[(pid, str(year))].append((team, "643"))

        players = {
            p.pk: p
            for p in models.Player.objects.filter(pk__in={pid for pid, _ in by_season.keys()})
        }

        # Teams 6-4-3 has anywhere in a player's career. 6-4-3 maps its own
        # players to our UUIDs, so a Trackman season at one of those teams is
        # a transfer we already have evidence for.
        career_643 = defaultdict(set)
        for (pid, _year), rows in by_season.items():
            for team, source in rows:
                if source == "643":
                    career_643[pid].add(normalize_school(team))

        queued = defaultdict(list)  # (pid, team_key) -> [(team, source, year, reason)]
        for (pid, year), rows in by_season.items():
            keys = {normalize_school(t) for t, _ in rows}
            conflict = len(keys) > 1
            for team, source in rows:
                k = normalize_school(team)
                if not k or k in known[pid] or k in decided[pid]:
                    continue
                if source == "trackman" and k in career_643[pid] and not conflict:
                    continue
                if conflict:
                    # Only flag the side(s) that aren't on his record.
                    reason = models.StatTeamLink.REASON_CONFLICT
                elif source == "trackman":
                    reason = models.StatTeamLink.REASON_UNKNOWN_SCHOOL
                else:
                    continue
                queued[(pid, k)].append((team, source, year, reason))

        conflicts = {key for key, v in queued.items() if any(r[3] == models.StatTeamLink.REASON_CONFLICT for r in v)}
        self.stdout.write(
            f"{len(queued)} player/team pairs to review on {len({pid for pid, _ in queued})} players "
            f"({len(conflicts)} pairs are same-season conflicts)"
        )

        shown = 0
        for (pid, k), v in sorted(queued.items(), key=lambda kv: ((kv[0] not in conflicts), players[kv[0][0]].name)):
            p = players[pid]
            if shown < options["limit"]:
                seasons = ", ".join(f"{src} {yr}" for _, src, yr, _ in sorted(v, key=lambda r: r[2]))
                self.stdout.write(f"  {p.name}: {v[0][0]} ({seasons})")
                shown += 1
            if dry:
                continue
            for team, source, year, reason in v:
                queue_link(p, p.name, team, year, source, reason)

        if dry:
            self.stdout.write(self.style.WARNING("Dry run: nothing queued."))
        else:
            self.stdout.write(self.style.SUCCESS("Queued. Review at /admin/stat-links/."))
