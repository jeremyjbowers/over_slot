# Generated manually

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('overslot', '0048_playerstatseason'),
    ]

    operations = [
        migrations.AddField(
            model_name='playerstatseason',
            name='draft_year',
            field=models.CharField(blank=True, help_text='Draft year for this player (e.g., 2025)', max_length=10, null=True),
        ),
        migrations.AddField(
            model_name='playerstatseason',
            name='school',
            field=models.CharField(blank=True, help_text='School/Team name for this stat season', max_length=255, null=True),
        ),
    ]
