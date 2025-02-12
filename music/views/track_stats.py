from music.views.utils.helpers import (
    get_preview_urls_batch,
    get_similar_tracks,
    get_track_visualizations,
)

from .utils.imports import *


@vary_on_cookie
@cache_page(60 * 60 * 24)
async def track_stats(request: HttpRequest) -> HttpResponse:
    spotify_user_id = await sync_to_async(request.session.get)("spotify_user_id")
    if not spotify_user_id or not await sync_to_async(is_spotify_authenticated)(
        spotify_user_id
    ):
        return redirect("spotify-auth")

    time_range = request.GET.get("time_range", "last_4_weeks")
    start_date = request.GET.get("start_date")
    end_date = request.GET.get("end_date")

    since, until = await get_date_range(time_range, start_date, end_date)
    user = await sync_to_async(SpotifyUser.objects.get)(spotify_user_id=spotify_user_id)
    top_tracks = await get_top_tracks(user, since, until, 10)

    async with SpotifyClient(spotify_user_id) as client:
        similar_tracks = await get_similar_tracks(client, top_tracks)

    visualizations = await get_track_visualizations(
        user, since, until, top_tracks, time_range
    )

    context = {
        "segment": "track-stats",
        "time_range": time_range,
        "start_date": start_date,
        "end_date": end_date,
        "stats_title": "Tracks",
        "top_tracks": top_tracks,
        "similar_tracks": similar_tracks,
        **visualizations,
    }

    return render(request, "music/pages/track_stats.html", context)


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
