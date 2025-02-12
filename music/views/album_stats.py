from music.views.utils.helpers import get_album_visualizations, get_similar_albums

from .utils.imports import *


@vary_on_cookie
@cache_page(60 * 60 * 24)
async def album_stats(request: HttpRequest) -> HttpResponse:
    spotify_user_id = await sync_to_async(request.session.get)("spotify_user_id")
    if not spotify_user_id or not await sync_to_async(is_spotify_authenticated)(
        spotify_user_id
    ):
        logger.warning(f"User not authenticated: {spotify_user_id}")
        return redirect("spotify-auth")

    time_range = request.GET.get("time_range", "last_4_weeks")
    start_date = request.GET.get("start_date")
    end_date = request.GET.get("end_date")

    since, until = await get_date_range(time_range, start_date, end_date)
    user = await sync_to_async(SpotifyUser.objects.get)(spotify_user_id=spotify_user_id)
    top_albums = await get_top_albums(user, since, until, 10)

    seen_album_ids = {album["album_id"] for album in top_albums}

    async with SpotifyClient(spotify_user_id) as client:
        similar_albums = await get_similar_albums(client, top_albums, seen_album_ids)

    visualizations = await get_album_visualizations(
        user, since, until, top_albums, time_range
    )

    context = {
        "segment": "album-stats",
        "time_range": time_range,
        "start_date": start_date,
        "end_date": end_date,
        "stats_title": "Albums",
        "top_albums": top_albums,
        "similar_albums": similar_albums,
        **visualizations,
    }

    return render(request, "music/pages/album_stats.html", context)
