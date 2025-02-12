from music.views.utils.helpers import get_preview_urls_batch, get_track_page_data

from .utils.imports import *


@vary_on_cookie
@cache_page(60 * 60 * 24 * 30)
async def track(request: HttpRequest, track_id: str) -> HttpResponse:
    spotify_user_id = await sync_to_async(request.session.get)("spotify_user_id")
    if not spotify_user_id or not await sync_to_async(is_spotify_authenticated)(
        spotify_user_id
    ):
        return redirect("spotify-auth")

    try:
        async with SpotifyClient(spotify_user_id) as client:
            data = await get_track_page_data(client, track_id)

        return await sync_to_async(render)(request, "music/pages/track.html", data)
    except Exception:
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
