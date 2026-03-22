# Generated manually for MockDraftShare

import uuid

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('overslot', '0068_alter_stockwatchplayer_direction_and_more'),
    ]

    operations = [
        migrations.CreateModel(
            name='MockDraftShare',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('payload', models.BinaryField()),
                ('created_at', models.DateTimeField(auto_now_add=True)),
            ],
        ),
    ]
