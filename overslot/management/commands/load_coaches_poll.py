"""
Load NCAA Baseball Coaches Poll from USA Today Sports and set Team.current_ranking.

Fetches https://sportsdata.usatoday.com/baseball/cbb/coaches-poll and parses
the __NEXT_DATA__ JSON to extract the Top 25. Matches teams by name and sets
current_ranking. Teams not in the poll have current_ranking cleared.
"""
import json
import re
import requests
from django.core.management.base import BaseCommand

from overslot import models
from overslot.utils import find_team_by_school_name

COACHES_POLL_URL = "https://sportsdata.usatoday.com/baseball/cbb/coaches-poll"


class Command(BaseCommand):
    help = "Load USA Today Coaches Poll and set Team.current_ranking for top 25 teams"

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Don't save changes, just show what would be updated",
        )
        parser.add_argument(
            "--url",
            type=str,
            default=COACHES_POLL_URL,
            help="Override the coaches poll URL (default: USA Today)",
        )

    def handle(self, *args, **options):
        dry_run = options.get("dry_run", False)
        url = options.get("url", COACHES_POLL_URL)

        self.stdout.write(f"Fetching coaches poll from {url}...")

        try:
            response = requests.get(url, timeout=30)
            response.raise_for_status()
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"Failed to fetch: {e}"))
            return

        team_ranks = self._parse_poll(response.text)
        if not team_ranks:
            self.stdout.write(self.style.ERROR("Could not parse poll data from page."))
            return

        self.stdout.write(f"Found {len(team_ranks)} teams in poll.")

        updated = 0
        matched = 0
        unmatched = []

        # Clear all current_ranking first (teams that dropped out get cleared)
        if not dry_run:
            cleared = models.Team.objects.filter(
                current_ranking__isnull=False, active=True
            ).update(current_ranking=None)
            if cleared:
                self.stdout.write(
                    f"Cleared ranking for {cleared} team(s) before applying poll."
                )

        for entry in team_ranks:
            rank = entry.get("rank")
            team_name = entry.get("teamName") or ""
            full_name = ""
            if isinstance(entry.get("team"), dict):
                full_name = entry["team"].get("teamName", "")

            if not rank or not team_name:
                continue

            # Try to find our team: teamName, full name, and stripped variants (e.g. "Miami (FL)" -> "Miami")
            names_to_try = [team_name]
            if full_name and full_name != team_name:
                names_to_try.append(full_name)
            # Strip parenthetical suffixes like "(FL)" for fuzzy matching
            if "(" in team_name:
                base = team_name.split("(")[0].strip()
                if base and base not in names_to_try:
                    names_to_try.append(base)

            team = None
            for name in names_to_try:
                team = find_team_by_school_name(name)
                if team:
                    break

            if team:
                matched += 1
                if not dry_run:
                    previous = team.current_ranking
                    team.current_ranking = rank
                    team.save(update_fields=["current_ranking"])
                    if previous != rank:
                        updated += 1
                        self.stdout.write(
                            f"  #{rank}: {team_name} -> {team.name} "
                            f"(was {previous})"
                        )
                else:
                    updated += 1
                    self.stdout.write(
                        f"  [DRY RUN] #{rank}: {team_name} -> would match {team.name}"
                    )
            else:
                unmatched.append(f"#{rank} {team_name}")

        if dry_run:
            self.stdout.write(self.style.WARNING("DRY RUN - no changes saved."))

        self.stdout.write(
            self.style.SUCCESS(
                f"Done. Matched: {matched}, Updated: {updated}"
            )
        )
        if unmatched:
            self.stdout.write(
                self.style.WARNING(f"Unmatched ({len(unmatched)}): {', '.join(unmatched[:10])}")
            )
            if len(unmatched) > 10:
                self.stdout.write(f"  ... and {len(unmatched) - 10} more")

    def _parse_poll(self, html):
        """Extract teamRanks from __NEXT_DATA__ JSON in the page."""
        m = re.search(
            r'<script id="__NEXT_DATA__" type="application/json">(.*?)</script>',
            html,
            re.DOTALL,
        )
        if not m:
            return []

        try:
            data = json.loads(m.group(1))
            poll_details = (
                data.get("props", {})
                .get("pageProps", {})
                .get("fallback", {})
                .get("pollDetails", {})
            )
            return poll_details.get("teamRanks", [])
        except (json.JSONDecodeError, KeyError, TypeError):
            return []
