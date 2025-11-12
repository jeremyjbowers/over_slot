from django.db import migrations
from django.contrib.auth import get_user_model
from django.db import connection


def lowercase_existing_emails(apps, schema_editor):
    User = get_user_model()
    # Lowercase User email and username in Python to keep signals out of the equation
    for user in User.objects.all().only("id", "email", "username"):
        updated = False
        if user.email:
            lower_email = user.email.strip().lower()
            if user.email != lower_email:
                user.email = lower_email
                updated = True
        if user.username:
            lower_username = user.username.strip().lower()
            if user.username != lower_username:
                user.username = lower_username
                updated = True
        if updated:
            # Save without triggering potential side effects from related models
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


