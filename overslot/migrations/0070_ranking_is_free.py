from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("overslot", "0069_mockdraftshare"),
    ]

    operations = [
        migrations.AddField(
            model_name="ranking",
            name="is_free",
            field=models.BooleanField(
                default=False,
                help_text="When checked, the full board is visible without a subscription. "
                "Unchecked (default) keeps content subscriber-only; mock drafts default to paid.",
            ),
        ),
    ]
