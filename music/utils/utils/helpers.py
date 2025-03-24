import logging
from collections import Counter
from datetime import datetime, timedelta

from asgiref.sync import sync_to_async
from django.core.cache import cache
from django.db import IntegrityError
from django.db.models import Count, Max, Min, Sum
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


async def fetch_spotify_users():
    return await sync_to_async(list)(SpotifyUser.objects.all())


def get_latest_track_timestamp(user_id):
    latest_track = (
        PlayedTrack.objects.filter(user=user_id).order_by("-played_at").first()
    )
    if latest_track:
        return int(latest_track.played_at.timestamp() * 1000)
    return None


async def fetch_recently_played_tracks(spotify_user_id, after_timestamp):
    async with SpotifyClient(spotify_user_id) as client:
        return await client.get_recently_played_since(after_timestamp)


async def save_played_tracks(user_id, tracks):
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


# save_tracks_atomic helpers


def get_track_details(info, track_details_dict, artist_details_dict):
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

    return {
        "track_id": track_id,
        "played_at": played_at,
        "track_name": track_name,
        "artist_name": artist_name,
        "album_name": album_name,
        "duration_ms": duration_ms,
        "genres": genres,
        "popularity": popularity,
        "artist_id": artist_id,
        "album_id": album_id,
    }


def track_exists(user, track_id, played_at):
    return PlayedTrack.objects.filter(
        user=user, track_id=track_id, played_at=played_at
    ).exists()


def create_played_track(user, track_data):
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


# Get_listening_stats helpers:


def set_time_range_parameters(time_range, start_date=None, end_date=None):
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
        except ValueError as e:
            logger.error(f"Invalid date format: {e}")
            since = None
            until = None
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
    else:
        since = None
        until = None
        truncate_func = TruncMonth("played_at")
        x_label = "Month"

    return since, until, truncate_func, x_label


def calculate_aggregate_statistics(tracks):
    stats_aggregate = tracks.aggregate(
        total_tracks=Count("stream_id"),
        total_minutes_streamed=Sum("duration_ms") / 60000.0,
        different_tracks=Count("track_id", distinct=True),
        different_artists=Count("artist_name", distinct=True),
        different_albums=Count("album_name", distinct=True),
        first_play_date=Min("played_at"),
        last_play_date=Max("played_at"),
    )
    return stats_aggregate


def calculate_most_played_genre(tracks):
    genre_counts = Counter()
    for track in tracks:
        if track.genres:
            genre_counts.update(track.genres)
    most_played_genre = genre_counts.most_common(1)
    return most_played_genre[0][0].capitalize() if most_played_genre else "N/A"


def calculate_top_listening_hour(tracks):
    top_listening_hour = (
        tracks.annotate(hour=ExtractHour("played_at"))
        .values("hour")
        .annotate(hour_count=Count("hour"))
        .order_by("-hour_count")
        .first()
    )
    return f"{top_listening_hour['hour']}:00" if top_listening_hour else "N/A"


def calculate_most_popular_day(tracks):
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


def calculate_days_streamed(stats_aggregate):
    if stats_aggregate["first_play_date"] and stats_aggregate["last_play_date"]:
        return (
            stats_aggregate["last_play_date"] - stats_aggregate["first_play_date"]
        ).days + 1
    else:
        return 0


def calculate_average_listening_time_per_day(stats_aggregate):
    if stats_aggregate["days_streamed"] > 0:
        return (
            stats_aggregate["total_minutes_streamed"] / stats_aggregate["days_streamed"]
        )
    else:
        return 0


def generate_all_periods(since, until, truncate_func):
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


def populate_dates_and_counts(all_periods, count_dict, truncate_func):
    dates = []
    counts = []

    if not count_dict:
        return dates, counts

    sample_key = next(iter(count_dict))

    # Handle datetime objects as dictionary keys
    if isinstance(sample_key, datetime):
        # Format date based on truncate function
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

            # Find matching date in count_dict by comparing year, month, day, hour (if applicable)
            found = False
            for dt, count in count_dict.items():
                if period.date() == dt.date():
                    # For hour truncation, also check the hour
                    if isinstance(truncate_func, TruncHour) and period.hour != dt.hour:
                        continue
                    counts.append(count)
                    found = True
                    break

            if not found:
                counts.append(0)

        return dates, counts

    # Original string-based key handling
    date_format = "%Y-%m-%d"  # Default format

    # Check for various string formats
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


# get_streaming_trend_data helpers


async def get_trend_data(
    user, item, item_type, since, until, truncate_func, date_format, chart_format
):
    """Get trend data for visualization."""
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


def determine_truncate_func_and_formats(total_duration):
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


async def get_artist_track_count_helper(user, artist_id):
    """Helper function to get accurate track count for an artist using SpotifyClient."""
    cache_key = f"artist_total_tracks_{artist_id}"
    cached_count = cache.get(cache_key)

    if cached_count:
        return cached_count

    try:
        # Get total track count from SpotifyClient
        async with SpotifyClient(user.spotify_user_id) as client:
            # Use the function that gets all songs data for an artist
            data = await get_artist_all_songs_data(client, artist_id)
            tracks = data.get("tracks", [])
            total_tracks = len(tracks)

            # Cache the result for future use
            if total_tracks > 0:
                cache.set(cache_key, total_tracks, 604800)

            return total_tracks

    except Exception as e:
        logger.error(f"Error getting artist track count from Spotify: {e}")
        return 0
