from music.views.utils.helpers import get_home_visualizations, validate_date_range

from .utils.imports import *


def index(request: HttpRequest) -> HttpResponse:
    spotify_user_id = request.session.get("spotify_user_id")
    if not spotify_user_id or not is_spotify_authenticated(spotify_user_id):
        if "spotify_user_id" in request.session:
            request.session.flush()
        return render(request, "music/pages/index.html")
    return render(request, "music/pages/index.html")


@vary_on_cookie
@cache_page(60 * 60 * 24)
async def home(request: HttpRequest) -> HttpResponse:
    spotify_user_id = await sync_to_async(request.session.get)("spotify_user_id")
    if not spotify_user_id or not await sync_to_async(is_spotify_authenticated)(
        spotify_user_id
    ):
        return redirect("spotify-auth")

    try:
        user = await sync_to_async(SpotifyUser.objects.get)(
            spotify_user_id=spotify_user_id
        )
        has_history = await sync_to_async(
            PlayedTrack.objects.filter(user=user).exists
        )()
    except SpotifyUser.DoesNotExist:
        return redirect("spotify-auth")

    time_range = request.GET.get("time_range", "last_4_weeks")
    start_date = request.GET.get("start_date")
    end_date = request.GET.get("end_date")

    start_date, end_date, error_message = await validate_date_range(
        time_range, start_date, end_date
    )

    stats = await get_home_visualizations(
        user, has_history, time_range, start_date, end_date
    )
    logger.critical(stats)

    context = {
        "segment": "home",
        "time_range": time_range,
        "start_date": start_date,
        "end_date": end_date,
        "error_message": error_message,
        **stats,
    }

    return render(request, "music/pages/home.html", context)


@vary_on_cookie
@cache_page(60 * 15)
async def recently_played_section(request: HttpRequest) -> HttpResponse:
    spotify_user_id = await sync_to_async(request.session.get)("spotify_user_id")

    try:
        user = await sync_to_async(SpotifyUser.objects.get)(
            spotify_user_id=spotify_user_id
        )
        recently_played = await get_recently_played(user, None, None, 20)
    except Exception as e:
        logger.error(f"Error fetching recently played: {e}")
        recently_played = []

    return render(
        request,
        "music/partials/recently_played.html",
        {"recently_played": recently_played},
    )
