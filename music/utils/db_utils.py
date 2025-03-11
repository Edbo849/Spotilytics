import asyncio
import logging
from collections import Counter
from datetime import datetime, timedelta

from asgiref.sync import sync_to_async
from django.core.cache import cache
from django.db import transaction
from django.db.models import Avg, Count, Sum
from django.db.models.functions import (
    ExtractHour,
    TruncDate,
    TruncDay,
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


async def read_full_history(self, *args, **options):
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

        after_timestamp = get_latest_track_timestamp(spotify_user_id)

        try:
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
def save_tracks_atomic(user, track_info_list, track_details_dict, artist_details_dict):
    count = 0
    with transaction.atomic():
        for info in track_info_list:
            track_data = get_track_details(
                info, track_details_dict, artist_details_dict
            )

            if track_exists(user, track_data["track_id"], track_data["played_at"]):
                logger.info(
                    f"Duplicate track found: {track_data['track_id']} at {track_data['played_at']}. Skipping."
                )
                continue

            if create_played_track(user, track_data):
                count += 1

    return count


def get_listening_stats(user, time_range="all_time", start_date=None, end_date=None):
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

    # Calculate most played genre
    stats_aggregate["most_played_genre"] = calculate_most_played_genre(tracks)

    # Calculate top listening hour
    stats_aggregate["top_listening_hour"] = calculate_top_listening_hour(tracks)

    # Calculate most popular day
    stats_aggregate["most_popular_day"] = calculate_most_popular_day(tracks)

    # Calculate total days streamed
    stats_aggregate["days_streamed"] = calculate_days_streamed(stats_aggregate)

    # Calculate average listening time per day
    stats_aggregate["average_listening_time_per_day"] = (
        calculate_average_listening_time_per_day(stats_aggregate)
    )

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
    all_periods = generate_all_periods(since, until, truncate_func)

    # Populate dates and counts arrays
    dates, counts = populate_dates_and_counts(all_periods, count_dict, truncate_func)

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
                        cache.set(cache_key, album_image, timeout=client.CACHE_TIMEOUT)

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
                        cache.set(
                            cache_key,
                            artist_details,
                            timeout=client.CACHE_TIMEOUT,
                        )

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
                        cache.set(cache_key, album_image, timeout=client.CACHE_TIMEOUT)

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
                        cache.set(
                            cache_key, album_details, timeout=client.CACHE_TIMEOUT
                        )

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

    truncate_func, date_format, chart_format = determine_truncate_func_and_formats(
        total_duration
    )

    all_dates = set()
    trend_data = []

    if not isinstance(items, list):
        items = [items]

    for idx, item in enumerate(items[:limit]):
        dates, counts, raw_dates, label = await get_trend_data(
            user,
            item,
            item_type,
            since,
            until,
            truncate_func,
            date_format,
            chart_format,
        )
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

    if not isinstance(items, list):
        items = [items]

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

    if not isinstance(items, list):
        items = [items]

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

    if not isinstance(items, list):
        items = [items]

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

    if not isinstance(items, list):
        items = [items]

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

    if not isinstance(items, list):
        items = [items]

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


## Stats Section


async def get_listening_history_data(user, item, item_type, since, until):
    """Get line graph data showing listening over time."""

    @sync_to_async
    def get_data():
        base_query = PlayedTrack.objects.filter(user=user)
        if since:
            base_query = base_query.filter(played_at__gte=since)
        if until:
            base_query = base_query.filter(played_at__lte=until)

        # Filter based on item type
        if item_type == "artist":
            query = base_query.filter(artist_id=item["artist_id"])
        elif item_type == "album":
            query = base_query.filter(album_id=item["album_id"])
        elif item_type == "track":
            query = base_query.filter(track_id=item["track_id"])

        # Group plays by day
        plays_by_date = {}
        for track in query:
            date_key = track.played_at.date().isoformat()
            plays_by_date[date_key] = plays_by_date.get(date_key, 0) + 1

        # Generate full date range including days with zero plays
        dates = []
        plays = []

        if query.exists():
            current_date = (
                since.date() if since else query.earliest("played_at").played_at.date()
            )
            end_date = (
                until.date() if until else query.latest("played_at").played_at.date()
            )

            while current_date <= end_date:
                date_str = current_date.isoformat()
                dates.append(date_str)
                plays.append(plays_by_date.get(date_str, 0))
                current_date += timedelta(days=1)

        return {"labels": dates, "values": plays}

    result = await get_data()
    return result


async def get_listening_context_data(user, item, item_type, since, until):
    """Get data showing when an item is typically played throughout the day."""

    @sync_to_async
    def get_data():
        base_query = PlayedTrack.objects.filter(user=user)
        if since:
            base_query = base_query.filter(played_at__gte=since)
        if until:
            base_query = base_query.filter(played_at__lte=until)

        # Filter based on item type
        if item_type == "artist":
            query = base_query.filter(artist_id=item["artist_id"])
        elif item_type == "album":
            query = base_query.filter(album_id=item["album_id"])
        elif item_type == "track":
            query = base_query.filter(track_id=item["track_id"])

        # Define time categories
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

        # Calculate percentage for each category
        total = sum(counts.values())
        percentages = {}
        for category, count in counts.items():
            percentages[category] = round((count / total * 100) if total > 0 else 0, 1)

        # Prepare data for the chart
        labels = list(time_categories.keys())
        values = [counts[category] for category in labels]
        percentages_list = [percentages[category] for category in labels]

        # Add context descriptions
        contexts = {
            "Night (12am-6am)": "Late night listening",
            "Morning (6am-12pm)": "Morning routine & commute",
            "Afternoon (12pm-6pm)": "Work & daytime activities",
            "Evening (6pm-12am)": "Evening relaxation & social",
        }

        context_descriptions = [contexts[category] for category in labels]

        return {
            "labels": labels,
            "values": values,
            "percentages": percentages_list,
            "contexts": context_descriptions,
            "total_plays": total,
        }

    result = await get_data()
    return result


async def get_repeat_listen_histogram_data(user, item, item_type, since, until):
    """Get histogram data showing time between repeat listens."""

    @sync_to_async
    def get_data():
        base_query = PlayedTrack.objects.filter(user=user)
        if since:
            base_query = base_query.filter(played_at__gte=since)
        if until:
            base_query = base_query.filter(played_at__lte=until)

        # Filter based on item type
        if item_type == "artist":
            query = base_query.filter(artist_id=item["artist_id"])
        elif item_type == "album":
            query = base_query.filter(album_id=item["album_id"])
        elif item_type == "track":
            query = base_query.filter(track_id=item["track_id"])

        # Sort plays chronologically
        plays = list(query.order_by("played_at"))

        intervals = []
        for i in range(1, len(plays)):
            interval_seconds = (
                plays[i].played_at - plays[i - 1].played_at
            ).total_seconds()
            # Only count intervals less than 30 days
            if interval_seconds < 30 * 24 * 60 * 60:
                intervals.append(interval_seconds / 3600)  # Convert to hours

        # Create histogram bins
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

        for interval in intervals:
            for i, upper_bound in enumerate(bins[1:]):
                if interval < upper_bound:
                    counts[i] += 1
                    break

        return {"labels": bin_labels, "values": counts}

    result = await get_data()
    return result


async def get_listening_time_distribution_data(user, item, item_type, since, until):
    """Get polar area chart data showing times of day listening to item."""

    @sync_to_async
    def get_data():
        base_query = PlayedTrack.objects.filter(user=user)
        if since:
            base_query = base_query.filter(played_at__gte=since)
        if until:
            base_query = base_query.filter(played_at__lte=until)

        # Filter based on item type
        if item_type == "artist":
            query = base_query.filter(artist_id=item["artist_id"])
        elif item_type == "album":
            query = base_query.filter(album_id=item["album_id"])
        elif item_type == "track":
            query = base_query.filter(track_id=item["track_id"])

        # Group by 3-hour periods
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

        for track in query:
            hour = track.played_at.hour
            period_index = hour // 3
            counts[period_index] += 1

        return {"labels": time_periods, "values": counts}

    result = await get_data()
    return result


async def get_artist_genre_distribution(user, since, until, item):
    """Get genre distribution for an artist's tracks."""

    @sync_to_async
    def get_data():
        base_query = PlayedTrack.objects.filter(user=user)
        if since:
            base_query = base_query.filter(played_at__gte=since)
        if until:
            base_query = base_query.filter(played_at__lte=until)

        query = base_query.filter(artist_id=item["artist_id"])

        # Collect all genres from the tracks
        genre_counts = Counter()
        for track in query:
            if track.genres:
                genre_counts.update(track.genres)

        top_genres = genre_counts.most_common(10)

        return {
            "labels": [g[0] for g in top_genres],
            "values": [g[1] for g in top_genres],
        }

    result = await get_data()
    return result


async def get_artist_discography_coverage(user, artist_id):
    """Get percentage of artist's discography played by the user."""

    @sync_to_async
    def get_played_tracks_count():
        # Get all tracks from this artist that the user has played
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

    # Fall back to database query if the helper function returns 0
    if total_tracks == 0:

        @sync_to_async
        def get_all_artist_tracks_count():
            return (
                PlayedTrack.objects.filter(artist_id=artist_id)
                .values_list("track_id", flat=True)
                .distinct()
                .count()
            )

        total_tracks = await get_all_artist_tracks_count()

        # If that's still too small, use a conservative estimate
        if total_tracks < played_count or total_tracks < 10:
            total_tracks = max(played_count * 3, 10)

    # Avoid division by zero
    if total_tracks == 0:
        total_tracks = played_count or 1

    percentage = (played_count / total_tracks * 100) if total_tracks > 0 else 0

    result = {
        "played_count": played_count,
        "total_count": total_tracks,
        "percentage": percentage,
    }

    return result


async def get_track_duration_comparison(user, since, until, item):
    """Compare average listening duration to track's full duration."""

    @sync_to_async
    def get_data():
        base_query = PlayedTrack.objects.filter(user=user)
        if since:
            base_query = base_query.filter(played_at__gte=since)
        if until:
            base_query = base_query.filter(played_at__lte=until)

        query = base_query.filter(track_id=item["track_id"])

        # Calculate average listening duration from user history
        total_duration = 0
        count = 0

        for played in query:
            if hasattr(played, "duration_ms") and played.duration_ms:
                total_duration += played.duration_ms / 1000
                count += 1
        if count == 0:
            average_duration = 0
        else:
            average_duration = total_duration / count

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
        track_duration = track_details["duration_ms"] / 1000
    else:
        # Fallback if we can't get the official duration
        track_duration = 180  # Default to 3 minutes

    # Calculate percentage with accurate track duration
    percentage = (
        min(result["average_duration"] / track_duration, 1.0)
        if track_duration > 0 and result["count"] > 0
        else 0
    )

    return {
        "average_duration": result["average_duration"],
        "track_duration": track_duration,
        "percentage": percentage,
    }


async def get_artist_tracks_coverage(user, artist_id):
    """Get percentage of artist's tracks played by the user."""

    @sync_to_async
    def get_played_tracks_count():
        # Get all tracks from this artist that the user has played
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

    # Fall back to database query if the helper function returns 0
    if total_tracks == 0:

        @sync_to_async
        def get_all_artist_tracks_count():
            return (
                PlayedTrack.objects.filter(artist_id=artist_id)
                .values_list("track_id", flat=True)
                .distinct()
                .count()
            )

        total_tracks = await get_all_artist_tracks_count()

        # If that's still too small, use a conservative estimate
        if total_tracks < played_count or total_tracks < 10:
            total_tracks = max(played_count * 2, 10)

    # Avoid division by zero
    if total_tracks == 0:
        total_tracks = played_count or 1

    percentage = (played_count / total_tracks * 100) if total_tracks > 0 else 0

    result = {
        "played_count": played_count,
        "total_count": total_tracks,
        "percentage": percentage,
    }

    return result


async def get_album_track_plays(user, since, until, item):
    """Get play counts for each track in an album."""

    @sync_to_async
    def get_base_data():
        base_query = PlayedTrack.objects.filter(user=user)
        if since:
            base_query = base_query.filter(played_at__gte=since)
        if until:
            base_query = base_query.filter(played_at__lte=until)

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
        # This is now in the async function, not inside the sync_to_async function
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

                def truncate_name(name):
                    if len(name) > 20:
                        return name[:20] + "..."
                    return name

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


async def get_album_tracks_coverage(user, album_id):
    """Get percentage of album tracks played by the user."""

    @sync_to_async
    def get_played_tracks_count():
        # Get all tracks from this album that the user has played
        played_tracks = (
            PlayedTrack.objects.filter(user=user, album_id=album_id)
            .values_list("track_id", flat=True)
            .distinct()
        )
        return len(played_tracks)

    # Get played tracks count from the database
    played_count = await get_played_tracks_count()

    # Get the actual total track count from Spotify API
    try:
        async with SpotifyClient(user.spotify_user_id) as client:
            album_details = await client.get_album(album_id)

            if album_details and "total_tracks" in album_details:
                total_tracks = album_details["total_tracks"]
            elif (
                album_details
                and "tracks" in album_details
                and "items" in album_details["tracks"]
            ):
                total_tracks = len(album_details["tracks"]["items"])
            else:
                # Fallback to database estimate if API data is incomplete
                total_tracks = max(played_count, 10)
    except Exception as e:
        logger.error(f"Error getting album track count from Spotify: {e}")
        total_tracks = max(played_count, 10)  # Conservative fallback

    # Avoid division by zero
    if total_tracks == 0:
        total_tracks = played_count or 1

    percentage = (played_count / total_tracks * 100) if total_tracks > 0 else 0

    return {
        "played_count": played_count,
        "total_count": total_tracks,
        "percentage": percentage,
    }


async def get_user_played_tracks(user, track_ids=None, artist_id=None, album_id=None):
    """Get a set of track_ids that the user has listened to.
    Filter by specific tracks, artist, or album if provided."""

    @sync_to_async
    def get_data():
        query = PlayedTrack.objects.filter(user=user)

        if track_ids:
            query = query.filter(track_id__in=track_ids)
        if artist_id:
            query = query.filter(artist_id=artist_id)
        if album_id:
            query = query.filter(album_id=album_id)

        return set(query.values_list("track_id", flat=True).distinct())

    return await get_data()
