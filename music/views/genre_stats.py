from music.views.utils.helpers import get_genre_visualizations, get_similar_genres

from .utils.imports import *


@vary_on_cookie
@cache_page(60 * 60 * 24)
async def genre_stats(request: HttpRequest) -> HttpResponse:
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
    top_genres = await get_top_genres(user, since, until, 10)

    seen_genres = {genre["genre"] for genre in top_genres}

    async with SpotifyClient(spotify_user_id) as client:
        similar_genres = await get_similar_genres(client, top_genres, seen_genres)

    visualizations = await get_genre_visualizations(
        user, since, until, top_genres, time_range
    )

    context = {
        "segment": "genre-stats",
        "time_range": time_range,
        "start_date": start_date,
        "end_date": end_date,
        "stats_title": "Genres",
        "top_genres": top_genres,
        "similar_genres": similar_genres,
        **visualizations,
    }

    return render(request, "music/pages/genre_stats.html", context)
