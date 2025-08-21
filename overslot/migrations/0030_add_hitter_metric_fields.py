from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('overslot', '0029_alter_player_photo_url_and_more'),
    ]

    operations = [
        migrations.AddField(
            model_name='playerranking',
            name='whiff_pct',
            field=models.FloatField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='playerranking',
            name='whiff_pct_percentile',
            field=models.FloatField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='playerranking',
            name='iz_whiff_pct',
            field=models.FloatField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='playerranking',
            name='iz_whiff_pct_percentile',
            field=models.FloatField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='playerranking',
            name='ooz_whiff_pct',
            field=models.FloatField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='playerranking',
            name='ooz_whiff_pct_percentile',
            field=models.FloatField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='playerranking',
            name='chase_pct',
            field=models.FloatField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='playerranking',
            name='chase_pct_percentile',
            field=models.FloatField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='playerranking',
            name='k_pct',
            field=models.FloatField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='playerranking',
            name='k_pct_percentile',
            field=models.FloatField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='playerranking',
            name='bb_pct',
            field=models.FloatField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='playerranking',
            name='bb_pct_percentile',
            field=models.FloatField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='playerranking',
            name='avg_exit_velocity',
            field=models.FloatField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='playerranking',
            name='avg_exit_velocity_percentile',
            field=models.FloatField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='playerranking',
            name='ev_90th',
            field=models.FloatField(blank=True, null=True),
        ),
        migrations.SeparateDatabaseAndState(
            database_operations=[
                migrations.RunSQL(
                    sql='ALTER TABLE overslot_playerranking ADD COLUMN IF NOT EXISTS ev_90th_percentile double precision;',
                    reverse_sql='ALTER TABLE overslot_playerranking DROP COLUMN IF EXISTS ev_90th_percentile;'
                )
            ],
            state_operations=[
                migrations.AddField(
                    model_name='playerranking',
                    name='ev_90th_percentile',
                    field=models.FloatField(blank=True, null=True),
                )
            ]
        ),
        migrations.AddField(
            model_name='playerranking',
            name='barrel_pct',
            field=models.FloatField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='playerranking',
            name='barrel_pct_percentile',
            field=models.FloatField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='playerranking',
            name='pull_air_pct',
            field=models.FloatField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='playerranking',
            name='pull_air_pct_percentile',
            field=models.FloatField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='playerranking',
            name='xwoba',
            field=models.FloatField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='playerranking',
            name='xwoba_percentile',
            field=models.FloatField(blank=True, null=True),
        ),
    ]


