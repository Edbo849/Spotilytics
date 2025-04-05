"""
Album Detail View Module.
Handles the display of a specific album's details and user's listening statistics for it.
"""

import logging

from asgiref.sync import sync_to_async
from django.http import HttpRequest, HttpResponse
from django.shortcuts import redirect, render
from django.views.decorators.cache import cache_page
from django.views.decorators.vary import vary_on_cookie

from music.models import SpotifyUser
from music.services.spotify_data_helpers import get_album_details
from music.services.SpotifyClient import SpotifyClient
from music.utils.db_utils import get_user_played_tracks
from music.views.utils.helpers import (
    enrich_track_details,
    get_artist_details,
    get_item_stats,
    get_item_stats_graphs,
)
from spotify.util import is_spotify_authenticated

# Configure logger
logger = logging.getLogger(__name__)


@vary_on_cookie
@cache_page(60 * 60 * 24 * 30)  # Cache for 30 days
async def album(request: HttpRequest, album_id: str) -> HttpResponse:
    """
    Display detailed information and statistics for a specific album.

    Shows album tracks, artist info, listening statistics, and visualizations
    of the user's listening patterns for this album.

    Args:
        request: The HTTP request object
        album_id: Spotify album ID

    Returns:
        Rendered album page or redirect to authentication
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
            # Fetch album data and tracks from Spotify API
            album_data = await get_album_details(client, album_id)
            tracks = album_data["tracks"]["items"]

            # Get artist details and genres
            artist_id = (
                album_data["artists"][0]["id"] if album_data.get("artists") else None
            )
            artist_details = (
                await get_artist_details(client, artist_id) if artist_id else {}
            )
            genres = artist_details.get("genres", [])

            # Enrich track data with additional details
            tracks = await enrich_track_details(client, tracks)

            # Get user model for database queries
            user = await sync_to_async(SpotifyUser.objects.get)(
                spotify_user_id=spotify_user_id
            )

            # Get user's listening history for these tracks
            track_ids = [track["id"] for track in tracks if "id" in track]
            played_tracks = await get_user_played_tracks(user, track_ids=track_ids)

            # Mark tracks that user has listened to
            for track in tracks:
                track["listened"] = track.get("id") in played_tracks

            # Prepare album item data for statistics queries
            item = {
                "name": album_data.get("name", "Unknown Album"),
                "album_id": album_id,
                "artist_name": (
                    album_data["artists"][0]["name"]
                    if album_data.get("artists")
                    else None
                ),
            }

            # Get statistics and visualization data
            # Handle custom date range if provided
            stats_kwargs = {
                "user": user,
                "item": item,
                "item_type": "album",
                "time_range": time_range,
            }
            if start_date and end_date:
                stats_kwargs.update({"start_date": start_date, "end_date": end_date})

            # Fetch stats and graph data concurrently
            stats_data_task = get_item_stats(**stats_kwargs)
            graph_data_task = get_item_stats_graphs(**stats_kwargs)

            stats_data = await stats_data_task
            graph_data = await graph_data_task

            # Prepare template context
            context = {
                "artist_id": artist_id,
                "album": album_data,
                "tracks": tracks,
                "genres": genres,
                **stats_data,  # Unpack stats data
                **graph_data,  # Unpack graph data
                "time_range": time_range,
                "start_date": start_date,
                "end_date": end_date,
            }

            return await sync_to_async(render)(
                request, "music/pages/album.html", context
            )

    except Exception as e:
        # Log error and display error page
        logger.critical(f"Error fetching album data from Spotify: {e}", exc_info=True)

        # Provide minimal context for error template
        context = {
            "artist_id": None,
            "album": None,
            "tracks": [],
            "genres": [],
            "error": str(e),
        }

        return await sync_to_async(render)(request, "music/pages/album.html", context)
