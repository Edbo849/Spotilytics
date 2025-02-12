from .utils.imports import *


def index(request: HttpRequest) -> HttpResponse:
    spotify_user_id = request.session.get("spotify_user_id")
    if not spotify_user_id or not is_spotify_authenticated(spotify_user_id):
        if "spotify_user_id" in request.session:
            request.session.flush()
        return render(request, "music/index.html")
    return render(request, "music/index.html")


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

    error_message = None

    if time_range == "custom":
        if not start_date or not end_date:
            error_message = (
                "Both start date and end date are required for a custom range."
            )
        else:
            try:
                naive_start = datetime.strptime(start_date, "%Y-%m-%d")
                naive_end = datetime.strptime(end_date, "%Y-%m-%d")

                start = timezone.make_aware(naive_start)
                end = timezone.make_aware(naive_end) + timedelta(days=1)

                if start > end:
                    error_message = "Start date cannot be after end date."
                elif end > timezone.now() or start > timezone.now():
                    error_message = "Dates cannot be in the future."
            except ValueError:
                error_message = "Invalid date format. Please use YYYY-MM-DD."

    stats = None
    if has_history:
        try:
            since, until = await get_date_range(time_range, start_date, end_date)

            stats = await sync_to_async(get_listening_stats)(
                user, time_range, start_date, end_date
            )

            top_tracks = await get_top_tracks(user, since, until, 10)
            top_artists = await get_top_artists(user, since, until, 10)
            top_genres = await get_top_genres(user, since, until, 10)
            top_albums = await get_top_albums(user, since, until, 10)

        except ValueError as e:
            error_message = str(e)
            top_tracks, top_artists, top_genres, top_albums = (
                [],
                [],
                [],
                [],
            )
    else:
        top_tracks, top_artists, top_genres, top_albums = (
            [],
            [],
            [],
            [],
        )

    stats = stats or {}

    listening_dates = stats.get("dates", [])
    listening_counts = stats.get("counts", [])
    x_label = stats.get("x_label", "Date")

    datasets = (
        [
            {
                "label": "Plays",
                "data": listening_counts,
                "color": "#1DB954",
            }
        ]
        if listening_counts
        else []
    )

    written_stats = await get_dashboard_stats(user, since, until)

    chart_data = (
        generate_chartjs_line_graph(listening_dates, datasets, x_label)
        if listening_dates
        else None
    )
    genres = [item["genre"] for item in top_genres] if top_genres else []
    genre_counts = [item["count"] for item in top_genres] if top_genres else []
    genre_chart_data = (
        generate_chartjs_pie_chart(genres, genre_counts) if genres else None
    )

    context = {
        "segment": "home",
        "chart_data": chart_data if chart_data else None,
        "genre_data": genre_chart_data if genre_chart_data else None,
        "listening_stats": stats,
        "stats": written_stats,
        "top_tracks": top_tracks,
        "top_artists": top_artists,
        "top_albums": top_albums,
        "time_range": time_range,
        "start_date": start_date,
        "end_date": end_date,
        "error_message": error_message,
    }

    return render(request, "music/home.html", context)


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
