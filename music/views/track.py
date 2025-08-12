"""
Track Detail View Module.
Handles the display of a specific track's details and user's listening statistics for it.
"""

import logging

from asgiref.sync import sync_to_async
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import redirect, render
from django.views.decorators.cache import cache_page
from django.views.decorators.vary import vary_on_cookie

from music.models import SpotifyUser
from music.services.SpotifyClient import SpotifyClient
from music.views.utils.helpers import (
    get_item_stats,
    get_item_stats_graphs,
    get_preview_urls_batch,
    get_track_page_data,
)
from spotify.util import is_spotify_authenticated

# Configure logger
logger = logging.getLogger(__name__)

# Cache constants
MONTH_CACHE = 60 * 60 * 24 * 30  # 30 days in seconds


@vary_on_cookie
@cache_page(MONTH_CACHE)
async def track(request: HttpRequest, track_id: str) -> HttpResponse:
    """
    Display detailed information and statistics for a specific track.

    Shows track details, artist info, listening statistics, and visualizations
    of the user's listening patterns for this track.

    Args:
        request: The HTTP request object
        track_id: Spotify track ID

    Returns:
        Rendered track page or redirect to authentication
    """
    # Verify user authentication
    spotify_user_id = await sync_to_async(request.session.get)("spotify_user_id")
    if not spotify_user_id or not await sync_to_async(is_spotify_authenticated)(
        spotify_user_id
    ):
        return redirect("spotify-auth")

    # Get time range parameters from request
    time_range = request.GET.get("time_range", "last_4_weeks")
    start_date = request.GET.get("start_date")
    end_date = request.GET.get("end_date")

    try:
        # Create Spotify client with context manager for proper resource handling
        async with SpotifyClient(spotify_user_id) as client:
            # Get track data including related artists and albums
            data = await get_track_page_data(client, track_id)

            # Get user for database queries
            user = await sync_to_async(SpotifyUser.objects.get)(
                spotify_user_id=spotify_user_id
            )

            # Create item dictionary for statistics lookup
            item = {
                "name": data["track"]["name"],
                "track_id": track_id,
                "artist_name": (
                    data["track"]["artists"][0]["name"]
                    if data["track"]["artists"]
                    else None
                ),
                "artist_id": (
                    data["track"]["artists"][0]["id"]
                    if data["track"]["artists"]
                    else None
                ),
            }

            # Get statistics data and visualization graphs
            # Use kwargs pattern for cleaner parameter passing
            stats_kwargs = {
                "user": user,
                "item": item,
                "item_type": "track",
                "time_range": time_range,
            }

            # Add date parameters if provided
            if start_date and end_date:
                stats_kwargs.update({"start_date": start_date, "end_date": end_date})

            # Fetch statistics data
            stats_data = await get_item_stats(**stats_kwargs)
            graph_data = await get_item_stats_graphs(**stats_kwargs)

            # Merge all data into a single context dictionary
            data.update(stats_data)
            data.update(graph_data)
            data.update(
                {
                    "time_range": time_range,
                    "start_date": start_date,
                    "end_date": end_date,
                }
            )

        return await sync_to_async(render)(request, "music/pages/track.html", data)

    except Exception as e:
        logger.error(f"Error in track view: {e}", exc_info=True)
        return HttpResponse("Error fetching track details", status=500)


@vary_on_cookie
async def get_preview_urls(request: HttpRequest) -> JsonResponse:
    """
    API endpoint to get preview URLs for multiple tracks.

    Args:
        request: The HTTP request with track_ids parameter

    Returns:
        JSON response with track IDs mapped to preview URLs
    """
    # Verify user authentication
    spotify_user_id = await sync_to_async(request.session.get)("spotify_user_id")
    if not spotify_user_id:
        return JsonResponse({"error": "Not authenticated"}, status=401)

    # Get track IDs from request
    track_ids = request.GET.get("track_ids", "").split(",")
    if not track_ids or not track_ids[0]:
        return JsonResponse({"error": "No track IDs provided"}, status=400)

    try:
        # Fetch preview URLs from Spotify API
        async with SpotifyClient(spotify_user_id) as client:
            preview_urls = await get_preview_urls_batch(client, track_ids)
            return JsonResponse(preview_urls)
    except Exception as e:
        logger.error(f"Error fetching preview URLs: {e}", exc_info=True)
        return JsonResponse({"error": str(e)}, status=500)
