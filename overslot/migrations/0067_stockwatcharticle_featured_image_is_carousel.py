# Generated manually

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('overslot', '0066_stockwatcharticle_slug_publish'),
    ]

    operations = [
        migrations.AddField(
            model_name='stockwatcharticle',
            name='featured_image',
            field=models.ImageField(blank=True, help_text='Featured image for the article', null=True, upload_to='stock_watch/featured/'),
        ),
        migrations.AddField(
            model_name='stockwatcharticle',
            name='is_carousel',
            field=models.BooleanField(default=False, help_text='Display in homepage carousel'),
        ),
    ]
