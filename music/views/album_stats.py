"""
Album Statistics View Module.
Handles the visualization and display of user's album listening statistics.
"""

import logging

from asgiref.sync import sync_to_async
from django.http import HttpRequest, HttpResponse
from django.shortcuts import redirect, render
from django.views.decorators.cache import cache_page
from django.views.decorators.vary import vary_on_cookie

from music.models import SpotifyUser
from music.services.SpotifyClient import SpotifyClient
from music.utils.db_utils import get_date_range, get_top_albums
from music.views.utils.helpers import get_album_visualizations, get_similar_albums
from spotify.util import is_spotify_authenticated

logger = logging.getLogger(__name__)


@vary_on_cookie
@cache_page(60 * 60 * 24)  # Cache for 24 hours
async def album_stats(request: HttpRequest) -> HttpResponse:
    """
    Show album listening statistics for the authenticated user.

    Displays the top albums, similar album recommendations, and various
    visualizations of album listening patterns.

    Args:
        request: The HTTP request object

    Returns:
        Rendered album statistics page or redirect to authentication
    """
    # Get user ID from session and verify authentication
    spotify_user_id = await sync_to_async(request.session.get)("spotify_user_id")
    if not spotify_user_id or not await sync_to_async(is_spotify_authenticated)(
        spotify_user_id
    ):
        logger.warning(f"User not authenticated: {spotify_user_id}")
        return redirect("spotify-auth")

    # Extract time range parameters from request
    time_range = request.GET.get("time_range", "last_4_weeks")
    start_date = request.GET.get("start_date")
    end_date = request.GET.get("end_date")

    # Calculate date range and get user's top albums
    since, until = await get_date_range(time_range, start_date, end_date)
    user = await sync_to_async(SpotifyUser.objects.get)(spotify_user_id=spotify_user_id)
    top_albums = await get_top_albums(user, since, until, 10)

    # Track seen album IDs to avoid duplicates in recommendations
    seen_album_ids = {album["album_id"] for album in top_albums}

    # Get similar album recommendations using Spotify API
    async with SpotifyClient(spotify_user_id) as client:
        similar_albums = await get_similar_albums(client, top_albums, seen_album_ids)

    # Generate all visualizations for the albums page
    visualizations = await get_album_visualizations(
        user, since, until, top_albums, time_range
    )

    # Prepare template context with all necessary data
    context = {
        "segment": "album-stats",
        "time_range": time_range,
        "start_date": start_date,
        "end_date": end_date,
        "stats_title": "Albums",
        "top_albums": top_albums,
        "similar_albums": similar_albums,
        **visualizations,  # Unpack all visualization data
    }

    return render(request, "music/pages/album_stats.html", context)
