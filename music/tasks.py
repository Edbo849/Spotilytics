import datetime
import logging

from asgiref.sync import async_to_sync, sync_to_async
from celery import shared_task
from django.db import IntegrityError

from music.models import PlayedTrack, SpotifyUser
from music.spotify_api import get_recently_played_since
from spotify.util import is_spotify_authenticated

logger = logging.getLogger(__name__)


@shared_task
def update_played_tracks_task():
    async_to_sync(update_played_tracks)()


async def update_played_tracks():
    users = await sync_to_async(list)(SpotifyUser.objects.all())
    for user in users:
        spotify_user_id = user.spotify_user_id
        if not await sync_to_async(is_spotify_authenticated)(spotify_user_id):
            logger.info(f"User {spotify_user_id} is not authenticated. Skipping.")
            continue

        has_history = await sync_to_async(
            PlayedTrack.objects.filter(user=user).exists
        )()
        if not has_history:
            logger.info(
                f"User {spotify_user_id} has not imported listening history. Skipping."
            )
            continue

        latest_track = await sync_to_async(
            PlayedTrack.objects.filter(user=user).order_by("-played_at").first
        )()
        if latest_track:
            after_timestamp = int(latest_track.played_at.timestamp() * 1000)
        else:
            after_timestamp = 0

        recently_played = await get_recently_played_since(
            spotify_user_id, after_timestamp
        )
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
                )
                played_at = played_at.replace(tzinfo=datetime.UTC)
            except ValueError as ve:
                logger.warning(f"Invalid timestamp format: {played_at_str} - {ve}")
                continue

            if played_at <= latest_track.played_at:
                continue

            track = item.get("track")
            if not track or not track.get("id"):
                continue

            track_id = track["id"]
            track_name = track.get("name", "Unknown Track")
            artist_name = (
                track["artists"][0]["name"]
                if track.get("artists") and len(track["artists"]) > 0
                else "Unknown Artist"
            )
            album_name = (
                track["album"]["name"] if track.get("album") else "Unknown Album"
            )

            try:
                await sync_to_async(PlayedTrack.objects.create)(
                    user=user,
                    track_id=track_id,
                    played_at=played_at,
                    track_name=track_name,
                    artist_name=artist_name,
                    album_name=album_name,
                )
                logger.critical(f"Added track: {track_name} - {played_at}")
                new_tracks_added += 1
            except IntegrityError as e:
                logger.error(f"Database error while adding track {track_id}: {e}")
                continue

        logger.critical(
            f"Added {new_tracks_added} new tracks for user {spotify_user_id}."
        )
