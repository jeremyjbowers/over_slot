from django.contrib import admin

admin.site.site_title = "Overslot"
admin.site.site_header = "Overslot: Admin"
admin.site.index_title = "Administer The Overslot Website"

from overslot.models import (
    Article,
    Player,
    Ranking,
    PlayerRanking,
    PlayerRankingCarryingTool
)


@admin.register(Article)
class ArticleAdmin(admin.ModelAdmin):
    model = Article
    list_display = ["headline", "subhead", "blurb", "publish"]
    search_fields = ["headline", "body", "subhead", "blurb"]
    list_editable = ["subhead", "blurb", "publish"]
    autocomplete_fields = ["players"]


@admin.register(Player)
class PlayerAdmin(admin.ModelAdmin):
    model = Player
    list_display = ["name", "current_position", "current_school"]
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
    fieldsets = (
        (
            None,
            {
                "fields": (
                    ("rank", "player"),
                    ("ranking_position", "ranking_school"),
                    ('role', 'carrying_tools'),
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
                    "rank",
                    "player",
                    ("ranking_position", "ranking_school"),
                    ('role', 'carrying_tools'),
                ),
            },
        ),
    )

@admin.register(Ranking)
class RankingAdmin(admin.ModelAdmin):
    model = Ranking
    inlines = [PlayerRankingInline]
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