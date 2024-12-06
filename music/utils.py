from datetime import timedelta

from django.db.models import Count, Max, Min, Sum
from django.utils import timezone

from music.models import PlayedTrack
from music.spotify_api import get_recently_played_full
from spotify.util import get_user_tokens

SPOTIFY_API_BASE_URL = "https://api.spotify.com/v1"


def read_full_history(self, *args, **options):
    session_id = "your_session_id_here"
    tokens = get_user_tokens(session_id)
    if not tokens:
        self.stdout.write(self.style.ERROR("User not authenticated."))
        return

    latest_track = (
        PlayedTrack.objects.filter(user=session_id).order_by("-played_at").first()
    )
    after_timestamp = None
    if latest_track:
        after_timestamp = int(latest_track.played_at.timestamp() * 1000)

    tracks = get_recently_played_full(session_id, after=after_timestamp)

    for item in tracks:
        played_at_str = item["played_at"]
        played_at = timezone.datetime.strptime(played_at_str, "%Y-%m-%dT%H:%M:%S.%fZ")
        track = item["track"]
        PlayedTrack.objects.create(
            user=session_id,
            track_id=track["id"],
            played_at=played_at,
            track_name=track["name"],
            artist_name=track["artists"][0]["name"],
            album_name=track["album"]["name"],
        )
    self.stdout.write(self.style.SUCCESS(f"Fetched and stored {len(tracks)} tracks."))


def get_listening_stats(user, time_range="long_term"):
    if time_range == "short_term":
        since = timezone.now() - timedelta(weeks=4)
    elif time_range == "medium_term":
        since = timezone.now() - timedelta(weeks=24)
    else:
        since = None

    if since:
        tracks = PlayedTrack.objects.filter(user=user, played_at__gte=since)
    else:
        tracks = PlayedTrack.objects.filter(user=user)

    stats = tracks.aggregate(
        total_tracks=Count("stream_id"),
        total_minutes_streamed=Sum("duration_ms") / 60000.0,
        different_tracks=Count("track_id", distinct=True),
        different_artists=Count("artist_name", distinct=True),
        different_albums=Count("album_name", distinct=True),
        first_play_date=Min("played_at"),
        last_play_date=Max("played_at"),
    )

    if stats["first_play_date"] and stats["last_play_date"]:
        stats["days_streamed"] = (
            stats["last_play_date"].date() - stats["first_play_date"].date()
        ).days + 1
    else:
        stats["days_streamed"] = 0

    if stats["days_streamed"] > 0:
        stats["average_listening_time_per_day"] = (
            stats["total_minutes_streamed"] / stats["days_streamed"]
        )
    else:
        stats["average_listening_time_per_day"] = 0

    return stats
