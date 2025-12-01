from django.db import migrations
from django.contrib.auth import get_user_model
from django.db import connection


def lowercase_existing_emails(apps, schema_editor):
    """
    Normalize email and username to lowercase and resolve case-insensitive duplicates
    preemptively so that creating unique CI indexes does not fail.
    Strategy:
      - Keep the earliest user (smallest id) as the canonical owner of a value.
      - For any later user that would collide, append a deterministic "+dup<ID>" tag
        before the '@' for emails, and for usernames:
          * if it looks like an email, use the same "+dup<ID>" strategy
          * else append "-dup<ID>".
    """
    User = get_user_model()
    users = list(User.objects.all().only("id", "email", "username").order_by("id"))

    seen_email = {}
    seen_username = {}

    def make_email_unique(base_email: str, user_id: int) -> str:
        if not base_email:
            return base_email
        parts = base_email.split("@", 1)
        if len(parts) == 2:
            local, domain = parts
            return f"{local}+dup{user_id}@{domain}"
        # Fallback if somehow not an email
        return f"{base_email}+dup{user_id}"

    def make_username_unique(base_username: str, user_id: int) -> str:
        if not base_username:
            return base_username
        if "@" in base_username:
            return make_email_unique(base_username, user_id)
        return f"{base_username}-dup{user_id}"

    for user in users:
        updated = False

        # Normalize email
        if user.email:
            lower_email = user.email.strip().lower()
            candidate_email = lower_email
            if candidate_email in seen_email and seen_email[candidate_email] != user.id:
                candidate_email = make_email_unique(candidate_email, user.id)
            if user.email != candidate_email:
                user.email = candidate_email
                updated = True
            seen_email[candidate_email] = seen_email.get(candidate_email, user.id)

        # Normalize username
        if user.username:
            lower_username = user.username.strip().lower()
            candidate_username = lower_username
            if candidate_username in seen_username and seen_username[candidate_username] != user.id:
                candidate_username = make_username_unique(candidate_username, user.id)
            if user.username != candidate_username:
                user.username = candidate_username
                updated = True
            seen_username[candidate_username] = seen_username.get(candidate_username, user.id)

        if updated:
            user.save(update_fields=["email", "username"])

    UserEmail = apps.get_model("overslot", "UserEmail")
    for ue in UserEmail.objects.all().only("id", "email"):
        if ue.email:
            lower_email = ue.email.strip().lower()
            if ue.email != lower_email:
                ue.email = lower_email
                ue.save(update_fields=["email"])


class Migration(migrations.Migration):
    atomic = False  # Required to allow concurrent index creation in Postgres if needed

    dependencies = [
        ("overslot", "0044_featureflag"),
    ]

    operations = [
        migrations.RunPython(lowercase_existing_emails, migrations.RunPython.noop),
        migrations.RunSQL(
            sql="""
            -- Users: unique case-insensitive email
            DO $$
            BEGIN
                IF NOT EXISTS (
                    SELECT 1 FROM pg_class c
                    JOIN pg_namespace n ON n.oid = c.relnamespace
                    WHERE c.relname = 'auth_user_email_ci_uniq' AND n.nspname = 'public'
                ) THEN
                    CREATE UNIQUE INDEX auth_user_email_ci_uniq ON auth_user (LOWER(email));
                END IF;
            END$$;
            """,
            reverse_sql="""
            DROP INDEX IF EXISTS auth_user_email_ci_uniq;
            """,
        ),
        migrations.RunSQL(
            sql="""
            -- Users: unique case-insensitive username (email-backed usernames)
            DO $$
            BEGIN
                IF NOT EXISTS (
                    SELECT 1 FROM pg_class c
                    JOIN pg_namespace n ON n.oid = c.relnamespace
                    WHERE c.relname = 'auth_user_username_ci_uniq' AND n.nspname = 'public'
                ) THEN
                    CREATE UNIQUE INDEX auth_user_username_ci_uniq ON auth_user (LOWER(username));
                END IF;
            END$$;
            """,
            reverse_sql="""
            DROP INDEX IF EXISTS auth_user_username_ci_uniq;
            """,
        ),
        migrations.RunSQL(
            sql="""
            -- Secondary emails: unique case-insensitive
            DO $$
            BEGIN
                IF NOT EXISTS (
                    SELECT 1 FROM pg_class c
                    JOIN pg_namespace n ON n.oid = c.relnamespace
                    WHERE c.relname = 'overslot_useremail_email_ci_uniq' AND n.nspname = 'public'
                ) THEN
                    CREATE UNIQUE INDEX overslot_useremail_email_ci_uniq ON overslot_useremail (LOWER(email));
                END IF;
            END$$;
            """,
            reverse_sql="""
            DROP INDEX IF EXISTS overslot_useremail_email_ci_uniq;
            """,
        ),
    ]


