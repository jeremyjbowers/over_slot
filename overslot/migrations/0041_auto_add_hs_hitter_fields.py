from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('overslot', '0040_replace_prose_with_text'),
    ]

    operations = [
        # Actuals
        migrations.AddField(
            model_name='playerranking',
            name='hs_pa',
            field=models.FloatField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='playerranking',
            name='hs_ba',
            field=models.FloatField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='playerranking',
            name='hs_obp',
            field=models.FloatField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='playerranking',
            name='hs_slg',
            field=models.FloatField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='playerranking',
            name='hs_ops',
            field=models.FloatField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='playerranking',
            name='hs_iso',
            field=models.FloatField(blank=True, null=True),
        ),

        # Percentiles and deltas
        migrations.AddField(
            model_name='playerranking',
            name='hs_contact_pct_percentile',
            field=models.FloatField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='playerranking',
            name='hs_contact_pct_above_median',
            field=models.FloatField(blank=True, null=True),
        ),

        migrations.AddField(
            model_name='playerranking',
            name='hs_chase_pct_percentile',
            field=models.FloatField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='playerranking',
            name='hs_chase_pct_above_median',
            field=models.FloatField(blank=True, null=True),
        ),

        migrations.AddField(
            model_name='playerranking',
            name='hs_iz_contact_pct_percentile',
            field=models.FloatField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='playerranking',
            name='hs_iz_contact_pct_above_median',
            field=models.FloatField(blank=True, null=True),
        ),

        migrations.AddField(
            model_name='playerranking',
            name='hs_ooz_contact_pct_percentile',
            field=models.FloatField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='playerranking',
            name='hs_ooz_contact_pct_above_median',
            field=models.FloatField(blank=True, null=True),
        ),

        migrations.AddField(
            model_name='playerranking',
            name='hs_k_pct_percentile',
            field=models.FloatField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='playerranking',
            name='hs_k_pct_above_median',
            field=models.FloatField(blank=True, null=True),
        ),

        migrations.AddField(
            model_name='playerranking',
            name='hs_gb_pct_percentile',
            field=models.FloatField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='playerranking',
            name='hs_gb_pct_above_median',
            field=models.FloatField(blank=True, null=True),
        ),

        migrations.AddField(
            model_name='playerranking',
            name='hs_fb_pct_percentile',
            field=models.FloatField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='playerranking',
            name='hs_fb_pct_above_median',
            field=models.FloatField(blank=True, null=True),
        ),

        migrations.AddField(
            model_name='playerranking',
            name='hs_air_pull_pct_percentile',
            field=models.FloatField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='playerranking',
            name='hs_air_pull_pct_above_median',
            field=models.FloatField(blank=True, null=True),
        ),

        migrations.AddField(
            model_name='playerranking',
            name='hs_sprint_speed_percentile',
            field=models.FloatField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='playerranking',
            name='hs_sprint_speed_above_median',
            field=models.FloatField(blank=True, null=True),
        ),

        migrations.AddField(
            model_name='playerranking',
            name='hs_bat_speed_percentile',
            field=models.FloatField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='playerranking',
            name='hs_bat_speed_above_median',
            field=models.FloatField(blank=True, null=True),
        ),

        migrations.AddField(
            model_name='playerranking',
            name='hs_avg_rot_acc_percentile',
            field=models.FloatField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='playerranking',
            name='hs_avg_rot_acc_above_median',
            field=models.FloatField(blank=True, null=True),
        ),

        migrations.AddField(
            model_name='playerranking',
            name='hs_peak_hand_speed_percentile',
            field=models.FloatField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='playerranking',
            name='hs_peak_hand_speed_above_median',
            field=models.FloatField(blank=True, null=True),
        ),

        migrations.AddField(
            model_name='playerranking',
            name='hs_force_plate_explosiveness_percentile',
            field=models.FloatField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='playerranking',
            name='hs_force_plate_explosiveness_above_median',
            field=models.FloatField(blank=True, null=True),
        ),
    ]


