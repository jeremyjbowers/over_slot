from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('overslot', '0039_ranking_current'),
    ]

    operations = [
        migrations.AlterField(
            model_name='ranking',
            name='body',
            field=models.TextField(blank=True, null=True),
        ),
        migrations.AlterField(
            model_name='playerranking',
            name='scouting_report',
            field=models.TextField(blank=True, null=True),
        ),
        migrations.AlterField(
            model_name='article',
            name='body',
            field=models.TextField(blank=True, null=True),
        ),
    ]


