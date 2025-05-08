import datetime
import logging

from asgiref.sync import async_to_sync, sync_to_async
from django.db import IntegrityError

from music.models import PlayedTrack, SpotifyUser
from music.services.SpotifyClient import SpotifyClient
from spotify.util import is_spotify_authenticated
from Spotilytics.celery import app

logger = logging.getLogger(__name__)


@app.task(name="music.services.tasks.update_played_tracks_task")
def update_played_tracks_task() -> None:
    """Celery task to update played tracks for all users."""
    async_to_sync(update_played_tracks)()


async def update_played_tracks() -> None:
    """
    Async function to update played tracks for all users.

    Fetches recently played tracks from Spotify for each authenticated user
    and stores them in the database.
    """
    users = await sync_to_async(list)(SpotifyUser.objects.all())

    for user in users:
        spotify_user_id = user.spotify_user_id

        # Skip unauthenticated users
        if not await sync_to_async(is_spotify_authenticated)(spotify_user_id):
            logger.info(f"User {spotify_user_id} is not authenticated. Skipping.")
            continue

        # Determine the timestamp from which to fetch new tracks
        latest_track = await sync_to_async(
            PlayedTrack.objects.filter(user=user).order_by("-played_at").first
        )()

        after_timestamp = (
            int(latest_track.played_at.timestamp() * 1000) if latest_track else 0
        )

        # Fetch recently played tracks from Spotify
        async with SpotifyClient(spotify_user_id) as client:
            recently_played = await client.get_recently_played_since(after_timestamp)

        if not recently_played:
            logger.info(f"No new recently played tracks for user {spotify_user_id}.")
            continue

        # Process each track and save to database
        new_tracks_added = await process_recently_played_tracks(
            recently_played, user, spotify_user_id, latest_track
        )

        logger.critical(
            f"Added {new_tracks_added} new tracks for user {spotify_user_id}."
        )


async def process_recently_played_tracks(
    recently_played: list[dict],
    user: SpotifyUser,
    spotify_user_id: str,
    latest_track: PlayedTrack | None = None,
) -> int:
    """
    Process recently played tracks and save them to the database.

    Args:
        recently_played: List of recently played track data from Spotify API
        user: SpotifyUser model instance
        spotify_user_id: Spotify user ID
        latest_track: The most recent track in the database, if any

    Returns:
        Number of new tracks added to the database
    """
    new_tracks_added = 0

    for item in recently_played:
        played_at_str = item.get("played_at")
        if not played_at_str:
            continue

        # Parse the timestamp
        try:
            played_at = datetime.datetime.strptime(
                played_at_str, "%Y-%m-%dT%H:%M:%S.%fZ"
            ).replace(tzinfo=datetime.UTC)
        except ValueError as ve:
            logger.warning(f"Invalid timestamp format: {played_at_str} - {ve}")
            continue

        # Skip tracks that are already in the database
        if latest_track and played_at <= latest_track.played_at:
            continue

        # Extract track ID
        track = item.get("track")
        if not track or not track.get("id"):
            continue

        track_id = track["id"]

        # Get detailed track information
        track_details, artist_details = await fetch_track_and_artist_details(
            spotify_user_id, track_id
        )

        if not track_details:
            logger.error(f"Failed to fetch details for track {track_id}")
            continue

        # Extract track and album information
        track_info = extract_track_info(track_details, artist_details)

        # Save the track to the database
        try:
            await sync_to_async(PlayedTrack.objects.create)(
                user=user, track_id=track_id, played_at=played_at, **track_info
            )
            logger.critical(f"Added track: {track_info['track_name']} - {played_at}")
            new_tracks_added += 1
        except IntegrityError as e:
            logger.error(f"Database error while adding track {track_id}: {e}")
            continue

    return new_tracks_added


async def fetch_track_and_artist_details(spotify_user_id: str, track_id: str) -> tuple:
    """
    Fetch detailed information about a track and its artist from Spotify.

    Args:
        spotify_user_id: Spotify user ID
        track_id: Spotify track ID

    Returns:
        Tuple of (track_details, artist_details)
    """
    async with SpotifyClient(spotify_user_id) as client:
        track_details = await client.get_track_details(track_id)

    if not track_details:
        return None, None

    # Extract artist ID and fetch artist details if available
    artists = track_details.get("artists", [])
    artist_id = artists[0].get("id") if artists else None
    artist_details = None

    if artist_id:
        async with SpotifyClient(spotify_user_id) as client:
            artist_details = await client.get_artist(artist_id)

    return track_details, artist_details


def extract_track_info(track_details: dict, artist_details: dict | None = None) -> dict:
    """
    Extract relevant track, artist, and album information from API response.

    Args:
        track_details: Track details from Spotify API
        artist_details: Artist details from Spotify API

    Returns:
        Dictionary with extracted information
    """
    # Extract track information
    track_name = track_details.get("name", "Unknown Track")
    duration_ms = track_details.get("duration_ms", 0)
    popularity = track_details.get("popularity", 0)

    # Extract artist information
    artists = track_details.get("artists", [])
    if artists:
        artist_name = artists[0].get("name", "Unknown Artist")
        artist_id = artists[0].get("id")
    else:
        artist_name = "Unknown Artist"
        artist_id = None

    # Get genres from artist details
    genres = artist_details.get("genres", []) if artist_details else []

    # Extract album information
    album = track_details.get("album", {})
    album_name = album.get("name", "Unknown Album")
    album_id = album.get("id")

    return {
        "track_name": track_name,
        "artist_name": artist_name,
        "album_name": album_name,
        "duration_ms": duration_ms,
        "artist_id": artist_id,
        "album_id": album_id,
        "popularity": popularity,
        "genres": genres,
    }
