import logging
from collections import Counter
from datetime import datetime, timedelta

from asgiref.sync import sync_to_async
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
from music.SpotifyClient import SpotifyClient
from spotify.util import get_user_tokens

SPOTIFY_API_BASE_URL = "https://api.spotify.com/v1"

logger = logging.getLogger(__name__)


async def read_full_history(self, *args, **options):
    # Retrieve all Spotify users
    users = await sync_to_async(list)(SpotifyUser.objects.all())
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

        latest_track = (
            PlayedTrack.objects.filter(user=spotify_user_id)
            .order_by("-played_at")
            .first()
        )
        after_timestamp = None
        if latest_track:
            after_timestamp = int(latest_track.played_at.timestamp() * 1000)

        try:
            async with SpotifyClient(spotify_user_id) as client:
                tracks = await client.get_recently_played_since(after_timestamp)

            for item in tracks:
                played_at_str = item["played_at"]
                played_at = timezone.datetime.strptime(
                    played_at_str, "%Y-%m-%dT%H:%M:%S.%fZ"
                )
                track = item["track"]
                await sync_to_async(PlayedTrack.objects.create)(
                    user=spotify_user_id,
                    track_id=track["id"],
                    played_at=played_at,
                    track_name=track["name"],
                    artist_name=track["artists"][0]["name"],
                    album_name=track["album"]["name"],
                )
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


def get_listening_stats(user, time_range="all_time", start_date=None, end_date=None):
    stats = {}

    # Set time range parameters
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
        # Aggregate to find the earliest and latest played_at dates
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
            # Parse and make aware
            naive_start = datetime.strptime(start_date, "%Y-%m-%d")
            naive_end = datetime.strptime(end_date, "%Y-%m-%d")

            since = timezone.make_aware(naive_start)
            until = timezone.make_aware(naive_end) + timedelta(days=1)
        except ValueError as e:
            logger.error(f"Invalid date format: {e}")
            since = None
            until = None

        total_duration = (until - since).days if since and until else None
        # Set truncate_func and x_label based on duration
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
        # Default to all time
        since = None
        until = None
        truncate_func = TruncMonth("played_at")
        x_label = "Month"

    # Filter tracks based on time range
    tracks = PlayedTrack.objects.filter(user=user)
    if since:
        tracks = tracks.filter(played_at__gte=since)
    if until:
        tracks = tracks.filter(played_at__lt=until)

    # Add debug logging
    logger.debug(f"Total tracks found: {tracks.count()}")

    # Calculate aggregate statistics
    stats_aggregate = tracks.aggregate(
        total_tracks=Count("stream_id"),
        total_minutes_streamed=Sum("duration_ms") / 60000.0,
        different_tracks=Count("track_id", distinct=True),
        different_artists=Count("artist_name", distinct=True),
        different_albums=Count("album_name", distinct=True),
        first_play_date=Min("played_at"),
        last_play_date=Max("played_at"),
    )

    # Calculate most played genre
    genre_counts = Counter()
    for track in tracks:
        if track.genres:
            genre_counts.update(track.genres)

    most_played_genre = genre_counts.most_common(1)
    stats_aggregate["most_played_genre"] = (
        most_played_genre[0][0].capitalize() if most_played_genre else "N/A"
    )

    # Calculate top listening hour
    top_listening_hour = (
        tracks.annotate(hour=ExtractHour("played_at"))
        .values("hour")
        .annotate(hour_count=Count("hour"))
        .order_by("-hour_count")
        .first()
    )
    stats_aggregate["top_listening_hour"] = (
        f"{top_listening_hour['hour']}:00" if top_listening_hour else "N/A"
    )

    # Calculate most popular day
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
            most_popular_day = days[weekday - 1]
        else:
            logger.error(f"Invalid weekday value: {weekday}")
            most_popular_day = "N/A"
    else:
        most_popular_day = "N/A"
    stats_aggregate["most_popular_day"] = most_popular_day

    # Calculate total days streamed
    if stats_aggregate["first_play_date"] and stats_aggregate["last_play_date"]:
        stats_aggregate["days_streamed"] = (
            stats_aggregate["last_play_date"] - stats_aggregate["first_play_date"]
        ).days + 1
    else:
        stats_aggregate["days_streamed"] = 0

    # Calculate average listening time per day
    if stats_aggregate["days_streamed"] > 0:
        stats_aggregate["average_listening_time_per_day"] = (
            stats_aggregate["total_minutes_streamed"] / stats_aggregate["days_streamed"]
        )
    else:
        stats_aggregate["average_listening_time_per_day"] = 0

    # Add debug logging for aggregates
    logger.debug(f"Stats aggregate: {stats_aggregate}")

    # Aggregate counts based on the truncate function with proper grouping
    date_counts = (
        tracks.annotate(period=truncate_func)
        .values("period")
        .annotate(count=Count("stream_id"))
        .order_by("period")
    )

    # Add debug logging for date_counts
    logger.debug(f"Date counts query: {date_counts.query}")
    logger.debug(f"Date counts: {list(date_counts)}")

    # Create a dictionary from date_counts for quick lookup
    count_dict = {item["period"]: item["count"] for item in date_counts}

    # Generate all periods within the range
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
        # If no 'since', use the earliest period in date_counts or default to now
        if date_counts.exists():
            current = date_counts.first()["period"]
        else:
            current = timezone.now()

    # Ensure 'current' is timezone-aware
    if not timezone.is_aware(current):
        current = timezone.make_aware(current)

    # Generate all periods
    while current <= until:
        all_periods.append(current)

        if isinstance(truncate_func, TruncWeek):
            current += timedelta(weeks=1)
        elif isinstance(truncate_func, TruncMonth):
            # Advance to the next month
            if current.month == 12:
                current = current.replace(year=current.year + 1, month=1)
            else:
                current = current.replace(month=current.month + 1)
        elif isinstance(truncate_func, TruncDay):
            current += timedelta(days=1)
        elif isinstance(truncate_func, TruncHour):
            current += timedelta(hours=1)

    # Populate dates and counts arrays
    dates = []
    counts = []
    for period in all_periods:
        # Normalize period to match count_dict keys
        if not isinstance(truncate_func, TruncHour):
            period = period.replace(hour=0, minute=0, second=0, microsecond=0)

        if isinstance(truncate_func, TruncHour):
            date_str = period.strftime("%Y-%m-%d %H:%M")
        else:
            date_str = period.strftime("%Y-%m-%d")

        # Get count for this period, defaulting to 0 if not found
        count = count_dict.get(period, 0)

        dates.append(date_str)
        counts.append(count)

    stats.update(
        {
            "dates": dates,
            "counts": counts,
            "x_label": x_label,
            "total_tracks": stats_aggregate["total_tracks"],
            "total_minutes_streamed": stats_aggregate["total_minutes_streamed"],
            "different_tracks": stats_aggregate["different_tracks"],
            "different_artists": stats_aggregate["different_artists"],
            "different_albums": stats_aggregate["different_albums"],
            "days_streamed": stats_aggregate["days_streamed"],
            "average_listening_time_per_day": stats_aggregate[
                "average_listening_time_per_day"
            ],
            "most_played_genre": stats_aggregate["most_played_genre"],
            "top_listening_hour": stats_aggregate["top_listening_hour"],
            "most_popular_day": stats_aggregate["most_popular_day"],
        }
    )

    # Add final debug logging
    logger.debug(f"Final stats: {stats}")

    return stats


async def get_top_tracks(user, since=None, until=None, limit=10):
    @sync_to_async
    def get_tracks():
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

    try:
        async with SpotifyClient(user.spotify_user_id) as client:
            for track in top_tracks:
                album = await client.get_album(track["album_id"])
                track["album_image"] = (
                    album.get("images", [{}])[0].get("url") if album else None
                )
    except Exception as e:
        logger.error(f"Error fetching album details: {e}")

    return top_tracks


async def get_top_artists(user, since=None, until=None, limit=10):
    @sync_to_async
    def get_artists():
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

    try:
        async with SpotifyClient(user.spotify_user_id) as client:
            for artist in top_artists:
                artist_details = await client.get_artist(artist["artist_id"])
                artist["image"] = artist_details.get("images", [])
                artist["name"] = artist["artist_name"]
    except Exception as e:
        logger.error(f"Error fetching artist details: {e}")
    return top_artists


async def get_recently_played(user, since=None, until=None, limit=10):
    @sync_to_async
    def get_tracks():
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

    try:
        async with SpotifyClient(user.spotify_user_id) as client:
            for track in recently_played:
                album = await client.get_album(track["album_id"])
                track["album_image"] = (
                    album.get("images", [{}])[0].get("url") if album else None
                )
    except Exception as e:
        logger.error(f"Error fetching album details: {e}")

    return recently_played


async def get_top_genres(user, since=None, until=None, limit=10):
    @sync_to_async
    def get_genres():
        tracks_query = PlayedTrack.objects.filter(user=user)
        if since:
            tracks_query = tracks_query.filter(played_at__gte=since)
        if until:
            tracks_query = tracks_query.filter(played_at__lt=until)

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

    genre_counter = Counter(all_genres)
    top_genres = genre_counter.most_common(limit)
    top_genres = [{"genre": genre, "count": count} for genre, count in top_genres]
    return top_genres


async def get_top_albums(user, since=None, until=None, limit=10):
    @sync_to_async
    def get_albums():
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

    try:
        async with SpotifyClient(user.spotify_user_id) as client:
            for album in top_albums:
                album_details = await client.get_album(album["album_id"])
                album["image"] = album_details.get("images", [])
                album["release_date"] = album_details.get("release_date")
                album["total_tracks"] = album_details.get("total_tracks")
    except Exception as e:
        logger.error(f"Error fetching album details: {e}")

    return top_albums
