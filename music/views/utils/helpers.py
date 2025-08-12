# Helper functions for Views
import json
import logging
import os
from datetime import datetime, timedelta
from typing import Any

from asgiref.sync import sync_to_async
from django.conf import settings
from django.core.cache import cache
from django.core.files.storage import default_storage
from django.utils import timezone

from music.models import PlayedTrack
from music.services.graphs import (
    generate_chartjs_bar_chart,
    generate_chartjs_bubble_chart,
    generate_chartjs_doughnut_chart,
    generate_chartjs_line_graph,
    generate_chartjs_pie_chart,
    generate_chartjs_polar_area_chart,
    generate_chartjs_radar_chart,
    generate_chartjs_stacked_bar_chart,
    generate_gauge_chart,
    generate_horizontal_bar_chart,
    generate_listening_context_chart,
    generate_progress_chart,
)
from music.services.openai_service import OpenAIService
from music.utils.db_utils import (
    get_album_track_plays,
    get_album_tracks_coverage,
    get_artist_discography_coverage,
    get_artist_genre_distribution,
    get_artist_tracks_coverage,
    get_bubble_chart_data,
    get_dashboard_stats,
    get_date_range,
    get_discovery_timeline_data,
    get_doughnut_chart_data,
    get_hourly_listening_data,
    get_item_stats_util,
    get_listening_context_data,
    get_listening_stats,
    get_radar_chart_data,
    get_replay_gaps,
    get_stats_boxes_data,
    get_streaming_trend_data,
    get_time_period_distribution,
    get_top_albums,
    get_top_artists,
    get_top_genres,
    get_top_tracks,
    get_track_duration_comparison,
)
from spotify.util import is_spotify_authenticated

logger = logging.getLogger(__name__)

# Cache timeout constants
ONE_WEEK = 604800  # 7 days in seconds
ONE_MONTH = 2592000  # 30 days in seconds


## General Helpers
def get_x_label(time_range: str) -> str:
    """
    Determine the appropriate x-axis label based on the time range.

    Args:
        time_range: The selected time range

    Returns:
        Appropriate x-axis label for charts
    """
    # Map time ranges to appropriate x-axis labels for charts
    time_range_labels = {
        "last_7_days": "Date",
        "last_4_weeks": "Month",
        "6_months": "Month",
        "last_year": "Year",
        "all_time": "Year",
    }

    # Return appropriate label or default to "Date" if not found
    return time_range_labels.get(time_range, "Date")


##  Album Stats Helpers
async def get_album_visualizations(
    user: Any,
    since: datetime,
    until: datetime,
    top_albums: list[dict[str, Any]],
    time_range: str,
) -> dict[str, Any]:
    """
    Get all visualization data for album stats.

    Args:
        user: SpotifyUser instance
        since: Start datetime for filtering
        until: End datetime for filtering
        top_albums: List of top album dictionaries
        time_range: Time range selection

    Returns:
        Dictionary containing all visualization data
    """
    x_label = get_x_label(time_range)
    first_album = top_albums[0] if top_albums else None

    # Execute all async visualization data fetching operations in parallel
    streaming_task = get_streaming_trend_data(user, since, until, top_albums, "album")
    radar_task = get_radar_chart_data(user, since, until, top_albums, "album")
    doughnut_task = get_doughnut_chart_data(user, since, until, top_albums, "album")
    hourly_task = get_hourly_listening_data(user, since, until, "album", first_album)
    bubble_task = get_bubble_chart_data(user, since, until, top_albums, "album")
    stats_boxes_task = get_stats_boxes_data(user, since, until, top_albums, "album")
    discovery_task = get_discovery_timeline_data(user, since, until, "album")
    time_dist_task = get_time_period_distribution(
        user, since, until, top_albums, "album"
    )
    replay_gaps_task = get_replay_gaps(user, since, until, top_albums, "album")

    # Gather results
    dates, trends = await streaming_task
    radar_data = await radar_task
    doughnut_labels, doughnut_values, doughnut_colors = await doughnut_task
    hourly_data = await hourly_task
    bubble_data = await bubble_task
    stats_boxes = await stats_boxes_task
    discovery_dates, discovery_counts = await discovery_task
    time_labels, time_datasets = await time_dist_task
    replay_labels, replay_values = await replay_gaps_task

    # Generate charts from fetched data
    trends_chart = generate_chartjs_line_graph(dates, trends, x_label)
    radar_chart = generate_chartjs_radar_chart(
        [
            "Total Plays",
            "Total Time (min)",
            "Unique Tracks",
            "Variety",
            "Average Popularity",
        ],
        radar_data,
    )
    doughnut_chart = generate_chartjs_doughnut_chart(
        doughnut_labels, doughnut_values, doughnut_colors
    )
    polar_area_chart = generate_chartjs_polar_area_chart(hourly_data)
    bubble_chart = generate_chartjs_bubble_chart(bubble_data)
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
    stacked_chart = generate_chartjs_stacked_bar_chart(time_labels, time_datasets)
    bar_chart = generate_chartjs_bar_chart(
        replay_labels, replay_values, y_label="Hours Between Plays"
    )

    # Return all chart data in a single dictionary
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
    spotify_client: Any, top_albums: list[dict[str, Any]], seen_album_ids: set[str]
) -> list[dict[str, Any]]:
    """
    Get similar albums recommendations based on user's top albums.

    Args:
        spotify_client: SpotifyClient instance
        top_albums: List of user's top albums
        seen_album_ids: Set of already seen album IDs to avoid duplicates

    Returns:
        List of similar album recommendations
    """
    similar_albums = []
    MAX_SIMILAR_ALBUMS = 10

    try:
        for album in top_albums:
            # Get similar artists for each album's main artist
            artist_name = album["artist_name"]
            cache_key = spotify_client.sanitize_cache_key(
                f"similar_artists_10_{artist_name}"
            )
            similar_artists = cache.get(cache_key)

            if similar_artists is None:
                similar_artists = await spotify_client.get_similar_artists(
                    artist_name, limit=10
                )
                if similar_artists:
                    cache.set(cache_key, similar_artists, timeout=ONE_MONTH)

            # For each similar artist, get their top album
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
                        cache.set(cache_key, artist_top_albums, timeout=ONE_MONTH)

                # Add each similar album that hasn't been seen before
                for similar_album in artist_top_albums:
                    album_id = similar_album["id"]
                    if album_id not in seen_album_ids:
                        similar_albums.append(similar_album)
                        seen_album_ids.add(album_id)

                        # Return early if we've found enough albums
                        if len(similar_albums) >= MAX_SIMILAR_ALBUMS:
                            return similar_albums

    except Exception as e:
        logger.error(f"Error fetching similar albums: {e}", exc_info=True)

    return similar_albums


## Album helpers


async def get_artist_details(client: Any, artist_id: str) -> dict[str, Any]:
    """
    Get artist details with caching.

    Args:
        client: SpotifyClient instance
        artist_id: Spotify artist ID

    Returns:
        Dictionary with artist details
    """
    cache_key = client.sanitize_cache_key(f"artist_details_{artist_id}")
    artist_details = cache.get(cache_key)

    if artist_details is None:
        artist_details = await client.get_artist(artist_id)
        if artist_details:
            cache.set(cache_key, artist_details, timeout=ONE_WEEK)

    return artist_details or {}


async def enrich_track_details(
    client: Any, tracks: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """
    Enrich track details with additional information from Spotify API.

    Args:
        client: SpotifyClient instance
        tracks: List of track dictionaries to enrich

    Returns:
        List of tracks with additional details
    """
    # Skip processing if no tracks provided
    if not tracks:
        return []

    for track in tracks:
        track_id = track.get("id")
        if not track_id:
            continue

        # Try to get track details from cache first
        cache_key = client.sanitize_cache_key(f"track_details_{track_id}")
        track_details = cache.get(cache_key)

        # Fetch from API if not in cache
        if track_details is None:
            track_details = await client.get_track_details(track_id)
            if track_details:
                cache.set(cache_key, track_details, timeout=client.CACHE_TIMEOUT)

        # Add additional details to the track
        duration_ms = track.get("duration_ms", 0)
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
    spotify_client: Any, top_artists: list[dict[str, Any]], seen_artist_ids: set[str]
) -> list[dict[str, Any]]:
    """
    Get similar artists recommendations based on user's top artists.

    Args:
        spotify_client: SpotifyClient instance
        top_artists: List of user's top artists
        seen_artist_ids: Set of already seen artist IDs to avoid duplicates

    Returns:
        List of similar artist recommendations
    """
    similar_artists = []

    try:
        for artist in top_artists:
            artist_name = artist["artist_name"]
            cache_key = spotify_client.sanitize_cache_key(
                f"similar_artists_1_{artist_name}"
            )
            similar = cache.get(cache_key)

            # Fetch similar artists if not in cache
            if similar is None:
                similar = await spotify_client.get_similar_artists(artist_name, limit=1)
                if similar:
                    cache.set(cache_key, similar, timeout=ONE_MONTH)

            # Add unique similar artists to the result list
            for s in similar:
                artist_id = s.get("id")
                if artist_id and artist_id not in seen_artist_ids:
                    similar_artists.append(s)
                    seen_artist_ids.add(artist_id)

    except Exception as e:
        logger.error(f"Error fetching similar artists: {e}")

    return similar_artists


async def get_artist_visualizations(
    user: Any,
    since: datetime,
    until: datetime,
    top_artists: list[dict[str, Any]],
    time_range: str,
) -> dict[str, Any]:
    """
    Get all visualization data for artist stats.

    Args:
        user: SpotifyUser instance
        since: Start datetime for filtering
        until: End datetime for filtering
        top_artists: List of top artist dictionaries
        time_range: Time range selection

    Returns:
        Dictionary containing all visualization data
    """
    x_label = get_x_label(time_range)
    first_artist = top_artists[0] if top_artists else None

    # Radar chart labels (used for all item types)
    radar_labels = [
        "Total Plays",
        "Total Time (min)",
        "Unique Tracks",
        "Variety",
        "Average Popularity",
    ]

    # Execute all data fetching tasks in parallel
    tasks = {
        "streaming": get_streaming_trend_data(
            user, since, until, top_artists, "artist"
        ),
        "radar": get_radar_chart_data(user, since, until, top_artists, "artist"),
        "doughnut": get_doughnut_chart_data(user, since, until, top_artists, "artist"),
        "hourly": get_hourly_listening_data(user, since, until, "artist", first_artist),
        "bubble": get_bubble_chart_data(user, since, until, top_artists, "artist"),
        "stats_boxes": get_stats_boxes_data(user, since, until, top_artists, "artist"),
        "discovery": get_discovery_timeline_data(user, since, until, "artist"),
        "time_dist": get_time_period_distribution(
            user, since, until, top_artists, "artist"
        ),
        "replay_gaps": get_replay_gaps(user, since, until, top_artists, "artist"),
    }

    # Gather results from all tasks
    dates, trends = await tasks["streaming"]
    radar_data = await tasks["radar"]
    doughnut_labels, doughnut_values, doughnut_colors = await tasks["doughnut"]
    hourly_data = await tasks["hourly"]
    bubble_data = await tasks["bubble"]
    stats_boxes = await tasks["stats_boxes"]
    discovery_dates, discovery_counts = await tasks["discovery"]
    time_labels, time_datasets = await tasks["time_dist"]
    replay_labels, replay_values = await tasks["replay_gaps"]

    # Generate charts from the fetched data
    return {
        "trends_chart": generate_chartjs_line_graph(dates, trends, x_label),
        "radar_chart": generate_chartjs_radar_chart(radar_labels, radar_data),
        "doughnut_chart": generate_chartjs_doughnut_chart(
            doughnut_labels, doughnut_values, doughnut_colors
        ),
        "stats_boxes": stats_boxes,
        "polar_area_chart": generate_chartjs_polar_area_chart(hourly_data),
        "bubble_chart": generate_chartjs_bubble_chart(bubble_data),
        "discovery_chart": generate_chartjs_line_graph(
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
        ),
        "stacked_chart": generate_chartjs_stacked_bar_chart(time_labels, time_datasets),
        "bar_chart": generate_chartjs_bar_chart(
            replay_labels, replay_values, y_label="Hours Between Plays"
        ),
    }


## Artist helpers


async def get_artist_page_data(client: Any, artist_id: str) -> dict[str, Any]:
    """
    Get all data needed for the artist page.

    Args:
        client: SpotifyClient instance
        artist_id: Spotify artist ID

    Returns:
        Dictionary with artist page data including details, albums, and tracks
    """
    # Default empty response in case of error
    default_response: dict[str, Any] = {
        "artist": None,
        "similar_artists": [],
        "albums": [],
        "compilations": [],
        "top_tracks": [],
    }

    try:
        # Get artist details
        artist = await client.get_artist(artist_id)
        if not artist:
            raise ValueError("Artist not found")

        # Get similar artists with caching
        cache_key = client.sanitize_cache_key(f"similar_artists_{artist_id}")
        similar_artists = cache.get(cache_key)
        if similar_artists is None:
            similar_artists = await client.get_similar_artists(artist["name"])
            if similar_artists:
                cache.set(cache_key, similar_artists, timeout=client.CACHE_TIMEOUT)

        # Filter out the current artist from similar artists
        similar_artists_spotify = [
            similar
            for similar in (similar_artists or [])
            if similar.get("id") != artist_id
        ]

        # Get all albums with caching
        cache_key = client.sanitize_cache_key(f"artist_albums_all_{artist_id}")
        albums = cache.get(cache_key)
        if albums is None:
            albums = await client.get_artist_albums(artist_id, include_groups=None)
            if albums:
                cache.set(cache_key, albums, timeout=ONE_WEEK)

        # Extract compilation albums
        compilations = [
            album for album in albums if album.get("album_type") == "compilation"
        ]

        # Get top tracks with caching
        cache_key = client.sanitize_cache_key(f"artist_top_tracks_{artist_id}_5")
        top_tracks = cache.get(cache_key)
        if top_tracks is None:
            top_tracks = await client.get_artist_top_tracks(5, artist_id)
            if top_tracks:
                cache.set(cache_key, top_tracks, timeout=ONE_WEEK)

        # Enrich top tracks with preview URLs and album info
        enrichment_tasks = []
        for track in top_tracks:
            if track and track.get("id"):
                task = client.get_track_details(track["id"])
                enrichment_tasks.append((track, task))

        # Process enrichment results
        for track, task in enrichment_tasks:
            track_details = await task
            if track_details:
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
        return default_response


## Chat helpers


async def handle_chat_message(
    spotify_user_id: str, user_message: str
) -> tuple[dict[str, Any], int]:
    """
    Handle processing of chat messages and getting AI responses.

    Args:
        spotify_user_id: Spotify user ID for authentication
        user_message: User's message text

    Returns:
        Tuple of (response_data, http_status_code)
    """
    try:
        # Validate input
        if not user_message:
            return {"error": "No message provided."}, 400

        # Check authentication
        if not spotify_user_id or not await sync_to_async(is_spotify_authenticated)(
            spotify_user_id
        ):
            return {"error": "User not authenticated."}, 401

        # Process message and get AI response
        openai_service = OpenAIService()

        # Execute tasks in sequence since each depends on the previous
        listening_data = await openai_service.get_listening_data(spotify_user_id)
        prompt = await openai_service.create_prompt(user_message, listening_data)
        ai_response = await openai_service.get_ai_response(prompt)

        return {"reply": ai_response}, 200

    except Exception as e:
        logger.error(f"Error processing chat message: {e}")
        return {"error": "Internal server error."}, 500


## Genre Stats Helpers


async def get_genre_visualizations(
    user: Any,
    since: datetime,
    until: datetime,
    top_genres: list[dict[str, Any]],
    time_range: str,
) -> dict[str, Any]:
    """
    Get all visualization data for genre stats.

    Args:
        user: SpotifyUser instance
        since: Start datetime for filtering
        until: End datetime for filtering
        top_genres: List of top genre dictionaries
        time_range: Time range selection

    Returns:
        Dictionary containing all visualization data
    """
    x_label = get_x_label(time_range)
    first_genre = top_genres[0] if top_genres else None

    # Define common radar chart labels
    radar_labels = [
        "Total Plays",
        "Total Time (min)",
        "Unique Tracks",
        "Variety",
        "Average Popularity",
    ]

    # Execute all data fetching tasks concurrently
    tasks = {
        "streaming": get_streaming_trend_data(user, since, until, top_genres, "genre"),
        "radar": get_radar_chart_data(user, since, until, top_genres, "genre"),
        "doughnut": get_doughnut_chart_data(user, since, until, top_genres, "genre"),
        "hourly": get_hourly_listening_data(user, since, until, "genre", first_genre),
        "bubble": get_bubble_chart_data(user, since, until, top_genres, "genre"),
        "stats_boxes": get_stats_boxes_data(user, since, until, top_genres, "genre"),
        "discovery": get_discovery_timeline_data(user, since, until, "genre"),
        "time_dist": get_time_period_distribution(
            user, since, until, top_genres, "genre"
        ),
        "replay_gaps": get_replay_gaps(user, since, until, top_genres, "genre"),
    }

    # Gather results from all tasks
    results = {}
    for key, task in tasks.items():
        results[key] = await task

    # Generate charts from fetched data
    dates, trends = results["streaming"]
    discovery_dates, discovery_counts = results["discovery"]
    time_labels, time_datasets = results["time_dist"]
    replay_labels, replay_values = results["replay_gaps"]
    doughnut_labels, doughnut_values, doughnut_colors = results["doughnut"]

    return {
        "trends_chart": generate_chartjs_line_graph(dates, trends, x_label),
        "radar_chart": generate_chartjs_radar_chart(radar_labels, results["radar"]),
        "doughnut_chart": generate_chartjs_doughnut_chart(
            doughnut_labels, doughnut_values, doughnut_colors
        ),
        "stats_boxes": results["stats_boxes"],
        "polar_area_chart": generate_chartjs_polar_area_chart(results["hourly"]),
        "bubble_chart": generate_chartjs_bubble_chart(results["bubble"]),
        "discovery_chart": generate_chartjs_line_graph(
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
        ),
        "stacked_chart": generate_chartjs_stacked_bar_chart(time_labels, time_datasets),
        "bar_chart": generate_chartjs_bar_chart(
            replay_labels, replay_values, y_label="Hours Between Plays"
        ),
    }


async def get_similar_genres(
    spotify_client: Any, top_genres: list[dict[str, Any]], seen_genres: set[str]
) -> list[dict[str, Any]]:
    """
    Get similar genres recommendations based on user's top genres.

    Args:
        spotify_client: SpotifyClient instance
        top_genres: List of user's top genres
        seen_genres: Set of already seen genres to avoid duplicates

    Returns:
        List of similar genre recommendations
    """
    similar_genres = []
    MAX_SIMILAR_GENRES = 10

    try:
        for genre in top_genres:
            # Get artists in this genre
            artists, _ = await spotify_client.get_items_by_genre(genre["genre"])

            # For each artist, find similar artists and their genres
            for artist in artists[:3]:  # Limit to avoid too many API calls
                cache_key = spotify_client.sanitize_cache_key(
                    f"similar_artists_1_{artist['name']}"
                )
                similar_artists = cache.get(cache_key)

                # Fetch similar artists if not cached
                if similar_artists is None:
                    similar_artists = await spotify_client.get_similar_artists(
                        artist["name"], limit=1
                    )
                    if similar_artists:
                        cache.set(cache_key, similar_artists, timeout=ONE_MONTH)

                # Extract genres from similar artists
                for similar_artist in similar_artists:
                    artist_genres = similar_artist.get("genres", [])

                    # Add each new genre to results
                    for artist_genre in artist_genres:
                        if artist_genre not in seen_genres:
                            seen_genres.add(artist_genre)
                            similar_genres.append(
                                {
                                    "genre": artist_genre,
                                    "count": 1,
                                }
                            )

                            # Return early if we've found enough genres
                            if len(similar_genres) >= MAX_SIMILAR_GENRES:
                                return similar_genres

    except Exception as e:
        logger.error(f"Error fetching similar genres: {e}", exc_info=True)

    return similar_genres


## Genre helpers


async def get_genre_items(client: Any, genre_name: str) -> dict[str, list[Any]]:
    """
    Get artists and tracks for a specific genre with caching.

    Args:
        client: SpotifyClient instance
        genre_name: Name of the genre

    Returns:
        Dictionary with lists of artists and tracks in the genre
    """
    try:
        # Try to get genre items from cache
        cache_key = client.sanitize_cache_key(f"genre_items_{genre_name}")
        genre_items = cache.get(cache_key)

        if genre_items is None:
            # Fetch genre items from API if not cached
            artists, tracks = await client.get_items_by_genre(genre_name)

            if artists or tracks:
                genre_items = {"artists": artists, "tracks": tracks}
                cache.set(cache_key, genre_items, timeout=client.CACHE_TIMEOUT)
        else:
            # Extract artists and tracks from cached data
            artists = genre_items.get("artists", [])
            tracks = genre_items.get("tracks", [])

        return {"artists": artists, "tracks": tracks}

    except Exception as e:
        logger.error(f"Error fetching items for genre {genre_name}: {e}")
        return {"artists": [], "tracks": []}


## History Helpers


async def handle_history_import(
    user: Any, file_content: bytes, file_hash: str
) -> tuple[bool, str]:
    """
    Handle the import of a history file from Spotify.

    Args:
        user: SpotifyUser instance
        file_content: Binary content of the uploaded file
        file_hash: Hash of the file for storage

    Returns:
        Tuple of (success_status, message)
    """
    try:
        # Parse JSON data from file
        data = json.loads(file_content.decode("utf-8"))

        # Validate input data
        if not data:
            return False, "Empty JSON file. Please upload a non-empty JSON file."

        if not isinstance(data, list):
            return False, "Invalid JSON format. Expected a list of tracks."

        # Initialize containers for processed data
        track_ids = []
        durations = {}
        track_info_list = []
        required_keys = [
            "ts",
            "master_metadata_track_name",
            "master_metadata_album_artist_name",
            "master_metadata_album_album_name",
            "spotify_track_uri",
        ]

        # Process each item in the history file
        for item in data:
            # Skip items missing required keys
            if not all(key in item for key in required_keys):
                continue

            # Parse timestamp
            played_at_str = item["ts"]
            try:
                played_at = datetime.strptime(played_at_str, "%Y-%m-%dT%H:%M:%S%z")
            except ValueError:
                continue

            # Skip future dates (likely errors)
            if played_at > timezone.now():
                continue

            # Extract track metadata
            track_name = item["master_metadata_track_name"]
            artist_name = item["master_metadata_album_artist_name"]
            album_name = item["master_metadata_album_album_name"]
            track_uri = item.get("spotify_track_uri")
            duration_ms = item.get("ms_played", 0)

            # Skip invalid track URIs
            if not track_uri or not track_uri.startswith("spotify:track:"):
                continue

            # Extract track ID and save data
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

        # Ensure we have valid tracks
        if not track_ids:
            return False, "No valid tracks found in the uploaded file."

        # Save the file to storage
        file_path = os.path.join("listening_history", f"{file_hash}.json")
        await sync_to_async(default_storage.save)(file_path, file_content)

        return True, "History import successful."

    except json.JSONDecodeError:
        return False, "Invalid JSON format. Please upload a valid JSON file."
    except Exception as e:
        logger.error(f"Error importing history: {e}")
        return False, f"Error importing history: {str(e)}"


async def delete_listening_history() -> tuple[bool, str]:
    """
    Delete all listening history files and records.

    Returns:
        Tuple of (success_status, message)
    """
    history_dir = os.path.join(settings.BASE_DIR, "media/listening_history")

    # Check if directory exists
    if not os.path.exists(history_dir):
        return False, "Listening history directory not found."

    try:
        # List all files in the directory
        filenames = await sync_to_async(os.listdir)(history_dir)

        # Delete each file
        for filename in filenames:
            file_path = os.path.join(history_dir, filename)
            if await sync_to_async(os.path.isfile)(file_path):
                try:
                    await sync_to_async(os.remove)(file_path)
                except Exception as e:
                    logger.error(f"Error removing file {file_path}: {e}")
                    return False, f"Error removing file: {file_path}"

        # Delete all database records
        await sync_to_async(lambda: PlayedTrack.objects.all().delete())()

        return True, "All listening history has been deleted."

    except FileNotFoundError:
        return False, "Listening history directory not found."
    except Exception as e:
        logger.error(f"Error deleting listening history: {e}")
        return False, f"Error: {str(e)}"


## Home Helpers


async def get_home_visualizations(
    user: Any,
    has_history: bool,
    time_range: str,
    start_date: str | None,
    end_date: str | None,
) -> dict[str, Any]:
    """
    Get all visualization data for home page.

    Args:
        user: SpotifyUser instance
        has_history: Whether the user has listening history
        time_range: Time range selection
        start_date: Start date string for custom range
        end_date: End date string for custom range

    Returns:
        Dictionary with all visualization data for home page
    """
    # Return early if user has no history
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
        # Get date range based on time range selection
        since, until = await get_date_range(time_range, start_date, end_date)

        # Run data fetching operations in parallel
        tasks = {
            "stats": sync_to_async(get_listening_stats)(
                user, time_range, start_date, end_date
            ),
            "top_tracks": get_top_tracks(user, since, until, 10),
            "top_artists": get_top_artists(user, since, until, 10),
            "top_genres": get_top_genres(user, since, until, 10),
            "top_albums": get_top_albums(user, since, until, 10),
            "written_stats": get_dashboard_stats(user, since, until),
        }

        # Gather results
        results = {}
        for key, task in tasks.items():
            results[key] = await task

        stats = results["stats"]
        top_tracks = results["top_tracks"]
        top_artists = results["top_artists"]
        top_genres = results["top_genres"]
        top_albums = results["top_albums"]
        written_stats = results["written_stats"]

        # Get stats boxes data based on top tracks
        stats_boxes = await get_stats_boxes_data(
            user, since, until, top_tracks, "track"
        )

        # Generate trend chart from listening stats
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

        # Generate genre chart from top genres
        genres = [item["genre"] for item in top_genres] if top_genres else []
        genre_counts = [item["count"] for item in top_genres] if top_genres else []
        genre_chart_data = (
            generate_chartjs_pie_chart(genres, genre_counts) if genres else None
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
    time_range: str, start_date: str | None, end_date: str | None
) -> tuple[str | None, str | None, str]:
    """
    Validate custom date range inputs.

    Args:
        time_range: Time range selection
        start_date: Start date string for custom range
        end_date: End date string for custom range

    Returns:
        Tuple of (validated_start_date, validated_end_date, error_message)
    """
    error_message = ""

    # Only validate for custom time range
    if time_range == "custom":
        # Check if both dates are provided
        if not start_date or not end_date:
            error_message = (
                "Both start date and end date are required for a custom range."
            )
        else:
            try:
                # Parse and validate dates
                naive_start = datetime.strptime(start_date, "%Y-%m-%d")
                naive_end = datetime.strptime(end_date, "%Y-%m-%d")

                start = timezone.make_aware(naive_start)
                end = timezone.make_aware(naive_end) + timedelta(days=1)

                # Check if dates are valid
                if start > end:
                    error_message = "Start date cannot be after end date."
                elif end > timezone.now() or start > timezone.now():
                    error_message = "Dates cannot be in the future."

            except ValueError:
                error_message = "Invalid date format. Please use YYYY-MM-DD."

    return start_date, end_date, error_message


## Track Stats Helpers


async def get_similar_tracks(
    client: Any, top_tracks: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """
    Get similar tracks based on user's top tracks.

    Args:
        client: SpotifyClient instance
        top_tracks: List of user's top tracks

    Returns:
        List of similar track recommendations
    """
    seen_tracks = set()
    similar_tracks = []
    MAX_SIMILAR_TRACKS = 10

    try:
        for track in top_tracks:
            try:
                artist_name = track.get("artist_name", "")
                track_name = track.get("track_name", "")

                if not artist_name or not track_name:
                    continue

                # Try to get similar tracks from cache
                cache_key = client.sanitize_cache_key(
                    f"lastfm_similar_1_{artist_name}_{track_name}"
                )
                lastfm_similar = cache.get(cache_key)

                # Fetch from API if not in cache
                if lastfm_similar is None:
                    lastfm_similar = await client.get_lastfm_similar_tracks(
                        artist_name, track_name, limit=1
                    )
                    if lastfm_similar:
                        cache.set(
                            cache_key, lastfm_similar, timeout=client.CACHE_TIMEOUT
                        )

                # Process each similar track
                for similar in lastfm_similar:
                    similar_name = similar.get("name", "")
                    similar_artist = similar.get("artist", {}).get("name", "")

                    if not similar_name or not similar_artist:
                        continue

                    # Create a unique identifier for this track
                    identifier = (similar_name, similar_artist)
                    if identifier in seen_tracks:
                        continue

                    # Get Spotify track ID with caching
                    id_cache_key = client.sanitize_cache_key(
                        f"spotify_track_id_{similar_name}_{similar_artist}"
                    )
                    track_id = cache.get(id_cache_key)

                    if track_id is None:
                        track_id = await client.get_spotify_track_id(
                            similar_name, similar_artist
                        )
                        if track_id:
                            cache.set(
                                id_cache_key, track_id, timeout=client.CACHE_TIMEOUT
                            )

                    # Get track details if we have a valid ID
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

                            # Return early if we've found enough tracks
                            if len(similar_tracks) >= MAX_SIMILAR_TRACKS:
                                return similar_tracks

            except Exception as e:
                logger.error(
                    f"Error fetching similar track details: {e}", exc_info=True
                )
                continue

    except Exception as e:
        logger.error(f"Error fetching similar tracks: {e}", exc_info=True)

    return similar_tracks


async def get_track_visualizations(
    user: Any,
    since: datetime,
    until: datetime,
    top_tracks: list[dict[str, Any]],
    time_range: str,
) -> dict[str, Any]:
    """
    Get all visualization data for track stats.

    Args:
        user: SpotifyUser instance
        since: Start datetime for filtering
        until: End datetime for filtering
        top_tracks: List of top track dictionaries
        time_range: Time range selection

    Returns:
        Dictionary containing all visualization data
    """
    x_label = get_x_label(time_range)
    first_track = top_tracks[0] if top_tracks else None

    # Define shared chart labels
    radar_labels = [
        "Total Plays",
        "Total Time (min)",
        "Unique Tracks",
        "Variety",
        "Average Popularity",
    ]

    # Execute all data fetching tasks in parallel
    tasks = {
        "streaming": get_streaming_trend_data(user, since, until, top_tracks, "track"),
        "radar": get_radar_chart_data(user, since, until, top_tracks, "track"),
        "doughnut": get_doughnut_chart_data(user, since, until, top_tracks, "track"),
        "hourly": get_hourly_listening_data(user, since, until, "track", first_track),
        "bubble": get_bubble_chart_data(user, since, until, top_tracks, "track"),
        "stats_boxes": get_stats_boxes_data(user, since, until, top_tracks, "track"),
        "discovery": get_discovery_timeline_data(user, since, until, "track"),
        "time_dist": get_time_period_distribution(
            user, since, until, top_tracks, "track"
        ),
        "replay_gaps": get_replay_gaps(user, since, until, top_tracks, "track"),
    }

    # Gather all results
    results = {key: await task for key, task in tasks.items()}

    # Extract data from results
    dates, trends = results["streaming"]
    discovery_dates, discovery_counts = results["discovery"]
    time_labels, time_datasets = results["time_dist"]
    replay_labels, replay_values = results["replay_gaps"]
    doughnut_labels, doughnut_values, doughnut_colors = results["doughnut"]

    # Generate and return all charts
    return {
        "trends_chart": generate_chartjs_line_graph(dates, trends, x_label),
        "radar_chart": generate_chartjs_radar_chart(radar_labels, results["radar"]),
        "doughnut_chart": generate_chartjs_doughnut_chart(
            doughnut_labels, doughnut_values, doughnut_colors
        ),
        "stats_boxes": results["stats_boxes"],
        "polar_area_chart": generate_chartjs_polar_area_chart(results["hourly"]),
        "bubble_chart": generate_chartjs_bubble_chart(results["bubble"]),
        "discovery_chart": generate_chartjs_line_graph(
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
        ),
        "stacked_chart": generate_chartjs_stacked_bar_chart(time_labels, time_datasets),
        "bar_chart": generate_chartjs_bar_chart(
            replay_labels, replay_values, y_label="Hours Between Plays"
        ),
    }


## Track Helpers


async def get_track_page_data(client: Any, track_id: str) -> dict[str, Any]:
    """
    Get all data needed for track page.

    Args:
        client: SpotifyClient instance
        track_id: Spotify track ID

    Returns:
        Dictionary with track page data
    """
    try:
        # Get track details with caching
        cache_key = client.sanitize_cache_key(f"track_details_{track_id}")
        track_details = cache.get(cache_key)

        if track_details is None:
            track_details = await client.get_track_details(track_id)
            if track_details:
                cache.set(
                    cache_key, track_details, timeout=None
                )  # No expiration for tracks
            else:
                raise ValueError("Track details not found.")

        # Add formatted duration
        track = track_details
        duration_ms = track.get("duration_ms")
        if duration_ms:
            track["duration"] = await sync_to_async(client.get_duration_ms)(duration_ms)
        else:
            track["duration"] = "N/A"

        # Get album details if available
        album = None
        if track.get("album") and track["album"].get("id"):
            album_id = track["album"]["id"]
            cache_key = client.sanitize_cache_key(f"album_details_{album_id}")
            album = cache.get(cache_key)

            if album is None:
                album = await client.get_album(album_id)
                if album:
                    cache.set(cache_key, album, timeout=client.CACHE_TIMEOUT)

        # Get artist details if available
        artist = None
        artist_id = None

        if track.get("artists") and track["artists"]:
            artist_id = track["artists"][0].get("id")

        if artist_id:
            cache_key = client.sanitize_cache_key(f"artist_details_{artist_id}")
            artist = cache.get(cache_key)

            if artist is None:
                artist = await client.get_artist(artist_id)
                if artist:
                    cache.set(cache_key, artist, timeout=ONE_WEEK)

        # Get similar tracks if available
        similar_tracks = []
        seen_tracks: set[tuple[str, str]] = set()

        if track.get("artists") and track["artists"]:
            artist_name = track["artists"][0].get("name", "")
            track_name = track.get("name", "")

            if artist_name and track_name:
                cache_key = client.sanitize_cache_key(
                    f"lastfm_similar_10_{artist_name}_{track_name}"
                )
                lastfm_similar = cache.get(cache_key)

                if lastfm_similar is None:
                    lastfm_similar = await client.get_lastfm_similar_tracks(
                        artist_name, track_name, limit=10
                    )
                    if lastfm_similar:
                        cache.set(
                            cache_key, lastfm_similar, timeout=client.CACHE_TIMEOUT
                        )

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
    client: Any, lastfm_similar: list[dict[str, Any]], seen_tracks: set[tuple[str, str]]
) -> list[dict[str, Any]]:
    """
    Get Spotify details for similar tracks from LastFM.

    Args:
        client: SpotifyClient instance
        lastfm_similar: List of similar tracks from LastFM API
        seen_tracks: Set of already seen tracks to avoid duplicates

    Returns:
        List of track details from Spotify API
    """
    similar_tracks = []

    # Process each similar track from LastFM
    for similar in lastfm_similar:
        similar_name = similar.get("name", "")
        similar_artist = similar.get("artist", {}).get("name", "")

        if not similar_name or not similar_artist:
            continue

        # Create unique identifier and skip if already seen
        identifier = (similar_name, similar_artist)
        if identifier in seen_tracks:
            continue

        # Get Spotify track ID with caching
        id_cache_key = client.sanitize_cache_key(
            f"spotify_track_id_{similar_name}_{similar_artist}"
        )
        similar_track_id = cache.get(id_cache_key)

        if similar_track_id is None:
            similar_track_id = await client.get_spotify_track_id(
                similar_name, similar_artist
            )
            if similar_track_id:
                cache.set(id_cache_key, similar_track_id, timeout=client.CACHE_TIMEOUT)

        # Get track details if we have a valid ID
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
                        details_cache_key, track_details, timeout=client.CACHE_TIMEOUT
                    )

            if track_details:
                seen_tracks.add(identifier)
                similar_tracks.append(track_details)

    return similar_tracks


async def get_preview_urls_batch(client: Any, track_ids: list[str]) -> dict[str, str]:
    """
    Get preview URLs for a batch of tracks efficiently.

    Args:
        client: SpotifyClient instance
        track_ids: List of Spotify track IDs

    Returns:
        Dictionary mapping track IDs to preview URLs
    """
    if not track_ids:
        return {}

    preview_urls = {}
    preview_tasks = []

    # Initiate all fetch tasks in parallel
    for track_id in track_ids:
        preview_cache_key = client.sanitize_cache_key(f"preview_url_{track_id}")
        cached_url = cache.get(preview_cache_key)

        if cached_url:
            preview_urls[track_id] = cached_url
        else:
            task = client.get_track_details(track_id, preview=True)
            preview_tasks.append((track_id, task))

    # Process all fetch results
    for track_id, task in preview_tasks:
        track = await task
        if track and track.get("preview_url"):
            preview_url = track["preview_url"]
            preview_urls[track_id] = preview_url

            # Cache the result for future use
            cache.set(
                client.sanitize_cache_key(f"preview_url_{track_id}"),
                preview_url,
                timeout=client.CACHE_TIMEOUT,
            )

    return preview_urls


## Stats Section Helpers


async def get_item_stats(
    user: Any,
    item: dict[str, str],
    item_type: str,
    time_range: str,
    start_date: str | None = None,
    end_date: str | None = None,
) -> dict[str, Any]:
    """
    Get stats data for an item (artist, album, or track).

    Args:
        user: SpotifyUser instance
        item: Dictionary with item information
        item_type: Type of item ('artist', 'album', 'track')
        time_range: Time range selection
        start_date: Start date string for custom range
        end_date: End date string for custom range

    Returns:
        Dictionary with item stats
    """
    try:
        # Get date range based on time range parameters
        if start_date and end_date:
            since, until = await get_date_range(time_range, start_date, end_date)
        else:
            since, until = await get_date_range(time_range)

        # Format item information consistently
        formatted_item = {
            "artist_name": item["name"] if item_type == "artist" else None,
            "album_name": item["name"] if item_type == "album" else None,
            "track_name": item["name"] if item_type == "track" else None,
            "artist_id": item.get("artist_id", ""),
            "album_id": item.get("album_id", ""),
            "track_id": item.get("track_id", ""),
        }

        # Get relevant ID for the item type
        item_id = formatted_item[f"{item_type}_id"]

        # Return default stats if ID is missing
        if not item_id:
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

        # Get stats for the item
        item_stats = await get_item_stats_util(user, item_id, item_type, since, until)

        # Return default stats if no data found
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
    user: Any,
    item: dict[str, str],
    item_type: str,
    time_range: str,
    start_date: str | None = None,
    end_date: str | None = None,
) -> dict[str, Any]:
    """
    Get visualization data for an item's stats page.

    Args:
        user: SpotifyUser instance
        item: Dictionary with item information
        item_type: Type of item ('artist', 'album', 'track')
        time_range: Time range selection
        start_date: Start date string for custom range
        end_date: End date string for custom range

    Returns:
        Dictionary with visualization data
    """
    try:
        # Get date range based on time range parameters
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

        # Shared graphs for all item types - fetch data in parallel
        shared_tasks = {
            "streaming": get_streaming_trend_data(
                user, since, until, [formatted_item], item_type
            ),
            "context": get_listening_context_data(
                user, formatted_item, item_type, since, until
            ),
            "hourly": get_hourly_listening_data(
                user, since, until, item_type, formatted_item
            ),
        }

        # Wait for all shared tasks to complete
        shared_results = {key: await task for key, task in shared_tasks.items()}

        # Generate shared charts
        dates, trends = shared_results["streaming"]
        graphs["listening_trend_chart"] = generate_chartjs_line_graph(
            dates, trends, "Date"
        )
        graphs["listening_context_chart"] = generate_listening_context_chart(
            shared_results["context"]
        )
        graphs["hourly_distribution_chart"] = generate_chartjs_polar_area_chart(
            shared_results["hourly"]
        )

        # Item-specific graphs
        if item_type == "artist":
            # Artist-specific tasks
            artist_tasks = {
                "genre": get_artist_genre_distribution(
                    user, since, until, formatted_item
                ),
            }

            # Only add discography coverage if we have a valid artist_id
            artist_id = formatted_item.get("artist_id")
            if artist_id:
                artist_tasks["discography"] = get_artist_discography_coverage(
                    user, artist_id
                )

            # Wait for artist-specific tasks
            artist_results = {key: await task for key, task in artist_tasks.items()}

            # Generate artist-specific charts
            genre_data = artist_results["genre"]
            graphs["genre_distribution_chart"] = generate_chartjs_pie_chart(
                genre_data["labels"], genre_data["values"]
            )

            # Only generate discography chart if we have the data
            if "discography" in artist_results:
                graphs["discography_coverage_chart"] = generate_gauge_chart(
                    artist_results["discography"], "Discography Played"
                )

        elif item_type == "track":
            # Track-specific tasks
            track_tasks = {
                "duration": get_track_duration_comparison(
                    user, since, until, formatted_item
                ),
            }

            # Add artist tracks coverage if artist_id is available
            artist_id = formatted_item.get("artist_id")
            if artist_id:  # Only add if we have a valid artist_id
                track_tasks["artist_tracks"] = get_artist_tracks_coverage(
                    user, artist_id
                )

            # Wait for track-specific tasks
            track_results = {key: await task for key, task in track_tasks.items()}

            # Generate track-specific charts
            graphs["duration_comparison_chart"] = generate_progress_chart(
                track_results["duration"]
            )

            # Only generate artist tracks chart if we have the data
            if "artist_tracks" in track_results:
                graphs["artist_tracks_chart"] = generate_gauge_chart(
                    track_results["artist_tracks"], "Artist's Tracks Played"
                )

        elif item_type == "album":
            # Album-specific tasks
            album_tasks = {}

            # Only add album-specific tasks if we have a valid album_id
            album_id = formatted_item.get("album_id")
            if album_id:  # Only add if we have a valid album_id
                album_tasks["tracks"] = get_album_track_plays(
                    user, since, until, formatted_item
                )
                album_tasks["coverage"] = get_album_tracks_coverage(user, album_id)

                # Wait for album-specific tasks
                album_results = {key: await task for key, task in album_tasks.items()}

                # Generate album-specific charts
                graphs["album_tracks_chart"] = generate_horizontal_bar_chart(
                    album_results["tracks"]
                )
                graphs["album_coverage_chart"] = generate_gauge_chart(
                    album_results["coverage"], "Album Tracks Played"
                )

        return graphs

    except Exception as e:
        logger.error(f"Error getting {item_type} stats graphs: {e}", exc_info=True)
        return {}
