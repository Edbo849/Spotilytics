from music.services.spotify_data_helpers import get_artist_all_songs_data
from music.utils.db_utils import get_user_played_tracks
from music.views.utils.helpers import (
    get_artist_page_data,
    get_item_stats,
    get_item_stats_graphs,
)

from .utils.imports import *


@vary_on_cookie
@cache_page(60 * 60 * 24 * 7)
async def artist(request: HttpRequest, artist_id: str) -> HttpResponse:
    spotify_user_id = await sync_to_async(request.session.get)("spotify_user_id")
    if not spotify_user_id or not await sync_to_async(is_spotify_authenticated)(
        spotify_user_id
    ):
        return redirect("spotify-auth")

    time_range = request.GET.get("time_range", "last_4_weeks")
    start_date = request.GET.get("start_date")
    end_date = request.GET.get("end_date")

    async with SpotifyClient(spotify_user_id) as client:
        # Get artist data
        data = await get_artist_page_data(client, artist_id)

        # Get user for stats
        user = await sync_to_async(SpotifyUser.objects.get)(
            spotify_user_id=spotify_user_id
        )

        # Create item dict with artist data
        item = {
            "name": data["artist"]["name"],
            "artist_name": data["artist"]["name"],
            "artist_id": artist_id,
        }

        # Get stats data with the artist info
        if start_date and end_date:
            stats_data = await get_item_stats(
                user, item, "artist", time_range, start_date, end_date
            )
            graph_data = await get_item_stats_graphs(
                user, item, "artist", time_range, start_date, end_date
            )

        else:
            stats_data = await get_item_stats(user, item, "artist", time_range)
            graph_data = await get_item_stats_graphs(user, item, "artist", time_range)

        # Combine all data
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
@cache_page(60 * 60 * 24 * 7)
@csrf_exempt
async def artist_all_songs(request: HttpRequest, artist_id: str) -> HttpResponse:
    spotify_user_id = await sync_to_async(request.session.get)("spotify_user_id")
    if not spotify_user_id or not await sync_to_async(is_spotify_authenticated)(
        spotify_user_id
    ):
        return await sync_to_async(redirect)("spotify-auth")

    async with SpotifyClient(spotify_user_id) as client:
        data = await get_artist_all_songs_data(client, artist_id)

    # Get user's played tracks
    user = await sync_to_async(SpotifyUser.objects.get)(spotify_user_id=spotify_user_id)
    track_ids = [track["id"] for track in data.get("tracks", [])]
    played_tracks = await get_user_played_tracks(user, track_ids=track_ids)

    # Add listened flag to each track
    for track in data.get("tracks", []):
        track["listened"] = track["id"] in played_tracks

    return await sync_to_async(render)(request, "music/pages/artist_tracks.html", data)


@vary_on_cookie
async def get_artist_releases(request: HttpRequest, artist_id: str) -> JsonResponse:
    spotify_user_id = await sync_to_async(request.session.get)("spotify_user_id")
    if not spotify_user_id:
        return JsonResponse({"error": "Not authenticated"}, status=401)

    release_type = request.GET.get("type", "all")

    try:
        async with SpotifyClient(spotify_user_id) as client:
            releases = await client.get_artist_albums(
                artist_id,
                include_groups=[release_type] if release_type != "all" else None,
            )
            return JsonResponse({"releases": releases})
    except Exception as e:
        logger.error(f"Error fetching artist releases: {e}")
        return JsonResponse({"error": str(e)}, status=500)
