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

    # Get the latest timestamp from the existing data
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
