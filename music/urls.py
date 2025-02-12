from django.urls import path

from music.views import (
    ChatAPI,
    album,
    album_stats,
    artist,
    artist_all_songs,
    artist_stats,
    chat,
    genre,
    genre_stats,
    get_artist_releases,
    get_item_stats,
    get_preview_urls,
    history,
    home,
    index,
    new_releases,
    recently_played_section,
    search,
    track,
    track_stats,
)

app_name = "music"

urlpatterns = [
    path("", index, name="index"),
    path("home/", home, name="home"),
    path("artist/<str:artist_id>", artist, name="artist"),
    path("search/", search, name="search"),
    path("album/<str:album_id>", album, name="album"),
    path("track/<str:track_id>", track, name="track"),
    path(
        "artist/<str:artist_id>/songs/",
        artist_all_songs,
        name="artist_all_songs",
    ),
    path("import-history/", history.import_history, name="import_history"),
    path("delete-history/", history.delete_history, name="delete_history"),
    path("genre/<str:genre_name>/", genre, name="genre"),
    path("chat/", chat, name="chat"),
    path("new-releases/", new_releases.new_releases, name="new_releases"),
    path("chat-api/", ChatAPI.as_view(), name="chat_api"),
    path("artist-stats/", artist_stats, name="artist_stats"),
    path("album-stats/", album_stats, name="album_stats"),
    path("track-stats/", track_stats, name="track_stats"),
    path("genre-stats/", genre_stats, name="genre_stats"),
    path("preview-urls/", get_preview_urls, name="preview_urls"),
    path(
        "artist/<str:artist_id>/releases/",
        get_artist_releases,
        name="artist_releases",
    ),
    path("recently-played/", recently_played_section, name="recently-played"),
    path(
        "item-stats/<str:item_type>/<str:item_id>/",
        get_item_stats,
        name="get_item_stats",
    ),
]
