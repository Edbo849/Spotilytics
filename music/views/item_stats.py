from .utils.imports import *


@vary_on_cookie
async def get_item_stats(
    request: HttpRequest, item_type: str, item_id: str
) -> JsonResponse:
    spotify_user_id = await sync_to_async(request.session.get)("spotify_user_id")
    if not spotify_user_id:
        return JsonResponse({"error": "Not authenticated"}, status=401)

    time_range = request.GET.get("time_range", "last_4_weeks")
    since, until = await get_date_range(time_range)

    try:
        user = await sync_to_async(SpotifyUser.objects.get)(
            spotify_user_id=spotify_user_id
        )
        stats = await get_item_stats_util(user, item_id, item_type, since, until)
        return JsonResponse(stats)
    except Exception as e:
        logger.error(f"Error fetching stats: {e}")
        return JsonResponse({"error": str(e)}, status=500)
