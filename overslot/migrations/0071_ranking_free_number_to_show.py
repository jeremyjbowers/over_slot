from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("overslot", "0070_ranking_is_free"),
    ]

    operations = [
        migrations.AddField(
            model_name="ranking",
            name="free_number_to_show",
            field=models.PositiveIntegerField(
                default=5,
                help_text="How many players non-subscribers see in the subscription preview (full board requires subscription or is_free).",
            ),
        ),
    ]
