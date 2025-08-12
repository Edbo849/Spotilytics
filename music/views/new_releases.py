"""
New Releases View Module.
Displays recent album releases from Spotify.
"""

import logging

from asgiref.sync import sync_to_async
from django.http import HttpRequest, HttpResponse
from django.shortcuts import redirect, render
from django.views.decorators.cache import cache_page
from django.views.decorators.vary import vary_on_cookie

from music.services.SpotifyClient import SpotifyClient
from spotify.util import is_spotify_authenticated

# Configure logger
logger = logging.getLogger(__name__)

# Cache constants
DAY_CACHE = 60 * 60 * 24  # 24 hours in seconds


@vary_on_cookie
@cache_page(DAY_CACHE)
async def new_releases(request: HttpRequest) -> HttpResponse:
    """
    Display new album releases from Spotify.

    Args:
        request: The HTTP request object

    Returns:
        Rendered new releases page or redirect to authentication
    """
    # Verify user authentication
    spotify_user_id = await sync_to_async(request.session.get)("spotify_user_id")
    if not spotify_user_id or not await sync_to_async(is_spotify_authenticated)(
        spotify_user_id
    ):
        return redirect("spotify-auth")

    try:
        # Fetch new releases from Spotify API
        async with SpotifyClient(spotify_user_id) as client:
            new_releases_data = await client.get_new_releases()
            albums = new_releases_data.get("albums", {}).get("items", [])
    except Exception as e:
        logger.error(f"Error fetching new releases: {e}", exc_info=True)
        albums = []  # Provide empty list on error

    # Prepare template context
    context = {
        "segment": "new-releases",  # For navigation highlighting
        "albums": albums,
    }

    return render(request, "music/pages/new_releases.html", context)
