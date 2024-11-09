from django.urls import path

from . import views

app_name = "music"

urlpatterns = [
    path("", views.index, name=""),
    path("home/", views.home, name="home"),
    path("artist/<str:artist_id>", views.artist, name="artist"),
    path("search/", views.search, name="search"),
    path("album/<str:album_id>", views.album, name="album"),
]
