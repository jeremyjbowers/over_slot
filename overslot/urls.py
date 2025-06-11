from django.contrib import admin
from django.urls import include, path
from django.contrib.auth.views import LogoutView

from overslot import views, subscription_views
from . import auth

urlpatterns = [
    path("admin/", admin.site.urls),

    path("articles/", views.articles_list, name="articles_list"),
    path("articles/<slug:slug>/", views.articles_detail, name="articles_detail"),

    path("rankings/", views.rankings_list, name="rankings_list"),
    path("rankings/<slug:slug>/", views.rankings_detail, name="rankings_detail"),

    path("players/<slug:slug>/", views.players_detail, name="players_detail"),

    path("", views.index, name="index"),

    path("api/search/", views.search, name="search"),

    # Subscription URLs
    path('subscription/', subscription_views.subscription_dashboard, name='subscription_dashboard'),
    path('subscription/checkout/', subscription_views.create_checkout_session, name='create_checkout_session'),
    path('subscription/success/', subscription_views.subscription_success, name='subscription_success'),
    path('subscription/cancel/', subscription_views.cancel_subscription, name='cancel_subscription'),
    path('subscription/billing/', subscription_views.manage_billing, name='manage_billing'),
    path('webhooks/stripe/', subscription_views.stripe_webhook, name='stripe_webhook'),

    # Authentication URLs
    path('accounts/', include('allauth.urls')),  # This includes all django-allauth URLs
    path('magic-link/', auth.magic_link_view, name='magic_link'),
    path('magic-link/signup/', auth.magic_link_signup_view, name='magic_link_signup'),
    path('magic-link/verify/<str:token>/', auth.magic_link_verify_view, name='magic_link_verify'),
]