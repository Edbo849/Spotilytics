from music.views.utils.helpers import (
    get_item_stats,
    get_item_stats_graphs,
    get_preview_urls_batch,
    get_track_page_data,
)

from .utils.imports import *


@vary_on_cookie
@cache_page(60 * 60 * 24 * 30)
async def track(request: HttpRequest, track_id: str) -> HttpResponse:
    spotify_user_id = await sync_to_async(request.session.get)("spotify_user_id")
    if not spotify_user_id or not await sync_to_async(is_spotify_authenticated)(
        spotify_user_id
    ):
        return redirect("spotify-auth")

    time_range = request.GET.get("time_range", "last_4_weeks")
    start_date = request.GET.get("start_date")
    end_date = request.GET.get("end_date")

    try:
        async with SpotifyClient(spotify_user_id) as client:
            # Get track data
            data = await get_track_page_data(client, track_id)

            # Get user for stats
            user = await sync_to_async(SpotifyUser.objects.get)(
                spotify_user_id=spotify_user_id
            )

            # Create item dict with track data
            item = {
                "name": data["track"]["name"],
                "track_id": track_id,
                "artist_name": (
                    data["track"]["artists"][0]["name"]
                    if data["track"]["artists"]
                    else None
                ),
                "artist_id": (
                    data["track"]["artists"][0]["id"]
                    if data["track"]["artists"]
                    else None
                ),
            }

            # Get stats data with the track info
            if start_date and end_date:
                stats_data = await get_item_stats(
                    user, item, "track", time_range, start_date, end_date
                )
                graph_data = await get_item_stats_graphs(
                    user, item, "track", time_range, start_date, end_date
                )
            else:
                stats_data = await get_item_stats(user, item, "track", time_range)
                graph_data = await get_item_stats_graphs(
                    user, item, "track", time_range
                )

            # Combine all data
            data.update(stats_data)
            data.update(graph_data)

            data.update(
                {
                    "time_range": time_range,
                    "start_date": start_date,
                    "end_date": end_date,
                }
            )

        return await sync_to_async(render)(request, "music/pages/track.html", data)
    except Exception as e:
        logger.error(f"Error in track view: {e}")
        return HttpResponse("Error fetching track details", status=500)


@vary_on_cookie
async def get_preview_urls(request: HttpRequest) -> JsonResponse:
    spotify_user_id = await sync_to_async(request.session.get)("spotify_user_id")
    if not spotify_user_id:
        return JsonResponse({"error": "Not authenticated"}, status=401)

    track_ids = request.GET.get("track_ids", "").split(",")
    if not track_ids:
        return JsonResponse({"error": "No track IDs provided"}, status=400)

    try:
        async with SpotifyClient(spotify_user_id) as client:
            preview_urls = await get_preview_urls_batch(client, track_ids)
            return JsonResponse(preview_urls)
    except Exception as e:
        logger.error(f"Error fetching preview URLs: {e}")
        return JsonResponse({"error": str(e)}, status=500)
