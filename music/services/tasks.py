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
def update_played_tracks_task():
    async_to_sync(update_played_tracks)()


async def update_played_tracks():
    users = await sync_to_async(list)(SpotifyUser.objects.all())
    for user in users:
        spotify_user_id = user.spotify_user_id
        if not await sync_to_async(is_spotify_authenticated)(spotify_user_id):
            logger.info(f"User {spotify_user_id} is not authenticated. Skipping.")
            continue

        # Fetch the latest track
        latest_track = await sync_to_async(
            PlayedTrack.objects.filter(user=user).order_by("-played_at").first
        )()
        if latest_track:
            after_timestamp = int(latest_track.played_at.timestamp() * 1000)
        else:
            after_timestamp = 0

        async with SpotifyClient(spotify_user_id) as client:
            recently_played = await client.get_recently_played_since(after_timestamp)

        if not recently_played:
            logger.info(f"No new recently played tracks for user {spotify_user_id}.")
            continue

        new_tracks_added = 0
        for item in recently_played:
            played_at_str = item.get("played_at")
            if not played_at_str:
                continue

            try:
                played_at = datetime.datetime.strptime(
                    played_at_str, "%Y-%m-%dT%H:%M:%S.%fZ"
                ).replace(tzinfo=datetime.UTC)
            except ValueError as ve:
                logger.warning(f"Invalid timestamp format: {played_at_str} - {ve}")
                continue

            if latest_track and played_at <= latest_track.played_at:
                continue

            track = item.get("track")
            if not track or not track.get("id"):
                continue
            track_id = track["id"]

            # Fetch track details from Spotify API
            async with SpotifyClient(spotify_user_id) as client:
                track_details = await client.get_track_details(track_id)
            if not track_details:
                logger.error(f"Failed to fetch details for track {track_id}")
                continue

            # Extract track information
            track_name = track_details.get("name", "Unknown Track")
            duration_ms = track_details.get("duration_ms", 0)
            popularity = track_details.get("popularity", 0)  # Fetch popularity

            # Extract artist information
            artists = track_details.get("artists", [])
            if artists:
                artist_name = artists[0].get("name", "Unknown Artist")
                artist_id = artists[0].get("id")
            else:
                artist_name = "Unknown Artist"
                artist_id = None

            # Fetch artist details to get genres
            if artist_id:
                async with SpotifyClient(spotify_user_id) as client:
                    artist_details = await client.get_artist(artist_id)
                if artist_details:
                    genres = artist_details.get("genres", [])
                else:
                    genres = []
            else:
                genres = []

            # Extract album information
            album = track_details.get("album", {})
            album_name = album.get("name", "Unknown Album")
            album_id = album.get("id")

            try:
                await sync_to_async(PlayedTrack.objects.create)(
                    user=user,
                    track_id=track_id,
                    played_at=played_at,
                    track_name=track_name,
                    artist_name=artist_name,
                    album_name=album_name,
                    duration_ms=duration_ms,
                    artist_id=artist_id,
                    album_id=album_id,
                    popularity=popularity,
                    genres=genres,
                )
                logger.critical(f"Added track: {track_name} - {played_at}")
                new_tracks_added += 1
            except IntegrityError as e:
                logger.error(f"Database error while adding track {track_id}: {e}")
                continue

        logger.critical(
            f"Added {new_tracks_added} new tracks for user {spotify_user_id}."
        )
