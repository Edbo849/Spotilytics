"""
API endpoints for music statistics data.
Provides access to user's top artists, tracks, albums, and genres.
"""

import logging

from asgiref.sync import sync_to_async
from django.db.models import Avg
from django.http import HttpRequest, JsonResponse
from django.views.decorators.http import require_GET

from music.models import PlayedTrack, SpotifyUser
from music.services.SpotifyClient import SpotifyClient
from music.utils.db_utils import (
    get_date_range,
    get_top_albums,
    get_top_artists,
    get_top_genres,
    get_top_tracks,
)

logger = logging.getLogger(__name__)

# Constants
DEFAULT_TIME_RANGE = "last_4_weeks"
DEFAULT_SONG_LENGTH_MS = 180000  # 3 minutes as fallback value
RESULT_LIMIT = 50


@require_GET
async def get_top_items(request: HttpRequest) -> JsonResponse:
    """
    API endpoint to get top artists/tracks/albums/genres for the list view.

    Args:
        request: The HTTP request containing query parameters

    Returns:
        JsonResponse with items list or error message
    """
    # Verify authentication
    spotify_user_id = await sync_to_async(request.session.get)("spotify_user_id")
    if not spotify_user_id:
        return JsonResponse({"error": "Not authenticated"}, status=401)

    # Extract query parameters
    item_type = request.GET.get("type")  # "artists", "tracks", "albums", "genres"
    time_range = request.GET.get("time_range", DEFAULT_TIME_RANGE)
    start_date = request.GET.get("start_date")
    end_date = request.GET.get("end_date")

    # Validate required parameters
    if not item_type:
        return JsonResponse({"error": "Item type is required"}, status=400)

    try:
        # Calculate date range and get user
        since, until = await get_date_range(time_range, start_date, end_date)
        user = await sync_to_async(SpotifyUser.objects.get)(
            spotify_user_id=spotify_user_id
        )

        # Retrieve top items based on type
        if item_type == "artists":
            top_items = await get_top_artists(user, since, until, RESULT_LIMIT)
        elif item_type == "tracks":
            top_items = await get_top_tracks(user, since, until, RESULT_LIMIT)
        elif item_type == "albums":
            top_items = await get_top_albums(user, since, until, RESULT_LIMIT)
        elif item_type == "genres":
            top_items = await get_top_genres(user, since, until, RESULT_LIMIT)

            # For genres, calculate total minutes using average song length
            avg_duration = await get_average_song_length(user)

            # Enrich genre data with total listening time
            for item in top_items:
                # Convert from milliseconds to minutes and multiply by count
                item["total_minutes"] = (avg_duration / 60000) * item["count"]
        else:
            return JsonResponse(
                {"error": f"Invalid item type: {item_type}"}, status=400
            )

        return JsonResponse({"items": top_items})

    except Exception as e:
        logger.error(f"Error retrieving top {item_type}: {e}", exc_info=True)
        return JsonResponse({"error": f"Failed to retrieve data: {str(e)}"}, status=500)


async def get_average_song_length(user: SpotifyUser) -> float:
    """
    Calculate average song length for a user.

    Args:
        user: The SpotifyUser to calculate for

    Returns:
        Average song length in milliseconds, with fallback to default
    """

    @sync_to_async
    def _get_avg_song_length() -> float:
        # Query average duration with fallback to default value
        return (
            PlayedTrack.objects.filter(user=user).aggregate(avg=Avg("duration_ms"))[
                "avg"
            ]
            or DEFAULT_SONG_LENGTH_MS
        )

    return await _get_avg_song_length()


@require_GET
async def get_playlist_items(request: HttpRequest) -> JsonResponse:
    """
    API endpoint to get details about tracks in a playlist.

    Args:
        request: The HTTP request containing query parameters

    Returns:
        JsonResponse with playlist tracks or error message
    """
    # Verify authentication
    spotify_user_id = await sync_to_async(request.session.get)("spotify_user_id")
    if not spotify_user_id:
        return JsonResponse({"error": "Not authenticated"}, status=401)

    # Extract query parameters
    playlist_id = request.GET.get("playlist_id")

    # Validate required parameters
    if not playlist_id:
        return JsonResponse({"error": "Playlist ID is required"}, status=400)

    try:
        async with SpotifyClient(spotify_user_id) as client:
            # Get playlist tracks
            playlist_tracks = await client.get_playlist_tracks(playlist_id)

            # Get user for database queries
            user = await sync_to_async(SpotifyUser.objects.get)(
                spotify_user_id=spotify_user_id
            )

            # Get track IDs and query listened tracks
            track_ids = [
                item["track"]["id"]
                for item in playlist_tracks
                if item.get("track") and item["track"].get("id")
            ]

            from music.utils.db_utils import get_user_played_tracks

            played_tracks = await get_user_played_tracks(user, track_ids=track_ids)

            # Enrich track data with listening status
            for item in playlist_tracks:
                if item.get("track") and item["track"].get("id"):
                    item["listened"] = item["track"]["id"] in played_tracks
                else:
                    item["listened"] = False

            return JsonResponse({"tracks": playlist_tracks})

    except Exception as e:
        logger.error(f"Error retrieving playlist tracks: {e}", exc_info=True)
        return JsonResponse(
            {"error": f"Failed to retrieve playlist data: {str(e)}"}, status=500
        )
