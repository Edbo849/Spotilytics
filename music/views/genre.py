"""
Genre Detail View Module.
Handles the display of a specific genre's artists and tracks.
"""

import logging

from asgiref.sync import sync_to_async
from django.http import HttpRequest, HttpResponse
from django.shortcuts import redirect, render
from django.views.decorators.cache import cache_page
from django.views.decorators.vary import vary_on_cookie

from music.services.SpotifyClient import SpotifyClient
from music.views.utils.helpers import get_genre_items
from spotify.util import is_spotify_authenticated

# Configure logger
logger = logging.getLogger(__name__)

# Cache duration constants
WEEK_CACHE = 60 * 60 * 24 * 7  # 7 days in seconds


@vary_on_cookie
@cache_page(WEEK_CACHE)  # Cache for 7 days
async def genre(request: HttpRequest, genre_name: str) -> HttpResponse:
    """
    Display detailed information about a specific genre.

    Shows artists and tracks that belong to the specified genre.

    Args:
        request: The HTTP request object
        genre_name: Name of the genre to display

    Returns:
        Rendered genre page or redirect to authentication
    """
    # Verify user authentication
    spotify_user_id = await sync_to_async(request.session.get)("spotify_user_id")
    if not spotify_user_id or not await sync_to_async(is_spotify_authenticated)(
        spotify_user_id
    ):
        logger.warning(f"User not authenticated while accessing genre: {genre_name}")
        return await sync_to_async(redirect)("spotify-auth")

    try:
        # Fetch genre data using Spotify API
        async with SpotifyClient(spotify_user_id) as client:
            items = await get_genre_items(client, genre_name)

        # Prepare template context
        context = {
            "genre_name": genre_name,
            "artists": items["artists"],
            "tracks": items["tracks"],
            "segment": "genre",  # For navigation highlighting
        }

        return await sync_to_async(render)(request, "music/pages/genre.html", context)

    except Exception as e:
        # Log error and display minimal genre page
        logger.error(f"Error fetching genre data for {genre_name}: {e}", exc_info=True)
        context = {
            "genre_name": genre_name,
            "artists": [],
            "tracks": [],
            "error": f"Error loading genre data: {str(e)}",
            "segment": "genre",
        }
        return await sync_to_async(render)(request, "music/pages/genre.html", context)
