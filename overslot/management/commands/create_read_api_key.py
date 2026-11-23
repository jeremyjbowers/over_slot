# Mint a long-lived read API key for MCP / agent access.
from django.contrib.auth.models import User
from django.core.management.base import BaseCommand, CommandError

from overslot.models import ReadAPIKey


class Command(BaseCommand):
    help = (
        "Create a read API key for MCP access. "
        "Prints the key. The account can also see it on /account/api-keys/."
    )

    def add_arguments(self, parser):
        parser.add_argument("--email", help="Account email")
        parser.add_argument(
            "--label",
            default="mcp",
            help="Label for this key (for example, claude). Default: mcp",
        )
        parser.add_argument(
            "--list-users",
            action="store_true",
            help="List accounts and exit",
        )

    def handle(self, *args, **options):
        if options["list_users"]:
            for user in User.objects.order_by("email"):
                self.stdout.write(
                    f"{user.email or user.username}  staff={user.is_staff}  active={user.is_active}"
                )
            return

        email = (options.get("email") or "").strip()
        if not email:
            raise CommandError("Provide --email (or --list-users)")

        matches = list(User.objects.filter(email__iexact=email))
        if not matches:
            raise CommandError(f"No account with email {email}")
        if len(matches) > 1:
            raise CommandError(f"Ambiguous email match: {email}")

        user = matches[0]
        if not ReadAPIKey.account_is_paid(user):
            raise CommandError(
                "This account does not have an active subscription, so it cannot have a read API key."
            )
        if ReadAPIKey.active_for_user(user).count() >= ReadAPIKey.MAX_ACTIVE_PER_USER:
            raise CommandError(
                f"This account already has {ReadAPIKey.MAX_ACTIVE_PER_USER} active read keys."
            )

        raw, key = ReadAPIKey.create_key(user, label=options["label"])
        self.stdout.write(self.style.SUCCESS("Created read API key"))
        self.stdout.write(f"Account: {user.email}")
        self.stdout.write(f"Label:   {key.label}")
        self.stdout.write(f"Prefix:  {key.token_prefix}")
        self.stdout.write(raw)
        self.stdout.write(
            "The account can copy this key again from /account/api-keys/."
        )
