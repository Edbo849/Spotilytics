from music.services.spotify_data_helpers import get_album_details
from music.views.utils.helpers import (
    enrich_track_details,
    get_artist_details,
    get_item_stats,
    get_item_stats_graphs,
)

from .utils.imports import *


@vary_on_cookie
@cache_page(60 * 60 * 24 * 30)
async def album(request: HttpRequest, album_id: str) -> HttpResponse:
    spotify_user_id = await sync_to_async(request.session.get)("spotify_user_id")
    if not spotify_user_id or not await sync_to_async(is_spotify_authenticated)(
        spotify_user_id
    ):
        return redirect("spotify-auth")

    time_range = request.GET.get("time_range", "last_4_weeks")

    try:
        async with SpotifyClient(spotify_user_id) as client:
            # Get album data
            album = await get_album_details(client, album_id)
            tracks = album["tracks"]["items"]

            artist_id = album["artists"][0]["id"]
            artist_details = await get_artist_details(client, artist_id)
            genres = artist_details.get("genres", []) if artist_details else []

            tracks = await enrich_track_details(client, tracks)

            # Get user for stats
            user = await sync_to_async(SpotifyUser.objects.get)(
                spotify_user_id=spotify_user_id
            )

            # Create item dict with album data
            item = {
                "name": album["name"],
                "album_id": album_id,
                "artist_name": (
                    album["artists"][0]["name"] if album["artists"] else None
                ),
            }

            # Get stats data with the album info
            stats_data = await get_item_stats(user, item, "album", time_range)

            # Get graph data for the stats section
            graph_data = await get_item_stats_graphs(user, item, "album", time_range)

            # Combine all data
            context = {
                "artist_id": artist_id,
                "album": album,
                "tracks": tracks,
                "genres": genres,
                **stats_data,
                **graph_data,
            }

            return await sync_to_async(render)(
                request, "music/pages/album.html", context
            )

    except Exception as e:
        logger.critical(f"Error fetching album data from Spotify: {e}")
        context = {
            "artist_id": None,
            "album": None,
            "tracks": [],
            "genres": [],
            "error": str(e),
        }
        return await sync_to_async(render)(request, "music/pages/album.html", context)
