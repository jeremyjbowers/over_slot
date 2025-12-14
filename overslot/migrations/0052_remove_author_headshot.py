# Generated manually

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('overslot', '0051_make_author_email_optional'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='author',
            name='headshot',
        ),
    ]
