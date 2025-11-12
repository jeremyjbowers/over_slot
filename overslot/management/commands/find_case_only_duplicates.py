from django.core.management.base import BaseCommand
from django.contrib.auth.models import User
from django.db.models import Count
from django.db.models.functions import Lower

from overslot.models import UserEmail


class Command(BaseCommand):
    help = "Find and print case-only duplicates for emails (and optionally usernames)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--skip-users",
            action="store_true",
            help="Skip scanning primary user emails in auth_user.",
        )
        parser.add_argument(
            "--skip-useremails",
            action="store_true",
            help="Skip scanning secondary emails in overslot_useremail.",
        )
        parser.add_argument(
            "--include-usernames",
            action="store_true",
            help="Also scan usernames in auth_user (email-as-username setups).",
        )
        parser.add_argument(
            "--include-identical",
            action="store_true",
            help="Include duplicates where casing is identical (not only case-only).",
        )

    def handle(self, *args, **options):
        include_identical = bool(options.get("include_identical"))
        skip_users = bool(options.get("skip_users"))
        skip_useremails = bool(options.get("skip_useremails"))
        include_usernames = bool(options.get("include_usernames"))

        any_output = False

        def print_group(header, groups, fetch_records):
            nonlocal any_output
            if not groups:
                return
            self.stdout.write(self.style.WARNING(header))
            for g in groups:
                key = g["key"]
                total = g["total"]
                distinct = g["distinct"]
                self.stdout.write(f"- key (lower): {key}  | total: {total}  | distinct casings: {distinct}")
                for rec in fetch_records(key):
                    self.stdout.write(f"    • id={rec['id']}  value='{rec['value']}'  is_active={rec.get('is_active')}")
            self.stdout.write("")  # blank line
            any_output = True

        # Users: primary emails
        if not skip_users:
            user_dupes_qs = (
                User.objects.exclude(email__isnull=True)
                .exclude(email__exact="")
                .values(key=Lower("email"))
                .annotate(total=Count("id"), distinct=Count("email", distinct=True))
                .filter(total__gt=1)
            )
            if not include_identical:
                user_dupes_qs = user_dupes_qs.filter(distinct__gt=1)

            def fetch_user_records(lower_key):
                rows = (
                    User.objects.filter(email__iexact=lower_key)
                    .values("id", "email", "is_active")
                    .order_by("id")
                )
                return [{"id": r["id"], "value": r["email"], "is_active": r["is_active"]} for r in rows]

            print_group(
                "Primary user email duplicates (auth_user):",
                list(user_dupes_qs.order_by("key")),
                fetch_user_records,
            )

        # Users: usernames (optional)
        if include_usernames:
            username_dupes_qs = (
                User.objects.exclude(username__isnull=True)
                .exclude(username__exact="")
                .values(key=Lower("username"))
                .annotate(total=Count("id"), distinct=Count("username", distinct=True))
                .filter(total__gt=1)
            )
            if not include_identical:
                username_dupes_qs = username_dupes_qs.filter(distinct__gt=1)

            def fetch_username_records(lower_key):
                rows = (
                    User.objects.filter(username__iexact=lower_key)
                    .values("id", "username", "is_active")
                    .order_by("id")
                )
                return [{"id": r["id"], "value": r["username"], "is_active": r["is_active"]} for r in rows]

            print_group(
                "Username duplicates (auth_user):",
                list(username_dupes_qs.order_by("key")),
                fetch_username_records,
            )

        # Secondary emails
        if not skip_useremails:
            ue_dupes_qs = (
                UserEmail.objects.exclude(email__isnull=True)
                .exclude(email__exact="")
                .values(key=Lower("email"))
                .annotate(total=Count("id"), distinct=Count("email", distinct=True))
                .filter(total__gt=1)
            )
            if not include_identical:
                ue_dupes_qs = ue_dupes_qs.filter(distinct__gt=1)

            def fetch_ue_records(lower_key):
                rows = (
                    UserEmail.objects.filter(email__iexact=lower_key)
                    .values("id", "email", "is_verified", "user_id")
                    .order_by("id")
                )
                return [
                    {
                        "id": r["id"],
                        "value": r["email"],
                        "is_active": f"user_id={r['user_id']} verified={r['is_verified']}",
                    }
                    for r in rows
                ]

            print_group(
                "Secondary email duplicates (overslot_useremail):",
                list(ue_dupes_qs.order_by("key")),
                fetch_ue_records,
            )

        if not any_output:
            if include_usernames:
                self.stdout.write(self.style.SUCCESS("No case-only duplicates found for emails or usernames."))
            else:
                self.stdout.write(self.style.SUCCESS("No case-only duplicates found for emails."))


