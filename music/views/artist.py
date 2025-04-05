"""
Artist Detail View Module.
Handles the display of artist details, statistics, and all songs by an artist.
"""

import logging

from asgiref.sync import sync_to_async
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import redirect, render
from django.views.decorators.cache import cache_page
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.vary import vary_on_cookie

from music.models import SpotifyUser
from music.services.spotify_data_helpers import get_artist_all_songs_data
from music.services.SpotifyClient import SpotifyClient
from music.utils.db_utils import get_user_played_tracks
from music.views.utils.helpers import (
    get_artist_page_data,
    get_item_stats,
    get_item_stats_graphs,
)
from spotify.util import is_spotify_authenticated

# Configure logger
logger = logging.getLogger(__name__)

# Cache duration constants
WEEK_CACHE = 60 * 60 * 24 * 7  # 7 days in seconds


@vary_on_cookie
@cache_page(WEEK_CACHE)  # Cache for 7 days
async def artist(request: HttpRequest, artist_id: str) -> HttpResponse:
    """
    Display detailed information and statistics for a specific artist.

    Shows artist albums, top tracks, similar artists, listening statistics,
    and visualizations of the user's listening patterns for this artist.

    Args:
        request: The HTTP request object
        artist_id: Spotify artist ID

    Returns:
        Rendered artist page or redirect to authentication
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

    # Fetch data and generate statistics
    async with SpotifyClient(spotify_user_id) as client:
        # Get artist data (albums, top tracks, similar artists)
        data = await get_artist_page_data(client, artist_id)

        # Get user for database queries
        user = await sync_to_async(SpotifyUser.objects.get)(
            spotify_user_id=spotify_user_id
        )

        # Create item dictionary for statistics lookup
        item = {
            "name": data["artist"]["name"] if data.get("artist") else "Unknown Artist",
            "artist_name": (
                data["artist"]["name"] if data.get("artist") else "Unknown Artist"
            ),
            "artist_id": artist_id,
        }

        # Fetch statistics and visualization data
        # Use common kwargs pattern for cleaner parameter passing
        stats_kwargs = {
            "user": user,
            "item": item,
            "item_type": "artist",
            "time_range": time_range,
        }

        # Add date parameters if provided
        if start_date and end_date:
            stats_kwargs.update({"start_date": start_date, "end_date": end_date})

        # Get statistics data concurrently
        stats_data = await get_item_stats(**stats_kwargs)
        graph_data = await get_item_stats_graphs(**stats_kwargs)

        # Merge all data into a single context dictionary
        data.update(stats_data)
        data.update(graph_data)
        data.update(
            {
                "segment": "artist",
                "time_range": time_range,
                "start_date": start_date,
                "end_date": end_date,
            }
        )

    return await sync_to_async(render)(request, "music/pages/artist.html", data)


@vary_on_cookie
@cache_page(WEEK_CACHE)  # Cache for 7 days
@csrf_exempt
async def artist_all_songs(request: HttpRequest, artist_id: str) -> HttpResponse:
    """
    Display all songs by an artist, with indicators for which ones the user has played.

    Args:
        request: The HTTP request object
        artist_id: Spotify artist ID

    Returns:
        Rendered artist tracks page or redirect to authentication
    """
    # Verify user authentication
    spotify_user_id = await sync_to_async(request.session.get)("spotify_user_id")
    if not spotify_user_id or not await sync_to_async(is_spotify_authenticated)(
        spotify_user_id
    ):
        return await sync_to_async(redirect)("spotify-auth")

    # Fetch all artist songs from Spotify API
    async with SpotifyClient(spotify_user_id) as client:
        data = await get_artist_all_songs_data(client, artist_id)

    # Get user's listening history for these tracks
    user = await sync_to_async(SpotifyUser.objects.get)(spotify_user_id=spotify_user_id)
    track_ids = [track["id"] for track in data.get("tracks", []) if "id" in track]
    played_tracks = await get_user_played_tracks(user, track_ids=track_ids)

    # Mark tracks that user has listened to
    for track in data.get("tracks", []):
        track["listened"] = track.get("id", "") in played_tracks

    return await sync_to_async(render)(request, "music/pages/artist_tracks.html", data)


@vary_on_cookie
async def get_artist_releases(request: HttpRequest, artist_id: str) -> JsonResponse:
    """
    API endpoint to get an artist's releases (albums, singles, etc.).

    Args:
        request: The HTTP request object
        artist_id: Spotify artist ID

    Returns:
        JSON response with artist releases or error message
    """
    # Verify user authentication
    spotify_user_id = await sync_to_async(request.session.get)("spotify_user_id")
    if not spotify_user_id:
        return JsonResponse({"error": "Not authenticated"}, status=401)

    # Extract filter parameters
    release_type = request.GET.get("type", "all")

    try:
        # Fetch artist albums filtered by release type if specified
        async with SpotifyClient(spotify_user_id) as client:
            releases = await client.get_artist_albums(
                artist_id,
                include_groups=[release_type] if release_type != "all" else None,
            )
            return JsonResponse({"releases": releases})
    except Exception as e:
        logger.error(f"Error fetching artist releases: {e}", exc_info=True)
        return JsonResponse({"error": str(e)}, status=500)
