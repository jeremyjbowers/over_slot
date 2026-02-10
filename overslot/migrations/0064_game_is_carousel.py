# Generated manually

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('overslot', '0063_game_featured'),
    ]

    operations = [
        migrations.AddField(
            model_name='game',
            name='is_carousel',
            field=models.BooleanField(default=False, help_text='Display this game in the homepage carousel'),
        ),
    ]
