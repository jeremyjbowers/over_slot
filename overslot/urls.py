from django.contrib import admin
from django.urls import include, path, re_path
from django.contrib.auth.views import LogoutView
from django.conf import settings
from django.conf.urls.static import static
from django.contrib.sitemaps.views import sitemap

from overslot import views, subscription_views, duplicate_views, account_views, team_duplicate_views
from overslot.admin import admin_site
from . import auth
from .sitemaps import StaticViewSitemap, ArticleSitemap, RankingSitemap, PlayerSitemap, MockDraftSitemap, GamesSitemap

urlpatterns = [
    # Internal data status (admin only)
    path('admin/data-status/', duplicate_views.data_status, name='data_status'),
    # Duplicate Management URLs (admin only)
    path('admin/duplicates/', duplicate_views.duplicate_dashboard, name='duplicate_dashboard'),
    path('admin/duplicates/review/', duplicate_views.review_duplicate, name='review_duplicate'),
    path('admin/duplicates/review/<uuid:player1_uuid>/<uuid:player2_uuid>/', duplicate_views.review_duplicate_pair, name='review_duplicate_pair'),
    path('admin/duplicates/merge/<uuid:player1_uuid>/<uuid:player2_uuid>/', duplicate_views.merge_players, name='merge_players'),
    path('admin/duplicates/separate/<uuid:player1_uuid>/<uuid:player2_uuid>/', duplicate_views.mark_separate, name='mark_separate'),
    path('admin/duplicates/history/', duplicate_views.duplicate_history, name='duplicate_history'),
    path('admin/duplicates/search/', duplicate_views.search_duplicates, name='search_duplicates'),
    path('admin/duplicates/check/<uuid:player1_uuid>/<uuid:player2_uuid>/', duplicate_views.manual_duplicate_check, name='manual_duplicate_check'),
    path('admin/duplicates/suggest/', duplicate_views.suggest_duplicate, name='suggest_duplicate'),
    
    # Team Duplicate Management URLs (admin only)
    path('admin/team-duplicates/', team_duplicate_views.team_duplicate_dashboard, name='team_duplicate_dashboard'),
    path('admin/team-duplicates/review/', team_duplicate_views.review_team_duplicate, name='review_team_duplicate'),
    path('admin/team-duplicates/review/<int:team1_id>/<int:team2_id>/', team_duplicate_views.review_team_duplicate_pair, name='review_team_duplicate_pair'),
    path('admin/team-duplicates/merge/<int:team1_id>/<int:team2_id>/', team_duplicate_views.merge_teams, name='merge_teams'),
    path('admin/team-duplicates/separate/<int:team1_id>/<int:team2_id>/', team_duplicate_views.mark_teams_separate, name='mark_teams_separate'),
    path('admin/team-duplicates/history/', team_duplicate_views.team_duplicate_history, name='team_duplicate_history'),

    path("admin/", admin_site.urls),
    # Summernote editor URLs (includes image upload endpoints)
    path('summernote/', include('django_summernote.urls')),

    path("articles/", views.articles_list, name="articles_list"),
    path("articles/<slug:slug>/", views.articles_detail, name="articles_detail"),

    path("rankings/", views.rankings_list, name="rankings_list"),
    path("rankings/<slug:slug>/", views.rankings_detail, name="rankings_detail"),

    path("mock-drafts/", views.mock_drafts_list, name="mock_drafts_list"),
    path("mock-drafts/<slug:slug>/", views.mock_drafts_detail, name="mock_drafts_detail"),

    path("players/<slug:slug>/", views.players_detail, name="players_detail"),

    # Hitters lists
    path("hitters/college/", views.college_hitters_list, name="college_hitters_list"),
    path("hitters/college/<int:year>/", views.college_hitters_year, name="college_hitters_year"),
    path("hitters/high-school/", views.hs_hitters_list, name="hs_hitters_list"),
    path("hitters/high-school/<int:year>/", views.hs_hitters_year, name="hs_hitters_year"),

    # Stats lists (643 stats)
    path("stats/", views.stats_list, name="stats_list"),
    path("stats/hit/<int:year>/", views.stats_hit_year, name="stats_hit_year"),
    path("stats/pitch/<int:year>/", views.stats_pitch_year, name="stats_pitch_year"),

    path("videos/", views.videos_list, name="videos_list"),

    path("live-games/", views.games_list, name="games_list"),
    path("live-games/<int:year>/<int:month>/<int:day>/", views.games_list, name="games_list_date"),

    path("teams/", views.teams_list, name="teams_list"),
    path("teams/<slug:slug>/", views.team_detail, name="team_detail"),

    path("about-us/", views.about_us, name="about_us"),

    path("", views.index, name="index"),

    # SEO
    path("robots.txt", views.robots_txt, name="robots_txt"),
    path(
        "sitemap.xml",
        sitemap,
        {"sitemaps": {
            # High priority - important for SEO
            "mock_drafts": MockDraftSitemap(),
            "games": GamesSitemap(),
            # Standard priority
            "static": StaticViewSitemap(),
            "articles": ArticleSitemap(),
            "rankings": RankingSitemap(),
            "players": PlayerSitemap(),
        }},
        name="django.contrib.sitemaps.views.sitemap",
    ),

    path("api/search/", views.search, name="search"),
    path("api/v1/players/", views.api_players, name="api_players"),

    # Subscription URLs
    path('subscription/', subscription_views.subscription_dashboard, name='subscription_dashboard'),
    path('subscription/checkout/', subscription_views.create_checkout_session, name='create_checkout_session'),
    path('subscription/success/', subscription_views.subscription_success, name='subscription_success'),
    path('subscription/cancel/', subscription_views.cancel_subscription, name='cancel_subscription'),
    path('subscription/billing/', subscription_views.manage_billing, name='manage_billing'),
    path('webhooks/stripe/', subscription_views.stripe_webhook, name='stripe_webhook'),

    # Authentication URLs
    # Use magic link authentication only
    path('accounts/login/', auth.magic_link_view, name='account_login'),
    path('accounts/signup/', auth.magic_link_signup_view, name='account_signup'),
    path('accounts/', include('allauth.urls')),  # This includes all django-allauth URLs
    path('magic-link/', auth.magic_link_view, name='magic_link'),
    path('magic-link/signup/', auth.magic_link_signup_view, name='magic_link_signup'),
    # Compatibility: allow reverse with 'slug' kwarg used by older tests
    path('magic-link/verify/<slug:slug>/', auth.magic_link_verify_view_slug, name='magic_link_verify'),
    path('magic-link/verify/<path:token>/', auth.magic_link_verify_view, name='magic_link_verify'),


    # Account Management URLs
    path('account/', account_views.account_dashboard, name='account_dashboard'),
    path('account/email/add/', account_views.add_secondary_email, name='add_secondary_email'),
    path('account/email/<int:email_id>/remove/', account_views.remove_secondary_email, name='remove_secondary_email'),
    path('account/email/<int:email_id>/resend/', account_views.resend_verification_email, name='resend_verification_email'),
    # allow empty token via regex path
    re_path(r'^account/email/verify/(?P<token>.*)$', account_views.verify_secondary_email, name='verify_secondary_email'),

]

# Serve media files during development
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)