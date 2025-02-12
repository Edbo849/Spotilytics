import hashlib
import json
import logging
import os
from collections import Counter
from datetime import datetime, timedelta

from asgiref.sync import sync_to_async
from django.conf import settings
from django.core.cache import cache
from django.core.files.storage import default_storage
from django.db import IntegrityError, transaction
from django.db.models import Avg, Count, Max, Min, Sum
from django.db.models.functions import (ExtractHour, ExtractWeekDay, TruncDate,
                                        TruncDay, TruncHour, TruncMonth,
                                        TruncWeek)
from django.http import HttpRequest, HttpResponse
from django.shortcuts import redirect
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt

from music.core.models import PlayedTrack, SpotifyUser
from music.services.SpotifyClient import SpotifyClient
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
                cache_key = f"album_image_{track['album_id']}"
                album_image = cache.get(cache_key)

                if album_image is None:
                    album = await client.get_album(track["album_id"])
                    album_image = (
                        album.get("images", [{}])[0].get("url") if album else None
                    )
                    if album_image:
                        cache.set(cache_key, album_image, timeout=None)

                track["album_image"] = album_image
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
                cache_key = f"artist_details_{artist['artist_id']}"
                artist_details = cache.get(cache_key)

                if artist_details is None:
                    artist_details = await client.get_artist(artist["artist_id"])
                    if artist_details:
                        cache.set(cache_key, artist_details, timeout=None)

                artist["image"] = (
                    artist_details.get("images", []) if artist_details else []
                )
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
                cache_key = f"album_image_{track['album_id']}"
                album_image = cache.get(cache_key)

                if album_image is None:
                    album = await client.get_album(track["album_id"])
                    album_image = (
                        album.get("images", [{}])[0].get("url") if album else None
                    )
                    if album_image:
                        cache.set(cache_key, album_image, timeout=None)

                track["album_image"] = album_image
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
                cache_key = f"album_details_{album['album_id']}"
                album_details = cache.get(cache_key)

                if album_details is None:
                    album_details = await client.get_album(album["album_id"])
                    if album_details:
                        cache.set(cache_key, album_details, timeout=None)

                if album_details:
                    album["image"] = album_details.get("images", [])
                    album["release_date"] = album_details.get("release_date")
                    album["total_tracks"] = album_details.get("total_tracks")

    except Exception as e:
        logger.error(f"Error fetching album details: {e}")

    return top_albums


async def get_streaming_trend_data(user, since, until, items, item_type, limit=5):
    """Get streaming trend data for top items."""
    trends = []
    colors = ["#1DB954", "#FF6B6B", "#4A90E2", "#F7B731", "#A463F2"]

    total_duration = (until - since).days if since and until else None

    if total_duration:
        if total_duration <= 7:
            truncate_func = TruncDay("played_at")
            date_format = "%m-%d"
            all_dates = {
                (since + timedelta(days=x)).strftime(date_format) for x in range(8)
            }
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
    else:
        truncate_func = TruncMonth("played_at")
        date_format = "%b %Y"
        chart_format = "%Y-%m-%d"

    @sync_to_async
    def get_trend_data(item):
        counts = []
        dates = []
        raw_dates = []

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

        query = (
            query.annotate(period=truncate_func)
            .values("period")
            .annotate(count=Count("stream_id"))
            .order_by("period")
        )

        for entry in query:
            display_date = entry["period"].strftime(date_format)
            chart_date = entry["period"].strftime(chart_format)
            dates.append(display_date)
            raw_dates.append(chart_date)
            counts.append(entry["count"])

        return dates, counts, raw_dates, label

    all_dates = set()
    trend_data = []

    for idx, item in enumerate(items[:limit]):
        dates, counts, raw_dates, label = await get_trend_data(item)
        all_dates.update(zip(dates, raw_dates))
        trend_data.append(
            {
                "label": label
                or item.get("genre")
                or item.get("track_name")
                or item.get("album_name"),
                "data": counts,
                "dates": dates,
                "raw_dates": raw_dates,
                "color": colors[idx],
            }
        )

    sorted_date_pairs = sorted(all_dates, key=lambda x: x[1])
    display_dates, raw_dates = (
        zip(*sorted_date_pairs) if sorted_date_pairs else ([], [])
    )

    trends = []
    for trend in trend_data:
        normalized_counts = []
        date_to_count = dict(zip(trend["dates"], trend["data"]))

        for display_date in display_dates:
            normalized_counts.append(date_to_count.get(display_date, 0))

        trends.append(
            {
                "label": trend["label"],
                "data": normalized_counts,
                "color": trend["color"],
            }
        )

    return display_dates, trends


def format_day_suffix(day):
    if 4 <= day <= 20 or 24 <= day <= 30:
        suffix = "th"
    else:
        suffix = ["st", "nd", "rd"][day % 10 - 1]
    return suffix


def format_date(date):
    suffix = format_day_suffix(date.day)
    return date.strftime(f"%A {date.day}{suffix} %B %Y")


def get_longest_streak(user, start_date, end_date):
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

    longest_streak = 1
    current_streak = 1
    current_streak_start = played_tracks[0]["played_day"]
    longest_streak_start = current_streak_start
    longest_streak_end = current_streak_start
    previous_date = played_tracks[0]["played_day"]

    for i in range(1, len(played_tracks)):
        current_date = played_tracks[i]["played_day"]

        if current_date == previous_date + timedelta(days=1):
            current_streak += 1
        else:
            current_streak = 1
            current_streak_start = current_date

        if current_streak > longest_streak:
            longest_streak = current_streak
            longest_streak_start = current_streak_start
            longest_streak_end = current_date

        previous_date = current_date

    longest_streak_start_formatted = format_date(longest_streak_start)
    longest_streak_end_formatted = format_date(longest_streak_end)

    return longest_streak, longest_streak_start_formatted, longest_streak_end_formatted


async def get_dashboard_stats(user, since, until):
    """Get dashboard statistics."""

    @sync_to_async
    def get_data():
        base_query = PlayedTrack.objects.filter(user=user)

        if since:
            base_query = base_query.filter(played_at__gte=since)
        if until:
            base_query = base_query.filter(played_at__lte=until)

        total_days = (until - since).days + 1
        days_with_music = base_query.dates("played_at", "day").count()
        coverage_percentage = (
            (days_with_music / total_days * 100) if total_days > 0 else 0
        )

        dates = list(
            base_query.dates("played_at", "day").order_by("played_at").distinct()
        )
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

        streak, streak_start, streak_end = get_longest_streak(user, since, until)

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


async def get_stats_boxes_data(user, since, until, items, item_type):
    """Get stats box data that works across all item types."""

    @sync_to_async
    def get_data():
        base_query = PlayedTrack.objects.filter(user=user)
        if since:
            base_query = base_query.filter(played_at__gte=since)
        if until:
            base_query = base_query.filter(played_at__lte=until)

        total_all_plays = base_query.count()

        if item_type == "artist":
            total_items = base_query.values("artist_name").distinct().count()
        elif item_type == "genre":
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

        total_plays = 0
        total_minutes = 0
        days_with_plays = set()

        for item in items[:3]:
            if item_type == "artist":
                query = base_query.filter(artist_name=item["artist_name"])
            elif item_type == "genre":
                query = base_query.filter(genres__contains=[item["genre"]])
            elif item_type == "track":
                query = base_query.filter(track_id=item["track_id"])
            elif item_type == "album":
                query = base_query.filter(album_id=item["album_id"])

            plays = query.count()
            total_plays += plays
            minutes = (
                query.aggregate(total_time=Sum("duration_ms"))["total_time"] or 0
            ) / 60000
            total_minutes += minutes
            days_with_plays.update(query.dates("played_at", "day"))

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


async def get_radar_chart_data(user, since, until, items, item_type, limit=5):
    """Get radar chart data for top items."""
    radar_data = []
    colors = [
        "rgba(29, 185, 84, 0.2)",
        "rgba(255, 107, 107, 0.2)",
        "rgba(74, 144, 226, 0.2)",
        "rgba(247, 183, 49, 0.2)",
        "rgba(164, 99, 242, 0.2)",
    ]
    border_colors = ["#1DB954", "#FF6B6B", "#4A90E2", "#F7B731", "#A463F2"]

    @sync_to_async
    def calculate_metrics(item):
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
            "total_time": total_time / 60000,
            "unique_tracks": unique_tracks,
            "variety": variety,
            "average_popularity": average_popularity,
        }

    metrics_list = []
    for idx, item in enumerate(items[:limit]):
        metrics = await calculate_metrics(item)
        metrics["backgroundColor"] = colors[idx % len(colors)]
        metrics["borderColor"] = border_colors[idx % len(border_colors)]
        metrics_list.append(metrics)

    max_values = {
        "total_plays": max(m["total_plays"] for m in metrics_list) or 1,
        "total_time": max(m["total_time"] for m in metrics_list) or 1,
        "unique_tracks": max(m["unique_tracks"] for m in metrics_list) or 1,
        "variety": max(m["variety"] for m in metrics_list) or 1,
        "average_popularity": max(m["average_popularity"] for m in metrics_list) or 1,
    }

    for metrics in metrics_list:
        metrics["total_plays"] = (
            metrics["total_plays"] / max_values["total_plays"]
        ) * 100
        metrics["total_time"] = (metrics["total_time"] / max_values["total_time"]) * 100
        metrics["unique_tracks"] = (
            metrics["unique_tracks"] / max_values["unique_tracks"]
        ) * 100
        metrics["variety"] = (metrics["variety"] / max_values["variety"]) * 100
        metrics["average_popularity"] = (
            metrics["average_popularity"] / max_values["average_popularity"]
        ) * 100
        radar_data.append(metrics)

    return radar_data


async def get_doughnut_chart_data(user, since, until, items, item_type):
    """Get doughnut chart data for top items."""
    doughnut_data = []
    colors = [
        "#FF6384",
        "#36A2EB",
        "#FFCE56",
        "#4BC0C0",
        "#9966FF",
    ]

    @sync_to_async
    def calculate_total_minutes(item):
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

        total_minutes = (
            query.aggregate(total_time=Sum("duration_ms"))["total_time"] or 0
        )
        total_minutes = total_minutes / 60000

        if len(label) > 25:
            label = f"{label[:22]}..."

        return {
            "label": label,
            "total_minutes": total_minutes,
        }

    @sync_to_async
    def calculate_total_listening_time():
        base_query = PlayedTrack.objects.filter(user=user)
        if since:
            base_query = base_query.filter(played_at__gte=since)
        if until:
            base_query = base_query.filter(played_at__lte=until)

        total_minutes = (
            base_query.aggregate(total_time=Sum("duration_ms"))["total_time"] or 0
        )
        return total_minutes / 60000

    total_listening_time = await calculate_total_listening_time()

    for item in items:
        metrics = await calculate_total_minutes(item)
        doughnut_data.append(metrics)

    for data in doughnut_data:
        data["percentage"] = (
            (data["total_minutes"] / total_listening_time) * 100
            if total_listening_time > 0
            else 0
        )

    labels = [data["label"] for data in doughnut_data]
    values = [data["percentage"] for data in doughnut_data]
    background_colors = [colors[idx % len(colors)] for idx in range(len(doughnut_data))]

    return labels, values, background_colors


async def get_hourly_listening_data(user, since, until, item_type, item=None):
    """Get hourly listening data for a specific item or all items."""

    @sync_to_async
    def get_data():
        base_query = PlayedTrack.objects.filter(user=user)
        if since:
            base_query = base_query.filter(played_at__gte=since)
        if until:
            base_query = base_query.filter(played_at__lte=until)

        if item:
            if item_type == "artist":
                base_query = base_query.filter(artist_name=item["artist_name"])
            elif item_type == "genre":
                base_query = base_query.filter(genres__contains=[item["genre"]])
            elif item_type == "track":
                base_query = base_query.filter(track_id=item["track_id"])
            elif item_type == "album":
                base_query = base_query.filter(album_id=item["album_id"])

        hourly_data = (
            base_query.annotate(hour=ExtractHour("played_at"))
            .values("hour")
            .annotate(total_minutes=Sum("duration_ms") / 60000.0)
            .order_by("hour")
        )

        hours = list(range(24))
        minutes_by_hour = {
            entry["hour"]: entry["total_minutes"] for entry in hourly_data
        }

        return [minutes_by_hour.get(hour, 0) for hour in hours]

    return await get_data()


async def get_bubble_chart_data(user, since, until, items, item_type):
    """Get bubble chart data showing play patterns."""

    @sync_to_async
    def get_data():
        base_query = PlayedTrack.objects.filter(user=user)
        if since:
            base_query = base_query.filter(played_at__gte=since)
        if until:
            base_query = base_query.filter(played_at__lte=until)

        data_points = []

        for item in items:
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

            play_count = query.count()

            avg_popularity = query.aggregate(Avg("popularity"))["popularity__avg"] or 0

            total_minutes = (
                query.aggregate(total_time=Sum("duration_ms"))["total_time"] or 0
            ) / 60000

            if play_count > 0:
                data_points.append(
                    {
                        "x": avg_popularity,
                        "y": total_minutes,
                        "r": play_count * 2,
                        "name": name,
                    }
                )

        return data_points

    return await get_data()


async def get_discovery_timeline_data(user, since, until, item_type):
    """Get cumulative discovery data showing when new items were first encountered."""
    total_duration = (until - since).days if since and until else None

    # Set time grouping based on duration
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
    def get_data():
        base_query = PlayedTrack.objects.filter(user=user)
        if since:
            base_query = base_query.filter(played_at__gte=since)
        if until:
            base_query = base_query.filter(played_at__lte=until)

        periods = (
            base_query.annotate(period=truncate_func)
            .values("period")
            .distinct()
            .order_by("period")
        )

        dates = []
        counts = []

        for period_data in periods:
            period = period_data["period"]

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
                items = base_query.filter(played_at__lte=period).exclude(genres=[])
                current_items = set()
                for item in items:
                    current_items.update(item.genres)

            if current_items:
                dates.append(period.strftime(date_format))
                counts.append(len(current_items))

        return dates, counts

    return await get_data()


async def get_time_period_distribution(user, since, until, items, item_type):
    """Get listening distribution across different time periods."""

    @sync_to_async
    def get_data():
        base_query = PlayedTrack.objects.filter(user=user)
        if since:
            base_query = base_query.filter(played_at__gte=since)
        if until:
            base_query = base_query.filter(played_at__lte=until)

        periods = {
            "Morning (6-12)": (6, 12),
            "Afternoon (12-18)": (12, 18),
            "Evening (18-24)": (18, 24),
            "Night (0-6)": (0, 6),
        }

        datasets = []
        for item in items[:5]:
            period_data = []

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

            for period_name, (start_hour, end_hour) in periods.items():
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

            datasets.append(
                {
                    "label": label,
                    "data": period_data,
                    "backgroundColor": f"rgba(29, 185, 84, {0.8 - (len(datasets) * 0.1)})",
                }
            )

        return list(periods.keys()), datasets

    return await get_data()


async def get_replay_gaps(user, since, until, items, item_type):
    """Calculate average time between repeated listens."""

    @sync_to_async
    def get_data():
        gaps = []
        labels = []

        for item in items[:10]:
            query = PlayedTrack.objects.filter(user=user)
            if since:
                query = query.filter(played_at__gte=since)
            if until:
                query = query.filter(played_at__lte=until)

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

            plays = query.order_by("played_at").values_list("played_at", flat=True)
            if len(plays) < 2:
                continue

            total_gap = 0
            play_count = 0

            for i in range(1, len(plays)):
                gap = (plays[i] - plays[i - 1]).total_seconds() / 3600
                if gap <= 168:
                    total_gap += gap
                    play_count += 1

            if play_count > 0:
                avg_gap = total_gap / play_count
                gaps.append(round(avg_gap, 1))
                if len(label) > 20:
                    label = f"{label[:17]}..."
                labels.append(label)

        return labels, gaps

    return await get_data()


async def get_date_range(
    time_range: str, start_date: str | None = None, end_date: str | None = None
) -> tuple[datetime, datetime]:
    """Get date range based on time range selection."""
    until = timezone.now()

    @sync_to_async
    def get_earliest_track():
        return PlayedTrack.objects.order_by("played_at").first()

    if time_range == "last_7_days":
        since = until - timedelta(days=7)
    elif time_range == "last_4_weeks":
        since = until - timedelta(weeks=4)
    elif time_range == "6_months":
        since = until - timedelta(days=182)
    elif time_range == "last_year":
        since = until - timedelta(days=365)
    elif time_range == "all_time":
        earliest_track = await get_earliest_track()
        since = (
            earliest_track.played_at if earliest_track else until - timedelta(days=365)
        )
    elif time_range == "custom" and start_date and end_date:
        try:
            since = timezone.make_aware(datetime.strptime(start_date, "%Y-%m-%d"))
            until = timezone.make_aware(
                datetime.strptime(end_date, "%Y-%m-%d")
            ) + timedelta(days=1)
        except ValueError:
            since = until - timedelta(weeks=4)
    else:
        since = until - timedelta(weeks=4)

    return since, until


def get_peak_position(
    user, item_id: str, item_type: str, since=None, until=None
) -> int:
    """Get the peak (highest) position achieved by an item in its category."""
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

    return 0


async def get_item_stats_util(
    user, item_id: str, item_type: str, since=None, until=None
):
    """Get stats for a specific item (track, album, or artist)."""

    @sync_to_async
    def get_data():
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

        total_plays = query.count()
        total_minutes = (
            query.aggregate(total_time=Sum("duration_ms"))["total_time"] or 0
        )

        # Calculate time gaps between plays
        plays = list(query.order_by("played_at").values_list("played_at", flat=True))
        gaps = []
        for i in range(1, len(plays)):
            gap = plays[i] - plays[i - 1]
            gaps.append(gap.total_seconds() / 3600)

        avg_gap = sum(gaps) / len(gaps) if gaps else 0

        # Calculate streak
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

        # Calculate peak day
        peak_day = (
            query.annotate(day=TruncDate("played_at"))
            .values("day")
            .annotate(count=Count("stream_id"))
            .order_by("-count")
            .first()
        )
        peak_day_plays = peak_day["count"] if peak_day else 0

        # Calculate prime time
        prime_time = (
            query.annotate(hour=ExtractHour("played_at"))
            .values("hour")
            .annotate(count=Count("stream_id"))
            .order_by("-count")
            .first()
        )
        prime_time_hour = f"{prime_time['hour']:02d}:00" if prime_time else "N/A"

        # Calculate repeat rate
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
            "total_minutes": total_minutes / 60000,
            "avg_gap": avg_gap,
            "peak_position": get_peak_position(user, item_id, item_type, since, until),
            "longest_streak": longest_streak,
            "peak_day_plays": peak_day_plays,
            "prime_time": prime_time_hour,
            "repeat_rate": round(repeat_rate, 1),
        }

    return await get_data()
