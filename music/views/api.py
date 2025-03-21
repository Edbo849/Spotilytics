from django.db.models import Avg
from django.views.decorators.http import require_GET

from .utils.imports import *


@require_GET
async def get_top_items(request: HttpRequest) -> JsonResponse:
    """API endpoint to get top artists/tracks/albums/genres for the list view."""
    spotify_user_id = await sync_to_async(request.session.get)("spotify_user_id")
    if not spotify_user_id:
        return JsonResponse({"error": "Not authenticated"}, status=401)

    item_type = request.GET.get("type")  # "artists", "tracks", "albums", "genres"
    time_range = request.GET.get("time_range", "last_4_weeks")
    start_date = request.GET.get("start_date")
    end_date = request.GET.get("end_date")

    if not item_type:
        return JsonResponse({"error": "Item type is required"}, status=400)

    since, until = await get_date_range(time_range, start_date, end_date)
    user = await sync_to_async(SpotifyUser.objects.get)(spotify_user_id=spotify_user_id)

    if item_type == "artists":
        top_items = await get_top_artists(user, since, until, 50)
    elif item_type == "tracks":
        top_items = await get_top_tracks(user, since, until, 50)
    elif item_type == "albums":
        top_items = await get_top_albums(user, since, until, 50)
    elif item_type == "genres":
        top_items = await get_top_genres(user, since, until, 50)

        @sync_to_async
        def get_avg_song_length():
            return (
                PlayedTrack.objects.filter(user=user).aggregate(avg=Avg("duration_ms"))[
                    "avg"
                ]
                or 180000
            )

        avg_duration = await get_avg_song_length()
        for item in top_items:
            # Convert from milliseconds to minutes and multiply by count
            item["total_minutes"] = (avg_duration / 60000) * item["count"]

    else:
        return JsonResponse({"error": "Invalid item type"}, status=400)

    return JsonResponse({"items": top_items})
