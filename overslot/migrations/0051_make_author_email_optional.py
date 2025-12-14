# Generated manually

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('overslot', '0050_article_is_free_author_founder_author_headshot'),
    ]

    operations = [
        migrations.AlterField(
            model_name='author',
            name='email',
            field=models.EmailField(blank=True, help_text="Public contact email (if different from login email). If not set, uses user's email.", null=True),
        ),
    ]
