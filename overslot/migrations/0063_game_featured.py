# Generated manually

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('overslot', '0062_add_teams_to_article'),
    ]

    operations = [
        migrations.AddField(
            model_name='game',
            name='featured',
            field=models.BooleanField(default=False, help_text='Feature this game prominently on the games list page'),
        ),
    ]
