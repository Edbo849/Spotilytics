import logging

from django.http import HttpRequest, HttpResponse
from django.shortcuts import redirect, render

from spotify.util import is_spotify_authenticated

from .spotify_api import (
    get_album,
    get_artist,
    get_recently_played,
    get_similar_artists,
    get_top_artists,
    get_top_tracks,
    get_track_details,
    search_spotify,
)

logger = logging.getLogger(__name__)


def index(request: HttpRequest) -> HttpResponse:
    return render(request, "music/index.html")


def search(request: HttpRequest) -> HttpResponse:
    query = request.GET.get("q")
    if not query:
        return render(request, "music/search_results.html", {"results": None})

    try:
        results = search_spotify(query, session_id=request.session.session_key)
    except Exception as e:
        logger.critical(f"Error searching Spotify: {e}")
        results = None

    return render(request, "music/search_results.html", {"results": results})


def home(request: HttpRequest) -> HttpResponse:
    if not is_spotify_authenticated(request.session.session_key):
        return redirect("spotify-auth")

    try:
        top_tracks = get_top_tracks(3, session_id=request.session.session_key)
        top_artists = get_top_artists(5, session_id=request.session.session_key)
        recently_played = get_recently_played(
            25, session_id=request.session.session_key
        )
    except Exception as e:
        logger.critical(f"Error fetching data from Spotify: {e}")
        top_tracks, top_artists, recently_played = [], [], []

    context = {
        "top_tracks": top_tracks,
        "top_artists": top_artists,
        "recently_played": recently_played,
    }
    return render(request, "music/home.html", context)


def artist(request: HttpRequest, artist_id: int) -> HttpResponse:
    if not is_spotify_authenticated(request.session.session_key):
        return redirect("spotify-auth")

    try:
        artist = get_artist(str(artist_id), session_id=request.session.session_key)
        similar_artists = get_similar_artists(
            str(artist_id), request.session.session_key
        )
    except Exception as e:
        logger.critical(f"Error fetching artist data from Spotify: {e}")
        artist, similar_artists = None, []

    context = {
        "artist": artist,
        "similar_artists": similar_artists,
    }
    return render(request, "music/artist.html", context)


def album(request: HttpRequest, album_id: str) -> HttpResponse:
    if not is_spotify_authenticated(request.session.session_key):
        return redirect("spotify-auth")

    try:
        album = get_album(album_id, request.session.session_key)
        tracks = album["tracks"]["items"]

        # Fetch genres from the album's artist
        artist_id = album["artists"][0]["id"]
        artist_details = get_artist(artist_id, request.session.session_key)
        genres = artist_details.get("genres", [])
        similar_albums = artist_details.get("albums", [])

        # Preprocess track data
        for track in tracks:
            track_details = get_track_details(track["id"], request.session.session_key)
            duration_ms = track["duration_ms"]
            minutes = duration_ms // 60000
            seconds = (duration_ms // 1000) % 60
            track["duration"] = f"{minutes}:{seconds:02d}"
            track["preview_url"] = track.get("preview_url", None)
            track["popularity"] = track_details.get("popularity", "N/A")
    except Exception as e:
        logger.critical(f"Error fetching album data from Spotify: {e}")
        album, tracks, genres, similar_albums = None, [], [], []

    context = {
        "album": album,
        "tracks": tracks,
        "genres": genres,
        "similar_albums": similar_albums,
    }
    return render(request, "music/album.html", context)
