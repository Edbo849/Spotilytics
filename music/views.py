import hashlib
import json
import logging
import os
from datetime import datetime

from django.conf import settings
from django.core.cache import cache
from django.core.files.storage import default_storage
from django.db import IntegrityError, transaction
from django.http import HttpRequest, HttpResponse
from django.shortcuts import redirect, render
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt

from music.models import PlayedTrack, SpotifyUser
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
    spotify_user_id = request.session.get("spotify_user_id")
    if not spotify_user_id or not is_spotify_authenticated(spotify_user_id):
        return redirect("spotify-auth")

    time_range = request.GET.get("time_range", "medium_term")

    try:
        top_tracks = get_top_tracks(10, spotify_user_id, time_range)
        top_artists = get_top_artists(10, spotify_user_id, time_range)
        recently_played = get_recently_played(10, spotify_user_id)
        top_genres = get_top_genres(50, spotify_user_id, time_range)

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
    spotify_user_id = request.session.get("spotify_user_id")
    if not spotify_user_id or not is_spotify_authenticated(spotify_user_id):
        return redirect("spotify-auth")

    try:
        artist = get_artist(artist_id, spotify_user_id)
        similar_artists = get_similar_artists(artist_id, spotify_user_id)
        print(f"Similar artists: {similar_artists}")
        albums = fetch_artist_albums(artist_id, spotify_user_id, False)
        top_tracks = fetch_artist_top_tracks(5, artist_id, spotify_user_id)

    except Exception as e:
        logger.critical(f"Error fetching artist data from Spotify: {e}")
        artist, similar_artists, albums, top_tracks = None, [], [], []

    context = {
        "artist": artist,
        "similar_artists": similar_artists,
        "albums": albums,
        "top_tracks": top_tracks,
    }
    return render(request, "music/artist.html", context)


def album(request: HttpRequest, album_id: str) -> HttpResponse:
    spotify_user_id = request.session.get("spotify_user_id")
    if not spotify_user_id or not is_spotify_authenticated(spotify_user_id):
        return redirect("spotify-auth")

    try:
        album = get_album(album_id, spotify_user_id)
        tracks = album["tracks"]["items"]

        artist_id = album["artists"][0]["id"]
        artist_details = get_artist(artist_id, spotify_user_id)
        genres = artist_details.get("genres", [])

        for track in tracks:
            track_details = get_track_details(track["id"], spotify_user_id)
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
    spotify_user_id = request.session.get("spotify_user_id")
    if not spotify_user_id or not is_spotify_authenticated(spotify_user_id):
        return redirect("spotify-auth")

    try:
        track = get_track_details(track_id, spotify_user_id)
        duration_ms = track["duration_ms"]
        track["duration"] = get_duration_ms(duration_ms)
        album_id = track["album"]["id"]
        album = get_album(album_id, spotify_user_id)
        artist_id = track["artists"][0]["id"]
        artist = get_artist(artist_id, spotify_user_id)
        similar_tracks = get_similar_tracks(track_id, spotify_user_id)

    except Exception as e:
        logger.critical(f"Error fetching track data from Spotify: {e}")
        track, album, artist, similar_tracks = None, None, None, []

    context = {
        "track": track,
        "album": album,
        "artist": artist,
        "similar_tracks": similar_tracks,
    }
    return render(request, "music/track.html", context)


def artist_all_songs(request: HttpRequest, artist_id: str) -> HttpResponse:
    spotify_user_id = request.session.get("spotify_user_id")
    if not spotify_user_id or not is_spotify_authenticated(spotify_user_id):
        return redirect("spotify-auth")

    artist_cache_key = f"artist_{artist_id}"
    tracks_cache_key = f"artist_tracks_{artist_id}"
    cache_timeout = 3600

    artist = cache.get(artist_cache_key)
    tracks = cache.get(tracks_cache_key)

    if artist is None or tracks is None:
        try:
            artist = get_artist(artist_id, spotify_user_id)
            cache.set(artist_cache_key, artist, cache_timeout)

            albums = fetch_artist_albums(artist_id, spotify_user_id, True)
            tracks = []
            track_ids = set()

            for album in albums:
                album_data = get_album(album["id"], spotify_user_id)
                album_tracks = album_data["tracks"]["items"]

                for track in album_tracks:
                    if track["id"] not in track_ids:
                        track_ids.add(track["id"])
                        track_details = get_track_details(track["id"], spotify_user_id)
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


@csrf_exempt
@transaction.atomic
def import_history(request: HttpRequest) -> HttpResponse:
    if request.method == "POST":
        files = request.FILES.getlist("history_files")
        if not files:
            return HttpResponse(
                "No files uploaded. Please attach at least one JSON file.", status=400
            )

        spotify_user_id = request.session.get("spotify_user_id")
        user = SpotifyUser.objects.get(spotify_user_id=spotify_user_id)

        for file in files:
            file_content = file.read()
            file_hash = hashlib.sha256(file_content).hexdigest()
            file.seek(0)

            file_path = os.path.join(
                settings.BASE_DIR, "listening_history", f"{file_hash}.json"
            )

            if default_storage.exists(file_path):
                return HttpResponse(
                    "Duplicate file detected. Import rejected.", status=400
                )

            try:
                data = json.loads(file_content.decode("utf-8"))
            except json.JSONDecodeError:
                return HttpResponse(
                    "Invalid JSON file. Please upload a valid JSON file.", status=400
                )

            if not data:
                return HttpResponse(
                    "Empty JSON file. Please upload a non-empty JSON file.", status=400
                )

            if not isinstance(data, list):
                return HttpResponse(
                    "Invalid JSON format. Expected a list of tracks.", status=400
                )

            for item in data:
                if not all(
                    key in item
                    for key in [
                        "ts",
                        "master_metadata_track_name",
                        "master_metadata_album_artist_name",
                        "master_metadata_album_album_name",
                        "spotify_track_uri",
                    ]
                ):
                    return HttpResponse(
                        "Invalid JSON format. Missing required keys in some items.",
                        status=400,
                    )

                played_at_str = item["ts"]
                try:
                    played_at = datetime.strptime(played_at_str, "%Y-%m-%dT%H:%M:%S%z")
                except ValueError:
                    return HttpResponse(
                        f"Invalid timestamp format: {played_at_str}", status=400
                    )

                if played_at > timezone.now():
                    return HttpResponse(
                        f"Invalid timestamp: {played_at_str} is in the future.",
                        status=400,
                    )

                track_name = item["master_metadata_track_name"]
                artist_name = item["master_metadata_album_artist_name"]
                album_name = item["master_metadata_album_album_name"]
                track_uri = item.get("spotify_track_uri")

                if not track_uri or not track_uri.startswith("spotify:track:"):
                    continue

                track_id = track_uri.split(":")[-1]

            for item in data:
                played_at_str = item["ts"]
                played_at = datetime.strptime(played_at_str, "%Y-%m-%dT%H:%M:%S%z")
                track_name = item["master_metadata_track_name"]
                artist_name = item["master_metadata_album_artist_name"]
                album_name = item["master_metadata_album_album_name"]
                track_uri = item.get("spotify_track_uri")

                if not track_uri or not track_uri.startswith("spotify:track:"):
                    continue

                track_id = track_uri.split(":")[-1]

                try:
                    PlayedTrack.objects.create(
                        user=user,
                        track_id=track_id,
                        played_at=played_at,
                        track_name=track_name,
                        artist_name=artist_name,
                        album_name=album_name,
                    )
                except IntegrityError as e:
                    return HttpResponse(f"Database error: {str(e)}", status=500)

            with default_storage.open(file_path, "wb+") as destination:
                for chunk in file.chunks():
                    destination.write(chunk)

        return redirect("music:home")
    return HttpResponse(status=405)


@csrf_exempt
@transaction.atomic
def delete_history(request: HttpRequest) -> HttpResponse:
    if request.method == "POST":
        listening_history_path = os.path.join(settings.BASE_DIR, "listening_history")
        for filename in os.listdir(listening_history_path):
            file_path = os.path.join(listening_history_path, filename)
            if os.path.isfile(file_path):
                os.remove(file_path)

        PlayedTrack.objects.all().delete()

        return HttpResponse("All listening history has been deleted.", status=200)
    return HttpResponse(status=405)
