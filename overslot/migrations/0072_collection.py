from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("overslot", "0071_ranking_free_number_to_show"),
    ]

    operations = [
        migrations.CreateModel(
            name="Collection",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("active", models.BooleanField(default=True)),
                ("created", models.DateTimeField(auto_now_add=True, null=True)),
                ("last_modified", models.DateTimeField(auto_now=True, null=True)),
                ("title", models.CharField(max_length=255)),
                (
                    "deck",
                    models.CharField(
                        blank=True,
                        help_text="Subtitle or dek displayed with the title",
                        max_length=500,
                        null=True,
                    ),
                ),
                ("slug", models.SlugField(max_length=255, unique=True)),
                (
                    "show_on_homepage",
                    models.BooleanField(
                        default=False,
                        help_text="Include this collection in the homepage module (layout TBD).",
                    ),
                ),
                (
                    "articles",
                    models.ManyToManyField(blank=True, related_name="collections", to="overslot.article"),
                ),
            ],
            options={
                "ordering": ["-last_modified"],
                "verbose_name_plural": "Collections",
            },
        ),
    ]
