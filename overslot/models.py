import datetime
import os
import uuid

from dateutil.relativedelta import *
from django.contrib.auth.models import User
from django.db import models
from django.contrib.postgres.fields import JSONField, ArrayField
from django.db.models.signals import post_save, m2m_changed
from django.dispatch import receiver
from django.conf import settings
from django_prose_editor.fields import ProseEditorField
from django.utils.text import slugify

from overslot import utils


LEVEL_CHOICES = (
    ("College", "College"),
    ("High School", "High School"),
    ("International", "International"),
)

ROLE_CHOICES = (
    ("40", "40"),
    ("45", "45"),
    ("50", "50"),
    ("55", "55"),
    ("60", "60"),
    ("65", "65"),
    ("70", "70"),
    ("75", "75"),
    ("80", "80"),
)

class BaseModel(models.Model):
    """
    Base model for tracking create/update dates and also setting active.
    """
    active = models.BooleanField(default=True)
    created = models.DateTimeField(auto_now_add=True, blank=True, null=True)
    last_modified = models.DateTimeField(auto_now=True, blank=True, null=True)

    class Meta:
        abstract = True

    def __str__(self):
        return self.__unicode__()


class Player(BaseModel):
    """
    Canonical representation of a baseball player.
    Note: Position, school and country are denormalized versus PlayerRanking so that we can distinguish between players.
    """
    name = models.CharField(max_length=255)
    birthdate = models.DateField(blank=True, null=True)
    raw_age = models.IntegerField(default=None, blank=True, null=True)
    current_position = models.CharField(max_length=255, blank=True, null=True)
    current_school = models.CharField(max_length=255, blank=True, null=True)
    current_country = models.CharField(max_length=255, blank=True, null=True)
    mlb_id = models.CharField(max_length=255, blank=True, null=True)
    fg_id = models.CharField(max_length=255, blank=True, null=True)

    # publishing fields
    uuid = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    slug = models.SlugField(max_length=255, blank=True, null=True)
    regenerate_slug = models.BooleanField(default=False)
    scouting_report = ProseEditorField(
        extensions={
            # Core text formatting
            "Bold": True,
            "Italic": True,
            "Strike": True,
            "Underline": True,
            "HardBreak": True,

            # Structure
            "Heading": {
                "levels": [1, 2, 3, 4, 5]  # Only allow h1, h2, h3
            },
            "BulletList": True,
            "OrderedList": True,
            "Blockquote": True,
            "Table": True,

            # Editor capabilities
            "History": True,       # Enables undo/redo
            "HTML": True,          # Allows HTML view
            "Typographic": True,   # Enables typographic chars
        },
        sanitize=True,
        null=True,
        blank=True
    )

    def __unicode__(self):
        return self.name

    def save(self, *args, **kwargs):
        if self.regenerate_slug or not self.slug:
            self.slug = slugify(f"{self.name}-{self.uuid}")
            self.regenerate_slug = False

        super().save(*args, **kwargs)


class Ranking(BaseModel):
    """
    An instance of a ranking. Rankings are unique by date, by length, and if they are "final."
    """
    # ranking model data fields
    year = models.CharField(max_length=255)
    ranking_type = models.CharField(max_length=255, choices=LEVEL_CHOICES, blank=True, null=True)
    ranking_length = models.CharField(max_length=255, blank=True, null=True)
    is_final = models.BooleanField(default=False)
    is_draft = models.BooleanField(default=False)
    is_mock_draft = models.BooleanField(default=False)
    mock_draft_version = models.CharField(max_length=255, blank=True, null=True)

    # publishing fields
    headline = models.CharField(max_length=255, blank=True, null=True)
    uuid = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    slug = models.SlugField(max_length=255, blank=True, null=True)
    regenerate_slug = models.BooleanField(default=False)
    subhead = models.CharField(max_length=255, blank=True, null=True)
    blurb = models.CharField(max_length=255, blank=True, null=True)
    body = ProseEditorField(
        extensions={
            # Core text formatting
            "Bold": True,
            "Italic": True,
            "Strike": True,
            "Underline": True,
            "HardBreak": True,

            # Structure
            "Heading": {
                "levels": [1, 2, 3, 4, 5]  # Only allow h1, h2, h3
            },
            "BulletList": True,
            "OrderedList": True,
            "Blockquote": True,
            "Table": True,

            # Editor capabilities
            "History": True,       # Enables undo/redo
            "HTML": True,          # Allows HTML view
            "Typographic": True,   # Enables typographic chars
        },
        sanitize=True,
        null=True,
        blank=True
    )

    class Meta:
        ordering = ["-year", "is_final", "-ranking_length"]


    def get_playerrankings(self):
        return PlayerRanking.objects.filter(ranking=self).order_by("rank")


    def save(self, *args, **kwargs):
        if self.regenerate_slug or not self.slug:
            if self.headline:
                self.slug = slugify(f"{self.headline}-{self.uuid}")
            else:
                self.slug = slugify(f"{self.__unicode__()}-{self.uuid}")
    
            self.regenerate_slug = False

        super().save(*args, **kwargs)

    def __unicode__(self):
        payload = f"{self.year}"

        if self.is_draft:
            payload += " Draft"

        if self.is_mock_draft:
            payload += f" Mock Draft {self.mock_draft_version}"

        else:
            payload += f" Top {self.ranking_length}"
            if self.ranking_type:
                payload += f" {self.ranking_type} Players"

        return payload


class PlayerRankingCarryingTool(BaseModel):
    tool = models.CharField(max_length=255)
    score = models.CharField(max_length=5)
    description = models.CharField(max_length=255, blank=True, null=True)

    class Meta:
        ordering = ["tool", "-score"]

    def __unicode__(self):
        return f"{self.tool}: {self.score}"


class PlayerRanking(BaseModel):
    """
    An instance of a player in a ranking. This way players can have many ranks, tracking history.
    Note: Position, school and country are denormalized versus Player.
    """
    player = models.ForeignKey(Player, on_delete=models.SET_NULL, blank=True, null=True)
    ranking = models.ForeignKey(Ranking, on_delete=models.SET_NULL, blank=True, null=True)
    rank = models.IntegerField(blank=True, null=True)
    ranking_position = models.CharField(max_length=255, blank=True, null=True)
    ranking_school = models.CharField(max_length=255, blank=True, null=True)
    ranking_country = models.CharField(max_length=255, blank=True, null=True)
    level = models.CharField(max_length=255, choices=LEVEL_CHOICES, blank=True, null=True)

    role = models.CharField(max_length=10, choices=ROLE_CHOICES, blank=True, null=True)
    carrying_tools = models.ManyToManyField(PlayerRankingCarryingTool, blank=True)

    class Meta:
        ordering = ['ranking', 'rank']

    def __unicode__(self):
        return f"({self.rank}) {self.player} in {self.ranking}"


class Article(BaseModel):
    headline = models.CharField(max_length=255, blank=True, null=True)
    subhead = models.CharField(max_length=255, blank=True, null=True)
    blurb = models.CharField(max_length=255, blank=True, null=True)

    players = models.ManyToManyField(Player, blank=True)

    body = ProseEditorField(
        extensions={
            # Core text formatting
            "Bold": True,
            "Italic": True,
            "Strike": True,
            "Underline": True,
            "HardBreak": True,

            # Structure
            "Heading": {
                "levels": [1, 2, 3, 4, 5]  # Only allow h1, h2, h3
            },
            "BulletList": True,
            "OrderedList": True,
            "Blockquote": True,
            "Table": True,

            # Editor capabilities
            "History": True,       # Enables undo/redo
            "HTML": True,          # Allows HTML view
            "Typographic": True,   # Enables typographic chars
        },
        sanitize=True,
        null=True,
        blank=True
    )
    uuid = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    slug = models.SlugField(max_length=255, blank=True, null=True)
    regenerate_slug = models.BooleanField(default=False)

    publish = models.BooleanField(default=False)

    class Meta:
        ordering = ["-created"]

    def save(self, *args, **kwargs):
        if self.regenerate_slug or not self.slug:
            self.slug = slugify(f"{self.headline}-{self.uuid}")
            self.regenerate_slug = False

        super().save(*args, **kwargs)

    def __unicode__(self):
        return self.headline