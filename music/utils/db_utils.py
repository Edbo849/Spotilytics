import logging
from collections import Counter
from datetime import datetime, timedelta
from typing import Any

from asgiref.sync import sync_to_async
from django.core.cache import cache
from django.db import transaction
from django.db.models import Avg, Count, Sum
from django.db.models.functions import (
    ExtractHour,
    TruncDate,
    TruncDay,
    TruncHour,
    TruncMonth,
    TruncWeek,
)
from django.utils import timezone

from music.models import PlayedTrack
from music.services.SpotifyClient import SpotifyClient
from music.utils.utils.helpers import (
    calculate_aggregate_statistics,
    calculate_average_listening_time_per_day,
    calculate_days_streamed,
    calculate_most_played_genre,
    calculate_most_popular_day,
    calculate_top_listening_hour,
    create_played_track,
    determine_truncate_func_and_formats,
    fetch_recently_played_tracks,
    fetch_spotify_users,
    generate_all_periods,
    get_artist_track_count_helper,
    get_latest_track_timestamp,
    get_track_details,
    get_trend_data,
    populate_dates_and_counts,
    save_played_tracks,
    set_time_range_parameters,
    track_exists,
)
from spotify.util import get_user_tokens

SPOTIFY_API_BASE_URL = "https://api.spotify.com/v1"

logger = logging.getLogger(__name__)


async def read_full_history(self, *args, **options) -> None:
    """
    Read full listening history for all Spotify users.

    Fetches and stores recently played tracks for each authenticated user.
    """
    # Retrieve all Spotify users
    users = await fetch_spotify_users()
    if not users:
        self.stdout.write(self.style.ERROR("No Spotify users found."))
        return

    for user in users:
        spotify_user_id = user.spotify_user_id
        tokens = get_user_tokens(spotify_user_id)
        if not tokens:
            self.stdout.write(
                self.style.ERROR(f"User {spotify_user_id} not authenticated.")
            )
            continue

        # Get timestamp of latest track to fetch only newer tracks
        after_timestamp = get_latest_track_timestamp(spotify_user_id)

        if after_timestamp is None:
            after_timestamp = 0

        try:
            # Fetch and save tracks
            tracks = await fetch_recently_played_tracks(
                spotify_user_id, after_timestamp
            )
            await save_played_tracks(spotify_user_id, tracks)
            self.stdout.write(
                self.style.SUCCESS(
                    f"Fetched and stored {len(tracks)} tracks for user {spotify_user_id}."
                )
            )
        except Exception as e:
            logger.error(f"Error fetching history for user {spotify_user_id}: {e}")
            self.stdout.write(
                self.style.ERROR(
                    f"Error fetching history for user {spotify_user_id}: {e}"
                )
            )


@sync_to_async
def save_tracks_atomic(
    user,
    track_info_list: list[dict[str, Any]],
    track_details_dict: dict[str, dict],
    artist_details_dict: dict[str, dict],
) -> int:
    """
    Save multiple tracks atomically in a single transaction.

    Args:
        user: The SpotifyUser object
        track_info_list: List of track information dictionaries
        track_details_dict: Dictionary of track details indexed by track ID
        artist_details_dict: Dictionary of artist details indexed by artist ID

    Returns:
        Number of new tracks added
    """
    count = 0
    with transaction.atomic():
        for info in track_info_list:
            track_data = get_track_details(
                info, track_details_dict, artist_details_dict
            )

            # Skip if track already exists
            if track_exists(user, track_data["track_id"], track_data["played_at"]):
                logger.info(
                    f"Duplicate track found: {track_data['track_id']} at {track_data['played_at']}. Skipping."
                )
                continue

            # Create the track and increment counter if successful
            if create_played_track(user, track_data):
                count += 1

    return count


def get_listening_stats(
    user,
    time_range: str = "all_time",
    start_date: str | None = None,
    end_date: str | None = None,
) -> dict[str, Any]:
    """
    Get comprehensive listening statistics for a user.

    Args:
        user: The SpotifyUser object
        time_range: The time range to analyze
        start_date: Start date for custom range (YYYY-MM-DD)
        end_date: End date for custom range (YYYY-MM-DD)

    Returns:
        Dictionary with comprehensive listening statistics
    """
    stats = {}

    # Set time range parameters
    since, until, truncate_func, x_label = set_time_range_parameters(
        time_range, start_date, end_date
    )

    # Filter tracks based on time range
    tracks = PlayedTrack.objects.filter(user=user)
    if since:
        tracks = tracks.filter(played_at__gte=since)
    if until:
        tracks = tracks.filter(played_at__lt=until)

    # Add debug logging
    logger.debug(f"Total tracks found: {tracks.count()}")

    # Calculate aggregate statistics
    stats_aggregate = calculate_aggregate_statistics(tracks)

    # Calculate additional statistics
    stats_aggregate.update(
        {
            "most_played_genre": calculate_most_played_genre(tracks),
            "top_listening_hour": calculate_top_listening_hour(tracks),
            "most_popular_day": calculate_most_popular_day(tracks),
        }
    )

    # Calculate derived statistics
    stats_aggregate["days_streamed"] = calculate_days_streamed(stats_aggregate)
    stats_aggregate["average_listening_time_per_day"] = (
        calculate_average_listening_time_per_day(stats_aggregate)
    )

    logger.debug(f"Stats aggregate: {stats_aggregate}")

    # Aggregate counts based on the truncate function with proper grouping
    date_counts = (
        tracks.annotate(period=truncate_func)
        .values("period")
        .annotate(count=Count("stream_id"))
        .order_by("period")
    )

    logger.debug(f"Date counts query: {date_counts.query}")
    logger.debug(f"Date counts: {list(date_counts)}")

    # Create a dictionary from date_counts for quick lookup
    count_dict = {item["period"]: item["count"] for item in date_counts}

    # Generate all periods within the range
    if since and until:
        all_periods = generate_all_periods(since, until, truncate_func)
    else:
        all_periods = []

    # Populate dates and counts arrays for chart visualization
    dates, counts = populate_dates_and_counts(all_periods, count_dict, truncate_func)

    # Compile all statistics
    stats.update(
        {
            "dates": dates,
            "counts": counts,
            "x_label": x_label,
            **{
                k: stats_aggregate[k]
                for k in (
                    "total_tracks",
                    "total_minutes_streamed",
                    "different_tracks",
                    "different_artists",
                    "different_albums",
                    "days_streamed",
                    "average_listening_time_per_day",
                    "most_played_genre",
                    "top_listening_hour",
                    "most_popular_day",
                )
            },
        }
    )

    logger.debug(f"Final stats: {stats}")

    return stats


async def get_top_tracks(
    user,
    since: datetime | None = None,
    until: datetime | None = None,
    limit: int = 10,
) -> list[dict[str, Any]]:
    """
    Get top tracks for a user in a given time period.

    Args:
        user: The SpotifyUser object
        since: Start datetime for filtering
        until: End datetime for filtering
        limit: Number of tracks to return

    Returns:
        List of dictionaries with top track information
    """

    @sync_to_async
    def get_tracks() -> list[dict[str, Any]]:
        """Get top tracks from the database."""
        tracks_query = PlayedTrack.objects.filter(user=user)
        if since:
            tracks_query = tracks_query.filter(played_at__gte=since)
        if until:
            tracks_query = tracks_query.filter(played_at__lt=until)

        return list(
            tracks_query.values(
                "track_id", "track_name", "artist_name", "album_id", "artist_id"
            )
            .annotate(
                play_count=Count("stream_id"),
                total_minutes=Sum("duration_ms") / 60000.0,
            )
            .order_by("-total_minutes")[:limit]
        )

    top_tracks = await get_tracks()

    if not top_tracks:
        logger.info(f"No top tracks found for user {user.spotify_user_id}.")
        return top_tracks

    # Enrich tracks with album images
    try:
        async with SpotifyClient(user.spotify_user_id) as client:
            for track in top_tracks:
                # Try to get album image from cache first
                cache_key = f"album_image_{track['album_id']}"
                album_image = cache.get(cache_key)

                if album_image is None:
                    # Fetch album details if not in cache
                    album = await client.get_album(track["album_id"])
                    album_image = (
                        album.get("images", [{}])[0].get("url") if album else None
                    )
                    if album_image:
                        cache.set(cache_key, album_image, timeout=client.CACHE_TIMEOUT)

                track["album_image"] = album_image
    except Exception as e:
        logger.error(f"Error fetching album details: {e}")

    return top_tracks


async def get_top_artists(
    user,
    since: datetime | None = None,
    until: datetime | None = None,
    limit: int = 10,
) -> list[dict[str, Any]]:
    """
    Get top artists for a user in a given time period.

    Args:
        user: The SpotifyUser object
        since: Start datetime for filtering
        until: End datetime for filtering
        limit: Number of artists to return

    Returns:
        List of dictionaries with top artist information
    """

    @sync_to_async
    def get_artists() -> list[dict[str, Any]]:
        """Get top artists from the database."""
        tracks_query = PlayedTrack.objects.filter(user=user)
        if since:
            tracks_query = tracks_query.filter(played_at__gte=since)
        if until:
            tracks_query = tracks_query.filter(played_at__lt=until)

        return list(
            tracks_query.values("artist_name", "artist_id")
            .annotate(
                play_count=Count("stream_id"),
                total_minutes=Sum("duration_ms") / 60000.0,
            )
            .order_by("-total_minutes")[:limit]
        )

    top_artists = await get_artists()

    if not top_artists:
        logger.info(f"No top artists found for user {user.spotify_user_id}.")
        return top_artists

    # Enrich artists with details and images
    try:
        async with SpotifyClient(user.spotify_user_id) as client:
            for artist in top_artists:
                # Try to get artist details from cache first
                cache_key = f"artist_details_{artist['artist_id']}"
                artist_details = cache.get(cache_key)

                if artist_details is None:
                    # Fetch artist details if not in cache
                    artist_details = await client.get_artist(artist["artist_id"])
                    if artist_details:
                        cache.set(
                            cache_key, artist_details, timeout=client.CACHE_TIMEOUT
                        )

                # Add image and name properties
                artist["image"] = (
                    artist_details.get("images", []) if artist_details else []
                )
                artist["name"] = artist["artist_name"]
    except Exception as e:
        logger.error(f"Error fetching artist details: {e}")

    return top_artists


async def get_recently_played(
    user,
    since: datetime | None = None,
    until: datetime | None = None,
    limit: int = 10,
) -> list[dict[str, Any]]:
    """
    Get recently played tracks for a user in a given time period.

    Args:
        user: The SpotifyUser object
        since: Start datetime for filtering
        until: End datetime for filtering
        limit: Number of tracks to return

    Returns:
        List of dictionaries with recently played track information
    """

    @sync_to_async
    def get_tracks() -> list[dict[str, Any]]:
        """Get recently played tracks from the database."""
        tracks = PlayedTrack.objects.filter(user=user)
        if since:
            tracks = tracks.filter(played_at__gte=since)
        if until:
            tracks = tracks.filter(played_at__lt=until)

        return list(
            tracks.order_by("-played_at").values(
                "track_id",
                "track_name",
                "artist_name",
                "artist_id",
                "album_name",
                "album_id",
                "played_at",
            )[:limit]
        )

    recently_played = await get_tracks()

    if not recently_played:
        logger.info(f"No recently played tracks found for user {user.spotify_user_id}.")
        return recently_played

    # Enrich tracks with album images
    try:
        async with SpotifyClient(user.spotify_user_id) as client:
            for track in recently_played:
                # Try to get album image from cache first
                cache_key = f"album_image_{track['album_id']}"
                album_image = cache.get(cache_key)

                if album_image is None:
                    # Fetch album details if not in cache
                    album = await client.get_album(track["album_id"])
                    album_image = (
                        album.get("images", [{}])[0].get("url") if album else None
                    )
                    if album_image:
                        cache.set(cache_key, album_image, timeout=client.CACHE_TIMEOUT)

                track["album_image"] = album_image
    except Exception as e:
        logger.error(f"Error fetching album details: {e}")

    return recently_played


async def get_top_genres(
    user,
    since: datetime | None = None,
    until: datetime | None = None,
    limit: int = 10,
) -> list[dict[str, Any]]:
    """
    Get top genres for a user in a given time period.

    Args:
        user: The SpotifyUser object
        since: Start datetime for filtering
        until: End datetime for filtering
        limit: Number of genres to return

    Returns:
        List of dictionaries with top genre information
    """

    @sync_to_async
    def get_genres() -> list[str]:
        """Get all genres from the database."""
        tracks_query = PlayedTrack.objects.filter(user=user)
        if since:
            tracks_query = tracks_query.filter(played_at__gte=since)
        if until:
            tracks_query = tracks_query.filter(played_at__lt=until)

        # Flatten genres from all tracks
        genre_counts = tracks_query.values_list("genres", flat=True)
        all_genres = []
        for genres_list in genre_counts:
            if genres_list:
                all_genres.extend(genres_list)

        return all_genres

    all_genres = await get_genres()

    if not all_genres:
        logger.info(f"No genres found for user {user.spotify_user_id}.")
        return []

    # Count genres and return top ones
    genre_counter = Counter(all_genres)
    top_genres = [
        {"genre": genre, "count": count}
        for genre, count in genre_counter.most_common(limit)
    ]

    return top_genres


async def get_top_albums(
    user,
    since: datetime | None = None,
    until: datetime | None = None,
    limit: int = 10,
) -> list[dict[str, Any]]:
    """
    Get top albums for a user in a given time period.

    Args:
        user: The SpotifyUser object
        since: Start datetime for filtering
        until: End datetime for filtering
        limit: Number of albums to return

    Returns:
        List of dictionaries with top album information
    """

    @sync_to_async
    def get_albums() -> list[dict[str, Any]]:
        """Get top albums from the database."""
        tracks_query = PlayedTrack.objects.filter(user=user)
        if since:
            tracks_query = tracks_query.filter(played_at__gte=since)
        if until:
            tracks_query = tracks_query.filter(played_at__lt=until)

        return list(
            tracks_query.values("album_name", "album_id", "artist_name", "artist_id")
            .annotate(
                play_count=Count("stream_id"),
                total_minutes=Sum("duration_ms") / 60000.0,
            )
            .order_by("-total_minutes")[:limit]
        )

    top_albums = await get_albums()

    if not top_albums:
        logger.info(f"No top albums found for user {user.spotify_user_id}.")
        return top_albums

    # Enrich albums with details and images
    try:
        async with SpotifyClient(user.spotify_user_id) as client:
            for album in top_albums:
                # Try to get album details from cache first
                cache_key = f"album_details_{album['album_id']}"
                album_details = cache.get(cache_key)

                if album_details is None:
                    # Fetch album details if not in cache
                    album_details = await client.get_album(album["album_id"])
                    if album_details:
                        cache.set(
                            cache_key, album_details, timeout=client.CACHE_TIMEOUT
                        )

                # Add additional album information
                if album_details:
                    album["image"] = album_details.get("images", [])
                    album["release_date"] = album_details.get("release_date")
                    album["total_tracks"] = album_details.get("total_tracks")
    except Exception as e:
        logger.error(f"Error fetching album details: {e}")

    return top_albums


async def get_streaming_trend_data(
    user,
    since: datetime,
    until: datetime,
    items: list[dict[str, Any]] | dict[str, Any],
    item_type: str,
    limit: int = 5,
) -> tuple[list[str], list[dict[str, Any]]]:
    """
    Get streaming trend data for visualization of top items.

    Args:
        user: The SpotifyUser object
        since: Start datetime for filtering
        until: End datetime for filtering
        items: List of items or single item to analyze
        item_type: Type of item ('artist', 'genre', 'track', 'album')
        limit: Maximum number of items to include

    Returns:
        Tuple of (display_dates, trend_data) for chart visualization
    """
    # Predefined colors for chart lines
    colors = ["#1DB954", "#FF6B6B", "#4A90E2", "#F7B731", "#A463F2"]

    # Determine appropriate aggregation level based on time range
    total_duration = (until - since).days if since and until else None

    if total_duration is not None:
        truncate_func, date_format, chart_format = determine_truncate_func_and_formats(
            total_duration
        )
    else:
        # Handle the case where total_duration is None
        truncate_func = TruncMonth("played_at")
        date_format = "%b %Y"
        chart_format = "%Y-%m-%d"

    # Generate all periods in the time range
    all_periods = generate_all_periods(since, until, truncate_func)

    # Ensure items is a list
    if not isinstance(items, list):
        items = [items]

    # Process each item to get trend data
    trend_data = []
    for idx, item in enumerate(items[:limit]):
        # Get the raw data with only dates that have plays
        raw_dates, raw_counts, _, label = await get_trend_data(
            user,
            item,
            item_type,
            since,
            until,
            truncate_func,
            date_format,
            chart_format,
        )

        # Convert to a dictionary for quick lookup
        count_dict: dict[datetime | str, int] = {
            entry[0]: entry[2]
            for entry in zip(raw_dates, [0] * len(raw_dates), raw_counts)
        }

        # Ensure all dates in the range are included with zeros for no plays
        display_dates, normalized_counts = populate_dates_and_counts(
            all_periods, count_dict, truncate_func
        )

        # Build the trend data entry
        trend_data.append(
            {
                "label": label
                or item.get("genre")
                or item.get("track_name")
                or item.get("album_name"),
                "data": normalized_counts,
                "color": colors[idx % len(colors)],
            }
        )

    # Get common date labels for all trends
    display_dates = [
        (
            period.strftime("%Y-%m-%d %H:%M")
            if isinstance(truncate_func, TruncHour)
            else period.strftime("%Y-%m-%d")
        )
        for period in all_periods
    ]

    return display_dates, trend_data


def format_day_suffix(day: int) -> str:
    """
    Generate the correct ordinal suffix for a day number.

    Args:
        day: Day number (1-31)

    Returns:
        Appropriate suffix ('st', 'nd', 'rd', or 'th')
    """
    if 4 <= day <= 20 or 24 <= day <= 30:
        return "th"
    return ["st", "nd", "rd"][day % 10 - 1]


def format_date(date: datetime) -> str:
    """
    Format a date with proper ordinal suffix.

    Args:
        date: Datetime object

    Returns:
        Formatted date string (e.g., "Monday 1st January 2023")
    """
    suffix = format_day_suffix(date.day)
    return date.strftime(f"%A {date.day}{suffix} %B %Y")


def get_longest_streak(
    user, start_date: datetime, end_date: datetime
) -> tuple[int, str | None, str | None]:
    """
    Calculate the longest streak of consecutive days with music listening.

    Args:
        user: The SpotifyUser object
        start_date: Start date for analysis
        end_date: End date for analysis

    Returns:
        Tuple of (streak_length, formatted_start_date, formatted_end_date)
    """
    # Get all distinct days with played tracks
    played_tracks = (
        PlayedTrack.objects.filter(
            user=user, played_at__gte=start_date, played_at__lte=end_date
        )
        .annotate(played_day=TruncDate("played_at"))
        .values("played_day")
        .distinct()
        .order_by("played_day")
    )

    if not played_tracks:
        return 0, None, None

    # Initialize variables for streak calculation
    longest_streak = 1
    current_streak = 1
    current_streak_start = played_tracks[0]["played_day"]
    longest_streak_start = current_streak_start
    longest_streak_end = current_streak_start
    previous_date = played_tracks[0]["played_day"]

    # Calculate streaks by analyzing consecutive days
    for i in range(1, len(played_tracks)):
        current_date = played_tracks[i]["played_day"]

        # Check if the current date is consecutive to the previous one
        if current_date == previous_date + timedelta(days=1):
            current_streak += 1
        else:
            # Reset streak counter if days are not consecutive
            current_streak = 1
            current_streak_start = current_date

        # Update longest streak if current streak is longer
        if current_streak > longest_streak:
            longest_streak = current_streak
            longest_streak_start = current_streak_start
            longest_streak_end = current_date

        previous_date = current_date

    # Format dates for display
    longest_streak_start_formatted = format_date(longest_streak_start)
    longest_streak_end_formatted = format_date(longest_streak_end)

    return longest_streak, longest_streak_start_formatted, longest_streak_end_formatted


async def get_dashboard_stats(user, since: datetime, until: datetime) -> dict[str, Any]:
    """
    Get comprehensive dashboard statistics for a user.

    Args:
        user: The SpotifyUser object
        since: Start datetime for filtering
        until: End datetime for filtering

    Returns:
        Dictionary with dashboard statistics
    """

    @sync_to_async
    def get_data() -> dict[str, Any]:
        """Get dashboard statistics from the database."""
        # Base query for filtered tracks
        base_query = PlayedTrack.objects.filter(user=user)
        if since:
            base_query = base_query.filter(played_at__gte=since)
        if until:
            base_query = base_query.filter(played_at__lte=until)

        # Calculate time period coverage
        total_days = (until - since).days + 1
        days_with_music = base_query.dates("played_at", "day").count()
        coverage_percentage = (
            (days_with_music / total_days * 100) if total_days > 0 else 0
        )

        # Get distinct dates for further analysis
        dates = list(
            base_query.dates("played_at", "day").order_by("played_at").distinct()
        )

        # Return empty stats if no data
        if not dates:
            return {
                "days_with_music": 0,
                "total_days": total_days,
                "coverage_percentage": 0,
                "streak_days": 0,
                "streak_start": None,
                "streak_end": None,
                "top_artist_name": "No artist",
                "top_artist_percentage": 0,
                "repeat_percentage": 0,
            }

        # Calculate longest listening streak
        streak, streak_start, streak_end = get_longest_streak(user, since, until)

        # Get top artist and their percentage of total plays
        artist_counts = (
            base_query.values("artist_name")
            .annotate(count=Count("stream_id"))
            .order_by("-count")
        )
        total_plays = base_query.count()
        top_artist = artist_counts.first()
        top_artist_name = top_artist["artist_name"] if top_artist else "No artist"
        top_artist_percentage = (
            (top_artist["count"] / total_plays * 100)
            if top_artist and total_plays > 0
            else 0
        )

        # Calculate repeat listening percentage
        total_tracks = base_query.values("track_id").distinct().count()
        repeat_tracks = (
            base_query.values("track_id")
            .annotate(play_count=Count("stream_id"))
            .filter(play_count__gt=1)
            .count()
        )
        repeat_percentage = (
            (repeat_tracks / total_tracks * 100) if total_tracks > 0 else 0
        )

        return {
            "days_with_music": days_with_music,
            "total_days": total_days,
            "coverage_percentage": coverage_percentage,
            "streak_days": streak,
            "streak_start": streak_start,
            "streak_end": streak_end,
            "top_artist_name": top_artist_name,
            "top_artist_percentage": top_artist_percentage,
            "repeat_percentage": repeat_percentage,
        }

    return await get_data()


async def get_stats_boxes_data(
    user, since: datetime, until: datetime, items: list[dict[str, Any]], item_type: str
) -> dict[str, Any]:
    """
    Get statistics box data that works across all item types.

    Args:
        user: The SpotifyUser object
        since: Start datetime for filtering
        until: End datetime for filtering
        items: List of items to analyze
        item_type: Type of item ('artist', 'genre', 'track', 'album')

    Returns:
        Dictionary with statistics for the stats boxes
    """

    @sync_to_async
    def get_data() -> dict[str, Any]:
        """Get statistics box data from the database."""
        # Base query for filtered tracks
        base_query = PlayedTrack.objects.filter(user=user)
        if since:
            base_query = base_query.filter(played_at__gte=since)
        if until:
            base_query = base_query.filter(played_at__lte=until)

        # Count total plays across all items
        total_all_plays = base_query.count()

        # Calculate total unique items based on item type
        if item_type == "artist":
            total_items = base_query.values("artist_name").distinct().count()
        elif item_type == "genre":
            # For genres, we need to extract unique genres from genre lists
            genres = base_query.values_list("genres", flat=True)
            unique_genres = set()
            for genre_list in genres:
                if genre_list:
                    unique_genres.update(genre_list)
            total_items = len(unique_genres)
        elif item_type == "track":
            total_items = base_query.values("track_id").distinct().count()
        elif item_type == "album":
            total_items = base_query.values("album_id").distinct().count()
        else:
            total_items = 0

        # Calculate statistics for top 3 items
        total_plays = 0
        total_minutes: float = 0
        days_with_plays = set()

        for item in items[:3]:
            # Filter query based on item type
            if item_type == "artist":
                query = base_query.filter(artist_name=item["artist_name"])
            elif item_type == "genre":
                query = base_query.filter(genres__contains=[item["genre"]])
            elif item_type == "track":
                query = base_query.filter(track_id=item["track_id"])
            elif item_type == "album":
                query = base_query.filter(album_id=item["album_id"])
            else:
                continue

            # Accumulate statistics
            plays = query.count()
            total_plays += plays

            minutes = (
                query.aggregate(total_time=Sum("duration_ms"))["total_time"] or 0
            ) / 60000
            total_minutes += minutes

            days_with_plays.update(query.dates("played_at", "day"))

        # Calculate percentages
        total_days = (until - since).days + 1
        coverage_percentage = (
            (len(days_with_plays) / total_days) * 100 if total_days > 0 else 0
        )
        play_percentage = (
            (total_plays / total_all_plays * 100) if total_all_plays > 0 else 0
        )

        return {
            "total_items": total_items,
            "top_3_plays": play_percentage,
            "top_3_minutes": total_minutes,
            "coverage_percentage": coverage_percentage,
        }

    return await get_data()


async def get_radar_chart_data(
    user,
    since: datetime | None,
    until: datetime | None,
    items: dict[str, Any] | list[dict[str, Any]],
    item_type: str,
    limit: int = 5,
) -> list[dict[str, Any]]:
    """
    Get radar chart data for top items.

    Args:
        user: The SpotifyUser object
        since: Start datetime for filtering
        until: End datetime for filtering
        items: Single item or list of items to analyze
        item_type: Type of item ('artist', 'genre', 'track', 'album')
        limit: Maximum number of items to include

    Returns:
        List of radar chart data dictionaries for visualization
    """
    # Define chart colors
    colors = [
        "rgba(29, 185, 84, 0.2)",
        "rgba(255, 107, 107, 0.2)",
        "rgba(74, 144, 226, 0.2)",
        "rgba(247, 183, 49, 0.2)",
        "rgba(164, 99, 242, 0.2)",
    ]
    border_colors = ["#1DB954", "#FF6B6B", "#4A90E2", "#F7B731", "#A463F2"]

    # Ensure items is a list
    if not isinstance(items, list):
        items = [items]

    @sync_to_async
    def calculate_metrics(item: dict[str, Any]) -> dict[str, Any]:
        """Calculate metrics for a single item."""
        # Set up base query with timeframe filtering
        base_query = PlayedTrack.objects.filter(user=user)
        if since:
            base_query = base_query.filter(played_at__gte=since)
        if until:
            base_query = base_query.filter(played_at__lt=until)

        # Filter query based on item type
        if item_type == "artist":
            query = base_query.filter(artist_name=item["artist_name"])
            label = item["artist_name"]
        elif item_type == "genre":
            query = base_query.filter(genres__contains=[item["genre"]])
            label = item["genre"]
        elif item_type == "track":
            query = base_query.filter(track_id=item["track_id"])
            label = item["track_name"]
        elif item_type == "album":
            query = base_query.filter(album_id=item["album_id"])
            label = item["album_name"]
        else:
            return {
                "label": "Unknown",
                "total_plays": 0,
                "total_time": 0,
                "unique_tracks": 0,
                "variety": 0,
                "average_popularity": 0,
            }

        # Calculate metrics
        total_plays = query.count()
        total_time = query.aggregate(total_time=Sum("duration_ms"))["total_time"] or 0
        unique_tracks = query.values("track_id").distinct().count()
        variety = query.values("genres").distinct().count()
        average_popularity = (
            query.aggregate(avg_popularity=Avg("popularity"))["avg_popularity"] or 0
        )

        return {
            "label": label,
            "total_plays": total_plays,
            "total_time": total_time / 60000,  # Convert to minutes
            "unique_tracks": unique_tracks,
            "variety": variety,
            "average_popularity": average_popularity,
        }

    # Gather metrics for all items
    metrics_list = []
    for idx, item in enumerate(items[:limit]):
        metrics = await calculate_metrics(item)
        # Add color information
        metrics["backgroundColor"] = colors[idx % len(colors)]
        metrics["borderColor"] = border_colors[idx % len(border_colors)]
        metrics_list.append(metrics)

    # Calculate maximum values for normalization
    max_values = {
        "total_plays": max((m["total_plays"] for m in metrics_list), default=1),
        "total_time": max((m["total_time"] for m in metrics_list), default=1),
        "unique_tracks": max((m["unique_tracks"] for m in metrics_list), default=1),
        "variety": max((m["variety"] for m in metrics_list), default=1),
        "average_popularity": max(
            (m["average_popularity"] for m in metrics_list), default=1
        ),
    }

    # Normalize metrics to percentages
    radar_data = []
    for metrics in metrics_list:
        normalized_metrics = {
            "label": metrics["label"],
            "backgroundColor": metrics["backgroundColor"],
            "borderColor": metrics["borderColor"],
            "total_plays": (metrics["total_plays"] / max_values["total_plays"]) * 100,
            "total_time": (metrics["total_time"] / max_values["total_time"]) * 100,
            "unique_tracks": (metrics["unique_tracks"] / max_values["unique_tracks"])
            * 100,
            "variety": (metrics["variety"] / max_values["variety"]) * 100,
            "average_popularity": (
                metrics["average_popularity"] / max_values["average_popularity"]
            )
            * 100,
        }
        radar_data.append(normalized_metrics)

    return radar_data


async def get_doughnut_chart_data(
    user,
    since: datetime | None,
    until: datetime | None,
    items: dict[str, Any] | list[dict[str, Any]],
    item_type: str,
) -> tuple[list[str], list[float], list[str]]:
    """
    Get doughnut chart data for visualizing listening distribution.

    Args:
        user: The SpotifyUser object
        since: Start datetime for filtering
        until: End datetime for filtering
        items: Single item or list of items to analyze
        item_type: Type of item ('artist', 'genre', 'track', 'album')

    Returns:
        Tuple of (labels, values, background_colors) for chart visualization
    """
    # Define chart colors
    colors = [
        "#FF6384",
        "#36A2EB",
        "#FFCE56",
        "#4BC0C0",
        "#9966FF",
    ]

    # Ensure items is a list
    if not isinstance(items, list):
        items = [items]

    @sync_to_async
    def calculate_total_minutes(item: dict[str, Any]) -> dict[str, Any]:
        """Calculate total minutes listened for a single item."""
        # Set up base query with timeframe filtering
        base_query = PlayedTrack.objects.filter(user=user)
        if since:
            base_query = base_query.filter(played_at__gte=since)
        if until:
            base_query = base_query.filter(played_at__lt=until)

        # Filter query based on item type
        if item_type == "artist":
            query = base_query.filter(artist_name=item["artist_name"])
            label = item["artist_name"]
        elif item_type == "genre":
            query = base_query.filter(genres__contains=[item["genre"]])
            label = item["genre"]
        elif item_type == "track":
            query = base_query.filter(track_id=item["track_id"])
            label = item["track_name"]
        elif item_type == "album":
            query = base_query.filter(album_id=item["album_id"])
            label = item["album_name"]
        else:
            return {"label": "Unknown", "total_minutes": 0}

        # Calculate total listening time
        total_minutes = (
            query.aggregate(total_time=Sum("duration_ms"))["total_time"] or 0
        ) / 60000

        # Truncate long labels
        if len(label) > 25:
            label = f"{label[:22]}..."

        return {
            "label": label,
            "total_minutes": total_minutes,
        }

    @sync_to_async
    def calculate_total_listening_time() -> float:
        """Calculate total listening time across all items."""
        base_query = PlayedTrack.objects.filter(user=user)
        if since:
            base_query = base_query.filter(played_at__gte=since)
        if until:
            base_query = base_query.filter(played_at__lt=until)

        total_minutes = (
            base_query.aggregate(total_time=Sum("duration_ms"))["total_time"] or 0
        ) / 60000
        return total_minutes

    # Get total listening time for percentage calculations
    total_listening_time = await calculate_total_listening_time()

    # Gather data for each item
    doughnut_data = []
    for item in items:
        metrics = await calculate_total_minutes(item)
        doughnut_data.append(metrics)

    # Calculate percentages
    for data in doughnut_data:
        data["percentage"] = (
            (data["total_minutes"] / total_listening_time * 100)
            if total_listening_time > 0
            else 0
        )

    # Extract data for chart
    labels = [data["label"] for data in doughnut_data]
    values = [data["percentage"] for data in doughnut_data]
    background_colors = [colors[idx % len(colors)] for idx in range(len(doughnut_data))]

    return labels, values, background_colors


async def get_hourly_listening_data(
    user,
    since: datetime | None,
    until: datetime | None,
    item_type: str,
    item: dict[str, Any] | None = None,
) -> list[float]:
    """
    Get hourly listening data for visualization.

    Args:
        user: The SpotifyUser object
        since: Start datetime for filtering
        until: End datetime for filtering
        item_type: Type of item ('artist', 'genre', 'track', 'album')
        item: Optional specific item to analyze

    Returns:
        List of minutes listened for each hour (0-23)
    """

    @sync_to_async
    def get_data() -> list[float]:
        """Get hourly listening data from the database."""
        # Set up base query with timeframe filtering
        base_query = PlayedTrack.objects.filter(user=user)
        if since:
            base_query = base_query.filter(played_at__gte=since)
        if until:
            base_query = base_query.filter(played_at__lt=until)

        # Filter by specific item if provided
        if item:
            if item_type == "artist":
                base_query = base_query.filter(artist_name=item["artist_name"])
            elif item_type == "genre":
                base_query = base_query.filter(genres__contains=[item["genre"]])
            elif item_type == "track":
                base_query = base_query.filter(track_id=item["track_id"])
            elif item_type == "album":
                base_query = base_query.filter(album_id=item["album_id"])

        # Get minutes listened by hour
        hourly_data = (
            base_query.annotate(hour=ExtractHour("played_at"))
            .values("hour")
            .annotate(total_minutes=Sum("duration_ms") / 60000.0)
            .order_by("hour")
        )

        # Create a map of hour to minutes
        minutes_by_hour = {
            entry["hour"]: entry["total_minutes"] for entry in hourly_data
        }

        # Return data for all 24 hours, filling in zeros for hours with no plays
        return [minutes_by_hour.get(hour, 0) for hour in range(24)]

    return await get_data()


async def get_bubble_chart_data(
    user,
    since: datetime | None,
    until: datetime | None,
    items: dict[str, Any] | list[dict[str, Any]],
    item_type: str,
) -> list[dict[str, Any]]:
    """
    Get bubble chart data showing play patterns.

    Args:
        user: The SpotifyUser object
        since: Start datetime for filtering
        until: End datetime for filtering
        items: Single item or list of items to analyze
        item_type: Type of item ('artist', 'genre', 'track', 'album')

    Returns:
        List of data points for bubble chart visualization
    """
    # Ensure items is a list
    if not isinstance(items, list):
        items = [items]

    @sync_to_async
    def get_data() -> list[dict[str, Any]]:
        """Get bubble chart data from the database."""
        # Set up base query with timeframe filtering
        base_query = PlayedTrack.objects.filter(user=user)
        if since:
            base_query = base_query.filter(played_at__gte=since)
        if until:
            base_query = base_query.filter(played_at__lt=until)

        data_points = []

        # Process each item
        for item in items:
            # Filter query based on item type
            if item_type == "artist":
                query = base_query.filter(artist_name=item["artist_name"])
                name = item["artist_name"]
            elif item_type == "genre":
                query = base_query.filter(genres__contains=[item["genre"]])
                name = item["genre"]
            elif item_type == "track":
                query = base_query.filter(track_id=item["track_id"])
                name = item["track_name"]
            elif item_type == "album":
                query = base_query.filter(album_id=item["album_id"])
                name = item["album_name"]
            else:
                continue

            # Calculate metrics for the bubble chart
            play_count = query.count()
            avg_popularity = query.aggregate(Avg("popularity"))["popularity__avg"] or 0
            total_minutes = (
                query.aggregate(total_time=Sum("duration_ms"))["total_time"] or 0
            ) / 60000

            # Only add data points for items with plays
            if play_count > 0:
                data_points.append(
                    {
                        "x": avg_popularity,  # X-axis: popularity
                        "y": total_minutes,  # Y-axis: listening time
                        "r": play_count * 2,  # Bubble radius: play count
                        "name": name,  # Label: item name
                    }
                )

        return data_points

    return await get_data()


async def get_discovery_timeline_data(
    user, since: datetime | None, until: datetime | None, item_type: str
) -> tuple[list[str], list[int]]:
    """
    Get cumulative discovery data showing when new items were first encountered.

    Args:
        user: The SpotifyUser object
        since: Start datetime for filtering
        until: End datetime for filtering
        item_type: Type of item to track ('artist', 'track', 'album', 'genre')

    Returns:
        Tuple of (dates, counts) for timeline visualization
    """
    # Determine appropriate date format based on time range
    total_duration = (until - since).days if since and until else None

    if total_duration:
        if total_duration <= 7:
            truncate_func = TruncDay("played_at")
            date_format = "%m-%d"
        elif total_duration <= 28:
            truncate_func = TruncDay("played_at")
            date_format = "%b %d"
        elif total_duration <= 182:
            truncate_func = TruncWeek("played_at")
            date_format = "%b %d"
        else:
            truncate_func = TruncMonth("played_at")
            date_format = "%b %Y"
    else:
        truncate_func = TruncMonth("played_at")
        date_format = "%b %Y"

    @sync_to_async
    def get_data() -> tuple[list[str], list[int]]:
        """Get discovery timeline data from the database."""
        # Set up base query with timeframe filtering
        base_query = PlayedTrack.objects.filter(user=user)
        if since:
            base_query = base_query.filter(played_at__gte=since)
        if until:
            base_query = base_query.filter(played_at__lte=until)

        # Get all distinct periods in the range
        periods = (
            base_query.annotate(period=truncate_func)
            .values("period")
            .distinct()
            .order_by("period")
        )

        dates = []
        counts = []

        # For each period, count unique items discovered up to that point
        for period_data in periods:
            period = period_data["period"]

            # Get unique items up to this period based on item type
            if item_type == "artist":
                items = (
                    base_query.filter(played_at__lte=period)
                    .values("artist_name")
                    .distinct()
                )
                current_items = {item["artist_name"] for item in items}
            elif item_type == "track":
                items = (
                    base_query.filter(played_at__lte=period)
                    .values("track_id")
                    .distinct()
                )
                current_items = {item["track_id"] for item in items}
            elif item_type == "album":
                items = (
                    base_query.filter(played_at__lte=period)
                    .values("album_id")
                    .distinct()
                )
                current_items = {item["album_id"] for item in items}
            elif item_type == "genre":
                # For genres, we need to collect all unique genres from all tracks
                items = base_query.filter(played_at__lte=period).exclude(genres=[])
                current_items = set()
                for item in items:
                    if item.genres:
                        current_items.update(item.genres)
            else:
                current_items = set()

            # Add data point if we have items
            if current_items:
                dates.append(period.strftime(date_format))
                counts.append(len(current_items))

        return dates, counts

    return await get_data()


async def get_time_period_distribution(
    user,
    since: datetime | None,
    until: datetime | None,
    items: dict[str, Any] | list[dict[str, Any]],
    item_type: str,
) -> tuple[list[str], list[dict[str, Any]]]:
    """
    Get listening distribution across different time periods of the day.

    Args:
        user: The SpotifyUser object
        since: Start datetime for filtering
        until: End datetime for filtering
        items: Single item or list of items to analyze
        item_type: Type of item ('artist', 'genre', 'track', 'album')

    Returns:
        Tuple of (period_names, datasets) for chart visualization
    """
    # Ensure items is a list
    if not isinstance(items, list):
        items = [items]

    @sync_to_async
    def get_data() -> tuple[list[str], list[dict[str, Any]]]:
        """Get time period distribution data from the database."""
        # Set up base query with timeframe filtering
        base_query = PlayedTrack.objects.filter(user=user)
        if since:
            base_query = base_query.filter(played_at__gte=since)
        if until:
            base_query = base_query.filter(played_at__lt=until)

        # Define time periods
        periods = {
            "Morning (6-12)": (6, 12),
            "Afternoon (12-18)": (12, 18),
            "Evening (18-24)": (18, 24),
            "Night (0-6)": (0, 6),
        }

        datasets: list[dict[str, Any]] = []

        # Process up to 5 items
        for item in items[:5]:
            period_data = []

            # Filter query based on item type
            if item_type == "artist":
                item_query = base_query.filter(artist_name=item["artist_name"])
                label = item["artist_name"]
            elif item_type == "genre":
                item_query = base_query.filter(genres__contains=[item["genre"]])
                label = item["genre"]
            elif item_type == "track":
                item_query = base_query.filter(track_id=item["track_id"])
                label = item["track_name"]
            elif item_type == "album":
                item_query = base_query.filter(album_id=item["album_id"])
                label = item["album_name"]
            else:
                continue

            # Count plays in each time period
            for period_name, (start_hour, end_hour) in periods.items():
                # Handle periods that span midnight
                if start_hour < end_hour:
                    count = item_query.filter(
                        played_at__hour__gte=start_hour, played_at__hour__lt=end_hour
                    ).count()
                else:
                    count = (
                        item_query.filter(played_at__hour__gte=start_hour).count()
                        + item_query.filter(played_at__hour__lt=end_hour).count()
                    )
                period_data.append(count)

            # Create dataset for this item
            datasets.append(
                {
                    "label": label,
                    "data": period_data,
                    "backgroundColor": f"rgba(29, 185, 84, {0.8 - (len(datasets) * 0.1)})",
                }
            )

        return list(periods.keys()), datasets

    return await get_data()


async def get_replay_gaps(
    user,
    since: datetime | None,
    until: datetime | None,
    items: dict[str, Any] | list[dict[str, Any]],
    item_type: str,
) -> tuple[list[str], list[float]]:
    """
    Calculate average time between repeated listens.

    Args:
        user: The SpotifyUser object
        since: Start datetime for filtering
        until: End datetime for filtering
        items: Single item or list of items to analyze
        item_type: Type of item ('artist', 'genre', 'track', 'album')

    Returns:
        Tuple of (labels, gap_hours) for chart visualization
    """
    # Ensure items is a list
    if not isinstance(items, list):
        items = [items]

    @sync_to_async
    def get_data() -> tuple[list[str], list[float]]:
        """Get replay gap data from the database."""
        gaps = []
        labels = []

        # Process up to 10 items
        for item in items[:10]:
            # Set up base query with timeframe filtering
            query = PlayedTrack.objects.filter(user=user)
            if since:
                query = query.filter(played_at__gte=since)
            if until:
                query = query.filter(played_at__lte=until)

            # Filter query based on item type
            if item_type == "artist":
                query = query.filter(artist_name=item["artist_name"])
                label = item["artist_name"]
            elif item_type == "track":
                query = query.filter(track_id=item["track_id"])
                label = item["track_name"]
            elif item_type == "album":
                query = query.filter(album_id=item["album_id"])
                label = item["album_name"]
            elif item_type == "genre":
                query = query.filter(genres__contains=[item["genre"]])
                label = item["genre"]
            else:
                continue

            # Get timestamps of all plays in chronological order
            plays = list(
                query.order_by("played_at").values_list("played_at", flat=True)
            )

            # Need at least 2 plays to calculate gaps
            if len(plays) < 2:
                continue

            # Calculate gaps between consecutive plays
            total_gap = 0
            play_count = 0

            for i in range(1, len(plays)):
                # Calculate gap in hours
                gap = (plays[i] - plays[i - 1]).total_seconds() / 3600

                # Only count gaps less than a week (168 hours)
                if gap <= 168:
                    total_gap += gap
                    play_count += 1

            # Calculate average gap and add to results
            if play_count > 0:
                avg_gap = total_gap / play_count
                gaps.append(round(avg_gap, 1))

                # Truncate long labels
                if len(label) > 20:
                    label = f"{label[:17]}..."
                labels.append(label)

        return labels, gaps

    return await get_data()


async def get_date_range(
    time_range: str, start_date: str | None = None, end_date: str | None = None
) -> tuple[datetime, datetime]:
    """
    Get date range based on time range selection.

    Args:
        time_range: Predefined time range ('last_7_days', 'last_4_weeks', etc.) or 'custom'
        start_date: Start date string (YYYY-MM-DD) for custom range
        end_date: End date string (YYYY-MM-DD) for custom range

    Returns:
        Tuple of (since, until) datetime objects
    """
    # End date is always today unless custom range is specified
    until = timezone.now()

    @sync_to_async
    def get_earliest_track() -> PlayedTrack | None:
        """Get the earliest track in the database."""
        return PlayedTrack.objects.order_by("played_at").first()

    # Determine start date based on time range
    if time_range == "last_7_days":
        since = until - timedelta(days=7)
    elif time_range == "last_4_weeks":
        since = until - timedelta(weeks=4)
    elif time_range == "6_months":
        since = until - timedelta(days=182)
    elif time_range == "last_year":
        since = until - timedelta(days=365)
    elif time_range == "all_time":
        # For all_time, find the earliest track in the database
        earliest_track = await get_earliest_track()
        since = (
            earliest_track.played_at if earliest_track else until - timedelta(days=365)
        )
    elif time_range == "custom" and start_date and end_date:
        # For custom range, parse the provided dates
        try:
            since = timezone.make_aware(datetime.strptime(start_date, "%Y-%m-%d"))
            # Include the full end date by adding one day
            until = timezone.make_aware(
                datetime.strptime(end_date, "%Y-%m-%d")
            ) + timedelta(days=1)
        except ValueError:
            # Fall back to 4 weeks if date parsing fails
            since = until - timedelta(weeks=4)
    else:
        # Default to 4 weeks
        since = until - timedelta(weeks=4)

    return since, until


def get_peak_position(
    user,
    item_id: str,
    item_type: str,
    since: datetime | None = None,
    until: datetime | None = None,
) -> int:
    """
    Get the peak (highest) position achieved by an item in its category.

    Args:
        user: The SpotifyUser object
        item_id: ID of the item to check
        item_type: Type of item ('track', 'album', 'artist')
        since: Start datetime for filtering
        until: End datetime for filtering

    Returns:
        Peak position (1 is highest) or 0 if not found
    """
    # Set up base query with timeframe filtering
    base_query = PlayedTrack.objects.filter(user=user)
    if since:
        base_query = base_query.filter(played_at__gte=since)
    if until:
        base_query = base_query.filter(played_at__lte=until)

    # Get total play count for each item of the given type
    if item_type == "track":
        rankings = (
            base_query.values("track_id", "track_name")
            .annotate(total_plays=Count("stream_id"))
            .order_by("-total_plays")
        )
        item_field = "track_id"
    elif item_type == "album":
        rankings = (
            base_query.values("album_id", "album_name")
            .annotate(total_plays=Count("stream_id"))
            .order_by("-total_plays")
        )
        item_field = "album_id"
    elif item_type == "artist":
        rankings = (
            base_query.values("artist_id", "artist_name")
            .annotate(total_plays=Count("stream_id"))
            .order_by("-total_plays")
        )
        item_field = "artist_id"
    else:
        return 0

    # Find position of the target item
    for position, item in enumerate(rankings, 1):
        if item[item_field] == item_id:
            return position

    # Return 0 if item not found
    return 0


async def get_item_stats_util(
    user,
    item_id: str,
    item_type: str,
    since: datetime | None = None,
    until: datetime | None = None,
) -> dict[str, Any]:
    """
    Get comprehensive statistics for a specific item.

    Args:
        user: The SpotifyUser object
        item_id: ID of the item to analyze
        item_type: Type of item ('track', 'album', 'artist')
        since: Start datetime for filtering
        until: End datetime for filtering

    Returns:
        Dictionary with comprehensive item statistics
    """

    @sync_to_async
    def get_data() -> dict[str, Any]:
        """Get item statistics from the database."""
        # Set up base query with timeframe filtering
        base_query = PlayedTrack.objects.filter(user=user)
        if since:
            base_query = base_query.filter(played_at__gte=since)
        if until:
            base_query = base_query.filter(played_at__lte=until)

        # Filter based on item type
        if item_type == "track":
            query = base_query.filter(track_id=item_id)
        elif item_type == "album":
            query = base_query.filter(album_id=item_id)
        elif item_type == "artist":
            query = base_query.filter(artist_id=item_id)
        else:
            return {
                "total_plays": 0,
                "total_minutes": 0,
                "avg_gap": 0,
                "peak_position": 0,
                "longest_streak": 0,
                "peak_day_plays": 0,
                "prime_time": "N/A",
                "repeat_rate": 0,
            }

        # Return empty stats if no plays found
        if query.count() == 0:
            return {
                "total_plays": 0,
                "total_minutes": 0,
                "avg_gap": 0,
                "peak_position": 0,
                "longest_streak": 0,
                "peak_day_plays": 0,
                "prime_time": "N/A",
                "repeat_rate": 0,
            }

        # Calculate basic statistics
        total_plays = query.count()
        total_minutes = (
            query.aggregate(total_time=Sum("duration_ms"))["total_time"] or 0
        ) / 60000

        # Calculate time gaps between plays
        plays = list(query.order_by("played_at").values_list("played_at", flat=True))
        gaps = []
        for i in range(1, len(plays)):
            gap = plays[i] - plays[i - 1]
            gaps.append(gap.total_seconds() / 3600)  # Convert to hours

        avg_gap = sum(gaps) / len(gaps) if gaps else 0

        # Calculate listening streak
        play_dates = {p.date() for p in plays}
        sorted_dates = sorted(play_dates)

        longest_streak = 0
        current_streak = 1

        for i in range(1, len(sorted_dates)):
            if (sorted_dates[i] - sorted_dates[i - 1]).days == 1:
                current_streak += 1
            else:
                longest_streak = max(longest_streak, current_streak)
                current_streak = 1

        longest_streak = max(longest_streak, current_streak)

        # Calculate peak day (most plays in a single day)
        peak_day = (
            query.annotate(day=TruncDate("played_at"))
            .values("day")
            .annotate(count=Count("stream_id"))
            .order_by("-count")
            .first()
        )
        peak_day_plays = peak_day["count"] if peak_day else 0

        # Calculate prime time (hour with most plays)
        prime_time = (
            query.annotate(hour=ExtractHour("played_at"))
            .values("hour")
            .annotate(count=Count("stream_id"))
            .order_by("-count")
            .first()
        )
        prime_time_hour = f"{prime_time['hour']:02d}:00" if prime_time else "N/A"

        # Calculate repeat rate (percentage of days with multiple plays)
        days_played = len(play_dates)
        multiple_play_days = (
            query.annotate(day=TruncDate("played_at"))
            .values("day")
            .annotate(count=Count("stream_id"))
            .filter(count__gt=1)
            .count()
        )
        repeat_rate = (multiple_play_days / days_played * 100) if days_played else 0

        return {
            "total_plays": total_plays,
            "total_minutes": total_minutes,
            "avg_gap": avg_gap,
            "peak_position": get_peak_position(user, item_id, item_type, since, until),
            "longest_streak": longest_streak,
            "peak_day_plays": peak_day_plays,
            "prime_time": prime_time_hour,
            "repeat_rate": round(repeat_rate, 1),
        }

    return await get_data()


# Stats Section


async def get_listening_context_data(
    user,
    item: dict[str, Any],
    item_type: str,
    since: datetime | None,
    until: datetime | None,
) -> dict[str, Any]:
    """
    Get data showing when an item is typically played throughout the day.

    Args:
        user: The SpotifyUser object
        item: Item to analyze
        item_type: Type of item ('artist', 'album', 'track')
        since: Start datetime for filtering
        until: End datetime for filtering

    Returns:
        Dictionary with listening context data
    """

    @sync_to_async
    def get_data() -> dict[str, Any]:
        """Get listening context data from the database."""
        # Set up base query with timeframe filtering
        base_query = PlayedTrack.objects.filter(user=user)
        if since:
            base_query = base_query.filter(played_at__gte=since)
        if until:
            base_query = base_query.filter(played_at__lt=until)

        # Filter based on item type
        if item_type == "artist":
            query = base_query.filter(artist_id=item["artist_id"])
        elif item_type == "album":
            query = base_query.filter(album_id=item["album_id"])
        elif item_type == "track":
            query = base_query.filter(track_id=item["track_id"])
        else:
            return {
                "labels": [],
                "values": [],
                "percentages": [],
                "contexts": [],
                "total_plays": 0,
            }

        # Define time categories with their hour ranges
        time_categories = {
            "Night (12am-6am)": (0, 6),
            "Morning (6am-12pm)": (6, 12),
            "Afternoon (12pm-6pm)": (12, 18),
            "Evening (6pm-12am)": (18, 24),
        }

        # Count plays in each time category
        counts = {category: 0 for category in time_categories}

        for track in query:
            hour = track.played_at.hour
            for category, (start, end) in time_categories.items():
                if start <= hour < end:
                    counts[category] += 1
                    break

        # Calculate percentages
        total = sum(counts.values())
        percentages = {
            category: round((count / total * 100) if total > 0 else 0, 1)
            for category, count in counts.items()
        }

        # Define context descriptions
        contexts = {
            "Night (12am-6am)": "Late night listening",
            "Morning (6am-12pm)": "Morning routine & commute",
            "Afternoon (12pm-6pm)": "Work & daytime activities",
            "Evening (6pm-12am)": "Evening relaxation & social",
        }

        # Prepare data for the chart
        labels = list(time_categories.keys())
        values = [counts[category] for category in labels]
        percentages_list = [percentages[category] for category in labels]
        context_descriptions = [contexts[category] for category in labels]

        return {
            "labels": labels,
            "values": values,
            "percentages": percentages_list,
            "contexts": context_descriptions,
            "total_plays": total,
        }

    return await get_data()


async def get_repeat_listen_histogram_data(
    user,
    item: dict[str, Any],
    item_type: str,
    since: datetime | None,
    until: datetime | None,
) -> dict[str, Any]:
    """
    Get histogram data showing time between repeat listens.

    Args:
        user: The SpotifyUser object
        item: Item to analyze
        item_type: Type of item ('artist', 'album', 'track')
        since: Start datetime for filtering
        until: End datetime for filtering

    Returns:
        Dictionary with histogram data
    """

    @sync_to_async
    def get_data() -> dict[str, Any]:
        """Get repeat listen histogram data from the database."""
        # Set up base query with timeframe filtering
        base_query = PlayedTrack.objects.filter(user=user)
        if since:
            base_query = base_query.filter(played_at__gte=since)
        if until:
            base_query = base_query.filter(played_at__lt=until)

        # Filter based on item type
        if item_type == "artist":
            query = base_query.filter(artist_id=item["artist_id"])
        elif item_type == "album":
            query = base_query.filter(album_id=item["album_id"])
        elif item_type == "track":
            query = base_query.filter(track_id=item["track_id"])
        else:
            return {"labels": [], "values": []}

        # Sort plays chronologically
        plays = list(query.order_by("played_at"))

        # Calculate intervals between consecutive plays (in hours)
        intervals = []
        for i in range(1, len(plays)):
            interval_seconds = (
                plays[i].played_at - plays[i - 1].played_at
            ).total_seconds()
            # Only count intervals less than 30 days
            if interval_seconds < 30 * 24 * 60 * 60:
                intervals.append(interval_seconds / 3600)  # Convert to hours

        # Define histogram bins and labels
        bins = [0, 1, 3, 6, 12, 24, 48, 72, 168, 336, 720]  # hours
        bin_labels = [
            "<1h",
            "1-3h",
            "3-6h",
            "6-12h",
            "12-24h",
            "1-2d",
            "2-3d",
            "3-7d",
            "1-2w",
            "2-4w",
        ]
        counts = [0] * len(bin_labels)

        # Count intervals in each bin
        for interval in intervals:
            for i, upper_bound in enumerate(bins[1:]):
                if interval < upper_bound:
                    counts[i] += 1
                    break

        return {"labels": bin_labels, "values": counts}

    return await get_data()


async def get_listening_time_distribution_data(
    user,
    item: dict[str, Any],
    item_type: str,
    since: datetime | None,
    until: datetime | None,
) -> dict[str, Any]:
    """
    Get polar area chart data showing times of day listening to item.

    Args:
        user: The SpotifyUser object
        item: Item to analyze
        item_type: Type of item ('artist', 'album', 'track')
        since: Start datetime for filtering
        until: End datetime for filtering

    Returns:
        Dictionary with polar area chart data
    """

    @sync_to_async
    def get_data() -> dict[str, Any]:
        """Get listening time distribution data from the database."""
        # Set up base query with timeframe filtering
        base_query = PlayedTrack.objects.filter(user=user)
        if since:
            base_query = base_query.filter(played_at__gte=since)
        if until:
            base_query = base_query.filter(played_at__lt=until)

        # Filter based on item type
        if item_type == "artist":
            query = base_query.filter(artist_id=item["artist_id"])
        elif item_type == "album":
            query = base_query.filter(album_id=item["album_id"])
        elif item_type == "track":
            query = base_query.filter(track_id=item["track_id"])
        else:
            return {"labels": [], "values": []}

        # Define 3-hour time periods
        time_periods = [
            "12am-3am",
            "3am-6am",
            "6am-9am",
            "9am-12pm",
            "12pm-3pm",
            "3pm-6pm",
            "6pm-9pm",
            "9pm-12am",
        ]
        counts = [0] * 8

        # Group plays by 3-hour periods
        for track in query:
            hour = track.played_at.hour
            period_index = hour // 3
            counts[period_index] += 1

        return {"labels": time_periods, "values": counts}

    return await get_data()


async def get_artist_genre_distribution(
    user, since: datetime | None, until: datetime | None, item: dict[str, Any]
) -> dict[str, Any]:
    """
    Get genre distribution for an artist's tracks.

    Args:
        user: The SpotifyUser object
        since: Start datetime for filtering
        until: End datetime for filtering
        item: Artist item to analyze

    Returns:
        Dictionary with genre distribution data
    """

    @sync_to_async
    def get_data() -> dict[str, Any]:
        """Get artist genre distribution from the database."""
        # Set up base query with timeframe filtering
        base_query = PlayedTrack.objects.filter(user=user)
        if since:
            base_query = base_query.filter(played_at__gte=since)
        if until:
            base_query = base_query.filter(played_at__lt=until)

        # Filter for the artist
        query = base_query.filter(artist_id=item["artist_id"])

        # Collect all genres from the tracks
        genre_counts: Counter[str] = Counter()
        for track in query:
            if track.genres:
                genre_counts.update(track.genres)

        # Get top genres
        top_genres = genre_counts.most_common(10)

        return {
            "labels": [g[0] for g in top_genres],
            "values": [g[1] for g in top_genres],
        }

    return await get_data()


async def get_artist_discography_coverage(user, artist_id: str) -> dict[str, Any]:
    """
    Get percentage of artist's discography played by the user.

    Args:
        user: The SpotifyUser object
        artist_id: Spotify artist ID

    Returns:
        Dictionary with discography coverage data
    """

    @sync_to_async
    def get_played_tracks_count() -> int:
        """Get count of distinct tracks by this artist played by the user."""
        return (
            PlayedTrack.objects.filter(user=user, artist_id=artist_id)
            .values_list("track_id", flat=True)
            .distinct()
            .count()
        )

    # Get the number of distinct tracks played by this user
    played_count = await get_played_tracks_count()

    # Use the helper function to get total track count from Spotify
    total_tracks = await get_artist_track_count_helper(user, artist_id)

    # Fall back to database query if the helper returns no data
    if total_tracks == 0:

        @sync_to_async
        def get_all_artist_tracks_count() -> int:
            """Get count of all known tracks by this artist from all users."""
            return (
                PlayedTrack.objects.filter(artist_id=artist_id)
                .values_list("track_id", flat=True)
                .distinct()
                .count()
            )

        total_tracks = await get_all_artist_tracks_count()

        # Use a conservative estimate if database data is too limited
        if total_tracks < played_count or total_tracks < 10:
            total_tracks = max(played_count * 3, 10)

    # Avoid division by zero
    if total_tracks == 0:
        total_tracks = played_count or 1

    # Calculate percentage
    percentage = (played_count / total_tracks * 100) if total_tracks > 0 else 0

    return {
        "played_count": played_count,
        "total_count": total_tracks,
        "percentage": percentage,
    }


async def get_track_duration_comparison(
    user, since: datetime | None, until: datetime | None, item: dict[str, Any]
) -> dict[str, Any]:
    """
    Compare average listening duration to track's full duration.

    Args:
        user: The SpotifyUser object
        since: Start datetime for filtering
        until: End datetime for filtering
        item: Track item to analyze

    Returns:
        Dictionary with duration comparison data
    """

    @sync_to_async
    def get_data() -> dict[str, Any]:
        """Get track duration data from the database."""
        # Set up base query with timeframe filtering
        base_query = PlayedTrack.objects.filter(user=user)
        if since:
            base_query = base_query.filter(played_at__gte=since)
        if until:
            base_query = base_query.filter(played_at__lt=until)

        # Filter for the track
        query = base_query.filter(track_id=item["track_id"])

        # Calculate average listening duration
        total_duration = 0
        count = 0

        for played in query:
            if hasattr(played, "duration_ms") and played.duration_ms:
                total_duration += played.duration_ms / 1000  # Convert to seconds
                count += 1

        average_duration = total_duration / count if count > 0 else 0

        return {
            "average_duration": average_duration,
            "count": count,
            "track_id": item["track_id"],
        }

    result = await get_data()

    # Fetch actual track duration from Spotify API
    async with SpotifyClient(user.spotify_user_id) as client:
        track_details = await client.get_track_details(result["track_id"])

    # Get official track duration from Spotify
    if track_details and "duration_ms" in track_details:
        track_duration = track_details["duration_ms"] / 1000  # Convert to seconds
    else:
        # Fallback if we can't get the official duration
        track_duration = 180  # Default to 3 minutes

    # Calculate percentage with accurate track duration (cap at 100%)
    percentage = (
        min(result["average_duration"] / track_duration, 1.0)
        if track_duration > 0 and result["count"] > 0
        else 0
    )  # Gets *100 when displayed

    return {
        "average_duration": result["average_duration"],
        "track_duration": track_duration,
        "percentage": percentage,
    }


async def get_artist_tracks_coverage(user, artist_id: str) -> dict[str, Any]:
    """
    Get percentage of artist's tracks played by the user.

    Args:
        user: The SpotifyUser object
        artist_id: Spotify artist ID

    Returns:
        Dictionary with track coverage data
    """
    # This function is similar to get_artist_discography_coverage
    # but kept separate for potential future differentiation

    @sync_to_async
    def get_played_tracks_count() -> int:
        """Get count of distinct tracks by this artist played by the user."""
        return (
            PlayedTrack.objects.filter(user=user, artist_id=artist_id)
            .values_list("track_id", flat=True)
            .distinct()
            .count()
        )

    # Get the number of distinct tracks played by this user
    played_count = await get_played_tracks_count()

    # Use the helper function to get total track count
    total_tracks = await get_artist_track_count_helper(user, artist_id)

    # Fall back to database query if the helper returns no data
    if total_tracks == 0:

        @sync_to_async
        def get_all_artist_tracks_count() -> int:
            """Get count of all known tracks by this artist from all users."""
            return (
                PlayedTrack.objects.filter(artist_id=artist_id)
                .values_list("track_id", flat=True)
                .distinct()
                .count()
            )

        total_tracks = await get_all_artist_tracks_count()

        # Use a conservative estimate if database data is too limited
        if total_tracks < played_count or total_tracks < 10:
            total_tracks = max(played_count * 2, 10)

    # Avoid division by zero
    if total_tracks == 0:
        total_tracks = played_count or 1

    # Calculate percentage
    percentage = (played_count / total_tracks * 100) if total_tracks > 0 else 0

    return {
        "played_count": played_count,
        "total_count": total_tracks,
        "percentage": percentage,
    }


async def get_album_track_plays(
    user, since: datetime | None, until: datetime | None, item: dict[str, Any]
) -> dict[str, Any]:
    """
    Get play counts for each track in an album.

    Args:
        user: The SpotifyUser object
        since: Start datetime for filtering
        until: End datetime for filtering
        item: Album item to analyze

    Returns:
        Dictionary with album track plays data
    """

    @sync_to_async
    def get_base_data() -> list[dict[str, Any]]:
        """Get base album track play data from the database."""
        # Set up base query with timeframe filtering
        base_query = PlayedTrack.objects.filter(user=user)
        if since:
            base_query = base_query.filter(played_at__gte=since)
        if until:
            base_query = base_query.filter(played_at__lt=until)

        # Get tracks from this album
        album_tracks = base_query.filter(album_id=item["album_id"])

        # Count plays per track
        track_plays = (
            album_tracks.values("track_name", "track_id")
            .annotate(play_count=Count("stream_id"))
            .order_by("track_name")  # Default to alphabetical order
        )

        # Convert QuerySet to list to use outside of the database context
        return list(track_plays)

    # Get the base data first
    track_plays = await get_base_data()

    # Create mapping of track IDs to play counts
    track_id_to_plays = {t["track_id"]: t["play_count"] for t in track_plays}

    # Use Spotify API to get proper track order and ensure all tracks are included
    try:
        async with SpotifyClient(user.spotify_user_id) as client:
            album_details = await client.get_album(item["album_id"])

            if (
                album_details
                and "tracks" in album_details
                and "items" in album_details["tracks"]
            ):
                album_tracks = album_details["tracks"]["items"]

                ordered_labels = []
                ordered_values = []

                # Helper function to truncate track names
                def truncate_name(name: str) -> str:
                    """Truncate long track names."""
                    return f"{name[:20]}..." if len(name) > 20 else name

                # Add all tracks in album order, including unplayed tracks
                for track in album_tracks:
                    track_id = track["id"]
                    track_name = truncate_name(track["name"])

                    # Get play count (default to 0 if not played)
                    play_count = track_id_to_plays.get(track_id, 0)

                    ordered_labels.append(track_name)
                    ordered_values.append(play_count)

                # Add any tracks found in DB but not in Spotify API response
                for track in track_plays:
                    if track["track_id"] not in [t["id"] for t in album_tracks]:
                        track_name = truncate_name(track["track_name"])
                        ordered_labels.append(track_name)
                        ordered_values.append(track["play_count"])

                return {"labels": ordered_labels, "values": ordered_values}
    except Exception as e:
        logger.error(f"Error ordering album tracks: {e}")

    # Fallback to alphabetical order with truncated names
    return {
        "labels": [
            (t["track_name"][:10] + ("..." if len(t["track_name"]) > 10 else ""))
            for t in track_plays
        ],
        "values": [t["play_count"] for t in track_plays],
    }


async def get_album_tracks_coverage(user, album_id: str) -> dict[str, Any]:
    """
    Get percentage of album tracks played by the user.

    Args:
        user: The SpotifyUser object
        album_id: Spotify album ID

    Returns:
        Dictionary with album tracks coverage data
    """

    @sync_to_async
    def get_played_tracks_count() -> int:
        """Get count of distinct tracks from this album played by the user."""
        return len(
            PlayedTrack.objects.filter(user=user, album_id=album_id)
            .values_list("track_id", flat=True)
            .distinct()
        )

    # Get played tracks count from the database
    played_count = await get_played_tracks_count()

    # Get the actual total track count from Spotify API
    try:
        async with SpotifyClient(user.spotify_user_id) as client:
            album_details = await client.get_album(album_id)

            # Get track count from the most reliable source
            if album_details and "total_tracks" in album_details:
                total_tracks = album_details["total_tracks"]
            elif (
                album_details
                and "tracks" in album_details
                and "items" in album_details["tracks"]
            ):
                total_tracks = len(album_details["tracks"]["items"])
            else:
                # Fallback if API data is incomplete
                total_tracks = max(played_count, 10)
    except Exception as e:
        logger.error(f"Error getting album track count from Spotify: {e}")
        total_tracks = max(played_count, 10)  # Conservative fallback

    # Avoid division by zero
    if total_tracks == 0:
        total_tracks = played_count or 1

    # Calculate percentage
    percentage = (played_count / total_tracks * 100) if total_tracks > 0 else 0

    return {
        "played_count": played_count,
        "total_count": total_tracks,
        "percentage": percentage,
    }


async def get_user_played_tracks(
    user,
    track_ids: list[str] | None = None,
    artist_id: str | None = None,
    album_id: str | None = None,
) -> set[str]:
    """
    Get a set of track IDs that the user has listened to.

    Args:
        user: The SpotifyUser object
        track_ids: Optional list of track IDs to filter by
        artist_id: Optional artist ID to filter by
        album_id: Optional album ID to filter by

    Returns:
        Set of track IDs the user has played
    """

    @sync_to_async
    def get_data() -> set[str]:
        """Get played track IDs from the database."""
        query = PlayedTrack.objects.filter(user=user)

        # Apply filters if provided
        if track_ids:
            query = query.filter(track_id__in=track_ids)
        if artist_id:
            query = query.filter(artist_id=artist_id)
        if album_id:
            query = query.filter(album_id=album_id)

        # Return distinct track IDs as a set
        return set(query.values_list("track_id", flat=True).distinct())

    return await get_data()
