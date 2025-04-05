"""
Item Statistics API Module.
Provides JSON endpoints for fetching statistics about specific items.
"""

import logging

from asgiref.sync import sync_to_async
from django.http import HttpRequest, JsonResponse
from django.views.decorators.vary import vary_on_cookie

from music.models import SpotifyUser
from music.utils.db_utils import get_date_range, get_item_stats_util

# Configure logger
logger = logging.getLogger(__name__)


@vary_on_cookie
async def get_item_stats(
    request: HttpRequest, item_type: str, item_id: str
) -> JsonResponse:
    """
    API endpoint to get statistics for a specific artist, album, or track.

    Args:
        request: The HTTP request object
        item_type: Type of item ("artist", "album", or "track")
        item_id: Spotify ID of the item

    Returns:
        JSON response with statistics or error message
    """
    # Verify user authentication
    spotify_user_id = await sync_to_async(request.session.get)("spotify_user_id")
    if not spotify_user_id:
        return JsonResponse({"error": "Not authenticated"}, status=401)

    # Get time range parameter from request
    time_range = request.GET.get("time_range", "last_4_weeks")

    try:
        # Calculate date range and get user
        since, until = await get_date_range(time_range)
        user = await sync_to_async(SpotifyUser.objects.get)(
            spotify_user_id=spotify_user_id
        )

        # Get statistics for the requested item
        stats = await get_item_stats_util(user, item_id, item_type, since, until)
        return JsonResponse(stats)
    except Exception as e:
        logger.error(
            f"Error fetching stats for {item_type} {item_id}: {e}", exc_info=True
        )
        return JsonResponse({"error": str(e)}, status=500)
