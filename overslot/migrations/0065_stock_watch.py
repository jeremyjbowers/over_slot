# Generated manually

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('overslot', '0064_game_is_carousel'),
    ]

    operations = [
        migrations.CreateModel(
            name='StockWatchArticle',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('active', models.BooleanField(default=True)),
                ('created', models.DateTimeField(auto_now_add=True, null=True)),
                ('last_modified', models.DateTimeField(auto_now=True, null=True)),
                ('headline', models.CharField(max_length=255)),
                ('deck', models.CharField(blank=True, help_text='Subhead or summary', max_length=500, null=True)),
                ('body', models.TextField(blank=True, null=True)),
                ('date', models.DateField(help_text='Publication date')),
                ('author', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='stock_watch_articles', to='overslot.author')),
            ],
            options={
                'ordering': ['-date', '-created'],
                'verbose_name': 'Stock Watch Article',
                'verbose_name_plural': 'Stock Watch Articles',
            },
        ),
        migrations.CreateModel(
            name='StockWatchPlayer',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('active', models.BooleanField(default=True)),
                ('created', models.DateTimeField(auto_now_add=True, null=True)),
                ('last_modified', models.DateTimeField(auto_now=True, null=True)),
                ('direction', models.CharField(choices=[('up', 'Stock Up'), ('down', 'Stock Down')], help_text='Stock up or stock down', max_length=10)),
                ('body', models.TextField(blank=True, help_text="Analysis for this player's stock movement", null=True)),
                ('player', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='stock_watch_entries', to='overslot.player')),
                ('stock_watch_article', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='stock_watch_players', to='overslot.stockwatcharticle')),
            ],
            options={
                'ordering': ['stock_watch_article', '-direction', 'player__name'],
                'verbose_name': 'Stock Watch Player',
                'verbose_name_plural': 'Stock Watch Players',
            },
        ),
    ]
