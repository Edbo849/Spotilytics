import asyncio
import hashlib
import json
import logging
import os
from datetime import datetime, timedelta

import openai
from asgiref.sync import sync_to_async
from django.conf import settings
from django.core.files.storage import default_storage
from django.db import IntegrityError, transaction
from django.db.models import Count
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import redirect, render
from django.utils import timezone
from django.utils.decorators import method_decorator
from django.views import View
from django.views.decorators.cache import cache_page
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.vary import vary_on_cookie

from music.graphs import (
    generate_chartjs_doughnut_chart,
    generate_chartjs_line_graph,
    generate_chartjs_pie_chart,
    generate_chartjs_polar_area_chart,
    generate_chartjs_radar_chart,
)
from music.models import PlayedTrack, SpotifyUser
from music.SpotifyClient import SpotifyClient
from music.utils import (
    get_date_range,
    get_doughnut_chart_data,
    get_hourly_listening_data,
    get_listening_stats,
    get_radar_chart_data,
    get_recently_played,
    get_streaming_trend_data,
    get_top_albums,
    get_top_artists,
    get_top_genres,
    get_top_tracks,
)
from spotify.util import is_spotify_authenticated

logger = logging.getLogger(__name__)


def index(request: HttpRequest) -> HttpResponse:
    spotify_user_id = request.session.get("spotify_user_id")
    if not spotify_user_id or not is_spotify_authenticated(spotify_user_id):
        if "spotify_user_id" in request.session:
            request.session.flush()
        return render(request, "music/index.html")
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


@vary_on_cookie
@cache_page(60 * 30)
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

    time_range = request.GET.get("time_range", "last_4_weeks")
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
                naive_start = datetime.strptime(start_date, "%Y-%m-%d")
                naive_end = datetime.strptime(end_date, "%Y-%m-%d")

                start = timezone.make_aware(naive_start)
                end = timezone.make_aware(naive_end) + timedelta(days=1)

                if start > end:
                    error_message = "Start date cannot be after end date."
                elif end > timezone.now() or start > timezone.now():
                    error_message = "Dates cannot be in the future."
            except ValueError:
                error_message = "Invalid date format. Please use YYYY-MM-DD."

    stats = None
    if has_history:
        try:
            since, until = await get_date_range(time_range, start_date, end_date)

            stats = await sync_to_async(get_listening_stats)(
                user, time_range, start_date, end_date
            )

            top_tracks = await get_top_tracks(user, since, until, 10)
            top_artists = await get_top_artists(user, since, until, 10)
            recently_played = await get_recently_played(user, since, until, 20)
            top_genres = await get_top_genres(user, since, until, 10)
            top_albums = await get_top_albums(user, since, until, 10)

        except ValueError as e:
            error_message = str(e)
            top_tracks, top_artists, top_genres, recently_played, top_albums = (
                [],
                [],
                [],
                [],
                [],
            )
    else:
        top_tracks, top_artists, top_genres, recently_played, top_albums = (
            [],
            [],
            [],
            [],
            [],
        )

    # Ensure stats is a dictionary
    stats = stats or {}

    listening_dates = stats.get("dates", [])
    listening_counts = stats.get("counts", [])
    x_label = stats.get("x_label", "Date")

    datasets = (
        [
            {
                "label": "Plays",
                "data": listening_counts,
                "color": "#1DB954",
            }
        ]
        if listening_counts
        else []
    )

    chart_data = (
        generate_chartjs_line_graph(listening_dates, datasets, x_label)
        if listening_dates
        else None
    )
    genres = [item["genre"] for item in top_genres] if top_genres else []
    genre_counts = [item["count"] for item in top_genres] if top_genres else []
    genre_chart_data = (
        generate_chartjs_pie_chart(genres, genre_counts) if genres else None
    )

    context = {
        "segment": "home",
        "chart_data": json.dumps(chart_data) if chart_data else None,
        "top_genres": json.dumps(genre_chart_data) if genre_chart_data else None,
        "listening_stats": stats,
        "top_tracks": top_tracks,
        "top_artists": top_artists,
        "top_albums": top_albums,
        "recently_played": recently_played,
        "time_range": time_range,
        "start_date": start_date,
        "end_date": end_date,
        "error_message": error_message,
    }

    return render(request, "music/home.html", context)


@vary_on_cookie
@cache_page(60 * 60 * 24 * 7)
async def artist(request: HttpRequest, artist_id: str) -> HttpResponse:
    spotify_user_id = await sync_to_async(request.session.get)("spotify_user_id")
    if not spotify_user_id or not await sync_to_async(is_spotify_authenticated)(
        spotify_user_id
    ):
        return redirect("spotify-auth")

    try:
        async with SpotifyClient(spotify_user_id) as client:
            artist = await client.get_artist(artist_id)
            if not artist:
                raise ValueError("Artist not found")

            similar_artists_spotify = await client.get_similar_artists(artist["name"])
            similar_artists_spotify = [
                similar
                for similar in similar_artists_spotify
                if similar.get("id") != artist_id
            ]

            albums = await client.get_artist_albums(artist_id, include_groups=None)

            compilations = [
                album for album in albums if album.get("album_type") == "compilation"
            ]

            top_tracks = await client.get_artist_top_tracks(5, artist_id)
            for track in top_tracks:
                if track and track.get("id"):
                    track_details = await client.get_track_details(track["id"])
                    track["preview_url"] = track_details.get("preview_url")
                    track["album"] = track_details.get("album")

    except Exception as e:
        logger.critical(f"Error fetching artist data from Spotify: {e}")
        artist, similar_artists_spotify, albums, compilations, top_tracks = (
            None,
            [],
            [],
            [],
            [],
        )

    context = {
        "artist": artist,
        "similar_artists": similar_artists_spotify,
        "albums": albums,
        "compilations": compilations,
        "top_tracks": top_tracks,
    }
    return await sync_to_async(render)(request, "music/artist.html", context)


@vary_on_cookie
@cache_page(60 * 60 * 24 * 30)
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


@vary_on_cookie
@cache_page(60 * 60 * 24 * 30)
async def track(request: HttpRequest, track_id: str) -> HttpResponse:
    spotify_user_id = await sync_to_async(request.session.get)("spotify_user_id")
    if not spotify_user_id or not await sync_to_async(is_spotify_authenticated)(
        spotify_user_id
    ):
        return redirect("spotify-auth")

    artist_id = None
    similar_tracks = []
    seen_tracks = set()

    try:
        async with SpotifyClient(spotify_user_id) as client:
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

            if track.get("artists") and len(track["artists"]) > 0:
                lastfm_similar = await client.get_lastfm_similar_tracks(
                    track["artists"][0]["name"], track["name"], limit=6
                )

                for similar in lastfm_similar:
                    identifier = (similar["name"], similar["artist"]["name"])
                    if identifier not in seen_tracks:
                        similar_track_id = await client.get_spotify_track_id(
                            similar["name"], similar["artist"]["name"]
                        )
                        if similar_track_id:
                            track_details = await client.get_track_details(
                                similar_track_id, preview=False
                            )
                            if track_details:
                                seen_tracks.add(identifier)
                                similar_tracks.append(track_details)

    except Exception:
        return HttpResponse("Error fetching track details", status=500)

    context = {
        "track": track,
        "album": album,
        "artist": artist,
        "similar_tracks": similar_tracks,
    }
    return await sync_to_async(render)(request, "music/track.html", context)


@vary_on_cookie
@cache_page(60 * 60 * 24 * 7)
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


@vary_on_cookie
@cache_page(60 * 60 * 24 * 7)
@csrf_exempt
async def artist_all_songs(request: HttpRequest, artist_id: str) -> HttpResponse:
    spotify_user_id = await sync_to_async(request.session.get)("spotify_user_id")
    if not spotify_user_id or not await sync_to_async(is_spotify_authenticated)(
        spotify_user_id
    ):
        return await sync_to_async(redirect)("spotify-auth")

    try:
        async with SpotifyClient(spotify_user_id) as client:
            artist = await client.get_artist(artist_id)
            albums = await client.get_artist_albums(
                artist_id, include_groups=["album", "single", "compilation"]
            )

            track_ids_set: set[str] = set()
            for album in albums:
                album_data = await client.get_album(album["id"])
                album_tracks = album_data.get("tracks", {}).get("items", [])
                for track in album_tracks:
                    track_id = track.get("id")
                    if track_id:
                        track_ids_set.add(track_id)

            track_ids_list: list[str] = list(track_ids_set)
            batch_size = 50
            track_details_dict = {}

            async def fetch_track_batch(batch_ids):
                response = await client.get_multiple_track_details(batch_ids)
                tracks = response.get("tracks", [])
                for track in tracks:
                    if track and track.get("id"):
                        track_details_dict[track["id"]] = track

            tasks = [
                asyncio.create_task(
                    fetch_track_batch(track_ids_list[i : i + batch_size])
                )
                for i in range(0, len(track_ids_list), batch_size)
            ]

            await asyncio.gather(*tasks)

            tracks = []
            for album in albums:
                album_data = await client.get_album(album["id"])
                album_tracks = album_data.get("tracks", {}).get("items", [])
                for track in album_tracks:
                    track_id = track.get("id")
                    if track_id and track_id in track_details_dict:
                        track_detail = track_details_dict[track_id]
                        track_info = {
                            "id": track_id,
                            "name": track_detail.get("name"),
                            "album": {
                                "id": album["id"],
                                "name": album["name"],
                                "images": album["images"],
                                "release_date": album.get("release_date"),
                            },
                            "duration": SpotifyClient.get_duration_ms(
                                track_detail.get("duration_ms")
                            ),
                            "popularity": track_detail.get("popularity", "N/A"),
                        }
                        tracks.append(track_info)

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


@vary_on_cookie
async def chat(request: HttpRequest) -> HttpResponse:
    spotify_user_id = await sync_to_async(request.session.get)("spotify_user_id")
    if not spotify_user_id or not await sync_to_async(is_spotify_authenticated)(
        spotify_user_id
    ):
        return redirect("spotify-auth")

    return render(request, "music/chat.html", {"segment": "chat"})


def get_x_label(time_range):
    x_label = "Date"
    if time_range == "last_7_days":
        x_label = "Date"
    elif time_range in ["last_4_weeks", "6_months"]:
        x_label = "Month"
    elif time_range in ["last_year", "all_time"]:
        x_label = "Year"
    return x_label


@vary_on_cookie
@cache_page(60 * 60 * 24)
async def artist_stats(request: HttpRequest) -> HttpResponse:
    spotify_user_id = await sync_to_async(request.session.get)("spotify_user_id")
    if not spotify_user_id or not await sync_to_async(is_spotify_authenticated)(
        spotify_user_id
    ):
        return redirect("spotify-auth")

    time_range = request.GET.get("time_range", "last_4_weeks")
    start_date = request.GET.get("start_date")
    end_date = request.GET.get("end_date")

    since, until = await get_date_range(time_range, start_date, end_date)

    user = await sync_to_async(SpotifyUser.objects.get)(spotify_user_id=spotify_user_id)
    top_artists = await get_top_artists(user, since, until, 10)

    top_artist_ids = {artist["artist_id"] for artist in top_artists}

    seen_artist_ids = set(top_artist_ids)
    similar_artists = []
    try:
        async with SpotifyClient(spotify_user_id) as client:
            for artist in top_artists:
                similar = await client.get_similar_artists(
                    artist["artist_name"], limit=5
                )
                for s in similar:
                    if s["id"] not in seen_artist_ids:
                        similar_artists.append(s)
                        seen_artist_ids.add(s["id"])
    except Exception as e:
        logger.error(f"Error fetching similar artists: {e}")

    x_label = get_x_label(time_range)

    dates, trends = await get_streaming_trend_data(
        user, since, until, top_artists, "artist"
    )
    trends_chart = generate_chartjs_line_graph(dates, trends, x_label)

    radar_labels = [
        "Total Plays",
        "Total Time (min)",
        "Unique Tracks",
        "Variety",
        "Average Popularity",
    ]
    trends_chart = generate_chartjs_line_graph(dates, trends, x_label)

    radar_labels = [
        "Total Plays",
        "Total Time (min)",
        "Unique Tracks",
        "Variety",
        "Average Popularity",
    ]
    radar_data = await get_radar_chart_data(user, since, until, top_artists, "artist")
    radar_chart = generate_chartjs_radar_chart(radar_labels, radar_data)

    doughnut_labels, doughnut_values, doughnut_colors = await get_doughnut_chart_data(
        user, since, until, top_artists, "artist"
    )
    doughnut_chart = generate_chartjs_doughnut_chart(
        doughnut_labels, doughnut_values, doughnut_colors
    )

    hourly_data = await get_hourly_listening_data(
        user, since, until, "artist", top_artists[0] if top_artists else None
    )
    polar_area_chart = generate_chartjs_polar_area_chart(hourly_data)

    context = {
        "segment": "artist-stats",
        "time_range": time_range,
        "start_date": start_date,
        "end_date": end_date,
        "stats_title": "Artists",
        "top_artists": top_artists,
        "similar_artists": similar_artists,
        "trends_chart": trends_chart,
        "radar_chart": radar_chart,
        "doughnut_chart": doughnut_chart,
        "polar_area_chart": polar_area_chart,
    }

    return render(request, "music/artist_stats.html", context)


@vary_on_cookie
@cache_page(60 * 60 * 24)
async def album_stats(request: HttpRequest) -> HttpResponse:
    spotify_user_id = await sync_to_async(request.session.get)("spotify_user_id")
    if not spotify_user_id or not await sync_to_async(is_spotify_authenticated)(
        spotify_user_id
    ):
        logger.warning(f"User not authenticated: {spotify_user_id}")
        return redirect("spotify-auth")

    time_range = request.GET.get("time_range", "last_4_weeks")
    start_date = request.GET.get("start_date")
    end_date = request.GET.get("end_date")

    since, until = await get_date_range(time_range, start_date, end_date)

    user = await sync_to_async(SpotifyUser.objects.get)(spotify_user_id=spotify_user_id)
    top_albums = await get_top_albums(user, since, until, 10)

    similar_albums = []
    seen_album_ids = {album["album_id"] for album in top_albums}

    try:
        async with SpotifyClient(spotify_user_id) as client:
            for album in top_albums:
                similar_artists = await client.get_similar_artists(
                    album["artist_name"], limit=10
                )

                for artist in similar_artists:
                    if artist["id"] in seen_album_ids:
                        continue
                    artist_top_albums = await client.get_artist_top_albums(
                        artist["id"], limit=1
                    )

                    for similar_album in artist_top_albums:
                        album_id = similar_album["id"]
                        if album_id not in seen_album_ids:
                            similar_albums.append(similar_album)
                            seen_album_ids.add(album_id)
                            if len(similar_albums) >= 10:
                                break
                    if len(similar_albums) >= 10:
                        break
                if len(similar_albums) >= 10:
                    break

    except Exception as e:
        logger.error(f"Error fetching similar albums: {e}", exc_info=True)

    x_label = get_x_label(time_range)

    dates, trends = await get_streaming_trend_data(
        user, since, until, top_albums, "album"
    )
    trends_chart = generate_chartjs_line_graph(dates, trends, x_label)

    radar_labels = [
        "Total Plays",
        "Total Time (min)",
        "Unique Tracks",
        "Variety",
        "Average Popularity",
    ]
    radar_data = await get_radar_chart_data(user, since, until, top_albums, "album")
    radar_chart = generate_chartjs_radar_chart(radar_labels, radar_data)

    doughnut_labels, doughnut_values, doughnut_colors = await get_doughnut_chart_data(
        user, since, until, top_albums, "album"
    )
    doughnut_chart = generate_chartjs_doughnut_chart(
        doughnut_labels, doughnut_values, doughnut_colors
    )

    hourly_data = await get_hourly_listening_data(
        user,
        since,
        until,
        "album",
        top_albums[0] if top_albums else None,
    )
    polar_area_chart = generate_chartjs_polar_area_chart(hourly_data)

    context = {
        "segment": "album-stats",
        "time_range": time_range,
        "start_date": start_date,
        "end_date": end_date,
        "stats_title": "Albums",
        "top_albums": top_albums,
        "similar_albums": similar_albums,
        "trends_chart": trends_chart,
        "radar_chart": radar_chart,
        "doughnut_chart": doughnut_chart,
        "polar_area_chart": polar_area_chart,
    }

    return render(request, "music/album_stats.html", context)


@vary_on_cookie
@cache_page(60 * 60 * 24)
async def track_stats(request: HttpRequest) -> HttpResponse:
    spotify_user_id = await sync_to_async(request.session.get)("spotify_user_id")
    if not spotify_user_id or not await sync_to_async(is_spotify_authenticated)(
        spotify_user_id
    ):
        logger.warning(f"User not authenticated: {spotify_user_id}")
        return redirect("spotify-auth")

    time_range = request.GET.get("time_range", "last_4_weeks")
    start_date = request.GET.get("start_date")
    end_date = request.GET.get("end_date")

    since, until = await get_date_range(time_range, start_date, end_date)

    user = await sync_to_async(SpotifyUser.objects.get)(spotify_user_id=spotify_user_id)
    top_tracks = await get_top_tracks(user, since, until, 10)

    seen_tracks = set()
    similar_tracks = []

    try:
        async with SpotifyClient(spotify_user_id) as client:
            for track in top_tracks:
                try:
                    # Get similar tracks from Last.fm
                    lastfm_similar = await client.get_lastfm_similar_tracks(
                        track["artist_name"], track["track_name"], limit=1
                    )

                    for similar in lastfm_similar:
                        identifier = (similar["name"], similar["artist"]["name"])
                        if identifier not in seen_tracks:
                            # Get Spotify track ID
                            track_id = await client.get_spotify_track_id(
                                similar["name"], similar["artist"]["name"]
                            )
                            if track_id:
                                # Get full track details
                                track_details = await client.get_track_details(
                                    track_id, False
                                )
                                if track_details:
                                    seen_tracks.add(identifier)
                                    similar_tracks.append(track_details)

                except Exception as e:
                    logger.error(f"Error fetching similar tracks: {e}", exc_info=True)
                    continue

    except Exception as e:
        logger.error(f"Error fetching similar tracks: {e}", exc_info=True)

    x_label = get_x_label(time_range)
    dates, trends = await get_streaming_trend_data(
        user, since, until, top_tracks, "track"
    )
    trends_chart = generate_chartjs_line_graph(dates, trends, x_label)

    radar_labels = [
        "Total Plays",
        "Total Time (min)",
        "Unique Tracks",
        "Variety",
        "Average Popularity",
    ]
    radar_data = await get_radar_chart_data(user, since, until, top_tracks, "track")
    radar_chart = generate_chartjs_radar_chart(radar_labels, radar_data)

    doughnut_labels, doughnut_values, doughnut_colors = await get_doughnut_chart_data(
        user, since, until, top_tracks, "track"
    )
    doughnut_chart = generate_chartjs_doughnut_chart(
        doughnut_labels, doughnut_values, doughnut_colors
    )

    hourly_data = await get_hourly_listening_data(
        user, since, until, "track", top_tracks[0] if top_tracks else None
    )
    polar_area_chart = generate_chartjs_polar_area_chart(hourly_data)

    context = {
        "segment": "track-stats",
        "time_range": time_range,
        "start_date": start_date,
        "end_date": end_date,
        "stats_title": "Tracks",
        "top_tracks": top_tracks,
        "similar_tracks": similar_tracks,
        "trends_chart": trends_chart,
        "radar_chart": radar_chart,
        "doughnut_chart": doughnut_chart,
        "polar_area_chart": polar_area_chart,
    }

    return render(request, "music/track_stats.html", context)


@vary_on_cookie
@cache_page(60 * 60 * 24)
async def genre_stats(request: HttpRequest) -> HttpResponse:
    spotify_user_id = await sync_to_async(request.session.get)("spotify_user_id")
    if not spotify_user_id or not await sync_to_async(is_spotify_authenticated)(
        spotify_user_id
    ):
        return redirect("spotify-auth")

    time_range = request.GET.get("time_range", "last_4_weeks")
    start_date = request.GET.get("start_date")
    end_date = request.GET.get("end_date")

    since, until = await get_date_range(time_range, start_date, end_date)

    user = await sync_to_async(SpotifyUser.objects.get)(spotify_user_id=spotify_user_id)
    top_genres = await get_top_genres(user, since, until, 10)

    similar_genres = []
    seen_genres = {genre["genre"] for genre in top_genres}

    try:
        async with SpotifyClient(spotify_user_id) as client:
            for genre in top_genres:
                artists, _ = await client.get_items_by_genre(genre["genre"])

                for artist in artists[:3]:
                    similar_artists = await client.get_similar_artists(
                        artist["name"], limit=5
                    )
                    for similar_artist in similar_artists:
                        artist_genres = similar_artist.get("genres", [])
                        for artist_genre in artist_genres:
                            if artist_genre not in seen_genres:
                                seen_genres.add(artist_genre)
                                similar_genres.append(
                                    {
                                        "genre": artist_genre,
                                        "count": 1,
                                    }
                                )
                                if len(similar_genres) >= 10:
                                    break
                        if len(similar_genres) >= 10:
                            break
                    if len(similar_genres) >= 10:
                        break
                if len(similar_genres) >= 10:
                    break

    except Exception as e:
        logger.error(f"Error fetching similar genres: {e}", exc_info=True)

    x_label = get_x_label(time_range)
    dates, trends = await get_streaming_trend_data(
        user, since, until, top_genres, "genre"
    )
    trends_chart = generate_chartjs_line_graph(dates, trends, x_label)

    radar_labels = [
        "Total Plays",
        "Total Time (min)",
        "Unique Tracks",
        "Variety",
        "Average Popularity",
    ]
    radar_data = await get_radar_chart_data(user, since, until, top_genres, "genre")
    radar_chart = generate_chartjs_radar_chart(radar_labels, radar_data)

    doughnut_labels, doughnut_values, doughnut_colors = await get_doughnut_chart_data(
        user, since, until, top_genres, "genre"
    )
    doughnut_chart = generate_chartjs_doughnut_chart(
        doughnut_labels, doughnut_values, doughnut_colors
    )

    hourly_data = await get_hourly_listening_data(
        user, since, until, "genre", top_genres[0] if top_genres else None
    )
    polar_area_chart = generate_chartjs_polar_area_chart(hourly_data)

    context = {
        "segment": "genre-stats",
        "time_range": time_range,
        "start_date": start_date,
        "end_date": end_date,
        "stats_title": "Genres",
        "top_genres": top_genres,
        "similar_genres": similar_genres,
        "trends_chart": trends_chart,
        "radar_chart": radar_chart,
        "doughnut_chart": doughnut_chart,
        "polar_area_chart": polar_area_chart,
    }
    return render(request, "music/genre_stats.html", context)


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
                        continue

                    played_at_str = item["ts"]
                    try:
                        played_at = datetime.strptime(
                            played_at_str, "%Y-%m-%dT%H:%M:%S%z"
                        )
                    except ValueError:
                        continue

                    if played_at > timezone.now():
                        continue

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

                new_tracks_added = await save_tracks_atomic(
                    user, track_info_list, track_details_dict, artist_details_dict
                )

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


@vary_on_cookie
async def get_preview_urls(request: HttpRequest) -> JsonResponse:
    spotify_user_id = await sync_to_async(request.session.get)("spotify_user_id")
    if not spotify_user_id:
        return JsonResponse({"error": "Not authenticated"}, status=401)

    track_ids = request.GET.get("track_ids", "").split(",")
    if not track_ids:
        return JsonResponse({"error": "No track IDs provided"}, status=400)

    try:
        async with SpotifyClient(spotify_user_id) as client:
            preview_urls = {}
            for track_id in track_ids:
                track = await client.get_track_details(track_id, preview=True)
                if track and track.get("preview_url"):
                    preview_urls[track_id] = track["preview_url"]
            return JsonResponse(preview_urls)
    except Exception as e:
        logger.error(f"Error fetching preview URLs: {e}")
        return JsonResponse({"error": str(e)}, status=500)


@vary_on_cookie
async def get_artist_releases(request: HttpRequest, artist_id: str) -> JsonResponse:
    spotify_user_id = await sync_to_async(request.session.get)("spotify_user_id")
    if not spotify_user_id:
        return JsonResponse({"error": "Not authenticated"}, status=401)

    release_type = request.GET.get("type", "all")

    try:
        async with SpotifyClient(spotify_user_id) as client:
            releases = await client.get_artist_albums(
                artist_id,
                include_groups=[release_type] if release_type != "all" else None,
            )
            return JsonResponse({"releases": releases})
    except Exception as e:
        logger.error(f"Error fetching artist releases: {e}")
        return JsonResponse({"error": str(e)}, status=500)


@method_decorator(csrf_exempt, name="dispatch")
class ChatAPI(View):
    def post(self, request: HttpRequest) -> JsonResponse:
        try:
            data = json.loads(request.body)
            user_message = data.get("message")
            if not user_message:
                return JsonResponse({"error": "No message provided."}, status=400)

            spotify_user_id = request.session.get("spotify_user_id")
            if not spotify_user_id or not is_spotify_authenticated(spotify_user_id):
                return JsonResponse({"error": "User not authenticated."}, status=401)

            listening_data = self.get_listening_data(spotify_user_id)
            prompt = self.create_prompt(user_message, listening_data)
            ai_response = self.get_ai_response(prompt)

            return JsonResponse({"reply": ai_response})

        except Exception as e:
            logger.error(f"Error in ChatAPI: {e}")
            return JsonResponse({"error": "Internal server error."}, status=500)

    def get_listening_data(self, spotify_user_id: str) -> str:
        top_artists = (
            PlayedTrack.objects.filter(user_id=spotify_user_id)
            .values("artist_name")
            .annotate(count=Count("artist_name"))
            .order_by("-count")[:15]
        )
        top_tracks = (
            PlayedTrack.objects.filter(user_id=spotify_user_id)
            .values("track_name")
            .annotate(count=Count("track_name"))
            .order_by("-count")[:15]
        )
        top_albums = (
            PlayedTrack.objects.filter(user_id=spotify_user_id)
            .values("album_name")
            .annotate(count=Count("album_name"))
            .order_by("-count")[:15]
        )

        artists = ", ".join([artist["artist_name"] for artist in top_artists])
        tracks = ", ".join([track["track_name"] for track in top_tracks])
        albums = ", ".join([album["album_name"] for album in top_albums])

        return f"Top artists: {artists}. Top tracks: {tracks}. Top albums: {albums}."

    def create_prompt(self, user_message: str, listening_data: str) -> str:
        return (
            f"User's listening data: {listening_data}\n"
            f"User's question: {user_message}\n"
            f"AI response:"
        )

    def get_ai_response(self, prompt: str) -> str:
        openai.api_key = settings.OPENAI_API_KEY
        try:
            response = openai.ChatCompletion.create(
                model="gpt-3.5-turbo",
                messages=[
                    {"role": "system", "content": "You are a helpful assistant."},
                    {"role": "user", "content": prompt},
                ],
                max_tokens=150,
                temperature=0.7,
            )
            return response.choices[0].message["content"].strip()
        except Exception as e:
            logger.error(f"OpenAI API error: {e}")
            return "I'm sorry, I couldn't process your request at the moment."
