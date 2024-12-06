import asyncio
import hashlib
import json
import logging
import os
from datetime import datetime

from asgiref.sync import sync_to_async
from django.conf import settings
from django.core.cache import cache
from django.core.files.storage import default_storage
from django.db import IntegrityError
from django.http import HttpRequest, HttpResponse
from django.shortcuts import redirect, render
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt

from music.models import PlayedTrack, SpotifyUser
from music.utils import get_listening_stats
from spotify.util import is_spotify_authenticated

from .spotify_api import (
    fetch_artist_albums,
    fetch_artist_top_tracks,
    get_album,
    get_artist,
    get_duration_ms,
    get_items_by_genre,
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


async def search(request: HttpRequest) -> HttpResponse:
    spotify_user_id = await sync_to_async(request.session.get)("spotify_user_id")
    if not spotify_user_id or not await sync_to_async(is_spotify_authenticated)(
        spotify_user_id
    ):
        return redirect("spotify-auth")
    query = request.GET.get("q")
    if not query:
        return render(request, "music/search_results.html", {"results": None})

    try:
        results = await search_spotify(query, spotify_user_id)
    except Exception as e:
        logger.critical(f"Error searching Spotify: {e}")
        results = None

    return render(request, "music/search_results.html", {"results": results})


async def home(request: HttpRequest) -> HttpResponse:
    spotify_user_id = await sync_to_async(request.session.get)("spotify_user_id")
    if not spotify_user_id or not await sync_to_async(is_spotify_authenticated)(
        spotify_user_id
    ):
        return redirect("spotify-auth")

    try:
        user = await sync_to_async(SpotifyUser.objects.get)(
            spotify_user_id=spotify_user_id
        )
        has_history = await sync_to_async(
            PlayedTrack.objects.filter(user=user).exists
        )()
    except SpotifyUser.DoesNotExist:
        return redirect("spotify-auth")

    time_range = request.GET.get("time_range", "medium_term")

    stats = None
    if has_history:
        stats = await sync_to_async(get_listening_stats)(user, time_range)

    try:
        top_tracks, top_artists, recently_played, top_genres = await asyncio.gather(
            get_top_tracks(10, spotify_user_id, time_range),
            get_top_artists(10, spotify_user_id, time_range),
            get_recently_played(10, spotify_user_id),
            get_top_genres(50, spotify_user_id, time_range),
        )
    except Exception as e:
        logger.error(f"Error fetching data from Spotify: {e}")
        top_tracks, top_artists, recently_played, top_genres = [], [], [], []

    context = {
        "listening_stats": stats,
        "top_tracks": top_tracks,
        "top_artists": top_artists,
        "recently_played": recently_played,
        "top_genres": top_genres,
        "time_range": time_range,
    }
    return render(request, "music/home.html", context)


async def artist(request: HttpRequest, artist_id: str) -> HttpResponse:
    spotify_user_id = await sync_to_async(request.session.get)("spotify_user_id")
    if not spotify_user_id or not await sync_to_async(is_spotify_authenticated)(
        spotify_user_id
    ):
        return redirect("spotify-auth")

    try:
        artist = await get_artist(artist_id, spotify_user_id)
        similar_artists_spotify = await get_similar_artists(
            artist["name"], spotify_user_id
        )
        albums = await fetch_artist_albums(artist_id, spotify_user_id)
        top_tracks = await fetch_artist_top_tracks(5, artist_id, spotify_user_id)

        for track in top_tracks:
            track_details = await get_track_details(track["id"], spotify_user_id)
            track["preview_url"] = track_details.get("preview_url")
            track["album"] = track_details.get("album")

    except Exception as e:
        logger.critical(f"Error fetching artist data from Spotify: {e}")
        artist, similar_artists_spotify, albums, top_tracks = None, [], [], []

    context = {
        "artist": artist,
        "similar_artists": similar_artists_spotify,
        "albums": albums,
        "top_tracks": top_tracks,
    }
    return await sync_to_async(render)(request, "music/artist.html", context)


async def album(request: HttpRequest, album_id: str) -> HttpResponse:
    spotify_user_id = await sync_to_async(request.session.get)("spotify_user_id")
    if not spotify_user_id or not await sync_to_async(is_spotify_authenticated)(
        spotify_user_id
    ):
        return redirect("spotify-auth")

    try:
        album = await get_album(album_id, spotify_user_id)
        tracks = album["tracks"]["items"]

        artist_id = album["artists"][0]["id"]
        artist_details = await get_artist(artist_id, spotify_user_id)
        genres = artist_details.get("genres", [])

        for track in tracks:
            track_details = await get_track_details(track["id"], spotify_user_id)
            duration_ms = track["duration_ms"]
            track["duration"] = get_duration_ms(duration_ms)
            track["preview_url"] = track_details.get("preview_url", None)
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
    return await sync_to_async(render)(request, "music/album.html", context)


async def track(request: HttpRequest, track_id: str) -> HttpResponse:
    spotify_user_id = await sync_to_async(request.session.get)("spotify_user_id")
    if not spotify_user_id or not await sync_to_async(is_spotify_authenticated)(
        spotify_user_id
    ):
        return redirect("spotify-auth")

    try:
        track = await get_track_details(track_id, spotify_user_id)
        if not track:
            raise ValueError("Track details not found.")

        duration_ms = track.get("duration_ms")
        track["duration"] = (
            await sync_to_async(get_duration_ms)(duration_ms) if duration_ms else "N/A"
        )

        album = (
            await get_album(track["album"]["id"], spotify_user_id)
            if track.get("album")
            else None
        )
        artist_id = (
            track["artists"][0]["id"]
            if track.get("artists") and len(track["artists"]) > 0
            else None
        )

        if not artist_id:
            logger.error(f"Artist ID missing for track {track_id}.")
            artist = None
        else:
            artist = await get_artist(artist_id, spotify_user_id)

        similar_tracks = await get_similar_tracks(track_id, spotify_user_id)

    except Exception as e:
        logger.critical(f"Error fetching track data from Spotify: {e}")
        track, album, artist, similar_tracks = None, None, None, []

    if not artist_id:
        logger.error("Artist ID is missing. Cannot reverse 'artist' URL.")
        return HttpResponse("Artist information is unavailable.", status=500)

    context = {
        "track": track,
        "album": album,
        "artist": artist,
        "similar_tracks": similar_tracks,
    }

    return await sync_to_async(render)(request, "music/track.html", context)


async def genre(request: HttpRequest, genre_name: str) -> HttpResponse:
    spotify_user_id = await sync_to_async(request.session.get)("spotify_user_id")
    if not spotify_user_id or not await sync_to_async(is_spotify_authenticated)(
        spotify_user_id
    ):
        return await sync_to_async(redirect)("spotify-auth")

    try:
        artists, tracks = await get_items_by_genre(genre_name, spotify_user_id)
    except Exception as e:
        logger.error(f"Error fetching items for genre {genre_name}: {e}")
        artists, tracks = [], []

    context = {
        "genre_name": genre_name,
        "artists": artists,
        "tracks": tracks,
    }
    return await sync_to_async(render)(request, "music/genre.html", context)


@csrf_exempt
async def artist_all_songs(request: HttpRequest, artist_id: str) -> HttpResponse:
    spotify_user_id = await sync_to_async(request.session.get)("spotify_user_id")
    if not spotify_user_id or not await sync_to_async(is_spotify_authenticated)(
        spotify_user_id
    ):
        return await sync_to_async(redirect)("spotify-auth")

    artist_cache_key = f"artist_{artist_id}"
    tracks_cache_key = f"artist_tracks_{artist_id}"
    cache_timeout = 3600

    artist = await sync_to_async(cache.get)(artist_cache_key)
    tracks = await sync_to_async(cache.get)(tracks_cache_key)

    if artist is None or tracks is None:
        try:
            artist = await get_artist(artist_id, spotify_user_id)
            await sync_to_async(cache.set)(artist_cache_key, artist, cache_timeout)

            albums = await fetch_artist_albums(artist_id, spotify_user_id, True)
            tracks = []
            track_ids = set()

            for album in albums:
                album_data = await get_album(album["id"], spotify_user_id)
                album_tracks = album_data["tracks"]["items"]

                for track in album_tracks:
                    if track["id"] not in track_ids:
                        track_ids.add(track["id"])
                        track_details = await get_track_details(
                            track["id"], spotify_user_id
                        )
                        track["album"] = {
                            "id": album["id"],
                            "name": album["name"],
                            "images": album["images"],
                        }
                        track["duration"] = await sync_to_async(get_duration_ms)(
                            track["duration_ms"]
                        )
                        track["preview_url"] = track_details.get("preview_url", None)
                        track["popularity"] = track_details.get("popularity", "N/A")
                        tracks.append(track)

            await sync_to_async(cache.set)(tracks_cache_key, tracks, cache_timeout)

        except Exception as e:
            logger.error(f"Error fetching artist data from Spotify: {e}")
            artist, tracks = None, []

    context = {
        "artist": artist,
        "tracks": tracks,
    }
    return await sync_to_async(render)(request, "music/artist_tracks.html", context)


@csrf_exempt
async def import_history(request: HttpRequest) -> HttpResponse:
    if request.method == "POST":
        files = request.FILES.getlist("history_files")
        if not files:
            return HttpResponse(
                "No files uploaded. Please attach at least one JSON file.", status=400
            )

        spotify_user_id = await sync_to_async(request.session.get)("spotify_user_id")
        if not spotify_user_id:
            return await sync_to_async(redirect)("spotify-auth")

        try:
            user = await sync_to_async(SpotifyUser.objects.get)(
                spotify_user_id=spotify_user_id
            )
        except SpotifyUser.DoesNotExist:
            return HttpResponse("User does not exist.", status=400)
        except Exception as e:
            logger.error(f"Database error: {e}")
            return HttpResponse(f"Database error: {str(e)}", status=500)

        for file in files:
            file_content = await sync_to_async(file.read)()
            file_hash = hashlib.sha256(file_content).hexdigest()
            await sync_to_async(file.seek)(0)

            file_path = os.path.join("listening_history", f"{file_hash}.json")

            exists = await sync_to_async(default_storage.exists)(file_path)
            if exists:
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
                required_keys = [
                    "ts",
                    "master_metadata_track_name",
                    "master_metadata_album_artist_name",
                    "master_metadata_album_album_name",
                    "spotify_track_uri",
                ]
                if not all(key in item for key in required_keys):
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
                duration_ms = item.get("ms_played", 0)

                if not track_uri or not track_uri.startswith("spotify:track:"):
                    continue

                track_id = track_uri.split(":")[-1]

                try:
                    await sync_to_async(PlayedTrack.objects.create)(
                        user=user,
                        track_id=track_id,
                        played_at=played_at,
                        track_name=track_name,
                        artist_name=artist_name,
                        album_name=album_name,
                        duration_ms=duration_ms,
                    )
                except IntegrityError as e:
                    return HttpResponse(f"Database error: {str(e)}", status=500)

            await sync_to_async(default_storage.save)(file_path, file)

        return await sync_to_async(redirect)("music:home")
    return HttpResponse(status=405)


@csrf_exempt
async def delete_history(request: HttpRequest) -> HttpResponse:
    if request.method == "POST":
        listening_history_path = os.path.join(
            settings.BASE_DIR, "media/listening_history"
        )

        try:
            filenames = await sync_to_async(os.listdir)(listening_history_path)
        except FileNotFoundError:
            return HttpResponse("Listening history directory not found.", status=404)
        except Exception as e:
            logger.error(f"Error accessing listening history directory: {e}")
            return HttpResponse(f"Error: {str(e)}", status=500)

        for filename in filenames:
            file_path = os.path.join(listening_history_path, filename)
            if await sync_to_async(os.path.isfile)(file_path):
                try:
                    await sync_to_async(os.remove)(file_path)
                except Exception as e:
                    logger.error(f"Error removing file {file_path}: {e}")
                    return HttpResponse(f"Error removing file: {file_path}", status=500)

        try:
            await sync_to_async(PlayedTrack.objects.all().delete)()
        except Exception as e:
            logger.error(f"Error deleting listening history from database: {e}")
            return HttpResponse(f"Database error: {str(e)}", status=500)

        return HttpResponse("All listening history has been deleted.", status=200)
    return HttpResponse(status=405)
