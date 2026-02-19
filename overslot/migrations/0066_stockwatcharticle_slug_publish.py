# Generated manually

import uuid
from django.db import migrations, models
from django.db.models import Q
from django.utils.text import slugify


def populate_slugs(apps, schema_editor):
    StockWatchArticle = apps.get_model('overslot', 'StockWatchArticle')
    for article in StockWatchArticle.objects.filter(Q(slug__isnull=True) | Q(slug='')):
        article.slug = slugify(f"{article.headline}-{article.uuid}")
        article.save(update_fields=['slug'])


class Migration(migrations.Migration):

    dependencies = [
        ('overslot', '0065_stock_watch'),
    ]

    operations = [
        migrations.AddField(
            model_name='stockwatcharticle',
            name='uuid',
            field=models.UUIDField(default=uuid.uuid4, editable=False),
        ),
        migrations.AddField(
            model_name='stockwatcharticle',
            name='slug',
            field=models.SlugField(blank=True, max_length=255, null=True),
        ),
        migrations.AddField(
            model_name='stockwatcharticle',
            name='regenerate_slug',
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name='stockwatcharticle',
            name='publish',
            field=models.BooleanField(default=False, help_text='Controls visibility on site'),
        ),
        migrations.RunPython(populate_slugs, migrations.RunPython.noop),
    ]
