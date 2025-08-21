from django.contrib import admin
from django.contrib.admin import AdminSite
from django.urls import reverse_lazy
from django.contrib.auth.models import User, Group
from django.contrib.auth.admin import UserAdmin as DjangoUserAdmin, GroupAdmin as DjangoGroupAdmin

# Create a custom admin site for content editors
class ContentEditorAdminSite(AdminSite):
    site_title = "Overslot"
    site_header = "Overslot: Content Editor"
    index_title = "Content Management Dashboard"
    
    def get_app_list(self, request, app_label=None):
        """
        Return a sorted list of all the installed apps that have been
        registered in this site.
        """
        app_dict = self._build_app_dict(request, app_label)
        
        # Define the order we want for content editing
        content_priority_order = [
            ('overslot', 'Articles'),
            ('overslot', 'Rankings'), 
            ('overslot', 'Authors'),
            ('overslot', 'Players'),
            ('overslot', 'Player rankings'),
            ('overslot', 'Subscriptions'),
            ('overslot', 'Player ranking carrying tools'),
            ('overslot', 'Duplicate decisions'),
            ('auth', 'Users'),
            ('auth', 'Groups'),
            ('sites', 'Sites'),
            ('socialaccount', 'Social accounts'),
            ('socialaccount', 'Social applications'),
            ('socialaccount', 'Social application tokens'),
            ('account', 'Email addresses'),
            ('account', 'Email confirmations'),
        ]
        
        # Convert to list and sort based on our priority
        app_list = list(app_dict.values())
        
        # Sort models within each app based on content editor priorities
        for app in app_list:
            if app['app_label'] == 'overslot':
                # For overslot app, put content models first
                priority_models = ['Articles', 'Rankings', 'Authors']
                support_models = ['Players', 'Player rankings'] 
                admin_models = ['Subscriptions', 'Player ranking carrying tools', 'Duplicate decisions']
                
                def model_sort_key(model):
                    name = model['name']
                    if name in priority_models:
                        return (0, priority_models.index(name))
                    elif name in support_models:
                        return (1, support_models.index(name))
                    elif name in admin_models:
                        return (2, admin_models.index(name))
                    else:
                        return (3, name)
                
                app['models'] = sorted(app['models'], key=model_sort_key)
            
            elif app['app_label'] == 'auth':
                # For auth app, Users first, then Groups
                auth_order = ['Users', 'Groups']
                def auth_sort_key(model):
                    name = model['name']
                    return auth_order.index(name) if name in auth_order else 999
                app['models'] = sorted(app['models'], key=auth_sort_key)
        
        # Sort apps based on content editor importance
        def app_sort_key(app):
            label = app['app_label']
            # Content apps first
            if label == 'overslot':
                return 0
            # User management second  
            elif label == 'auth':
                return 1
            # Less important apps last
            else:
                return 2
        
        app_list = sorted(app_list, key=app_sort_key)
        
        return app_list

# Replace the default admin site with our custom one
admin_site = ContentEditorAdminSite(name='admin')

# Override the default admin site's login URL to use magic link authentication
admin_site.site_title = "Over-Slot"
admin_site.site_header = "Over-Slot: Content Editor"
admin_site.index_title = "Content Management Dashboard"

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
        return admin_site.login(request, extra_context)
    
    # Get the redirect URL (where to go after login)
    redirect_to = request.GET.get(REDIRECT_FIELD_NAME, request.get_full_path())
    
    # Redirect to magic link login with next parameter
    magic_link_url = reverse('account_login')
    if redirect_to:
        magic_link_url += f'?{REDIRECT_FIELD_NAME}={redirect_to}'
    
    return redirect(magic_link_url)

# Override the admin site's login method
admin_site.login = custom_admin_login

# Also set the global admin.site for backwards compatibility
admin.site = admin_site

# Import models
from overslot.models import (
    Article,
    Author,
    Player,
    Ranking,
    PlayerRanking,
    PlayerRankingCarryingTool,
    Subscription,
    DuplicateDecision,
    UserEmail
)


@admin.register(Author, site=admin_site)
class AuthorAdmin(admin.ModelAdmin):
    model = Author
    list_display = ["name", "user", "email", "twitter", "bluesky"]
    search_fields = ["name", "user__username", "user__email", "email", "bio", "twitter", "bluesky"]
    autocomplete_fields = ["user"]
    readonly_fields = ["created", "last_modified"]


@admin.register(Article, site=admin_site)
class ArticleAdmin(admin.ModelAdmin):
    model = Article
    # --- List / overview ----------------------------------------------------
    list_display = [
        "headline",
        "subhead",
        "publish",
        "article_type",
        "is_carousel",
        "last_modified",
    ]
    list_editable = ["publish", "is_carousel", "article_type"]
    list_filter = [
        "publish",
        "is_carousel",
        "article_type",
        "authors",
    ]
    search_fields = [
        "headline",
        "subhead",
        "blurb",
        "body",
    ]
    date_hierarchy = "created"
    ordering = ("-created",)

    # --- Form configuration -------------------------------------------------
    autocomplete_fields = ["players", "authors"]

    fieldsets = (
        (
            "Core Content",
            {
                "fields": (
                    "headline",
                    "subhead",
                    "blurb",
                    "featured_image",
                    "body",
                )
            },
        ),
        (
            "Associations",
            {
                "classes": ("collapse",),
                "fields": (
                    "authors",
                    "players",
                ),
            },
        ),
        (
            "Publishing Controls",
            {
                "fields": (
                    "publish",
                    "is_carousel",
                )
            },
        ),
        (
            "Advanced",
            {
                "classes": ("collapse",),
                "fields": (
                    "slug",
                    "regenerate_slug",
                ),
            },
        ),
    )


@admin.register(Player, site=admin_site)
class PlayerAdmin(admin.ModelAdmin):
    model = Player
    list_display = ["name", "position", "school"]
    search_fields = ["name"]


@admin.register(PlayerRankingCarryingTool, site=admin_site)
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

@admin.register(PlayerRanking, site=admin_site)
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
        (
            "Mock Draft Information",
            {
                "fields": (
                    ("mock_team", "mock_pick_number"),
                    "mock_team_logo_url",
                ),
            },
        ),
    )

@admin.register(Ranking, site=admin_site)
class RankingAdmin(admin.ModelAdmin):
    model = Ranking
    # --- List / overview ----------------------------------------------------
    list_display = [
        "year",
        "draft_level",
        "ranking_length",
        "is_mock_draft",
        "mock_draft_version",
        "is_final",
        "publish",
        "is_carousel",
    ]
    list_editable = ["publish", "is_carousel"]
    list_filter = [
        "publish",
        "is_carousel",
        "year",
        "is_final",
        "is_draft",
        "is_mock_draft",
        "draft_level",
    ]
    search_fields = [
        "headline",
        "year",
        "subhead",
        "blurb",
    ]
    date_hierarchy = "created"
    ordering = ("-year", "-created")

    # --- Form configuration -------------------------------------------------
    fieldsets = (
        (
            "Board Details",
            {
                "fields": (
                    ("year", "ranking_type", "ranking_length"),
                    "draft_level",
                    "is_final",
                    "is_draft",
                    ("is_mock_draft", "mock_draft_version"),
                ),
            },
        ),
        (
            "Editorial Content",
            {
                "fields": (
                    "headline",
                    "subhead",
                    "blurb",
                    "featured_image",
                    "body",
                ),
            },
        ),
        (
            "Publishing Controls",
            {
                "fields": (
                    "publish",
                    "is_carousel",
                ),
            },
        ),
        (
            "Advanced",
            {
                "classes": ("collapse",),
                "fields": (
                    "slug",
                    "regenerate_slug",
                ),
            },
        ),
    )


@admin.register(Subscription, site=admin_site)
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


@admin.register(DuplicateDecision, site=admin_site)
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
                "classes": ("collapse",),
                "fields": ("created",),
            },
        ),
    )

# ---------------------------------------------------------------------------
# Core system models (Users & Groups)
# ---------------------------------------------------------------------------

# Register User and Group so that related admin inlines / autocomplete_fields
# work correctly. We keep the default Django admin behaviour but attach them to
# our custom admin_site so they appear in the index (lower priority).

@admin.register(User, site=admin_site)
class CustomUserAdmin(DjangoUserAdmin):
    pass


@admin.register(Group, site=admin_site)
class CustomGroupAdmin(DjangoGroupAdmin):
    pass


@admin.register(UserEmail, site=admin_site)
class UserEmailAdmin(admin.ModelAdmin):
    list_display = ['user', 'email', 'is_verified', 'created']
    list_filter = ['is_verified', 'created']
    search_fields = ['email', 'user__email', 'user__username', 'user__first_name', 'user__last_name']
    readonly_fields = ['verification_token', 'created', 'last_modified']
    
    fieldsets = (
        (None, {
            'fields': ('user', 'email', 'is_verified')
        }),
        ('Verification', {
            'fields': ('verification_token',),
            'classes': ('collapse',)
        }),
        ('Timestamps', {
            'fields': ('created', 'last_modified'),
            'classes': ('collapse',)
        }),
    )
    
    def get_queryset(self, request):
        return super().get_queryset(request).select_related('user')