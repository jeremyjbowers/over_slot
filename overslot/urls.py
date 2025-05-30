from django.contrib import admin
from django.urls import include, path
from django.contrib.auth.views import LogoutView

from overslot import views
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

    # Authentication URLs
    path('accounts/', include('allauth.urls')),  # This includes all django-allauth URLs
    path('magic-link/', auth.magic_link_view, name='magic_link'),
    path('magic-link/signup/', auth.magic_link_signup_view, name='magic_link_signup'),
    path('magic-link/verify/<str:token>/', auth.magic_link_verify_view, name='magic_link_verify'),
]