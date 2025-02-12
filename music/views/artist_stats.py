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

    top_artist_ids = {artist["artist_id"] for artist in top_artists}

    seen_artist_ids = set(top_artist_ids)
    similar_artists = []
    try:
        async with SpotifyClient(spotify_user_id) as client:
            for artist in top_artists:
                cache_key = client.sanitize_cache_key(
                    f"similar_artists_1_{artist['artist_name']}"
                )
                similar = cache.get(cache_key)

                if similar is None:
                    similar = await client.get_similar_artists(
                        artist["artist_name"], limit=1
                    )
                    if similar:
                        cache.set(cache_key, similar, timeout=2592000)

                for s in similar:
                    if s["id"] not in seen_artist_ids:
                        similar_artists.append(s)
                        seen_artist_ids.add(s["id"])
    except Exception as e:
        logger.error(f"Error fetching similar artists: {e}")

    x_label = get_x_label(time_range)

    dates, trends = await get_streaming_trend_data(
        user, since, until, top_artists, "artist"
    )
    trends_chart = generate_chartjs_line_graph(dates, trends, x_label)

    radar_labels = [
        "Total Plays",
        "Total Time (min)",
        "Unique Tracks",
        "Variety",
        "Average Popularity",
    ]
    trends_chart = generate_chartjs_line_graph(dates, trends, x_label)

    radar_labels = [
        "Total Plays",
        "Total Time (min)",
        "Unique Tracks",
        "Variety",
        "Average Popularity",
    ]
    radar_data = await get_radar_chart_data(user, since, until, top_artists, "artist")
    radar_chart = generate_chartjs_radar_chart(radar_labels, radar_data)

    doughnut_labels, doughnut_values, doughnut_colors = await get_doughnut_chart_data(
        user, since, until, top_artists, "artist"
    )
    doughnut_chart = generate_chartjs_doughnut_chart(
        doughnut_labels, doughnut_values, doughnut_colors
    )

    hourly_data = await get_hourly_listening_data(
        user, since, until, "artist", top_artists[0] if top_artists else None
    )
    polar_area_chart = generate_chartjs_polar_area_chart(hourly_data)

    bubble_data = await get_bubble_chart_data(user, since, until, top_artists, "artist")
    bubble_chart = generate_chartjs_bubble_chart(bubble_data)

    stats_boxes = await get_stats_boxes_data(user, since, until, top_artists, "artist")

    discovery_dates, discovery_counts = await get_discovery_timeline_data(
        user, since, until, "artist"
    )

    discovery_chart = generate_chartjs_line_graph(
        discovery_dates,
        [
            {
                "label": "Artists Discovered",
                "data": discovery_counts,
                "color": "#1DB954",
            }
        ],
        x_label,
        fill_area=True,
    )

    time_labels, time_datasets = await get_time_period_distribution(
        user, since, until, top_artists, "artist"
    )
    stacked_chart = generate_chartjs_stacked_bar_chart(time_labels, time_datasets)

    replay_labels, replay_values = await get_replay_gaps(
        user, since, until, top_artists, "artist"
    )
    bar_chart = generate_chartjs_bar_chart(
        replay_labels, replay_values, y_label="Hours Between Plays"
    )

    context = {
        "segment": "artist-stats",
        "time_range": time_range,
        "start_date": start_date,
        "end_date": end_date,
        "stats_title": "Artists",
        "top_artists": top_artists,
        "similar_artists": similar_artists,
        "trends_chart": trends_chart,
        "radar_chart": radar_chart,
        "doughnut_chart": doughnut_chart,
        "stats_boxes": stats_boxes,
        "polar_area_chart": polar_area_chart,
        "bubble_chart": bubble_chart,
        "discovery_chart": discovery_chart,
        "stacked_chart": stacked_chart,
        "bar_chart": bar_chart,
    }

    return render(request, "music/pages/artist_stats.html", context)
