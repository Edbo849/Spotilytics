from django.urls import path

from . import views

app_name = "music"

urlpatterns = [
    path("", views.index, name="index"),
    path("home/", views.home, name="home"),
    path("artist/<str:artist_id>", views.artist, name="artist"),
    path("search/", views.search, name="search"),
    path("album/<str:album_id>", views.album, name="album"),
    path("track/<str:track_id>", views.track, name="track"),
    path(
        "artist/<str:artist_id>/songs/", views.artist_all_songs, name="artist_all_songs"
    ),
    path("import-history/", views.import_history, name="import_history"),
    path("delete-history/", views.delete_history, name="delete_history"),
    path("genre/<str:genre_name>/", views.genre, name="genre"),
    path("chat/", views.chat, name="chat"),
    path("chat-api/", views.ChatAPI.as_view(), name="chat_api"),
    path("artist-stats/", views.artist_stats, name="artist_stats"),
    path("album-stats/", views.album_stats, name="album_stats"),
    path("track-stats/", views.track_stats, name="track_stats"),
    path("genre-stats/", views.genre_stats, name="genre_stats"),
    path("preview-urls/", views.get_preview_urls, name="preview_urls"),
    path(
        "artist/<str:artist_id>/releases/",
        views.get_artist_releases,
        name="artist_releases",
    ),
]
