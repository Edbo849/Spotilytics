import logging
from collections import Counter
from datetime import datetime, timedelta
from typing import Any

from asgiref.sync import sync_to_async
from django.core.cache import cache
from django.db import IntegrityError
from django.db.models import Count, Max, Min, QuerySet, Sum
from django.db.models.functions import (
    ExtractHour,
    ExtractWeekDay,
    TruncDay,
    TruncHour,
    TruncMonth,
    TruncWeek,
)
from django.utils import timezone

from music.models import PlayedTrack, SpotifyUser
from music.services.spotify_data_helpers import get_artist_all_songs_data
from music.services.SpotifyClient import SpotifyClient

logger = logging.getLogger(__name__)


# Read full history helpers


async def fetch_spotify_users() -> list[SpotifyUser]:
    """Fetch all Spotify users from the database asynchronously."""
    return await sync_to_async(list)(SpotifyUser.objects.all())


def get_latest_track_timestamp(user_id: int) -> int | None:
    """
    Get the timestamp of the latest track for a user.

    Args:
        user_id: The ID of the SpotifyUser

    Returns:
        Unix timestamp in milliseconds or None if no tracks found
    """
    latest_track = (
        PlayedTrack.objects.filter(user=user_id).order_by("-played_at").first()
    )
    return int(latest_track.played_at.timestamp() * 1000) if latest_track else None


async def fetch_recently_played_tracks(
    spotify_user_id: str, after_timestamp: int
) -> list[dict]:
    """
    Fetch recently played tracks for a Spotify user since a specific timestamp.

    Args:
        spotify_user_id: The Spotify user ID
        after_timestamp: Fetch tracks after this timestamp in milliseconds

    Returns:
        List of track dictionaries from the Spotify API
    """
    async with SpotifyClient(spotify_user_id) as client:
        return await client.get_recently_played_since(after_timestamp)


async def save_played_tracks(user_id: int, tracks: list[dict]) -> None:
    """
    Save played tracks to the database.

    Args:
        user_id: The ID of the SpotifyUser
        tracks: List of track dictionaries from the Spotify API
    """
    for item in tracks:
        played_at_str = item["played_at"]
        played_at = timezone.datetime.strptime(played_at_str, "%Y-%m-%dT%H:%M:%S.%fZ")
        track = item["track"]
        await sync_to_async(PlayedTrack.objects.create)(
            user=user_id,
            track_id=track["id"],
            played_at=played_at,
            track_name=track["name"],
            artist_name=track["artists"][0]["name"],
            album_name=track["album"]["name"],
        )


# Save tracks atomic helpers


def get_track_details(
    info: dict[str, Any],
    track_details_dict: dict[str, dict],
    artist_details_dict: dict[str, dict],
) -> dict[str, Any]:
    """
    Extract comprehensive track details from API responses.

    Args:
        info: Basic track information
        track_details_dict: Dictionary of track details indexed by track_id
        artist_details_dict: Dictionary of artist details indexed by artist_id

    Returns:
        Dictionary with complete track information
    """
    track_id = info["track_id"]
    track_details = track_details_dict.get(track_id, {})
    popularity = track_details.get("popularity", 0)
    album_info = track_details.get("album", {})
    artist_info_list = track_details.get("artists", [])

    album_id = album_info.get("id") if album_info else None
    artist_id = None
    genres = []

    if artist_info_list:
        artist_info = artist_info_list[0]
        artist_id = artist_info.get("id")
        artist_details = artist_details_dict.get(artist_id, {})
        genres = artist_details.get("genres", [])

    return {
        "track_id": track_id,
        "played_at": info["played_at"],
        "track_name": info["track_name"],
        "artist_name": info["artist_name"],
        "album_name": info["album_name"],
        "duration_ms": info["duration_ms"],
        "genres": genres,
        "popularity": popularity,
        "artist_id": artist_id,
        "album_id": album_id,
    }


def track_exists(user: SpotifyUser, track_id: str, played_at: datetime) -> bool:
    """
    Check if a track already exists in the database.

    Args:
        user: SpotifyUser instance
        track_id: Spotify track ID
        played_at: Timestamp when the track was played

    Returns:
        True if the track exists, False otherwise
    """
    return PlayedTrack.objects.filter(
        user=user, track_id=track_id, played_at=played_at
    ).exists()


def create_played_track(user: SpotifyUser, track_data: dict[str, Any]) -> bool:
    """
    Create a PlayedTrack record in the database.

    Args:
        user: SpotifyUser instance
        track_data: Dictionary with track information

    Returns:
        True if creation was successful, False otherwise
    """
    try:
        PlayedTrack.objects.create(
            user=user,
            track_id=track_data["track_id"],
            played_at=track_data["played_at"],
            track_name=track_data["track_name"],
            artist_name=track_data["artist_name"],
            album_name=track_data["album_name"],
            duration_ms=track_data["duration_ms"],
            genres=track_data["genres"],
            popularity=track_data["popularity"],
            artist_id=track_data["artist_id"],
            album_id=track_data["album_id"],
        )
        return True
    except IntegrityError as e:
        logger.error(f"Database error while adding track {track_data['track_id']}: {e}")
        return False


# Get listening stats helpers


def set_time_range_parameters(
    time_range: str, start_date: str | None = None, end_date: str | None = None
) -> tuple[datetime | None, datetime | None, Any, str]:
    """
    Set parameters for time range filtering.

    Args:
        time_range: One of 'last_7_days', 'last_4_weeks', '6_months', 'last_year',
                    'all_time', or 'custom'
        start_date: Start date string for custom range (format: YYYY-MM-DD)
        end_date: End date string for custom range (format: YYYY-MM-DD)

    Returns:
        Tuple of (since, until, truncate_func, x_label)
    """
    since = None
    until = None
    truncate_func = None
    x_label = ""

    if time_range == "last_7_days":
        since = timezone.now() - timedelta(days=7)
        until = timezone.now()
        truncate_func = TruncDay("played_at")
        x_label = "Day"
    elif time_range == "last_4_weeks":
        since = timezone.now() - timedelta(weeks=4)
        until = timezone.now()
        truncate_func = TruncWeek("played_at")
        x_label = "Week"
    elif time_range == "6_months":
        since = timezone.now() - timedelta(days=182)
        until = timezone.now()
        truncate_func = TruncMonth("played_at")
        x_label = "Month"
    elif time_range == "last_year":
        since = timezone.now() - timedelta(days=365)
        until = timezone.now()
        truncate_func = TruncMonth("played_at")
        x_label = "Month"
    elif time_range == "all_time":
        earliest_play = PlayedTrack.objects.aggregate(Min("played_at"))[
            "played_at__min"
        ]
        latest_play = PlayedTrack.objects.aggregate(Max("played_at"))["played_at__max"]
        since = earliest_play if earliest_play else timezone.now()
        until = latest_play if latest_play else timezone.now()
        truncate_func = TruncMonth("played_at")
        x_label = "Month"
    elif time_range == "custom" and start_date and end_date:
        try:
            naive_start = datetime.strptime(start_date, "%Y-%m-%d")
            naive_end = datetime.strptime(end_date, "%Y-%m-%d")
            since = timezone.make_aware(naive_start)
            until = timezone.make_aware(naive_end) + timedelta(days=1)

            total_duration = (until - since).days if since and until else None

            if total_duration and total_duration <= 2:
                truncate_func = TruncHour("played_at")
                x_label = "Hour"
            elif total_duration and total_duration <= 30:
                truncate_func = TruncDay("played_at")
                x_label = "Day"
            elif total_duration and total_duration <= 180:
                truncate_func = TruncWeek("played_at")
                x_label = "Week"
            else:
                truncate_func = TruncMonth("played_at")
                x_label = "Month"
        except ValueError as e:
            logger.error(f"Invalid date format: {e}")
            since = None
            until = None
            truncate_func = TruncMonth("played_at")
            x_label = "Month"
    else:
        truncate_func = TruncMonth("played_at")
        x_label = "Month"

    return since, until, truncate_func, x_label


def calculate_aggregate_statistics(tracks: QuerySet) -> dict[str, Any]:
    """
    Calculate aggregate statistics from a queryset of tracks.

    Args:
        tracks: QuerySet of PlayedTrack objects

    Returns:
        Dictionary with aggregate statistics
    """
    return tracks.aggregate(
        total_tracks=Count("stream_id"),
        total_minutes_streamed=Sum("duration_ms") / 60000.0,
        different_tracks=Count("track_id", distinct=True),
        different_artists=Count("artist_name", distinct=True),
        different_albums=Count("album_name", distinct=True),
        first_play_date=Min("played_at"),
        last_play_date=Max("played_at"),
    )


def calculate_most_played_genre(tracks: QuerySet) -> str:
    """
    Calculate the most played genre from a queryset of tracks.

    Args:
        tracks: QuerySet of PlayedTrack objects

    Returns:
        String with the most played genre or 'N/A' if none found
    """
    genre_counts: Counter[str] = Counter()
    for track in tracks:
        if track.genres:
            genre_counts.update(track.genres)

    most_played_genre = genre_counts.most_common(1)
    return most_played_genre[0][0].capitalize() if most_played_genre else "N/A"


def calculate_top_listening_hour(tracks: QuerySet) -> str:
    """
    Calculate the top listening hour from a queryset of tracks.

    Args:
        tracks: QuerySet of PlayedTrack objects

    Returns:
        String with the top listening hour or 'N/A' if none found
    """
    top_listening_hour = (
        tracks.annotate(hour=ExtractHour("played_at"))
        .values("hour")
        .annotate(hour_count=Count("hour"))
        .order_by("-hour_count")
        .first()
    )
    return f"{top_listening_hour['hour']}:00" if top_listening_hour else "N/A"


def calculate_most_popular_day(tracks: QuerySet) -> str:
    """
    Calculate the most popular day of the week from a queryset of tracks.

    Args:
        tracks: QuerySet of PlayedTrack objects

    Returns:
        String with the most popular day or 'N/A' if none found
    """
    most_popular_day_entry = (
        tracks.annotate(weekday=ExtractWeekDay("played_at"))
        .values("weekday")
        .annotate(day_count=Count("weekday"))
        .order_by("-day_count")
        .first()
    )

    if most_popular_day_entry:
        days = [
            "Sunday",
            "Monday",
            "Tuesday",
            "Wednesday",
            "Thursday",
            "Friday",
            "Saturday",
        ]
        weekday = most_popular_day_entry["weekday"]
        if 1 <= weekday <= 7:
            return days[weekday - 1]
        else:
            logger.error(f"Invalid weekday value: {weekday}")
            return "N/A"
    else:
        return "N/A"


def calculate_days_streamed(stats_aggregate: dict[str, Any]) -> int:
    """
    Calculate total days streamed from aggregate statistics.

    Args:
        stats_aggregate: Dictionary with aggregate statistics

    Returns:
        Integer with the total days streamed
    """
    if stats_aggregate["first_play_date"] and stats_aggregate["last_play_date"]:
        return (
            stats_aggregate["last_play_date"] - stats_aggregate["first_play_date"]
        ).days + 1
    return 0


def calculate_average_listening_time_per_day(stats_aggregate: dict[str, Any]) -> float:
    """
    Calculate average listening time per day from aggregate statistics.

    Args:
        stats_aggregate: Dictionary with aggregate statistics

    Returns:
        Float with the average listening time in minutes per day
    """
    if stats_aggregate.get("days_streamed", 0) > 0:
        return (
            stats_aggregate["total_minutes_streamed"] / stats_aggregate["days_streamed"]
        )
    return 0


def generate_all_periods(
    since: datetime, until: datetime, truncate_func: Any
) -> list[datetime]:
    """
    Generate all periods between since and until based on truncate function.

    Args:
        since: Start datetime
        until: End datetime
        truncate_func: Django truncate function

    Returns:
        List of datetime objects representing all periods
    """
    all_periods = []

    if since:
        current = since
        if isinstance(truncate_func, TruncWeek):
            current = since - timedelta(days=since.weekday())
        elif isinstance(truncate_func, TruncMonth):
            current = since.replace(day=1)
        elif isinstance(truncate_func, TruncHour):
            current = since.replace(minute=0, second=0, microsecond=0)
    else:
        current = timezone.now()

    if not timezone.is_aware(current):
        current = timezone.make_aware(current)

    while current <= until:
        all_periods.append(current)

        if isinstance(truncate_func, TruncWeek):
            current += timedelta(weeks=1)
        elif isinstance(truncate_func, TruncMonth):
            if current.month == 12:
                current = current.replace(year=current.year + 1, month=1)
            else:
                current = current.replace(month=current.month + 1)
        elif isinstance(truncate_func, TruncDay):
            current += timedelta(days=1)
        elif isinstance(truncate_func, TruncHour):
            current += timedelta(hours=1)

    return all_periods


def populate_dates_and_counts(
    all_periods: list[datetime],
    count_dict: dict[datetime | str, int],
    truncate_func: Any,
) -> tuple[list[str], list[int]]:
    """
    Populate dates and counts for chart visualization.

    Args:
        all_periods: List of datetime objects representing all periods
        count_dict: Dictionary mapping dates to counts
        truncate_func: Django truncate function

    Returns:
        Tuple of (dates, counts) lists
    """
    dates: list[str] = []
    counts: list[int] = []

    if not count_dict:
        return dates, counts

    sample_key = next(iter(count_dict))

    # Handle datetime objects as dictionary keys
    if isinstance(sample_key, datetime):
        # Determine format based on truncate function
        if isinstance(truncate_func, TruncHour):
            date_format = "%Y-%m-%d %H:%M"
        elif isinstance(truncate_func, TruncDay):
            date_format = "%b %d"
        elif isinstance(truncate_func, TruncWeek):
            date_format = "%b %d"
        elif isinstance(truncate_func, TruncMonth):
            date_format = "%b %Y"
        else:
            date_format = "%Y-%m-%d"

        # Process all periods with datetime keys
        for period in all_periods:
            formatted_date = period.strftime(date_format)
            dates.append(formatted_date)

            # Find matching date in count_dict
            found = False
            for dt, count in count_dict.items():
                if isinstance(dt, datetime) and period.date() == dt.date():
                    # For hour truncation, also check the hour
                    if isinstance(truncate_func, TruncHour) and period.hour != dt.hour:
                        continue
                    counts.append(count)
                    found = True
                    break

            if not found:
                counts.append(0)

        return dates, counts

    # String-based key handling
    date_format = "%Y-%m-%d"  # Default format

    # Determine format based on sample key
    if isinstance(sample_key, str):
        if " " in sample_key and len(sample_key) >= 8:
            date_format = "%b %Y"
        elif " " in sample_key and len(sample_key) < 8:
            date_format = "%b %d"
        elif "-" in sample_key and len(sample_key) <= 5:
            date_format = "%m-%d"

    # Process periods for string-based keys
    for period in all_periods:
        if not isinstance(truncate_func, TruncHour):
            period = period.replace(hour=0, minute=0, second=0, microsecond=0)

        display_str = (
            period.strftime("%Y-%m-%d %H:%M")
            if isinstance(truncate_func, TruncHour)
            else period.strftime("%Y-%m-%d")
        )
        lookup_str = period.strftime(date_format)
        count = count_dict.get(lookup_str, 0)

        dates.append(display_str)
        counts.append(count)

    return dates, counts


# Get streaming trend data helpers


async def get_trend_data(
    user: SpotifyUser,
    item: dict[str, Any],
    item_type: str,
    since: datetime,
    until: datetime,
    truncate_func: Any,
    date_format: str,
    chart_format: str,
) -> tuple[list[str], list[int], list[str], str]:
    """
    Get trend data for visualization.

    Args:
        user: SpotifyUser instance
        item: Dictionary with item details
        item_type: Type of item ('artist', 'genre', 'track', 'album')
        since: Start datetime
        until: End datetime
        truncate_func: Django truncate function
        date_format: Format string for display dates
        chart_format: Format string for chart dates

    Returns:
        Tuple of (dates, counts, raw_dates, label)
    """
    counts = []
    dates = []
    raw_dates = []

    @sync_to_async
    def get_query_data():
        base_query = PlayedTrack.objects.filter(user=user)
        if since:
            base_query = base_query.filter(played_at__gte=since)
        if until:
            base_query = base_query.filter(played_at__lte=until)

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

        query_results = list(
            query.annotate(period=truncate_func)
            .values("period")
            .annotate(count=Count("stream_id"))
            .order_by("period")
        )

        results = []
        for entry in query_results:
            display_date = entry["period"].strftime(date_format)
            chart_date = entry["period"].strftime(chart_format)
            results.append((display_date, chart_date, entry["count"]))

        return results, label

    results, label = await get_query_data()

    for display_date, chart_date, count in results:
        dates.append(display_date)
        raw_dates.append(chart_date)
        counts.append(count)

    return dates, counts, raw_dates, label


def determine_truncate_func_and_formats(total_duration: int) -> tuple[Any, str, str]:
    """
    Determine the appropriate truncate function and date formats based on duration.

    Args:
        total_duration: Duration in days

    Returns:
        Tuple of (truncate_func, date_format, chart_format)
    """
    if total_duration <= 7:
        truncate_func = TruncDay("played_at")
        date_format = "%m-%d"
        chart_format = "%Y-%m-%d"
    elif total_duration <= 28:
        truncate_func = TruncDay("played_at")
        date_format = "%b %d"
        chart_format = "%Y-%m-%d"
    elif total_duration <= 182:
        truncate_func = TruncWeek("played_at")
        date_format = "%b %d"
        chart_format = "%Y-%m-%d"
    else:
        truncate_func = TruncMonth("played_at")
        date_format = "%b %Y"
        chart_format = "%Y-%m-%d"

    return truncate_func, date_format, chart_format


async def get_artist_track_count_helper(user: SpotifyUser, artist_id: str) -> int:
    """
    Helper function to get accurate track count for an artist using SpotifyClient.

    Args:
        user: SpotifyUser instance
        artist_id: Spotify artist ID

    Returns:
        Integer with the total track count
    """
    cache_key = f"artist_total_tracks_{artist_id}"
    cached_count = cache.get(cache_key)

    if cached_count is not None:
        return cached_count

    try:
        # Get total track count from SpotifyClient
        async with SpotifyClient(user.spotify_user_id) as client:
            # Use the function that gets all songs data for an artist
            data = await get_artist_all_songs_data(client, artist_id)
            tracks = data.get("tracks", [])
            total_tracks = len(tracks)

            # Cache the result for future use (1 week)
            if total_tracks > 0:
                cache.set(cache_key, total_tracks, 604800)

            return total_tracks

    except Exception as e:
        logger.error(f"Error getting artist track count from Spotify: {e}")
        return 0
