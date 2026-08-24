from django.contrib.auth.models import User
from django.core.management.base import BaseCommand

from overslot.name_spam import (
    name_contains_domain,
    user_is_protected,
    users_with_domain_in_name,
)


class Command(BaseCommand):
    help = (
        "Find users whose first or last name contains a domain (e.g. .com). "
        "Dry-run by default; pass --delete to remove matching unprotected accounts."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--delete",
            action="store_true",
            help="Delete matching unprotected users. Without this flag, only list them.",
        )
        parser.add_argument(
            "--include-protected",
            action="store_true",
            help="Also delete staff, superusers, authors, and users with an active subscription.",
        )

    def handle(self, *args, **options):
        do_delete = bool(options.get("delete"))
        include_protected = bool(options.get("include_protected"))

        matches = []
        skipped = []
        for user in users_with_domain_in_name().order_by("id"):
            if not name_contains_domain(user.first_name, user.last_name):
                continue
            reason = user_is_protected(user)
            if reason and not include_protected:
                skipped.append((user, reason))
                continue
            matches.append((user, reason))

        if not matches and not skipped:
            self.stdout.write(self.style.SUCCESS("No users with a domain in first/last name."))
            return

        if skipped:
            self.stdout.write(self.style.WARNING(f"Skipping {len(skipped)} protected account(s):"))
            for user, reason in skipped:
                self._write_user(user, suffix=f"  skip={reason}")
            self.stdout.write("")

        if not matches:
            self.stdout.write(self.style.SUCCESS("Nothing to delete."))
            return

        action = "Deleting" if do_delete else "Would delete"
        self.stdout.write(self.style.WARNING(f"{action} {len(matches)} user(s):"))
        for user, reason in matches:
            extra = f"  protected={reason}" if reason else ""
            self._write_user(user, suffix=extra)

        if not do_delete:
            self.stdout.write("")
            self.stdout.write("Dry run. Re-run with --delete to remove these accounts.")
            return

        ids = [user.id for user, _reason in matches]
        deleted_count, _ = User.objects.filter(id__in=ids).delete()
        self.stdout.write(self.style.SUCCESS(f"Deleted {deleted_count} row(s) (users plus related objects)."))

    def _write_user(self, user, suffix=""):
        self.stdout.write(
            f"  id={user.id}  email={user.email!r}  "
            f"first={user.first_name!r}  last={user.last_name!r}{suffix}"
        )
