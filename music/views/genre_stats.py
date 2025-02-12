from utils.imports import *


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

    similar_genres = []
    seen_genres = {genre["genre"] for genre in top_genres}

    try:
        async with SpotifyClient(spotify_user_id) as client:
            for genre in top_genres:
                artists, _ = await client.get_items_by_genre(genre["genre"])

                for artist in artists[:3]:
                    cache_key = client.sanitize_cache_key(
                        f"similar_artists_1_{artist['name']}"
                    )
                    similar_artists = cache.get(cache_key)

                    if similar_artists is None:
                        similar_artists = await client.get_similar_artists(
                            artist["name"], limit=1
                        )
                        if similar_artists:
                            cache.set(cache_key, similar_artists, timeout=2592000)

                    for similar_artist in similar_artists:
                        artist_genres = similar_artist.get("genres", [])
                        for artist_genre in artist_genres:
                            if artist_genre not in seen_genres:
                                seen_genres.add(artist_genre)
                                similar_genres.append(
                                    {
                                        "genre": artist_genre,
                                        "count": 1,
                                    }
                                )
                                if len(similar_genres) >= 10:
                                    break
                        if len(similar_genres) >= 10:
                            break
                    if len(similar_genres) >= 10:
                        break
                if len(similar_genres) >= 10:
                    break

    except Exception as e:
        logger.error(f"Error fetching similar genres: {e}", exc_info=True)

    x_label = get_x_label(time_range)
    dates, trends = await get_streaming_trend_data(
        user, since, until, top_genres, "genre"
    )
    trends_chart = generate_chartjs_line_graph(dates, trends, x_label)

    radar_labels = [
        "Total Plays",
        "Total Time (min)",
        "Unique Tracks",
        "Variety",
        "Average Popularity",
    ]
    radar_data = await get_radar_chart_data(user, since, until, top_genres, "genre")
    radar_chart = generate_chartjs_radar_chart(radar_labels, radar_data)

    doughnut_labels, doughnut_values, doughnut_colors = await get_doughnut_chart_data(
        user, since, until, top_genres, "genre"
    )
    doughnut_chart = generate_chartjs_doughnut_chart(
        doughnut_labels, doughnut_values, doughnut_colors
    )

    hourly_data = await get_hourly_listening_data(
        user, since, until, "genre", top_genres[0] if top_genres else None
    )
    polar_area_chart = generate_chartjs_polar_area_chart(hourly_data)

    bubble_data = await get_bubble_chart_data(user, since, until, top_genres, "genre")
    bubble_chart = generate_chartjs_bubble_chart(bubble_data)

    stats_boxes = await get_stats_boxes_data(user, since, until, top_genres, "genre")

    discovery_dates, discovery_counts = await get_discovery_timeline_data(
        user, since, until, "genre"
    )

    discovery_chart = generate_chartjs_line_graph(
        discovery_dates,
        [
            {
                "label": "Genres Discovered",
                "data": discovery_counts,
                "color": "#1DB954",
            }
        ],
        x_label,
        fill_area=True,
    )

    time_labels, time_datasets = await get_time_period_distribution(
        user, since, until, top_genres, "genre"
    )
    stacked_chart = generate_chartjs_stacked_bar_chart(time_labels, time_datasets)

    replay_labels, replay_values = await get_replay_gaps(
        user, since, until, top_genres, "genre"
    )
    bar_chart = generate_chartjs_bar_chart(
        replay_labels, replay_values, y_label="Hours Between Plays"
    )

    context = {
        "segment": "genre-stats",
        "time_range": time_range,
        "start_date": start_date,
        "end_date": end_date,
        "stats_title": "Genres",
        "top_genres": top_genres,
        "similar_genres": similar_genres,
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
    return render(request, "music/genre_stats.html", context)
