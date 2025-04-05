"""
Track Statistics View Module.
Handles the visualization and display of user's track listening statistics.
"""

import logging

from asgiref.sync import sync_to_async
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import redirect, render
from django.views.decorators.cache import cache_page
from django.views.decorators.vary import vary_on_cookie

from music.models import SpotifyUser
from music.services.SpotifyClient import SpotifyClient
from music.utils.db_utils import get_date_range, get_top_tracks
from music.views.utils.helpers import (
    get_preview_urls_batch,
    get_similar_tracks,
    get_track_visualizations,
)
from spotify.util import is_spotify_authenticated

# Configure logger
logger = logging.getLogger(__name__)

# Cache constants
DAY_CACHE = 60 * 60 * 24  # 24 hours in seconds


@vary_on_cookie
@cache_page(DAY_CACHE)
async def track_stats(request: HttpRequest) -> HttpResponse:
    """
    Show track listening statistics for the authenticated user.

    Displays the top tracks, similar track recommendations, and various
    visualizations of track listening patterns.

    Args:
        request: The HTTP request object

    Returns:
        Rendered track statistics page or redirect to authentication
    """
    # Verify user authentication
    spotify_user_id = await sync_to_async(request.session.get)("spotify_user_id")
    if not spotify_user_id or not await sync_to_async(is_spotify_authenticated)(
        spotify_user_id
    ):
        return redirect("spotify-auth")

    # Extract time range parameters from request
    time_range = request.GET.get("time_range", "last_4_weeks")
    start_date = request.GET.get("start_date")
    end_date = request.GET.get("end_date")

    # Calculate date range and get user's top tracks
    since, until = await get_date_range(time_range, start_date, end_date)
    user = await sync_to_async(SpotifyUser.objects.get)(spotify_user_id=spotify_user_id)
    top_tracks = await get_top_tracks(user, since, until, 10)

    # Get similar track recommendations using Spotify API
    async with SpotifyClient(spotify_user_id) as client:
        similar_tracks = await get_similar_tracks(client, top_tracks)

    # Generate all visualizations for the tracks page
    visualizations = await get_track_visualizations(
        user, since, until, top_tracks, time_range
    )

    # Prepare template context with all necessary data
    context = {
        "segment": "track-stats",
        "time_range": time_range,
        "start_date": start_date,
        "end_date": end_date,
        "stats_title": "Tracks",
        "top_tracks": top_tracks,
        "similar_tracks": similar_tracks,
        **visualizations,  # Unpack all visualization data
    }

    return render(request, "music/pages/track_stats.html", context)


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
