from music.views.utils.helpers import get_artist_visualizations, get_similar_artists

from .utils.imports import *


@vary_on_cookie
@cache_page(60 * 60 * 24)
async def artist_stats(request: HttpRequest) -> HttpResponse:
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
    top_artists = await get_top_artists(user, since, until, 10)

    seen_artist_ids = {artist["artist_id"] for artist in top_artists}

    async with SpotifyClient(spotify_user_id) as client:
        similar_artists = await get_similar_artists(
            client, top_artists, seen_artist_ids
        )

    visualizations = await get_artist_visualizations(
        user, since, until, top_artists, time_range
    )

    context = {
        "segment": "artist-stats",
        "time_range": time_range,
        "start_date": start_date,
        "end_date": end_date,
        "stats_title": "Artists",
        "top_artists": top_artists,
        "similar_artists": similar_artists,
        **visualizations,
    }

    return render(request, "music/pages/artist_stats.html", context)
