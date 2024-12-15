import hashlib
import json
import logging
import os
from datetime import datetime, timedelta

from asgiref.sync import sync_to_async
from django.conf import settings
from django.core.cache import cache
from django.core.files.storage import default_storage
from django.db import IntegrityError, transaction
from django.http import HttpRequest, HttpResponse
from django.shortcuts import redirect, render
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt

from music.graphs import generate_plotly_line_graph, generate_plotly_pie_chart
from music.models import PlayedTrack, SpotifyUser
from music.SpotifyClient import SpotifyClient
from music.utils import (
    get_listening_stats,
    get_recently_played,
    get_top_artists,
    get_top_genres,
    get_top_tracks,
)
from spotify.util import is_spotify_authenticated

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
        async with SpotifyClient(spotify_user_id) as client:
            results = await client.search_spotify(query)
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

    time_range = request.GET.get("time_range", "all_time")
    start_date = request.GET.get("start_date")
    end_date = request.GET.get("end_date")

    error_message = None

    if time_range == "custom":
        if not start_date or not end_date:
            error_message = (
                "Both start date and end date are required for a custom range."
            )
        else:
            try:
                start = datetime.strptime(start_date, "%Y-%m-%d")
                end = datetime.strptime(end_date, "%Y-%m-%d")
                if start > end:
                    error_message = "Start date cannot be after end date."
                elif end > timezone.now() or start > timezone.now():
                    error_message = "Dates cannot be in the future."
            except ValueError:
                error_message = "Invalid date format. Please use YYYY-MM-DD."

    stats = None
    if has_history and not error_message:
        # Set since and until based on time_range
        since, until = None, None
        if time_range == "last_7_days":
            since = timezone.now() - timedelta(days=7)
            until = timezone.now()
        elif time_range == "last_4_weeks":
            since = timezone.now() - timedelta(weeks=4)
            until = timezone.now()
        elif time_range == "6_months":
            since = timezone.now() - timedelta(days=182)
            until = timezone.now()
        elif time_range == "last_year":
            since = timezone.now() - timedelta(days=365)
            until = timezone.now()
        elif time_range == "custom" and start_date and end_date:
            since = timezone.make_aware(datetime.strptime(start_date, "%Y-%m-%d"))
            until = timezone.make_aware(
                datetime.strptime(end_date, "%Y-%m-%d")
            ) + timedelta(days=1)
        else:
            since = None
            until = None

        # Fetch stats using the correct time range
        stats = await sync_to_async(get_listening_stats)(
            user, time_range, start_date, end_date
        )
        logger.debug(f"Listening stats: {stats}")

        # Use sync_to_async to call the functions with since and until
        top_tracks = await get_top_tracks(user, since, until, 10)
        top_artists = await get_top_artists(user, since, until, 10)
        recently_played = await get_recently_played(user, since, until, 20)
        top_genres = await get_top_genres(user, since, until, 10)
    else:
        top_tracks, top_artists, top_genres, recently_played = [], [], [], []

    # Ensure stats is a dictionary
    stats = stats or {}

    listening_dates = stats.get("dates", [])
    listening_counts = stats.get("counts", [])
    x_label = stats.get("x_label", "Date")

    line_graph = (
        generate_plotly_line_graph(listening_dates, listening_counts, x_label)
        if listening_dates
        else None
    )

    genres = [item["genre"] for item in top_genres] if top_genres else []
    genre_counts = [item["count"] for item in top_genres] if top_genres else []
    pie_chart = generate_plotly_pie_chart(genres, genre_counts) if genres else None

    context = {
        "line_graph": line_graph,
        "pie_chart": pie_chart,
        "listening_stats": stats,
        "top_tracks": top_tracks,
        "top_artists": top_artists,
        "recently_played": recently_played,
        "time_range": time_range,
        "start_date": start_date,
        "end_date": end_date,
        "error_message": error_message,
    }

    return render(request, "music/home.html", context)


async def artist(request: HttpRequest, artist_id: str) -> HttpResponse:
    spotify_user_id = await sync_to_async(request.session.get)("spotify_user_id")
    if not spotify_user_id or not await sync_to_async(is_spotify_authenticated)(
        spotify_user_id
    ):
        return redirect("spotify-auth")

    try:
        async with SpotifyClient(spotify_user_id) as client:
            artist = await client.get_artist(artist_id)
            similar_artists_spotify = await client.get_similar_artists(artist["name"])
            albums = await client.get_artist_albums(artist_id)
            top_tracks = await client.get_artist_top_tracks(5, artist_id)

            for track in top_tracks:
                track_details = await client.get_track_details(track["id"])
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
        async with SpotifyClient(spotify_user_id) as client:
            album = await client.get_album(album_id)
            tracks = album["tracks"]["items"]

            artist_id = album["artists"][0]["id"]
            artist_details = await client.get_artist(artist_id)
            genres = artist_details.get("genres", [])

            for track in tracks:
                track_details = await client.get_track_details(track["id"])
                duration_ms = track["duration_ms"]
                track["duration"] = client.get_duration_ms(duration_ms)
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

    artist_id = None

    try:
        async with SpotifyClient(spotify_user_id) as client:
            logger.critical("Fetching track details")
            track = await client.get_track_details(track_id)
            if not track:
                raise ValueError("Track details not found.")

            duration_ms = track.get("duration_ms")
            track["duration"] = (
                await sync_to_async(client.get_duration_ms)(duration_ms)
                if duration_ms
                else "N/A"
            )

            album = (
                await client.get_album(track["album"]["id"])
                if track.get("album")
                else None
            )
            artist_id = (
                track["artists"][0]["id"]
                if track.get("artists") and len(track["artists"]) > 0
                else None
            )

            if not artist_id:
                artist = None
            else:
                artist = await client.get_artist(artist_id)

            similar_tracks = await client.get_similar_tracks(track_id, 6)

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
        async with SpotifyClient(spotify_user_id) as client:
            artists, tracks = await client.get_items_by_genre(genre_name)
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
            async with SpotifyClient(spotify_user_id) as client:
                artist = await client.get_artist(artist_id)
                await sync_to_async(cache.set)(artist_cache_key, artist, cache_timeout)

                albums = await client.get_artist_albums(artist_id, True)
                tracks = []
                track_ids = set()

                for album in albums:
                    album_data = await client.get_album(album["id"])
                    album_tracks = album_data["tracks"]["items"]

                    for track in album_tracks:
                        if track["id"] not in track_ids:
                            track_ids.add(track["id"])
                            track_details = await client.get_track_details(track["id"])
                            track["album"] = {
                                "id": album["id"],
                                "name": album["name"],
                                "images": album["images"],
                            }
                            track["duration"] = await sync_to_async(
                                client.get_duration_ms
                            )(track["duration_ms"])

                            track["preview_url"] = track_details.get(
                                "preview_url", None
                            )
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


@sync_to_async
def save_tracks_atomic(user, track_info_list, track_details_dict, artist_details_dict):
    count = 0
    with transaction.atomic():
        for info in track_info_list:
            track_id = info["track_id"]
            played_at = info["played_at"]
            track_name = info["track_name"]
            artist_name = info["artist_name"]
            album_name = info["album_name"]
            duration_ms = info["duration_ms"]

            track_details = track_details_dict.get(track_id, {})
            popularity = track_details.get("popularity", 0)
            album_info = track_details.get("album", {})
            artist_info_list = track_details.get("artists", [])

            genres = []

            album_id = album_info.get("id") if album_info else None

            if artist_info_list:
                artist_info = artist_info_list[0]
                artist_id = artist_info.get("id")
                artist_details = artist_details_dict.get(artist_id, {})
                genres = artist_details.get("genres", [])
            else:
                artist_id = None

            exists = PlayedTrack.objects.filter(
                user=user, track_id=track_id, played_at=played_at
            ).exists()

            if exists:
                logger.info(
                    f"Duplicate track found: {track_id} at {played_at}. Skipping."
                )
                continue

            try:
                PlayedTrack.objects.create(
                    user=user,
                    track_id=track_id,
                    played_at=played_at,
                    track_name=track_name,
                    artist_name=artist_name,
                    album_name=album_name,
                    duration_ms=duration_ms,
                    genres=genres,
                    popularity=popularity,
                    artist_id=artist_id,
                    album_id=album_id,
                )
                count += 1
            except IntegrityError as e:
                logger.error(f"Database error while adding track {track_id}: {e}")
                continue
    return count


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
            try:
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
                        "Invalid JSON file. Please upload a valid JSON file.",
                        status=400,
                    )

                if not data:
                    return HttpResponse(
                        "Empty JSON file. Please upload a non-empty JSON file.",
                        status=400,
                    )

                if not isinstance(data, list):
                    return HttpResponse(
                        "Invalid JSON format. Expected a list of tracks.", status=400
                    )

                track_ids = []
                durations = {}
                track_info_list = []

                for item in data:
                    required_keys = [
                        "ts",
                        "master_metadata_track_name",
                        "master_metadata_album_artist_name",
                        "master_metadata_album_album_name",
                        "spotify_track_uri",
                    ]
                    if not all(key in item for key in required_keys):
                        continue  # Skip items with missing keys

                    played_at_str = item["ts"]
                    try:
                        played_at = datetime.strptime(
                            played_at_str, "%Y-%m-%dT%H:%M:%S%z"
                        )
                    except ValueError:
                        continue  # Skip items with invalid timestamps

                    if played_at > timezone.now():
                        continue  # Skip items with future timestamps

                    track_name = item["master_metadata_track_name"]
                    artist_name = item["master_metadata_album_artist_name"]
                    album_name = item["master_metadata_album_album_name"]
                    track_uri = item.get("spotify_track_uri")
                    duration_ms = item.get("ms_played", 0)

                    if not track_uri or not track_uri.startswith("spotify:track:"):
                        continue

                    track_id = track_uri.split(":")[-1]
                    track_ids.append(track_id)
                    durations[track_id] = duration_ms
                    track_info_list.append(
                        {
                            "track_id": track_id,
                            "played_at": played_at,
                            "track_name": track_name,
                            "artist_name": artist_name,
                            "album_name": album_name,
                            "duration_ms": duration_ms,
                        }
                    )

                if not track_ids:
                    return HttpResponse(
                        "No valid tracks found in the uploaded file.", status=400
                    )

                # Batch fetch track details
                batch_size = 50
                track_details_dict = {}
                for i in range(0, len(track_ids), batch_size):
                    batch_ids = track_ids[i : i + batch_size]
                    async with SpotifyClient(spotify_user_id) as client:
                        track_details_response = (
                            await client.get_multiple_track_details(batch_ids)
                        )
                    track_details_list = track_details_response.get("tracks", [])

                    for track_details in track_details_list:
                        track_id = track_details.get("id")
                        if track_id:
                            track_details_dict[track_id] = track_details

                # Fetch artist details and cache them
                artist_ids = set()
                for track_details in track_details_dict.values():
                    artist_info_list = track_details.get("artists", [])
                    if artist_info_list:
                        artist_id = artist_info_list[0].get("id")
                        if artist_id:
                            artist_ids.add(artist_id)

                artist_details_dict = {}
                for i in range(0, len(artist_ids), batch_size):
                    batch_artist_ids = list(artist_ids)[i : i + batch_size]
                    async with SpotifyClient(spotify_user_id) as client:
                        artists_response = await client.get_multiple_artists(
                            batch_artist_ids
                        )
                    artist_details_list = artists_response.get("artists", [])
                    for artist_details in artist_details_list:
                        artist_id = artist_details.get("id")
                        if artist_id:
                            artist_details_dict[artist_id] = artist_details

                # Begin atomic transaction
                new_tracks_added = await save_tracks_atomic(
                    user, track_info_list, track_details_dict, artist_details_dict
                )

                # If all processing steps succeed, save the file
                await sync_to_async(default_storage.save)(file_path, file)
                logger.info(
                    f"Successfully imported and saved file: {file.name} {new_tracks_added} tracks)"
                )

            except Exception as e:
                logger.error(f"Failed to import file {file.name}: {e}")
                return HttpResponse(
                    f"Failed to import file {file.name}: {str(e)}", status=500
                )

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
