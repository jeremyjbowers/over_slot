from django.contrib import admin
from django.urls import include, path

from overslot import views

urlpatterns = [
    path("admin/", admin.site.urls),

    path("articles/", views.articles_list),
    path("articles/<str:slug>/", views.articles_detail),

    path("rankings/", views.rankings_list),
    path("rankings/<str:slug>/", views.rankings_detail),

    path("players/<str:slug>/", views.players_detail),

    path("", views.index),
]