"""
Search View Module.
Handles searching for artists, albums, and tracks on Spotify.
"""

import logging

from asgiref.sync import sync_to_async
from django.http import HttpRequest, HttpResponse
from django.shortcuts import redirect, render

from music.services.SpotifyClient import SpotifyClient
from spotify.util import is_spotify_authenticated

# Configure logger
logger = logging.getLogger(__name__)


async def search(request: HttpRequest) -> HttpResponse:
    """
    Search Spotify for artists, albums, and tracks.

    Args:
        request: The HTTP request object with search query

    Returns:
        Rendered search results page
    """
    # Verify user authentication
    spotify_user_id = await sync_to_async(request.session.get)("spotify_user_id")
    if not spotify_user_id or not await sync_to_async(is_spotify_authenticated)(
        spotify_user_id
    ):
        return redirect("spotify-auth")

    # Get search query parameter
    query = request.GET.get("q")
    if not query:
        # Return empty results if no query provided
        return render(request, "music/pages/search_results.html", {"results": None})

    try:
        # Execute search using Spotify API
        async with SpotifyClient(spotify_user_id) as client:
            results = await client.search_spotify(query)
    except Exception as e:
        # Log error and return empty results
        logger.critical(f"Error searching Spotify: {e}", exc_info=True)
        results = None

    return render(request, "music/pages/search_results.html", {"results": results})
