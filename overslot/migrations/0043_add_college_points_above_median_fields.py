from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('overslot', '0042_rename_hs_delta_fields_to_points'),
    ]

    operations = [
        migrations.AddField(
            model_name='playerranking',
            name='whiff_pct_points_above_median',
            field=models.FloatField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='playerranking',
            name='iz_whiff_pct_points_above_median',
            field=models.FloatField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='playerranking',
            name='ooz_whiff_pct_points_above_median',
            field=models.FloatField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='playerranking',
            name='chase_pct_points_above_median',
            field=models.FloatField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='playerranking',
            name='k_pct_points_above_median',
            field=models.FloatField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='playerranking',
            name='bb_pct_points_above_median',
            field=models.FloatField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='playerranking',
            name='avg_exit_velocity_points_above_median',
            field=models.FloatField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='playerranking',
            name='ev_90th_points_above_median',
            field=models.FloatField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='playerranking',
            name='barrel_pct_points_above_median',
            field=models.FloatField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='playerranking',
            name='pull_air_pct_points_above_median',
            field=models.FloatField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='playerranking',
            name='xwoba_points_above_median',
            field=models.FloatField(blank=True, null=True),
        ),
    ]


