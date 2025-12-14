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
from django.utils.text import slugify
from django.utils.crypto import get_random_string

from overslot import utils


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


class UserEmail(BaseModel):
    """
    Model to store additional email addresses for user accounts.
    Users can have multiple verified email addresses for login.
    """
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='additional_emails')
    email = models.EmailField(unique=True, help_text="Additional email address for this user")
    is_verified = models.BooleanField(default=False, help_text="Whether this email has been verified")
    verification_token = models.CharField(max_length=64, blank=True, null=True, help_text="Token for email verification")
    
    class Meta:
        ordering = ['email']
        verbose_name = "User Email"
        verbose_name_plural = "User Emails"
    
    def save(self, *args, **kwargs):
        # Normalize email to lowercase for consistent storage and comparisons
        if self.email:
            self.email = self.email.strip().lower()
        super().save(*args, **kwargs)
    
    def __unicode__(self):
        verified_status = "✓" if self.is_verified else "✗"
        return f"{self.user.username} - {self.email} {verified_status}"
    
    def generate_verification_token(self):
        """Generate a unique verification token for this email"""
        self.verification_token = get_random_string(64)
        self.save()
        return self.verification_token
    
    @classmethod
    def find_user_by_email(cls, email):
        """
        Find a user by email address, checking both primary and secondary emails.
        Returns the User object if found, None otherwise.
        """
        email = (email or "").strip().lower()
        # First check primary email
        try:
            return User.objects.get(email=email)
        except User.DoesNotExist:
            pass
        
        # Then check secondary emails (only verified ones for login)
        try:
            user_email = cls.objects.get(email=email, is_verified=True)
            return user_email.user
        except cls.DoesNotExist:
            return None


class Subscription(BaseModel):
    """
    Model to track user subscriptions linked to Stripe.
    """
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='subscription')
    stripe_customer_id = models.CharField(max_length=255, unique=True, blank=True, null=True)
    stripe_subscription_id = models.CharField(max_length=255, blank=True, null=True)
    
    # Subscription status from Stripe
    status = models.CharField(max_length=50, default='inactive')  # active, canceled, incomplete, etc.
    current_period_start = models.DateTimeField(blank=True, null=True)
    current_period_end = models.DateTimeField(blank=True, null=True)
    
    # Subscription details
    plan_name = models.CharField(max_length=100, blank=True, null=True)
    price_id = models.CharField(max_length=255, blank=True, null=True)
    
    def __unicode__(self):
        return f"{self.user.email} - {self.status}"
    
    @property
    def is_active(self):
        """Check if the subscription is currently active."""
        return self.status == 'active'
    
    @property
    def is_trial(self):
        """Check if the subscription is in trial period."""
        return self.status in ['trialing', 'active'] and self.current_period_start and self.current_period_end
    
    def can_access_premium_content(self):
        """Determine if user can access premium content."""
        return self.is_active or self.is_trial


# --- New subscription pricing models ---
class SubscriptionPlan(BaseModel):
    """
    Represents a purchasable plan (e.g., Standard membership). Prices (monthly/annual) are separate rows.
    """
    slug = models.SlugField(max_length=100, unique=True, help_text="Stable key, e.g., 'standard'")
    name = models.CharField(max_length=255, help_text="Display name, e.g., 'Overslot Membership'")
    description = models.TextField(blank=True, null=True)
    stripe_product_id = models.CharField(max_length=255, blank=True, null=True, help_text="Optional Stripe product id (prod_...)")
    sort_order = models.IntegerField(default=0)

    class Meta:
        ordering = ["sort_order", "slug"]
        verbose_name = "Subscription Plan"
        verbose_name_plural = "Subscription Plans"

    def __unicode__(self):
        return self.name or self.slug


class SubscriptionPrice(BaseModel):
    """
    A specific Stripe price for a plan and interval. Multiple historical prices can exist;
    one active default per plan+interval should be maintained.
    """
    INTERVAL_CHOICES = (
        ("month", "Monthly"),
        ("year", "Yearly"),
    )

    plan = models.ForeignKey(SubscriptionPlan, on_delete=models.CASCADE, related_name="prices")
    stripe_price_id = models.CharField(max_length=255, unique=True, help_text="Stripe price id (price_...)")
    currency = models.CharField(max_length=10, default="usd")
    interval = models.CharField(max_length=10, choices=INTERVAL_CHOICES)
    amount_decimal = models.DecimalField(max_digits=10, decimal_places=2)

    # Flags
    is_active = models.BooleanField(default=True)
    is_default_for_interval = models.BooleanField(
        default=False,
        help_text="Mark the default selectable price for this plan+interval"
    )

    trial_period_days = models.IntegerField(blank=True, null=True)
    tax_behavior = models.CharField(max_length=20, blank=True, null=True, help_text="inclusive|exclusive (optional)")

    class Meta:
        ordering = ["plan__sort_order", "plan__slug", "interval", "-created"]
        verbose_name = "Subscription Price"
        verbose_name_plural = "Subscription Prices"
        indexes = [
            models.Index(fields=["plan", "interval", "is_active", "is_default_for_interval"]),
        ]

    def __unicode__(self):
        return f"{self.plan.slug} {self.interval} {self.currency} {self.amount_decimal} ({self.stripe_price_id})"

    def save(self, *args, **kwargs):
        """
        Enforce single default per plan+interval by un-setting others when this becomes default.
        """
        super_result = None
        # We have to save first to ensure we have a PK for update queries when toggling defaults
        if self.pk is None:
            super_result = super().save(*args, **kwargs)
        
        if self.is_default_for_interval and self.is_active and self.plan_id:
            SubscriptionPrice.objects.filter(
                plan_id=self.plan_id,
                interval=self.interval,
                is_default_for_interval=True
            ).exclude(pk=self.pk).update(is_default_for_interval=False)
        
        # If deactivating a default, try to keep at least one default if any active price exists
        if not self.is_active and self.is_default_for_interval:
            # Remove default flag on self; caller should set another default explicitly
            self.is_default_for_interval = False
        
        # Final save to persist any flag changes
        return super().save(*args, **kwargs)


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

class Player(BaseModel):
    """
    Canonical representation of a baseball player.
    Note: Position, school and country are denormalized versus PlayerRanking so that we can distinguish between players.
    """
    name = models.CharField(max_length=255)
    birthdate = models.DateField(blank=True, null=True)
    raw_age = models.IntegerField(default=None, blank=True, null=True)
    position = models.CharField(max_length=255, blank=True, null=True)
    school = models.CharField(max_length=255, blank=True, null=True)
    hometown = models.CharField(max_length=255, blank=True, null=True)
    state = models.CharField(max_length=255, blank=True, null=True)
    country = models.CharField(max_length=255, blank=True, null=True)
    height = models.CharField(max_length=255, blank=True, null=True)
    weight = models.CharField(max_length=255, blank=True, null=True)
    bats = models.CharField(max_length=255, blank=True, null=True)
    throws = models.CharField(max_length=255, blank=True, null=True)

    # multimedia
    photo_url = models.TextField(blank=True, null=True)
    video_url = models.CharField(max_length=255, blank=True, null=True)

    # identifiers
    uuid = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    mlb_id = models.CharField(max_length=255, blank=True, null=True)
    fg_id = models.CharField(max_length=255, blank=True, null=True)

    # publishing fields
    slug = models.SlugField(max_length=255, blank=True, null=True)
    regenerate_slug = models.BooleanField(default=False)

    def __unicode__(self):
        player_string = f"{self.name}"
        if self.school:
            player_string += f" ({self.school})"

        if self.position:
            player_string += f" - {self.position}"

        return player_string

    def save(self, *args, **kwargs):
        if self.regenerate_slug or not self.slug:
            self.slug = slugify(f"{self.name}-{self.uuid}")
            self.regenerate_slug = False

        super().save(*args, **kwargs)


class Ranking(BaseModel):
    """
    An instance of a ranking. Rankings are unique by date, by length, and if they are "final."
    """
    LEVEL_CHOICES = (
        ("Overall", "Overall"),
        ("High School", "High School"),
        ("College", "College"),
    )

    # ranking model data fields
    year = models.CharField(max_length=255)
    ranking_type = models.CharField(max_length=255, choices=LEVEL_CHOICES, blank=True, null=True)
    ranking_length = models.CharField(max_length=255, blank=True, null=True)
    is_final = models.BooleanField(default=False)
    is_draft = models.BooleanField(default=False)
    is_mock_draft = models.BooleanField(default=False)
    mock_draft_version = models.CharField(max_length=255, blank=True, null=True)
    draft_level = models.CharField(max_length=255, choices=LEVEL_CHOICES, blank=True, null=True)

    # publishing fields
    headline = models.CharField(max_length=255, blank=True, null=True)
    custom_title = models.CharField(max_length=255, blank=True, null=True, help_text="Optional override for display title. Does not affect URL.")
    uuid = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    slug = models.SlugField(max_length=255, blank=True, null=True)
    regenerate_slug = models.BooleanField(default=False)
    current = models.BooleanField(default=True, help_text="Mark as current to include in current rankings; uncheck to archive.")
    subhead = models.CharField(max_length=255, blank=True, null=True)
    blurb = models.CharField(max_length=255, blank=True, null=True)
    featured_image = models.ImageField(upload_to='rankings/featured/', blank=True, null=True, help_text="Featured image for the ranking")
    publish = models.BooleanField(default=False)
    is_carousel = models.BooleanField(default=False, help_text="Display in homepage carousel")
    body = models.TextField(null=True, blank=True)

    class Meta:
        ordering = ["-year", "is_final", "-ranking_length"]

    def get_playerrankings(self):
        return PlayerRanking.objects.filter(ranking=self, active=True).order_by("rank")

    def get_initial_players(self):
        return PlayerRanking.objects.filter(ranking=self, active=True, rank__lte=10).order_by("rank")

    def save(self, *args, **kwargs):
        if self.regenerate_slug or not self.slug:
            if self.headline:
                self.slug = slugify(f"{self.headline}-{self.uuid}")
            else:
                # IMPORTANT: Do not base slug on custom_title so URLs remain stable
                self.slug = slugify(f"{self._get_default_computed_title()}-{self.uuid}")
    
            self.regenerate_slug = False

        super().save(*args, **kwargs)

    def get_computed_title(self):
        if self.custom_title:
            return self.custom_title

        return self._get_default_computed_title()

    def _get_default_computed_title(self):
        """Computed title that ignores custom_title. Used for slugs and fallback display."""
        parts = [str(self.year).strip()] if self.year else []
        if self.draft_level:
            parts.append(self.draft_level)
        title = " ".join(p for p in parts if p and p.lower() != 'none')

        # For mock drafts, don't append plain "Draft" to avoid "Draft Mock Draft"
        if self.is_mock_draft:
            if title:
                title += f" Mock Draft {self.mock_draft_version}"
            else:
                title = f"Mock Draft {self.mock_draft_version}"
        else:
            if self.is_draft:
                title += " Draft"
            else:
                title += f" Top {self.ranking_length}"
                if self.ranking_type:
                    title += f" {self.ranking_type} Players"

        return title

    def __unicode__(self):
        return self.get_computed_title()


class PlayerRankingCarryingTool(BaseModel):
    tool = models.CharField(max_length=255)
    score = models.CharField(max_length=5)
    description = models.CharField(max_length=255, blank=True, null=True)

    class Meta:
        ordering = ["tool", "-score"]

    def __unicode__(self):
        return f"{self.tool}: {self.score}"


class Author(BaseModel):
    """
    Extended profile for Users who can write articles.
    """
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='author_profile', blank=True, null=True)
    display_name = models.CharField(max_length=255, help_text="Name to display on articles", blank=True, null=True)
    # Backwards-compat: tests create Author with 'name'. Map to existing 'display_name' column.
    name = models.CharField(max_length=255, help_text="Name to display on articles", blank=True, null=True)
    email = models.EmailField(blank=True, null=True, help_text="Public contact email (if different from login email). If not set, uses user's email.")
    bio = models.TextField(blank=True, null=True, help_text="Author biography")
    founder = models.BooleanField(default=False, help_text="Mark this author as a founder")
    twitter = models.CharField(max_length=255, blank=True, null=True, help_text="Twitter handle (without @)")
    bluesky = models.CharField(max_length=255, blank=True, null=True, help_text="Bluesky handle (with or without @)")
    photo_url = models.CharField(max_length=255, blank=True, null=True)

    def __unicode__(self):
        return getattr(self, 'name', None) or self.user.get_full_name() or self.user.username

    @property
    def display_email(self):
        """
        Returns the public email if set, otherwise falls back to the user's email.
        """
        if self.email:
            return self.email
        if self.user and self.user.email:
            return self.user.email
        return None

    @property
    def first_name(self):
        """
        Returns the first name from display_name, name, or user's first name.
        """
        name = self.display_name or self.name
        if name:
            parts = name.split()
            if parts:
                return parts[0]
        if self.user and self.user.first_name:
            return self.user.first_name
        if self.user:
            # Fallback to username if no first name
            return self.user.username
        return "Author"

    @property
    def bluesky_url(self):
        """Returns the full Bluesky URL for the handle"""
        if not self.bluesky:
            return None
        handle = self.bluesky.strip('@')
        return f"https://bsky.app/profile/{handle}"

    class Meta:
        ordering = ["name"]


class PlayerRanking(BaseModel):
    """
    An instance of a player in a ranking. This way players can have many ranks, tracking history.
    Note: Position, school and country are denormalized versus Player.
    """
    player = models.ForeignKey(Player, on_delete=models.SET_NULL, blank=True, null=True)
    ranking = models.ForeignKey(Ranking, on_delete=models.SET_NULL, blank=True, null=True)
    rank = models.IntegerField(blank=True, null=True)
    position = models.CharField(max_length=255, blank=True, null=True)
    school = models.CharField(max_length=255, blank=True, null=True)
    country = models.CharField(max_length=255, blank=True, null=True)
    commitment = models.CharField(max_length=255, blank=True, null=True)
    raw_carrying_tools = models.TextField(blank=True, null=True)
    age_at_draft = models.CharField(max_length=10, blank=True, null=True)
    
    # Mock draft fields
    mock_team = models.CharField(max_length=255, blank=True, null=True, help_text="Team that drafted this player in mock draft")
    mock_team_logo_url = models.TextField(blank=True, null=True, help_text="URL to the team's logo image")
    mock_pick_number = models.IntegerField(blank=True, null=True, help_text="Pick number in mock draft")

    level = models.CharField(max_length=255, choices=LEVEL_CHOICES, blank=True, null=True)

    role = models.CharField(max_length=10, choices=ROLE_CHOICES, blank=True, null=True)
    risk = models.CharField(max_length=25, blank=True, null=True)
    carrying_tools = models.ManyToManyField(PlayerRankingCarryingTool, blank=True)

    # Trackman data - Hitters
    hitter_percentile = models.FloatField(blank=True, null=True)
    game_power_percentile = models.FloatField(blank=True, null=True)
    raw_power_percentile = models.FloatField(blank=True, null=True)
    approach_percentile = models.FloatField(blank=True, null=True)
    hitter_score = models.FloatField(blank=True, null=True)
    game_power_score = models.FloatField(blank=True, null=True)
    raw_power_score = models.FloatField(blank=True, null=True)
    approach_score = models.FloatField(blank=True, null=True)
    
    # Trackman data - Hitter metrics (raw values and corresponding percentiles)
    whiff_pct = models.FloatField(blank=True, null=True)
    whiff_pct_percentile = models.FloatField(blank=True, null=True)
    whiff_pct_points_above_median = models.FloatField(blank=True, null=True)
    iz_whiff_pct = models.FloatField(blank=True, null=True)
    iz_whiff_pct_percentile = models.FloatField(blank=True, null=True)
    iz_whiff_pct_points_above_median = models.FloatField(blank=True, null=True)
    ooz_whiff_pct = models.FloatField(blank=True, null=True)
    ooz_whiff_pct_percentile = models.FloatField(blank=True, null=True)
    ooz_whiff_pct_points_above_median = models.FloatField(blank=True, null=True)
    chase_pct = models.FloatField(blank=True, null=True)
    chase_pct_percentile = models.FloatField(blank=True, null=True)
    chase_pct_points_above_median = models.FloatField(blank=True, null=True)
    k_pct = models.FloatField(blank=True, null=True)
    k_pct_percentile = models.FloatField(blank=True, null=True)
    k_pct_points_above_median = models.FloatField(blank=True, null=True)
    bb_pct = models.FloatField(blank=True, null=True)
    bb_pct_percentile = models.FloatField(blank=True, null=True)
    bb_pct_points_above_median = models.FloatField(blank=True, null=True)
    avg_exit_velocity = models.FloatField(blank=True, null=True)
    avg_exit_velocity_percentile = models.FloatField(blank=True, null=True)
    avg_exit_velocity_points_above_median = models.FloatField(blank=True, null=True)
    ev_90th = models.FloatField(blank=True, null=True)
    ev_90th_percentile = models.FloatField(blank=True, null=True)
    ev_90th_points_above_median = models.FloatField(blank=True, null=True)
    barrel_pct = models.FloatField(blank=True, null=True)
    barrel_pct_percentile = models.FloatField(blank=True, null=True)
    barrel_pct_points_above_median = models.FloatField(blank=True, null=True)
    pull_air_pct = models.FloatField(blank=True, null=True)
    pull_air_pct_percentile = models.FloatField(blank=True, null=True)
    pull_air_pct_points_above_median = models.FloatField(blank=True, null=True)
    xwoba = models.FloatField(blank=True, null=True)
    xwoba_percentile = models.FloatField(blank=True, null=True)
    xwoba_points_above_median = models.FloatField(blank=True, null=True)

    # High School Hitters (Trackman/PG) - 2026 HS Hitters - 2025
    # Actual stat line values
    hs_pa = models.FloatField(blank=True, null=True)
    hs_ba = models.FloatField(blank=True, null=True)
    hs_obp = models.FloatField(blank=True, null=True)
    hs_slg = models.FloatField(blank=True, null=True)
    hs_ops = models.FloatField(blank=True, null=True)
    hs_iso = models.FloatField(blank=True, null=True)

    # Percentiles (0-100) and raw deltas above median for HS metrics
    hs_contact_pct_percentile = models.FloatField(blank=True, null=True)
    hs_contact_pct_points_above_median = models.FloatField(blank=True, null=True)

    hs_chase_pct_percentile = models.FloatField(blank=True, null=True)
    hs_chase_pct_points_above_median = models.FloatField(blank=True, null=True)

    hs_iz_contact_pct_percentile = models.FloatField(blank=True, null=True)
    hs_iz_contact_pct_points_above_median = models.FloatField(blank=True, null=True)

    hs_ooz_contact_pct_percentile = models.FloatField(blank=True, null=True)
    hs_ooz_contact_pct_points_above_median = models.FloatField(blank=True, null=True)

    hs_k_pct_percentile = models.FloatField(blank=True, null=True)
    hs_k_pct_points_above_median = models.FloatField(blank=True, null=True)

    hs_gb_pct_percentile = models.FloatField(blank=True, null=True)
    hs_gb_pct_points_above_median = models.FloatField(blank=True, null=True)

    hs_fb_pct_percentile = models.FloatField(blank=True, null=True)
    hs_fb_pct_points_above_median = models.FloatField(blank=True, null=True)

    hs_air_pull_pct_percentile = models.FloatField(blank=True, null=True)
    hs_air_pull_pct_points_above_median = models.FloatField(blank=True, null=True)

    # PG 60 Yard (displayed as Sprint Speed)
    hs_sprint_speed_percentile = models.FloatField(blank=True, null=True)
    hs_sprint_speed_points_above_median = models.FloatField(blank=True, null=True)

    # Bat metrics
    hs_bat_speed_percentile = models.FloatField(blank=True, null=True)
    hs_bat_speed_points_above_median = models.FloatField(blank=True, null=True)

    hs_avg_rot_acc_percentile = models.FloatField(blank=True, null=True)
    hs_avg_rot_acc_points_above_median = models.FloatField(blank=True, null=True)

    hs_peak_hand_speed_percentile = models.FloatField(blank=True, null=True)
    hs_peak_hand_speed_points_above_median = models.FloatField(blank=True, null=True)

    # Peak Power/BM (displayed as Force Plate Explosiveness)
    hs_force_plate_explosiveness_percentile = models.FloatField(blank=True, null=True)
    hs_force_plate_explosiveness_points_above_median = models.FloatField(blank=True, null=True)
    
    # Trackman data - Pitchers
    fourseam_percentile = models.FloatField(blank=True, null=True)
    sinker_percentile = models.FloatField(blank=True, null=True)
    slider_percentile = models.FloatField(blank=True, null=True)
    sweeper_percentile = models.FloatField(blank=True, null=True)
    curveball_percentile = models.FloatField(blank=True, null=True)
    changeup_percentile = models.FloatField(blank=True, null=True)
    fourseam_score = models.FloatField(blank=True, null=True)
    sinker_score = models.FloatField(blank=True, null=True)
    slider_score = models.FloatField(blank=True, null=True)
    sweeper_score = models.FloatField(blank=True, null=True)
    curveball_score = models.FloatField(blank=True, null=True)
    changeup_score = models.FloatField(blank=True, null=True)
    
    confidence = models.IntegerField(blank=True, null=True)

    scouting_report = models.TextField(null=True, blank=True)

    class Meta:
        ordering = ['ranking', 'rank']

    def __unicode__(self):
        return f"({self.rank}) {self.player} in {self.ranking}"


class PlayerStatSeason(BaseModel):
    """
    Seasonal stats for a player, by level (High School / College).
    This consolidates the various TrackMan- and event-derived metrics that previously
    lived on PlayerRanking. One row per (player, year, level).
    """
    LEVEL_CHOICES = (
        ("College", "College"),
        ("High School", "High School"),
    )

    player = models.ForeignKey(Player, on_delete=models.CASCADE, related_name="stat_seasons")
    year = models.CharField(max_length=10, help_text="Season year for these stats (e.g., 2025)")
    level = models.CharField(max_length=25, choices=LEVEL_CHOICES, help_text="High School or College")
    draft_year = models.CharField(max_length=10, blank=True, null=True, help_text="Draft year for this player (e.g., 2025)")
    school = models.CharField(max_length=255, blank=True, null=True, help_text="School/Team name for this stat season")

    # Composite hitter metrics (percentiles and scores)
    hitter_percentile = models.FloatField(blank=True, null=True)
    game_power_percentile = models.FloatField(blank=True, null=True)
    raw_power_percentile = models.FloatField(blank=True, null=True)
    approach_percentile = models.FloatField(blank=True, null=True)

    hitter_score = models.FloatField(blank=True, null=True)
    game_power_score = models.FloatField(blank=True, null=True)
    raw_power_score = models.FloatField(blank=True, null=True)
    approach_score = models.FloatField(blank=True, null=True)

    # College hitter requested metrics (raw values in "points" and associated percentiles and deltas)
    whiff_pct = models.FloatField(blank=True, null=True)
    whiff_pct_percentile = models.FloatField(blank=True, null=True)
    whiff_pct_points_above_median = models.FloatField(blank=True, null=True)
    iz_whiff_pct = models.FloatField(blank=True, null=True)
    iz_whiff_pct_percentile = models.FloatField(blank=True, null=True)
    iz_whiff_pct_points_above_median = models.FloatField(blank=True, null=True)
    ooz_whiff_pct = models.FloatField(blank=True, null=True)
    ooz_whiff_pct_percentile = models.FloatField(blank=True, null=True)
    ooz_whiff_pct_points_above_median = models.FloatField(blank=True, null=True)
    chase_pct = models.FloatField(blank=True, null=True)
    chase_pct_percentile = models.FloatField(blank=True, null=True)
    chase_pct_points_above_median = models.FloatField(blank=True, null=True)
    k_pct = models.FloatField(blank=True, null=True)
    k_pct_percentile = models.FloatField(blank=True, null=True)
    k_pct_points_above_median = models.FloatField(blank=True, null=True)
    bb_pct = models.FloatField(blank=True, null=True)
    bb_pct_percentile = models.FloatField(blank=True, null=True)
    bb_pct_points_above_median = models.FloatField(blank=True, null=True)
    avg_exit_velocity = models.FloatField(blank=True, null=True)
    avg_exit_velocity_percentile = models.FloatField(blank=True, null=True)
    avg_exit_velocity_points_above_median = models.FloatField(blank=True, null=True)
    ev_90th = models.FloatField(blank=True, null=True)
    ev_90th_percentile = models.FloatField(blank=True, null=True)
    ev_90th_points_above_median = models.FloatField(blank=True, null=True)
    barrel_pct = models.FloatField(blank=True, null=True)
    barrel_pct_percentile = models.FloatField(blank=True, null=True)
    barrel_pct_points_above_median = models.FloatField(blank=True, null=True)
    pull_air_pct = models.FloatField(blank=True, null=True)
    pull_air_pct_percentile = models.FloatField(blank=True, null=True)
    pull_air_pct_points_above_median = models.FloatField(blank=True, null=True)
    xwoba = models.FloatField(blank=True, null=True)
    xwoba_percentile = models.FloatField(blank=True, null=True)
    xwoba_points_above_median = models.FloatField(blank=True, null=True)

    # Pitcher pitch-type composite percentiles (when available)
    fourseam_percentile = models.FloatField(blank=True, null=True)
    sinker_percentile = models.FloatField(blank=True, null=True)
    slider_percentile = models.FloatField(blank=True, null=True)
    sweeper_percentile = models.FloatField(blank=True, null=True)
    curveball_percentile = models.FloatField(blank=True, null=True)
    changeup_percentile = models.FloatField(blank=True, null=True)
    fourseam_score = models.FloatField(blank=True, null=True)
    sinker_score = models.FloatField(blank=True, null=True)
    slider_score = models.FloatField(blank=True, null=True)
    sweeper_score = models.FloatField(blank=True, null=True)
    curveball_score = models.FloatField(blank=True, null=True)
    changeup_score = models.FloatField(blank=True, null=True)

    # High school statline actuals
    hs_pa = models.FloatField(blank=True, null=True)
    hs_ba = models.FloatField(blank=True, null=True)
    hs_obp = models.FloatField(blank=True, null=True)
    hs_slg = models.FloatField(blank=True, null=True)
    hs_ops = models.FloatField(blank=True, null=True)
    hs_iso = models.FloatField(blank=True, null=True)

    # High school percentiles and points above median
    hs_contact_pct_percentile = models.FloatField(blank=True, null=True)
    hs_contact_pct_points_above_median = models.FloatField(blank=True, null=True)
    hs_chase_pct_percentile = models.FloatField(blank=True, null=True)
    hs_chase_pct_points_above_median = models.FloatField(blank=True, null=True)
    hs_iz_contact_pct_percentile = models.FloatField(blank=True, null=True)
    hs_iz_contact_pct_points_above_median = models.FloatField(blank=True, null=True)
    hs_ooz_contact_pct_percentile = models.FloatField(blank=True, null=True)
    hs_ooz_contact_pct_points_above_median = models.FloatField(blank=True, null=True)
    hs_k_pct_percentile = models.FloatField(blank=True, null=True)
    hs_k_pct_points_above_median = models.FloatField(blank=True, null=True)
    hs_gb_pct_percentile = models.FloatField(blank=True, null=True)
    hs_gb_pct_points_above_median = models.FloatField(blank=True, null=True)
    hs_fb_pct_percentile = models.FloatField(blank=True, null=True)
    hs_fb_pct_points_above_median = models.FloatField(blank=True, null=True)
    hs_air_pull_pct_percentile = models.FloatField(blank=True, null=True)
    hs_air_pull_pct_points_above_median = models.FloatField(blank=True, null=True)
    hs_sprint_speed_percentile = models.FloatField(blank=True, null=True)
    hs_sprint_speed_points_above_median = models.FloatField(blank=True, null=True)
    hs_bat_speed_percentile = models.FloatField(blank=True, null=True)
    hs_bat_speed_points_above_median = models.FloatField(blank=True, null=True)
    hs_avg_rot_acc_percentile = models.FloatField(blank=True, null=True)
    hs_avg_rot_acc_points_above_median = models.FloatField(blank=True, null=True)
    hs_peak_hand_speed_percentile = models.FloatField(blank=True, null=True)
    hs_peak_hand_speed_points_above_median = models.FloatField(blank=True, null=True)
    hs_force_plate_explosiveness_percentile = models.FloatField(blank=True, null=True)
    hs_force_plate_explosiveness_points_above_median = models.FloatField(blank=True, null=True)

    confidence = models.IntegerField(blank=True, null=True)

    class Meta:
        unique_together = ['player', 'year', 'level']
        ordering = ['-year', 'player__name']
        verbose_name = "Player Stat Season"
        verbose_name_plural = "Player Stat Seasons"

    def __unicode__(self):
        return f"{self.player.name} {self.level} {self.year}"

class Article(BaseModel):
    ARTICLE_TYPE_CHOICES = (
        ("breaking news", "breaking news"),
        ("scouting", "scouting"),
        ("analysis", "analysis"),
        ("opinion", "opinion"),
    )

    headline = models.CharField(max_length=255, blank=True, null=True)
    subhead = models.CharField(max_length=255, blank=True, null=True)
    blurb = models.CharField(max_length=255, blank=True, null=True)
    featured_image = models.ImageField(upload_to='articles/featured/', blank=True, null=True, help_text="Featured image for the article")

    players = models.ManyToManyField(Player, blank=True)
    authors = models.ManyToManyField(Author, blank=True, related_name='articles')

    article_type = models.CharField(max_length=255, choices=ARTICLE_TYPE_CHOICES, blank=True, null=True)

    body = models.TextField(null=True, blank=True)
    uuid = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    slug = models.SlugField(max_length=255, blank=True, null=True)
    regenerate_slug = models.BooleanField(default=False)

    publish = models.BooleanField(default=False)
    is_carousel = models.BooleanField(default=False, help_text="Display in homepage carousel")
    is_free = models.BooleanField(default=False, help_text="Make this article free to view without subscription")

    class Meta:
        ordering = ["-created"]

    def save(self, *args, **kwargs):
        if self.regenerate_slug or not self.slug:
            self.slug = slugify(f"{self.headline}-{self.uuid}")
            self.regenerate_slug = False

        super().save(*args, **kwargs)

    def __unicode__(self):
        return self.headline


class PodcastEpisode(BaseModel):
    """
    Podcast episodes imported from Patreon RSS feed.
    Maps to typical RSS <item> fields including enclosure metadata.
    """
    # Core metadata
    title = models.CharField(max_length=255)
    external_url = models.TextField(help_text="Link to the original Patreon post")
    image_url = models.TextField(blank=True, null=True, help_text="Image URL from itunes:image@href")
    description_html = models.TextField(blank=True, null=True, help_text="Episode description from RSS (HTML)")

    # Audio enclosure
    audio_url = models.TextField(help_text="Enclosure URL for the audio file")
    audio_bytes = models.BigIntegerField(blank=True, null=True, help_text="Size in bytes from enclosure length")
    audio_mime_type = models.CharField(max_length=100, blank=True, null=True, help_text="MIME type from enclosure type (e.g., audio/mp4)")

    # Identifiers and publishing
    guid = models.CharField(max_length=255, unique=True, help_text="GUID from RSS, not necessarily a permalink")
    published_at = models.DateTimeField(db_index=True, help_text="Publication date from RSS pubDate")

    # Site publishing controls
    publish = models.BooleanField(default=False, help_text="Controls visibility on site")
    featured = models.BooleanField(default=False, help_text="Pin this episode to the right side of the homepage belt")

    # Slugging support for friendly URLs if we add detail pages
    slug = models.SlugField(max_length=255, blank=True, null=True)
    regenerate_slug = models.BooleanField(default=False)

    # Optional, extracted from titles like 'Ep. 183: ...'
    episode_number = models.IntegerField(blank=True, null=True)

    class Meta:
        ordering = ["-published_at", "-created"]

    def save(self, *args, **kwargs):
        if self.regenerate_slug or not self.slug:
            base = self.title or self.guid
            self.slug = slugify(f"{base}-{self.guid}")
            self.regenerate_slug = False
        super().save(*args, **kwargs)

    def __unicode__(self):
        return self.title

class DuplicateDecision(BaseModel):
    """
    Stores decisions about whether two players are duplicates or separate entities.
    This prevents the duplicate finder from asking about the same pair repeatedly.
    """
    player1 = models.ForeignKey(Player, on_delete=models.CASCADE, related_name='duplicate_decisions_as_player1')
    player2 = models.ForeignKey(Player, on_delete=models.CASCADE, related_name='duplicate_decisions_as_player2')
    decision = models.CharField(max_length=20, choices=[
        ('merged', 'Merged - players are the same person'),
        ('separate', 'Separate - players are different people')
    ])
    decided_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    primary_player = models.ForeignKey(Player, on_delete=models.SET_NULL, null=True, blank=True, 
                                     related_name='duplicate_decisions_as_primary',
                                     help_text="For merged decisions, which player was kept as primary")
    notes = models.TextField(blank=True, null=True, help_text="Optional notes about the decision")
    
    class Meta:
        unique_together = ['player1', 'player2']
        ordering = ['-created']
    
    def save(self, *args, **kwargs):
        # Ensure consistent ordering of players (smaller UUID first)
        if str(self.player1.uuid) > str(self.player2.uuid):
            self.player1, self.player2 = self.player2, self.player1
        super().save(*args, **kwargs)
    
    def __unicode__(self):
        return f"{self.player1.name} vs {self.player2.name} - {self.decision}"


class PotentialDuplicate(BaseModel):
    """
    Pre-calculated potential duplicate pairs for fast duplicate management.
    This table is populated by a management command and cleared/rebuilt as needed.
    """
    player1 = models.ForeignKey(Player, on_delete=models.CASCADE, related_name='potential_duplicates_as_player1')
    player2 = models.ForeignKey(Player, on_delete=models.CASCADE, related_name='potential_duplicates_as_player2')
    similarity_score = models.FloatField(help_text="Similarity score between 0 and 1")
    match_reasons = models.JSONField(default=list, help_text="List of reasons why these might be duplicates")
    
    # Denormalized fields for fast filtering/sorting
    player1_name = models.CharField(max_length=255)
    player2_name = models.CharField(max_length=255)
    player1_school = models.CharField(max_length=255, blank=True, null=True)
    player2_school = models.CharField(max_length=255, blank=True, null=True)
    player1_state = models.CharField(max_length=255, blank=True, null=True)
    player2_state = models.CharField(max_length=255, blank=True, null=True)
    
    class Meta:
        unique_together = ['player1', 'player2']
        ordering = ['-similarity_score', 'player1_name', 'player2_name']
        indexes = [
            models.Index(fields=['similarity_score']),
            models.Index(fields=['player1_name']),
            models.Index(fields=['player2_name']),
        ]
    
    def save(self, *args, **kwargs):
        # Ensure consistent ordering of players (smaller UUID first)
        if str(self.player1.uuid) > str(self.player2.uuid):
            self.player1, self.player2 = self.player2, self.player1
        
        # Update denormalized fields
        self.player1_name = self.player1.name
        self.player2_name = self.player2.name
        self.player1_school = self.player1.school
        self.player2_school = self.player2.school
        self.player1_state = self.player1.state
        self.player2_state = self.player2.state
        
        super().save(*args, **kwargs)
    
    def __unicode__(self):
        return f"{self.player1.name} vs {self.player2.name} ({self.similarity_score:.2f})"


class DataSheet(models.Model):
    """
    Model for storing sheet locations.
    """
    sheet_url = models.CharField(max_length=255)

    def __unicode__(self):
        return self.sheet_url


class DataSheetTab(models.Model):
    """
    Model for storing tabs within sheets.
    """
    data_sheet = models.ForeignKey(DataSheet, on_delete=models.CASCADE)
    ranking = models.ForeignKey(Ranking, blank=True, null=True, on_delete=models.CASCADE)
    tab = models.CharField(max_length=255)

    year = models.CharField(max_length=255)
    ranking_type = models.CharField(max_length=255, choices=LEVEL_CHOICES, blank=True, null=True)
    ranking_length = models.CharField(max_length=255, blank=True, null=True)
    is_final = models.BooleanField(default=False)
    is_draft = models.BooleanField(default=False)
    is_mock_draft = models.BooleanField(default=False)
    mock_draft_version = models.CharField(max_length=255, blank=True, null=True)

    def __unicode__(self):
        if self.data_sheet:
            return f"{self.data_sheet} {self.tab}"
        return self.tab


class FeatureFlag(BaseModel):
    """
    Configurable feature flag with multiple visibility modes:
    - staff_only: visible only to staff users when enabled
    - users: explicit allow-list of users
    - rollout_percentage: helper to pick a random cohort of public users
    - general_availability: visible to everyone when true
    """
    ROLLOUT_CHOICES = (
        (0, "0%"),
        (5, "5%"),
        (25, "25%"),
        (50, "50%"),
    )

    key = models.SlugField(max_length=100, unique=True, help_text="Stable key used in code/templates")
    name = models.CharField(max_length=255, help_text="Human readable name")
    description = models.TextField(blank=True, null=True)

    # Visibility controls
    staff_only = models.BooleanField(default=False, help_text="If checked, only staff users see this feature")
    general_availability = models.BooleanField(default=False, help_text="If checked, feature is visible to everyone")

    # Targeted rollout
    rollout_percentage = models.IntegerField(choices=ROLLOUT_CHOICES, default=0, help_text="Select cohort size and use 'Assign rollout users' action")
    users = models.ManyToManyField(User, blank=True, related_name='feature_flags', help_text="Users explicitly enabled for this feature")

    class Meta:
        ordering = ["key"]
        verbose_name = "Feature Flag"
        verbose_name_plural = "Feature Flags"

    def __unicode__(self):
        return self.name or self.key

    def is_enabled_for(self, user):
        """Return True if the feature is visible to the given user."""
        if self.general_availability:
            return True

        # Staff-only mode takes precedence over targeted lists
        if self.staff_only:
            return bool(user and user.is_authenticated and user.is_staff)

        # Explicit allow-list
        if user and getattr(user, 'is_authenticated', False):
            if self.users.filter(pk=user.pk).exists():
                return True

        return False

    def assign_rollout_users(self, replace=True):
        """
        Assign a random cohort of public users (non-staff, non-superuser) to this
        flag's allow-list based on rollout_percentage. If replace=True, replace the
        current allow-list with the new cohort; otherwise, add to it.
        """
        percent = int(self.rollout_percentage or 0)
        if percent <= 0:
            if replace:
                self.users.clear()
            return 0

        public_users = User.objects.filter(is_active=True, is_staff=False, is_superuser=False)
        total = public_users.count()
        if total == 0:
            if replace:
                self.users.clear()
            return 0

        target_size = max(1, round(total * (percent / 100.0)))
        # Random sample using database-level random ordering
        cohort = list(public_users.order_by('?')[:target_size])

        if replace:
            self.users.set(cohort)
        else:
            self.users.add(*cohort)
        return len(cohort)

    @classmethod
    def enabled(cls, key, user):
        """Convenience classmethod to check a flag by key for a user."""
        try:
            flag = cls.objects.get(key=key, active=True)
        except cls.DoesNotExist:
            return False
        return flag.is_enabled_for(user)
