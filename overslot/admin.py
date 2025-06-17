from django.contrib import admin
from django.contrib.admin import AdminSite
from django.urls import reverse_lazy

# Override the default admin site's login URL to use magic link authentication
admin.site.site_title = "Overslot"
admin.site.site_header = "Overslot: Admin"
admin.site.index_title = "Administer The Overslot Website"

# Custom login method for the admin site
def custom_admin_login(request, extra_context=None):
    """
    Override login to redirect to magic link authentication
    """
    from django.shortcuts import redirect
    from django.contrib.auth import REDIRECT_FIELD_NAME
    from django.urls import reverse
    
    # If user is already authenticated, proceed to admin
    if request.user.is_authenticated:
        return admin.site.login(request, extra_context)
    
    # Get the redirect URL (where to go after login)
    redirect_to = request.GET.get(REDIRECT_FIELD_NAME, request.get_full_path())
    
    # Redirect to magic link login with next parameter
    magic_link_url = reverse('account_login')
    if redirect_to:
        magic_link_url += f'?{REDIRECT_FIELD_NAME}={redirect_to}'
    
    return redirect(magic_link_url)

# Override the admin site's login method
admin.site.login = custom_admin_login

# Import models
from overslot.models import (
    Article,
    Author,
    Player,
    Ranking,
    PlayerRanking,
    PlayerRankingCarryingTool,
    Subscription,
    DuplicateDecision
)


@admin.register(Author)
class AuthorAdmin(admin.ModelAdmin):
    model = Author
    list_display = ["display_name", "user", "email", "twitter", "bluesky"]
    search_fields = ["display_name", "user__username", "user__email", "email", "bio", "twitter", "bluesky"]
    autocomplete_fields = ["user"]
    readonly_fields = ["created", "last_modified"]


@admin.register(Article)
class ArticleAdmin(admin.ModelAdmin):
    model = Article
    list_display = ["headline", "subhead", "blurb", "publish"]
    search_fields = ["headline", "body", "subhead", "blurb"]
    list_editable = ["subhead", "blurb", "publish"]
    autocomplete_fields = ["players", "authors"]


@admin.register(Player)
class PlayerAdmin(admin.ModelAdmin):
    model = Player
    list_display = ["name", "position", "school"]
    search_fields = ["name"]


@admin.register(PlayerRankingCarryingTool)
class PlayerRakingCarryingToolAdmin(admin.ModelAdmin):
    model = PlayerRankingCarryingTool
    list_display = ["tool", "score", "description"]
    search_fields = ["tool", "score", "description"]


class PlayerRankingCarryingToolInline(admin.TabularInline):
    model = PlayerRankingCarryingTool
    min_num = 0
    extra = 1


class PlayerRankingInline(admin.TabularInline):
    model = PlayerRanking
    autocomplete_fields = ["player", "carrying_tools"]
    inlines = [PlayerRankingCarryingToolInline]
    min_num = 30
    max_num = 1000
    extra = 0
    classes = ['collapse']
    fieldsets = (
        (
            None,
            {
                "fields": (
                    ("rank", "player"),
                    ("position", "school"),
                    ('role', 'risk', 'carrying_tools'),
                ),
            },
        ),
    )

@admin.register(PlayerRanking)
class PlayerRankingAdmin(admin.ModelAdmin):
    model = PlayerRanking
    list_display = ["ranking", "player", "rank"]
    search_fields = ["player", "ranking"]
    list_filter = ["ranking"]
    autocomplete_fields = ["carrying_tools"]
    fieldsets = (
        (
            None,
            {
                "fields": (
                    ("rank", "player"),
                    ("position", "school", 'commitment'),
                    ('role', 'risk', 'level'),
                    'scouting_report',
                    'raw_carrying_tools',
                    "carrying_tools",
                ),
            },
        ),
    )

@admin.register(Ranking)
class RankingAdmin(admin.ModelAdmin):
    model = Ranking
    list_display = ["year", "ranking_type", "ranking_length", "is_final"]
    list_editable = ["ranking_type", "is_final"]
    fieldsets = (
        (
            "Board details",
            {
                "fields": (
                    ("year", "ranking_type", "ranking_length"),
                    "is_final",
                    "is_draft",
                    ("is_mock_draft", "mock_draft_version"),
                ),
            },
        ),
        (
            "Publishing details",
            {
                "fields": (
                    "headline",
                    "subhead",
                    "blurb",
                    "featured_image",
                    "body"
                ),
            },
        ),
        (
            "Advanced",
            {
                "classes": ("collapse",),
                "fields": (
                    "slug",
                    "regenerate_slug"
                ),
            },
        ),
    )


@admin.register(Subscription)
class SubscriptionAdmin(admin.ModelAdmin):
    model = Subscription
    list_display = ["user", "status", "plan_name", "current_period_end", "is_active"]
    list_filter = ["status", "plan_name", "created"]
    search_fields = ["user__email", "user__username", "stripe_customer_id", "stripe_subscription_id"]
    readonly_fields = ["created", "last_modified", "stripe_customer_id", "stripe_subscription_id"]
    
    def is_active(self, obj):
        return obj.is_active
    is_active.boolean = True
    is_active.short_description = "Active"
    
    fieldsets = (
        (
            "User Information",
            {
                "fields": ("user",),
            },
        ),
        (
            "Subscription Details",
            {
                "fields": (
                    "status",
                    "plan_name",
                    ("current_period_start", "current_period_end"),
                ),
            },
        ),
        (
            "Stripe Information",
            {
                "classes": ("collapse",),
                "fields": (
                    "stripe_customer_id",
                    "stripe_subscription_id",
                    "price_id",
                ),
            },
        ),
        (
            "Timestamps",
            {
                "classes": ("collapse",),
                "fields": (
                    "created",
                    "last_modified",
                ),
            },
        ),
    )


@admin.register(DuplicateDecision)
class DuplicateDecisionAdmin(admin.ModelAdmin):
    model = DuplicateDecision
    list_display = ["player1", "player2", "decision", "decided_by", "created"]
    list_filter = ["decision", "created"]
    search_fields = ["player1__name", "player2__name", "decided_by__username"]
    readonly_fields = ["created"]
    
    fieldsets = (
        (
            "Decision Details",
            {
                "fields": (
                    ("player1", "player2"),
                    "decision",
                    "decided_by",
                    "notes",
                ),
            },
        ),
        (
            "Timestamps",
            {
                "fields": ("created",),
            },
        ),
    )