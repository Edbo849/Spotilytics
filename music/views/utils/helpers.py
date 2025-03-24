# Helper functions for Views
from typing import Optional

from music.services.graphs import (
    generate_gauge_chart,
    generate_horizontal_bar_chart,
    generate_listening_context_chart,
    generate_progress_chart,
)
from music.utils.db_utils import (
    get_album_track_plays,
    get_album_tracks_coverage,
    get_artist_discography_coverage,
    get_artist_genre_distribution,
    get_artist_tracks_coverage,
    get_item_stats_util,
    get_listening_context_data,
    get_replay_gaps,
    get_track_duration_comparison,
)

from .imports import *


## General Helpers
def get_x_label(time_range):
    x_label = "Date"
    if time_range == "last_7_days":
        x_label = "Date"
    elif time_range in ["last_4_weeks", "6_months"]:
        x_label = "Month"
    elif time_range in ["last_year", "all_time"]:
        x_label = "Year"
    return x_label


##  Album Stats Helpers
async def get_album_visualizations(
    user, since, until, top_albums, time_range
) -> Dict[str, Any]:
    """Get all visualization data for album stats."""
    x_label = get_x_label(time_range)

    # Get streaming trend data
    dates, trends = await get_streaming_trend_data(
        user, since, until, top_albums, "album"
    )
    trends_chart = generate_chartjs_line_graph(dates, trends, x_label)

    # Get radar chart data
    radar_labels = [
        "Total Plays",
        "Total Time (min)",
        "Unique Tracks",
        "Variety",
        "Average Popularity",
    ]
    radar_data = await get_radar_chart_data(user, since, until, top_albums, "album")
    radar_chart = generate_chartjs_radar_chart(radar_labels, radar_data)

    # Get doughnut chart data
    doughnut_labels, doughnut_values, doughnut_colors = await get_doughnut_chart_data(
        user, since, until, top_albums, "album"
    )
    doughnut_chart = generate_chartjs_doughnut_chart(
        doughnut_labels, doughnut_values, doughnut_colors
    )

    # Get hourly distribution data
    hourly_data = await get_hourly_listening_data(
        user, since, until, "album", top_albums[0] if top_albums else None
    )
    polar_area_chart = generate_chartjs_polar_area_chart(hourly_data)

    # Get bubble chart data
    bubble_data = await get_bubble_chart_data(user, since, until, top_albums, "album")
    bubble_chart = generate_chartjs_bubble_chart(bubble_data)

    # Get stats boxes data
    stats_boxes = await get_stats_boxes_data(user, since, until, top_albums, "album")

    # Get discovery timeline data
    discovery_dates, discovery_counts = await get_discovery_timeline_data(
        user, since, until, "album"
    )
    discovery_chart = generate_chartjs_line_graph(
        discovery_dates,
        [
            {
                "label": "Albums Discovered",
                "data": discovery_counts,
                "color": "#1DB954",
            }
        ],
        x_label,
        fill_area=True,
    )

    # Get time distribution data
    time_labels, time_datasets = await get_time_period_distribution(
        user, since, until, top_albums, "album"
    )
    stacked_chart = generate_chartjs_stacked_bar_chart(time_labels, time_datasets)

    # Get replay gaps data
    replay_labels, replay_values = await get_replay_gaps(
        user, since, until, top_albums, "album"
    )
    bar_chart = generate_chartjs_bar_chart(
        replay_labels, replay_values, y_label="Hours Between Plays"
    )

    return {
        "trends_chart": trends_chart,
        "radar_chart": radar_chart,
        "doughnut_chart": doughnut_chart,
        "stats_boxes": stats_boxes,
        "polar_area_chart": polar_area_chart,
        "bubble_chart": bubble_chart,
        "discovery_chart": discovery_chart,
        "stacked_chart": stacked_chart,
        "bar_chart": bar_chart,
    }


async def get_similar_albums(
    spotify_client, top_albums, seen_album_ids: set
) -> List[Dict]:
    """Get similar albums recommendations."""
    similar_albums = []

    try:
        for album in top_albums:
            cache_key = spotify_client.sanitize_cache_key(
                f"similar_artists_10_{album['artist_name']}"
            )
            similar_artists = cache.get(cache_key)

            if similar_artists is None:
                similar_artists = await spotify_client.get_similar_artists(
                    album["artist_name"], limit=10
                )
                if similar_artists:
                    cache.set(cache_key, similar_artists, timeout=2592000)

            for artist in similar_artists:
                if artist["id"] in seen_album_ids:
                    continue

                cache_key = spotify_client.sanitize_cache_key(
                    f"artist_top_albums_1_{artist['id']}"
                )
                artist_top_albums = cache.get(cache_key)

                if artist_top_albums is None:
                    artist_top_albums = await spotify_client.get_artist_top_albums(
                        artist["id"], limit=1
                    )
                    if artist_top_albums:
                        cache.set(cache_key, artist_top_albums, timeout=2592000)

                for similar_album in artist_top_albums:
                    album_id = similar_album["id"]
                    if album_id not in seen_album_ids:
                        similar_albums.append(similar_album)
                        seen_album_ids.add(album_id)
                        if len(similar_albums) >= 10:
                            return similar_albums

    except Exception as e:
        logger.error(f"Error fetching similar albums: {e}", exc_info=True)

    return similar_albums


## Album helpers


async def get_artist_details(client, artist_id: str) -> Dict[str, Any]:
    """Get artist details with caching."""
    cache_key = client.sanitize_cache_key(f"artist_details_{artist_id}")
    artist_details = cache.get(cache_key)

    if artist_details is None:
        artist_details = await client.get_artist(artist_id)
        if artist_details:
            cache.set(cache_key, artist_details, timeout=604800)
    return artist_details


async def enrich_track_details(client, tracks: List[Dict]) -> List[Dict]:
    """Enrich track details with additional information."""
    for track in tracks:
        cache_key = client.sanitize_cache_key(f"track_details_{track['id']}")
        track_details = cache.get(cache_key)

        if track_details is None:
            track_details = await client.get_track_details(track["id"])
            if track_details:
                cache.set(cache_key, track_details, timeout=client.CACHE_TIMEOUT)

        duration_ms = track["duration_ms"]
        track["duration"] = client.get_duration_ms(duration_ms)
        track["preview_url"] = (
            track_details.get("preview_url") if track_details else None
        )
        track["popularity"] = (
            track_details.get("popularity", "N/A") if track_details else "N/A"
        )

    return tracks


## Artist Stats Helpers


async def get_similar_artists(
    spotify_client, top_artists, seen_artist_ids: set
) -> List[Dict]:
    """Get similar artists recommendations."""
    similar_artists = []
    try:
        for artist in top_artists:
            cache_key = spotify_client.sanitize_cache_key(
                f"similar_artists_1_{artist['artist_name']}"
            )
            similar = cache.get(cache_key)

            if similar is None:
                similar = await spotify_client.get_similar_artists(
                    artist["artist_name"], limit=1
                )
                if similar:
                    cache.set(cache_key, similar, timeout=2592000)

            for s in similar:
                if s["id"] not in seen_artist_ids:
                    similar_artists.append(s)
                    seen_artist_ids.add(s["id"])
    except Exception as e:
        logger.error(f"Error fetching similar artists: {e}")
    return similar_artists


async def get_artist_visualizations(
    user, since, until, top_artists, time_range
) -> Dict[str, Any]:
    """Get all visualization data for artist stats."""
    x_label = get_x_label(time_range)

    # Get streaming trend data
    dates, trends = await get_streaming_trend_data(
        user, since, until, top_artists, "artist"
    )
    trends_chart = generate_chartjs_line_graph(dates, trends, x_label)

    # Get radar chart data
    radar_labels = [
        "Total Plays",
        "Total Time (min)",
        "Unique Tracks",
        "Variety",
        "Average Popularity",
    ]
    radar_data = await get_radar_chart_data(user, since, until, top_artists, "artist")
    radar_chart = generate_chartjs_radar_chart(radar_labels, radar_data)

    # Get doughnut chart data
    doughnut_labels, doughnut_values, doughnut_colors = await get_doughnut_chart_data(
        user, since, until, top_artists, "artist"
    )
    doughnut_chart = generate_chartjs_doughnut_chart(
        doughnut_labels, doughnut_values, doughnut_colors
    )

    # Get hourly distribution data
    hourly_data = await get_hourly_listening_data(
        user, since, until, "artist", top_artists[0] if top_artists else None
    )
    polar_area_chart = generate_chartjs_polar_area_chart(hourly_data)

    # Get bubble chart data
    bubble_data = await get_bubble_chart_data(user, since, until, top_artists, "artist")
    bubble_chart = generate_chartjs_bubble_chart(bubble_data)

    # Get stats boxes data
    stats_boxes = await get_stats_boxes_data(user, since, until, top_artists, "artist")

    # Get discovery timeline data
    discovery_dates, discovery_counts = await get_discovery_timeline_data(
        user, since, until, "artist"
    )
    discovery_chart = generate_chartjs_line_graph(
        discovery_dates,
        [
            {
                "label": "Artists Discovered",
                "data": discovery_counts,
                "color": "#1DB954",
            }
        ],
        x_label,
        fill_area=True,
    )

    # Get time distribution data
    time_labels, time_datasets = await get_time_period_distribution(
        user, since, until, top_artists, "artist"
    )
    stacked_chart = generate_chartjs_stacked_bar_chart(time_labels, time_datasets)

    # Get replay gaps data
    replay_labels, replay_values = await get_replay_gaps(
        user, since, until, top_artists, "artist"
    )
    bar_chart = generate_chartjs_bar_chart(
        replay_labels, replay_values, y_label="Hours Between Plays"
    )

    return {
        "trends_chart": trends_chart,
        "radar_chart": radar_chart,
        "doughnut_chart": doughnut_chart,
        "stats_boxes": stats_boxes,
        "polar_area_chart": polar_area_chart,
        "bubble_chart": bubble_chart,
        "discovery_chart": discovery_chart,
        "stacked_chart": stacked_chart,
        "bar_chart": bar_chart,
    }


## Artist helpers


async def get_artist_page_data(client, artist_id: str) -> Dict[str, Any]:
    """Get all data needed for the artist page."""
    try:
        # Get artist details
        artist = await client.get_artist(artist_id)
        if not artist:
            raise ValueError("Artist not found")

        # Get similar artists
        cache_key = client.sanitize_cache_key(f"similar_artists_{artist_id}")
        similar_artists = cache.get(cache_key)
        if similar_artists is None:
            similar_artists = await client.get_similar_artists(artist["name"])
            if similar_artists:
                cache.set(cache_key, similar_artists, timeout=client.CACHE_TIMEOUT)

        similar_artists_spotify = [
            similar
            for similar in (similar_artists or [])
            if similar.get("id") != artist_id
        ]

        # Get all albums
        cache_key = client.sanitize_cache_key(f"artist_albums_all_{artist_id}")
        albums = cache.get(cache_key)
        if albums is None:
            albums = await client.get_artist_albums(artist_id, include_groups=None)
            if albums:
                cache.set(cache_key, albums, timeout=604800)

        compilations = [
            album for album in albums if album.get("album_type") == "compilation"
        ]

        # Get top tracks
        cache_key = client.sanitize_cache_key(f"artist_top_tracks_{artist_id}_5")
        top_tracks = cache.get(cache_key)
        if top_tracks is None:
            top_tracks = await client.get_artist_top_tracks(5, artist_id)
            if top_tracks:
                cache.set(cache_key, top_tracks, timeout=604800)

        # Enrich top tracks with preview URLs and album info
        for track in top_tracks:
            if track and track.get("id"):
                track_details = await client.get_track_details(track["id"])
                track["preview_url"] = track_details.get("preview_url")
                track["album"] = track_details.get("album")

        return {
            "artist": artist,
            "similar_artists": similar_artists_spotify,
            "albums": albums,
            "compilations": compilations,
            "top_tracks": top_tracks,
        }
    except Exception as e:
        logger.critical(f"Error fetching artist data from Spotify: {e}")
        return {
            "artist": None,
            "similar_artists": [],
            "albums": [],
            "compilations": [],
            "top_tracks": [],
        }


## Chat helpers


async def handle_chat_message(
    spotify_user_id: str, user_message: str
) -> Tuple[Dict[str, Any], int]:
    """Handle processing of chat messages and getting AI responses."""
    try:
        if not user_message:
            return {"error": "No message provided."}, 400
        if not spotify_user_id or not await sync_to_async(is_spotify_authenticated)(
            spotify_user_id
        ):
            return {"error": "User not authenticated."}, 401

        openai_service = OpenAIService()
        listening_data = await openai_service.get_listening_data(spotify_user_id)
        prompt = await openai_service.create_prompt(user_message, listening_data)
        ai_response = await openai_service.get_ai_response(prompt)

        return {"reply": ai_response}, 200

    except Exception as e:
        logger.error(f"Error processing chat message: {e}")
        return {"error": "Internal server error."}, 500


## Genre Stats Helpers


async def get_genre_visualizations(
    user, since, until, top_genres, time_range
) -> Dict[str, Any]:
    """Get all visualization data for genre stats."""
    x_label = get_x_label(time_range)

    # Get streaming trend data
    dates, trends = await get_streaming_trend_data(
        user, since, until, top_genres, "genre"
    )
    trends_chart = generate_chartjs_line_graph(dates, trends, x_label)

    # Get radar chart data
    radar_labels = [
        "Total Plays",
        "Total Time (min)",
        "Unique Tracks",
        "Variety",
        "Average Popularity",
    ]
    radar_data = await get_radar_chart_data(user, since, until, top_genres, "genre")
    radar_chart = generate_chartjs_radar_chart(radar_labels, radar_data)

    # Get doughnut chart data
    doughnut_labels, doughnut_values, doughnut_colors = await get_doughnut_chart_data(
        user, since, until, top_genres, "genre"
    )
    doughnut_chart = generate_chartjs_doughnut_chart(
        doughnut_labels, doughnut_values, doughnut_colors
    )

    # Get hourly distribution data
    hourly_data = await get_hourly_listening_data(
        user, since, until, "genre", top_genres[0] if top_genres else None
    )
    polar_area_chart = generate_chartjs_polar_area_chart(hourly_data)

    # Get bubble chart data
    bubble_data = await get_bubble_chart_data(user, since, until, top_genres, "genre")
    bubble_chart = generate_chartjs_bubble_chart(bubble_data)

    # Get stats boxes data
    stats_boxes = await get_stats_boxes_data(user, since, until, top_genres, "genre")

    # Get discovery timeline data
    discovery_dates, discovery_counts = await get_discovery_timeline_data(
        user, since, until, "genre"
    )
    discovery_chart = generate_chartjs_line_graph(
        discovery_dates,
        [
            {
                "label": "Genres Discovered",
                "data": discovery_counts,
                "color": "#1DB954",
            }
        ],
        x_label,
        fill_area=True,
    )

    # Get time distribution data
    time_labels, time_datasets = await get_time_period_distribution(
        user, since, until, top_genres, "genre"
    )
    stacked_chart = generate_chartjs_stacked_bar_chart(time_labels, time_datasets)

    # Get replay gaps data
    replay_labels, replay_values = await get_replay_gaps(
        user, since, until, top_genres, "genre"
    )
    bar_chart = generate_chartjs_bar_chart(
        replay_labels, replay_values, y_label="Hours Between Plays"
    )

    return {
        "trends_chart": trends_chart,
        "radar_chart": radar_chart,
        "doughnut_chart": doughnut_chart,
        "stats_boxes": stats_boxes,
        "polar_area_chart": polar_area_chart,
        "bubble_chart": bubble_chart,
        "discovery_chart": discovery_chart,
        "stacked_chart": stacked_chart,
        "bar_chart": bar_chart,
    }


async def get_similar_genres(
    spotify_client, top_genres, seen_genres: set
) -> List[Dict]:
    """Get similar genres recommendations."""
    similar_genres = []
    try:
        for genre in top_genres:
            artists, _ = await spotify_client.get_items_by_genre(genre["genre"])

            for artist in artists[:3]:
                cache_key = spotify_client.sanitize_cache_key(
                    f"similar_artists_1_{artist['name']}"
                )
                similar_artists = cache.get(cache_key)

                if similar_artists is None:
                    similar_artists = await spotify_client.get_similar_artists(
                        artist["name"], limit=1
                    )
                    if similar_artists:
                        cache.set(cache_key, similar_artists, timeout=2592000)

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
                                return similar_genres

    except Exception as e:
        logger.error(f"Error fetching similar genres: {e}", exc_info=True)

    return similar_genres


## Genre helpers


async def get_genre_items(client, genre_name: str) -> Dict[str, List]:
    """Get artists and tracks for a specific genre with caching."""
    try:
        cache_key = client.sanitize_cache_key(f"genre_items_{genre_name}")
        genre_items = cache.get(cache_key)

        if genre_items is None:
            artists, tracks = await client.get_items_by_genre(genre_name)
            if artists or tracks:
                genre_items = {"artists": artists, "tracks": tracks}
                cache.set(cache_key, genre_items, timeout=client.CACHE_TIMEOUT)
        else:
            artists = genre_items.get("artists", [])
            tracks = genre_items.get("tracks", [])

        return {"artists": artists, "tracks": tracks}

    except Exception as e:
        logger.error(f"Error fetching items for genre {genre_name}: {e}")
        return {"artists": [], "tracks": []}


## History Helpers


async def handle_history_import(user, file_content, file_hash: str) -> Tuple[bool, str]:
    """Handle the import of a history file."""
    try:
        data = json.loads(file_content.decode("utf-8"))

        if not data:
            return False, "Empty JSON file. Please upload a non-empty JSON file."

        if not isinstance(data, list):
            return False, "Invalid JSON format. Expected a list of tracks."

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
                played_at = datetime.strptime(played_at_str, "%Y-%m-%dT%H:%M:%S%z")
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
            return False, "No valid tracks found in the uploaded file."

        file_path = os.path.join("listening_history", f"{file_hash}.json")
        await sync_to_async(default_storage.save)(file_path, file_content)

        return True, "History import successful."

    except Exception as e:
        logger.error(f"Error importing history: {e}")
        return False, f"Error importing history: {str(e)}"


async def delete_listening_history() -> Tuple[bool, str]:
    """Delete all listening history files and records."""
    if os.path.exists(os.path.join(settings.BASE_DIR, "media/listening_history")):
        try:
            filenames = await sync_to_async(os.listdir)(
                os.path.join(settings.BASE_DIR, "media/listening_history")
            )
        except FileNotFoundError:
            return False, "Listening history directory not found."
        except Exception as e:
            logger.error(f"Error accessing listening history directory: {e}")
            return False, f"Error: {str(e)}"

        for filename in filenames:
            file_path = os.path.join(
                settings.BASE_DIR, "media/listening_history", filename
            )
            if await sync_to_async(os.path.isfile)(file_path):
                try:
                    await sync_to_async(os.remove)(file_path)
                except Exception as e:
                    logger.error(f"Error removing file {file_path}: {e}")
                    return False, f"Error removing file: {file_path}"

        try:
            await sync_to_async(PlayedTrack.objects.all().delete)()
        except Exception as e:
            logger.error(f"Error deleting listening history from database: {e}")
            return False, f"Database error: {str(e)}"

        return True, "All listening history has been deleted."
    return False, "Listening history directory not found."


## Home Helpers


async def get_home_visualizations(
    user, has_history: bool, time_range: str, start_date: str, end_date: str
) -> Dict[str, Any]:
    """Get all visualization data for home page."""
    if not has_history:
        return {
            "stats": None,
            "chart_data": None,
            "genre_data": None,
            "listening_stats": None,
            "written_stats": None,
            "top_tracks": [],
            "top_artists": [],
            "top_genres": [],
            "top_albums": [],
            "error_message": None,
        }

    try:
        since, until = await get_date_range(time_range, start_date, end_date)

        # Get listening stats
        stats = await sync_to_async(get_listening_stats)(
            user, time_range, start_date, end_date
        )

        # Get top items
        top_tracks = await get_top_tracks(user, since, until, 10)
        top_artists = await get_top_artists(user, since, until, 10)
        top_genres = await get_top_genres(user, since, until, 10)
        top_albums = await get_top_albums(user, since, until, 10)

        # Generate chart data
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

        # Generate genre chart
        genres = [item["genre"] for item in top_genres] if top_genres else []
        genre_counts = [item["count"] for item in top_genres] if top_genres else []
        genre_chart_data = (
            generate_chartjs_pie_chart(genres, genre_counts) if genres else None
        )

        # Get written stats
        written_stats = await get_dashboard_stats(user, since, until)

        # Get stats boxes data (for example, based on top tracks)
        stats_boxes = await get_stats_boxes_data(
            user, since, until, top_tracks, "track"
        )

        return {
            "stats": stats,
            "chart_data": chart_data,
            "genre_data": genre_chart_data,
            "listening_stats": stats,
            "written_stats": written_stats,
            "top_tracks": top_tracks,
            "top_artists": top_artists,
            "top_genres": top_genres,
            "top_albums": top_albums,
            "stats_boxes": stats_boxes,
            "error_message": None,
        }

    except ValueError as e:
        return {
            "stats": None,
            "chart_data": None,
            "genre_data": None,
            "listening_stats": None,
            "written_stats": None,
            "top_tracks": [],
            "top_artists": [],
            "top_genres": [],
            "top_albums": [],
            "error_message": str(e),
        }


async def validate_date_range(
    time_range: str, start_date: str, end_date: str
) -> Tuple[str, str, str]:
    """Validate custom date range inputs."""
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

    if error_message:
        return (
            start_date,
            end_date,
            error_message,
        )

    return start_date, end_date, ""


## Track Stats Helpers


async def get_similar_tracks(client, top_tracks: List[Dict]) -> List[Dict]:
    """Get similar tracks based on top tracks."""
    seen_tracks = set()
    similar_tracks = []

    try:
        for track in top_tracks:
            try:
                cache_key = client.sanitize_cache_key(
                    f"lastfm_similar_1_{track['artist_name']}_{track['track_name']}"
                )
                lastfm_similar = cache.get(cache_key)

                if lastfm_similar is None:
                    lastfm_similar = await client.get_lastfm_similar_tracks(
                        track["artist_name"], track["track_name"], limit=1
                    )
                    if lastfm_similar:
                        cache.set(
                            cache_key,
                            lastfm_similar,
                            timeout=client.CACHE_TIMEOUT,
                        )

                for similar in lastfm_similar:
                    identifier = (similar["name"], similar["artist"]["name"])
                    if identifier not in seen_tracks:
                        id_cache_key = client.sanitize_cache_key(
                            f"spotify_track_id_{similar['name']}_{similar['artist']['name']}"
                        )
                        track_id = cache.get(id_cache_key)

                        if track_id is None:
                            track_id = await client.get_spotify_track_id(
                                similar["name"], similar["artist"]["name"]
                            )
                            if track_id:
                                cache.set(
                                    id_cache_key,
                                    track_id,
                                    timeout=client.CACHE_TIMEOUT,
                                )

                        if track_id:
                            details_cache_key = client.sanitize_cache_key(
                                f"track_details_false_{track_id}"
                            )
                            track_details = cache.get(details_cache_key)

                            if track_details is None:
                                track_details = await client.get_track_details(
                                    track_id, False
                                )
                                if track_details:
                                    cache.set(
                                        details_cache_key,
                                        track_details,
                                        timeout=client.CACHE_TIMEOUT,
                                    )

                            if track_details:
                                seen_tracks.add(identifier)
                                similar_tracks.append(track_details)

            except Exception as e:
                logger.error(f"Error fetching similar tracks: {e}", exc_info=True)
                continue

    except Exception as e:
        logger.error(f"Error fetching similar tracks: {e}", exc_info=True)

    return similar_tracks


async def get_track_visualizations(
    user, since, until, top_tracks, time_range
) -> Dict[str, Any]:
    """Get all visualization data for track stats."""
    x_label = get_x_label(time_range)

    # Get streaming trend data
    dates, trends = await get_streaming_trend_data(
        user, since, until, top_tracks, "track"
    )
    trends_chart = generate_chartjs_line_graph(dates, trends, x_label)

    # Get radar chart data
    radar_labels = [
        "Total Plays",
        "Total Time (min)",
        "Unique Tracks",
        "Variety",
        "Average Popularity",
    ]
    radar_data = await get_radar_chart_data(user, since, until, top_tracks, "track")
    radar_chart = generate_chartjs_radar_chart(radar_labels, radar_data)

    # Get doughnut chart data
    doughnut_labels, doughnut_values, doughnut_colors = await get_doughnut_chart_data(
        user, since, until, top_tracks, "track"
    )
    doughnut_chart = generate_chartjs_doughnut_chart(
        doughnut_labels, doughnut_values, doughnut_colors
    )

    # Get hourly distribution data
    hourly_data = await get_hourly_listening_data(
        user, since, until, "track", top_tracks[0] if top_tracks else None
    )
    polar_area_chart = generate_chartjs_polar_area_chart(hourly_data)

    # Get bubble chart data
    bubble_data = await get_bubble_chart_data(user, since, until, top_tracks, "track")
    bubble_chart = generate_chartjs_bubble_chart(bubble_data)

    # Get stats boxes data
    stats_boxes = await get_stats_boxes_data(user, since, until, top_tracks, "track")

    # Get discovery timeline data
    discovery_dates, discovery_counts = await get_discovery_timeline_data(
        user, since, until, "track"
    )
    discovery_chart = generate_chartjs_line_graph(
        discovery_dates,
        [
            {
                "label": "Tracks Discovered",
                "data": discovery_counts,
                "color": "#1DB954",
            }
        ],
        x_label,
        fill_area=True,
    )

    # Get time distribution data
    time_labels, time_datasets = await get_time_period_distribution(
        user, since, until, top_tracks, "track"
    )
    stacked_chart = generate_chartjs_stacked_bar_chart(time_labels, time_datasets)

    # Get replay gaps data
    replay_labels, replay_values = await get_replay_gaps(
        user, since, until, top_tracks, "track"
    )
    bar_chart = generate_chartjs_bar_chart(
        replay_labels, replay_values, y_label="Hours Between Plays"
    )

    return {
        "trends_chart": trends_chart,
        "radar_chart": radar_chart,
        "doughnut_chart": doughnut_chart,
        "stats_boxes": stats_boxes,
        "polar_area_chart": polar_area_chart,
        "bubble_chart": bubble_chart,
        "discovery_chart": discovery_chart,
        "stacked_chart": stacked_chart,
        "bar_chart": bar_chart,
    }


## Track Helpers


async def get_track_page_data(client, track_id: str) -> Dict[str, Any]:
    """Get all data needed for track page."""
    try:
        # Get track details
        cache_key = client.sanitize_cache_key(f"track_details_{track_id}")
        track_details = cache.get(cache_key)

        if track_details is None:
            track_details = await client.get_track_details(track_id)
            if track_details:
                cache.set(cache_key, track_details, timeout=None)
            else:
                raise ValueError("Track details not found.")

        track = track_details
        duration_ms = track.get("duration_ms")
        track["duration"] = (
            await sync_to_async(client.get_duration_ms)(duration_ms)
            if duration_ms
            else "N/A"
        )

        # Get album details
        album = None
        if track.get("album"):
            album_id = track["album"]["id"]
            cache_key = client.sanitize_cache_key(f"album_details_{album_id}")
            album = cache.get(cache_key)

            if album is None:
                album = await client.get_album(album_id)
                if album:
                    cache.set(cache_key, album, timeout=client.CACHE_TIMEOUT)

        # Get artist details
        artist = None
        artist_id = (
            track["artists"][0]["id"]
            if track.get("artists") and track["artists"]
            else None
        )

        if artist_id:
            cache_key = client.sanitize_cache_key(f"artist_details_{artist_id}")
            artist = cache.get(cache_key)

            if artist is None:
                artist = await client.get_artist(artist_id)
                if artist:
                    cache.set(cache_key, artist, timeout=604800)

        # Get similar tracks
        similar_tracks = []
        seen_tracks: set[Tuple[str, str]] = set()

        if track.get("artists") and len(track["artists"]) > 0:
            cache_key = client.sanitize_cache_key(
                f"lastfm_similar_10_{track['artists'][0]['name']}_{track['name']}"
            )
            lastfm_similar = cache.get(cache_key)

            if lastfm_similar is None:
                lastfm_similar = await client.get_lastfm_similar_tracks(
                    track["artists"][0]["name"], track["name"], limit=10
                )
                if lastfm_similar:
                    cache.set(cache_key, lastfm_similar, timeout=client.CACHE_TIMEOUT)

            similar_tracks = await get_similar_track_details(
                client, lastfm_similar, seen_tracks
            )

        return {
            "track": track,
            "album": album,
            "artist": artist,
            "similar_tracks": similar_tracks,
        }

    except Exception as e:
        logger.error(f"Error fetching track page data: {e}")
        raise


async def get_similar_track_details(
    client, lastfm_similar: List[Dict], seen_tracks: set[tuple[str, str]]
) -> List[Dict]:
    """Get Spotify details for similar tracks from LastFM."""
    similar_tracks = []

    for similar in lastfm_similar:
        identifier = (similar["name"], similar["artist"]["name"])
        if identifier not in seen_tracks:
            id_cache_key = client.sanitize_cache_key(
                f"spotify_track_id_{similar['name']}_{similar['artist']['name']}"
            )
            similar_track_id = cache.get(id_cache_key)

            if similar_track_id is None:
                similar_track_id = await client.get_spotify_track_id(
                    similar["name"], similar["artist"]["name"]
                )
                if similar_track_id:
                    cache.set(
                        id_cache_key,
                        similar_track_id,
                        timeout=client.CACHE_TIMEOUT,
                    )

            if similar_track_id:
                details_cache_key = client.sanitize_cache_key(
                    f"track_details_false_{similar_track_id}"
                )
                track_details = cache.get(details_cache_key)

                if track_details is None:
                    track_details = await client.get_track_details(
                        similar_track_id, preview=False
                    )
                    if track_details:
                        cache.set(
                            details_cache_key,
                            track_details,
                            timeout=client.CACHE_TIMEOUT,
                        )

                if track_details:
                    seen_tracks.add(identifier)
                    similar_tracks.append(track_details)

    return similar_tracks


async def get_preview_urls_batch(client, track_ids: List[str]) -> Dict[str, str]:
    """Get preview URLs for a batch of tracks."""
    preview_urls = {}
    for track_id in track_ids:
        preview_cache_key = client.sanitize_cache_key(f"preview_url_{track_id}")
        preview_url = cache.get(preview_cache_key)

        if preview_url:
            preview_urls[track_id] = preview_url
            continue

        track = await client.get_track_details(track_id, preview=True)
        if track and track.get("preview_url"):
            preview_urls[track_id] = track["preview_url"]
            cache.set(
                preview_cache_key,
                track["preview_url"],
                timeout=client.CACHE_TIMEOUT,
            )

    return preview_urls


## Stats Section Helpers


async def get_item_stats(
    user,
    item: Dict[str, str],
    item_type: str,
    time_range: str,
    start_date: str | None = None,
    end_date: str | None = None,
) -> Dict[str, Any]:
    """Get stats data for an item (artist, album, or track)."""
    try:
        if start_date and end_date:
            since, until = await get_date_range(time_range, start_date, end_date)
        else:
            since, until = await get_date_range(time_range)

        formatted_item = {
            "artist_name": item["name"] if item_type == "artist" else None,
            "album_name": item["name"] if item_type == "album" else None,
            "track_name": item["name"] if item_type == "track" else None,
            "artist_id": item.get("artist_id", ""),
            "album_id": item.get("album_id", ""),
            "track_id": item.get("track_id", ""),
        }

        # Get main stats for the item
        item_id = formatted_item[f"{item_type}_id"]

        if not item_id:
            # Handle the case where the ID is missing
            logger.warning(f"Missing {item_type}_id for {item}")
            return {
                "stats": {
                    "total_plays": 0,
                    "total_minutes": 0,
                    "avg_gap": 0,
                    "peak_position": 0,
                    "longest_streak": 0,
                    "peak_day_plays": 0,
                    "prime_time": "N/A",
                    "repeat_rate": 0,
                },
                "time_range": time_range,
            }

        item_stats = await get_item_stats_util(user, item_id, item_type, since, until)

        if not item_stats or "total_plays" not in item_stats:
            item_stats = {
                "total_plays": 0,
                "total_minutes": 0,
                "avg_gap": 0,
                "peak_position": 0,
                "longest_streak": 0,
                "peak_day_plays": 0,
                "prime_time": "N/A",
                "repeat_rate": 0,
            }

        return {
            "stats": item_stats,
            "time_range": time_range,
        }

    except Exception as e:
        logger.error(f"Error getting {item_type} stats: {e}")
        return {"stats": None, "time_range": time_range}


async def get_item_stats_graphs(
    user,
    item: Dict[str, str],
    item_type: str,
    time_range: str,
    start_date: str | None = None,
    end_date: str | None = None,
) -> Dict[str, Any]:
    """Get visualization data for an item's stats page."""
    try:
        if start_date and end_date:
            since, until = await get_date_range(time_range, start_date, end_date)
        else:
            since, until = await get_date_range(time_range)

        # Format item information consistently
        formatted_item = {
            "artist_name": item.get(
                "artist_name", item["name"] if item_type == "artist" else None
            ),
            "album_name": item.get(
                "album_name", item["name"] if item_type == "album" else None
            ),
            "track_name": item.get(
                "track_name", item["name"] if item_type == "track" else None
            ),
            "artist_id": item.get("artist_id"),
            "album_id": item.get("album_id"),
            "track_id": item.get("track_id"),
        }

        # Initialize results dictionary
        graphs = {}

        # Shared graphs for all item types

        # Line graph showing listening over time
        dates, trends = await get_streaming_trend_data(
            user, since, until, [formatted_item], item_type
        )
        graphs["listening_trend_chart"] = generate_chartjs_line_graph(
            dates, trends, "Date"
        )

        # Bar chart showing listening patterns
        listening_context_data = await get_listening_context_data(
            user, formatted_item, item_type, since, until
        )
        graphs["listening_context_chart"] = generate_listening_context_chart(
            listening_context_data
        )

        # Polar area chart showing times of day listening
        hourly_data = await get_hourly_listening_data(
            user, since, until, item_type, formatted_item
        )
        graphs["hourly_distribution_chart"] = generate_chartjs_polar_area_chart(
            hourly_data
        )

        # Item-specific graphs
        if item_type == "artist":
            # Artist-specific graphs
            genre_data = await get_artist_genre_distribution(
                user, since, until, formatted_item
            )
            graphs["genre_distribution_chart"] = generate_chartjs_pie_chart(
                genre_data["labels"], genre_data["values"]
            )

            discography_data = await get_artist_discography_coverage(
                user, formatted_item["artist_id"]
            )
            graphs["discography_coverage_chart"] = generate_gauge_chart(
                discography_data, "Discography Played"
            )

        elif item_type == "track":
            # Track-specific graphs
            duration_data = await get_track_duration_comparison(
                user, since, until, formatted_item
            )
            graphs["duration_comparison_chart"] = generate_progress_chart(duration_data)

            if formatted_item.get("artist_id"):
                artist_tracks_data = await get_artist_tracks_coverage(
                    user, formatted_item["artist_id"]
                )
                graphs["artist_tracks_chart"] = generate_gauge_chart(
                    artist_tracks_data, "Artist's Tracks Played"
                )

        elif item_type == "album":
            # Album-specific graphs
            album_tracks_data = await get_album_track_plays(
                user, since, until, formatted_item
            )
            graphs["album_tracks_chart"] = generate_horizontal_bar_chart(
                album_tracks_data
            )

            album_coverage_data = await get_album_tracks_coverage(
                user, formatted_item["album_id"]
            )
            graphs["album_coverage_chart"] = generate_gauge_chart(
                album_coverage_data, "Album Tracks Played"
            )

        return graphs

    except Exception as e:
        logger.error(f"Error getting {item_type} stats graphs: {e}")
        return {}
