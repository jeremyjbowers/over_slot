from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('overslot', '0041_auto_add_hs_hitter_fields'),
    ]

    operations = [
        migrations.RenameField(
            model_name='playerranking',
            old_name='hs_contact_pct_above_median',
            new_name='hs_contact_pct_points_above_median',
        ),
        migrations.RenameField(
            model_name='playerranking',
            old_name='hs_chase_pct_above_median',
            new_name='hs_chase_pct_points_above_median',
        ),
        migrations.RenameField(
            model_name='playerranking',
            old_name='hs_iz_contact_pct_above_median',
            new_name='hs_iz_contact_pct_points_above_median',
        ),
        migrations.RenameField(
            model_name='playerranking',
            old_name='hs_ooz_contact_pct_above_median',
            new_name='hs_ooz_contact_pct_points_above_median',
        ),
        migrations.RenameField(
            model_name='playerranking',
            old_name='hs_k_pct_above_median',
            new_name='hs_k_pct_points_above_median',
        ),
        migrations.RenameField(
            model_name='playerranking',
            old_name='hs_gb_pct_above_median',
            new_name='hs_gb_pct_points_above_median',
        ),
        migrations.RenameField(
            model_name='playerranking',
            old_name='hs_fb_pct_above_median',
            new_name='hs_fb_pct_points_above_median',
        ),
        migrations.RenameField(
            model_name='playerranking',
            old_name='hs_air_pull_pct_above_median',
            new_name='hs_air_pull_pct_points_above_median',
        ),
        migrations.RenameField(
            model_name='playerranking',
            old_name='hs_sprint_speed_above_median',
            new_name='hs_sprint_speed_points_above_median',
        ),
        migrations.RenameField(
            model_name='playerranking',
            old_name='hs_bat_speed_above_median',
            new_name='hs_bat_speed_points_above_median',
        ),
        migrations.RenameField(
            model_name='playerranking',
            old_name='hs_avg_rot_acc_above_median',
            new_name='hs_avg_rot_acc_points_above_median',
        ),
        migrations.RenameField(
            model_name='playerranking',
            old_name='hs_peak_hand_speed_above_median',
            new_name='hs_peak_hand_speed_points_above_median',
        ),
        migrations.RenameField(
            model_name='playerranking',
            old_name='hs_force_plate_explosiveness_above_median',
            new_name='hs_force_plate_explosiveness_points_above_median',
        ),
    ]


