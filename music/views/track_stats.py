from .utils.imports import *


@vary_on_cookie
@cache_page(60 * 60 * 24)
async def track_stats(request: HttpRequest) -> HttpResponse:
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
    top_tracks = await get_top_tracks(user, since, until, 10)

    seen_tracks = set()
    similar_tracks = []

    try:
        async with SpotifyClient(spotify_user_id) as client:
            for track in top_tracks:
                try:
                    cache_key = client.sanitize_cache_key(
                        f"lastfm_similar_1_{track['artist_name']}_{track['track_name']}"
                    )
                    lastfm_similar = cache.get(cache_key)

                    if lastfm_similar is None:
                        lastfm_similar = await client.get_lastfm_similar_tracks(
                            track["artist_name"], track["track_name"], limit=1
                        )
                        if lastfm_similar:
                            cache.set(cache_key, lastfm_similar, timeout=None)

                    for similar in lastfm_similar:
                        identifier = (similar["name"], similar["artist"]["name"])
                        if identifier not in seen_tracks:
                            id_cache_key = client.sanitize_cache_key(
                                f"spotify_track_id_{similar['name']}_{similar['artist']['name']}"
                            )
                            track_id = cache.get(id_cache_key)

                            if track_id is None:
                                track_id = await client.get_spotify_track_id(
                                    similar["name"], similar["artist"]["name"]
                                )
                                if track_id:
                                    cache.set(id_cache_key, track_id, timeout=None)

                            if track_id:
                                details_cache_key = client.sanitize_cache_key(
                                    f"track_details_false_{track_id}"
                                )
                                track_details = cache.get(details_cache_key)

                                if track_details is None:
                                    track_details = await client.get_track_details(
                                        track_id, False
                                    )
                                    if track_details:
                                        cache.set(
                                            details_cache_key,
                                            track_details,
                                            timeout=None,
                                        )

                                if track_details:
                                    seen_tracks.add(identifier)
                                    similar_tracks.append(track_details)

                except Exception as e:
                    logger.error(f"Error fetching similar tracks: {e}", exc_info=True)
                    continue

    except Exception as e:
        logger.error(f"Error fetching similar tracks: {e}", exc_info=True)

    x_label = get_x_label(time_range)
    dates, trends = await get_streaming_trend_data(
        user, since, until, top_tracks, "track"
    )
    trends_chart = generate_chartjs_line_graph(dates, trends, x_label)

    radar_labels = [
        "Total Plays",
        "Total Time (min)",
        "Unique Tracks",
        "Variety",
        "Average Popularity",
    ]
    radar_data = await get_radar_chart_data(user, since, until, top_tracks, "track")
    radar_chart = generate_chartjs_radar_chart(radar_labels, radar_data)

    doughnut_labels, doughnut_values, doughnut_colors = await get_doughnut_chart_data(
        user, since, until, top_tracks, "track"
    )
    doughnut_chart = generate_chartjs_doughnut_chart(
        doughnut_labels, doughnut_values, doughnut_colors
    )

    hourly_data = await get_hourly_listening_data(
        user, since, until, "track", top_tracks[0] if top_tracks else None
    )
    polar_area_chart = generate_chartjs_polar_area_chart(hourly_data)

    bubble_data = await get_bubble_chart_data(user, since, until, top_tracks, "track")
    bubble_chart = generate_chartjs_bubble_chart(bubble_data)

    stats_boxes = await get_stats_boxes_data(user, since, until, top_tracks, "track")

    discovery_dates, discovery_counts = await get_discovery_timeline_data(
        user, since, until, "track"
    )

    discovery_chart = generate_chartjs_line_graph(
        discovery_dates,
        [
            {
                "label": "Tracks Discovered",
                "data": discovery_counts,
                "color": "#1DB954",
            }
        ],
        x_label,
        fill_area=True,
    )

    time_labels, time_datasets = await get_time_period_distribution(
        user, since, until, top_tracks, "track"
    )
    stacked_chart = generate_chartjs_stacked_bar_chart(time_labels, time_datasets)

    replay_labels, replay_values = await get_replay_gaps(
        user, since, until, top_tracks, "track"
    )
    bar_chart = generate_chartjs_bar_chart(
        replay_labels, replay_values, y_label="Hours Between Plays"
    )

    context = {
        "segment": "track-stats",
        "time_range": time_range,
        "start_date": start_date,
        "end_date": end_date,
        "stats_title": "Tracks",
        "top_tracks": top_tracks,
        "similar_tracks": similar_tracks,
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

    return render(request, "music/pages/track_stats.html", context)
