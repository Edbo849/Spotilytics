import logging

from django.core.cache import cache
from django.http import HttpRequest, HttpResponse
from django.shortcuts import redirect, render

from spotify.util import is_spotify_authenticated

from .spotify_api import (
    fetch_artist_albums,
    fetch_artist_top_tracks,
    get_album,
    get_artist,
    get_duration_ms,
    get_recently_played,
    get_similar_artists,
    get_similar_tracks,
    get_top_artists,
    get_top_genres,
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

    time_range = request.GET.get("time_range", "medium_term")

    try:
        top_tracks = get_top_tracks(10, request.session.session_key, time_range)
        top_artists = get_top_artists(10, request.session.session_key, time_range)
        recently_played = get_recently_played(10, request.session.session_key)
        top_genres = get_top_genres(50, request.session.session_key, time_range)

    except Exception as e:
        logger.error(f"Error fetching data from Spotify: {e}")
        top_tracks, top_artists, recently_played, top_genres = [], [], [], []

    context = {
        "top_tracks": top_tracks,
        "top_artists": top_artists,
        "recently_played": recently_played,
        "top_genres": top_genres,
        "time_range": time_range,
    }
    return render(request, "music/home.html", context)


def artist(request: HttpRequest, artist_id: str) -> HttpResponse:
    if not is_spotify_authenticated(request.session.session_key):
        return redirect("spotify-auth")

    try:
        session_id = request.session.session_key
        artist = get_artist(artist_id, session_id)
        similar_artists = get_similar_artists(artist_id, session_id)
        albums = fetch_artist_albums(artist_id, session_id, False)
        top_tracks = fetch_artist_top_tracks(5, artist_id, session_id)

    except Exception as e:
        logger.critical(f"Error fetching artist data from Spotify: {e}")
        artist, similar_artists = None, []

    context = {
        "artist": artist,
        "similar_artists": similar_artists,
        "albums": albums,
        "top_tracks": top_tracks,
    }
    return render(request, "music/artist.html", context)


def album(request: HttpRequest, album_id: str) -> HttpResponse:
    if not is_spotify_authenticated(request.session.session_key):
        return redirect("spotify-auth")

    try:
        album = get_album(album_id, request.session.session_key)
        tracks = album["tracks"]["items"]

        artist_id = album["artists"][0]["id"]
        artist_details = get_artist(artist_id, request.session.session_key)
        genres = artist_details.get("genres", [])

        for track in tracks:
            track_details = get_track_details(track["id"], request.session.session_key)
            duration_ms = track["duration_ms"]
            track["duration"] = get_duration_ms(duration_ms)
            track["preview_url"] = track.get("preview_url", None)
            track["popularity"] = track_details.get("popularity", "N/A")
    except Exception as e:
        logger.critical(f"Error fetching album data from Spotify: {e}")
        album, tracks, genres = None, [], []
        artist_id = None

    context = {
        "artist_id": artist_id,
        "album": album,
        "tracks": tracks,
        "genres": genres,
    }
    return render(request, "music/album.html", context)


def track(request: HttpRequest, track_id: str) -> HttpResponse:
    if not is_spotify_authenticated(request.session.session_key):
        return redirect("spotify-auth")

    try:
        track = get_track_details(track_id, request.session.session_key)
        duration_ms = track["duration_ms"]
        track["duration"] = get_duration_ms(duration_ms)
        album_id = track["album"]["id"]
        album = get_album(album_id, request.session.session_key)
        artist_id = track["artists"][0]["id"]
        artist = get_artist(artist_id, request.session.session_key)
        similar_tracks = get_similar_tracks(track_id, request.session.session_key)

    except Exception as e:
        logger.critical(f"Error fetching track data from Spotify: {e}")
        track, album, artist = None, None, None

    context = {
        "track": track,
        "album": album,
        "artist": artist,
        "similar_tracks": similar_tracks,
    }
    return render(request, "music/track.html", context)


def artist_all_songs(request: HttpRequest, artist_id: str) -> HttpResponse:
    if not is_spotify_authenticated(request.session.session_key):
        return redirect("spotify-auth")

    session_id = request.session.session_key

    artist_cache_key = f"artist_{artist_id}"
    tracks_cache_key = f"artist_tracks_{artist_id}"
    cache_timeout = 3600

    artist = cache.get(artist_cache_key)
    tracks = cache.get(tracks_cache_key)

    if artist is None or tracks is None:
        try:
            artist = get_artist(artist_id, session_id)
            cache.set(artist_cache_key, artist, cache_timeout)

            albums = fetch_artist_albums(artist_id, session_id, True)
            tracks = []
            track_ids = set()

            for album in albums:
                album_data = get_album(album["id"], session_id)
                album_tracks = album_data["tracks"]["items"]

                for track in album_tracks:
                    if track["id"] not in track_ids:
                        track_ids.add(track["id"])
                        track_details = get_track_details(track["id"], session_id)
                        track["album"] = {
                            "id": album["id"],
                            "name": album["name"],
                            "images": album["images"],
                        }
                        track["duration"] = get_duration_ms(track["duration_ms"])
                        track["popularity"] = track_details.get("popularity", "N/A")
                        tracks.append(track)

            cache.set(tracks_cache_key, tracks, cache_timeout)

        except Exception as e:
            logger.error(f"Error fetching artist data from Spotify: {e}")
            artist, tracks = None, []

    context = {
        "artist": artist,
        "tracks": tracks,
    }
    return render(request, "music/artist_tracks.html", context)
