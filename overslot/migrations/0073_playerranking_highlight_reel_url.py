from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("overslot", "0072_collection"),
    ]

    operations = [
        migrations.AddField(
            model_name="playerranking",
            name="highlight_reel_url",
            field=models.TextField(
                blank=True,
                null=True,
                help_text="Highlight reel URL (e.g. from draft sheet draft_highlight_reel column)",
            ),
        ),
    ]
