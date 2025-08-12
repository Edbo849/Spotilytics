"""
Home Views Module.
Handles the landing page, dashboard, and recently played content.
"""

import logging

from asgiref.sync import sync_to_async
from django.http import HttpRequest, HttpResponse
from django.shortcuts import redirect, render
from django.views.decorators.cache import cache_page
from django.views.decorators.vary import vary_on_cookie

from music.models import PlayedTrack, SpotifyUser
from music.utils.db_utils import get_recently_played
from music.views.utils.helpers import get_home_visualizations, validate_date_range
from spotify.util import is_spotify_authenticated

# Configure logger
logger = logging.getLogger(__name__)

# Cache constants
DAY_CACHE = 60 * 60 * 24  # 24 hours in seconds
FIFTEEN_MIN_CACHE = 60 * 15  # 15 minutes in seconds


def index(request: HttpRequest) -> HttpResponse:
    """
    Render the landing page for non-authenticated users.

    Args:
        request: The HTTP request object

    Returns:
        Rendered landing page
    """
    spotify_user_id = request.session.get("spotify_user_id")

    # If not authenticated, clear session data and render landing page
    if not spotify_user_id or not is_spotify_authenticated(spotify_user_id):
        if "spotify_user_id" in request.session:
            request.session.flush()

    return render(request, "music/pages/index.html")


@vary_on_cookie
@cache_page(DAY_CACHE)
async def home(request: HttpRequest) -> HttpResponse:
    """
    Render the main dashboard with user's listening statistics.

    Args:
        request: The HTTP request object

    Returns:
        Rendered dashboard or redirect to authentication
    """
    # Verify user authentication
    spotify_user_id = await sync_to_async(request.session.get)("spotify_user_id")
    if not spotify_user_id or not await sync_to_async(is_spotify_authenticated)(
        spotify_user_id
    ):
        return redirect("spotify-auth")

    try:
        # Get user and check if they have listening history
        user = await sync_to_async(SpotifyUser.objects.get)(
            spotify_user_id=spotify_user_id
        )
        has_history = await sync_to_async(
            PlayedTrack.objects.filter(user=user).exists
        )()
    except SpotifyUser.DoesNotExist:
        return redirect("spotify-auth")

    # Extract time range parameters from request
    time_range = request.GET.get("time_range", "last_4_weeks")
    start_date = request.GET.get("start_date")
    end_date = request.GET.get("end_date")

    # Validate custom date range if provided
    start_date, end_date, error_message = await validate_date_range(
        time_range, start_date, end_date
    )

    # Get visualization data for dashboard
    stats = await get_home_visualizations(
        user, has_history, time_range, start_date, end_date
    )

    # Prepare template context
    context = {
        "segment": "home",
        "time_range": time_range,
        "start_date": start_date,
        "end_date": end_date,
        "error_message": error_message,
        **stats,  # Unpack all stats data
    }

    return render(request, "music/pages/home.html", context)


@vary_on_cookie
@cache_page(FIFTEEN_MIN_CACHE)
async def recently_played_section(request: HttpRequest) -> HttpResponse:
    """
    Render the recently played tracks section as a partial view.

    Args:
        request: The HTTP request object

    Returns:
        Rendered partial view with recently played tracks
    """
    spotify_user_id = await sync_to_async(request.session.get)("spotify_user_id")

    try:
        # Get user and fetch recently played tracks
        user = await sync_to_async(SpotifyUser.objects.get)(
            spotify_user_id=spotify_user_id
        )
        recently_played = await get_recently_played(user, None, None, 20)
    except Exception as e:
        logger.error(f"Error fetching recently played: {e}", exc_info=True)
        recently_played = []

    return render(
        request,
        "music/partials/recently_played.html",
        {"recently_played": recently_played},
    )
