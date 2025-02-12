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

    similar_albums = []
    seen_album_ids = {album["album_id"] for album in top_albums}

    try:
        async with SpotifyClient(spotify_user_id) as client:
            for album in top_albums:
                cache_key = client.sanitize_cache_key(
                    f"similar_artists_10_{album['artist_name']}"
                )
                similar_artists = cache.get(cache_key)

                if similar_artists is None:
                    similar_artists = await client.get_similar_artists(
                        album["artist_name"], limit=10
                    )
                    if similar_artists:
                        cache.set(cache_key, similar_artists, timeout=2592000)

                for artist in similar_artists:
                    if artist["id"] in seen_album_ids:
                        continue

                    cache_key = client.sanitize_cache_key(
                        f"artist_top_albums_1_{artist['id']}"
                    )
                    artist_top_albums = cache.get(cache_key)

                    if artist_top_albums is None:
                        artist_top_albums = await client.get_artist_top_albums(
                            artist["id"], limit=1
                        )
                        if artist_top_albums:
                            cache.set(cache_key, artist_top_albums, timeout=2592000)

                    for similar_album in artist_top_albums:
                        album_id = similar_album["id"]
                        if album_id not in seen_album_ids:
                            similar_albums.append(similar_album)
                            seen_album_ids.add(album_id)
                            if len(similar_albums) >= 10:
                                break
                    if len(similar_albums) >= 10:
                        break
                if len(similar_albums) >= 10:
                    break

    except Exception as e:
        logger.error(f"Error fetching similar albums: {e}", exc_info=True)

    x_label = get_x_label(time_range)

    dates, trends = await get_streaming_trend_data(
        user, since, until, top_albums, "album"
    )
    trends_chart = generate_chartjs_line_graph(dates, trends, x_label)

    radar_labels = [
        "Total Plays",
        "Total Time (min)",
        "Unique Tracks",
        "Variety",
        "Average Popularity",
    ]
    radar_data = await get_radar_chart_data(user, since, until, top_albums, "album")
    radar_chart = generate_chartjs_radar_chart(radar_labels, radar_data)

    doughnut_labels, doughnut_values, doughnut_colors = await get_doughnut_chart_data(
        user, since, until, top_albums, "album"
    )
    doughnut_chart = generate_chartjs_doughnut_chart(
        doughnut_labels, doughnut_values, doughnut_colors
    )

    hourly_data = await get_hourly_listening_data(
        user,
        since,
        until,
        "album",
        top_albums[0] if top_albums else None,
    )
    polar_area_chart = generate_chartjs_polar_area_chart(hourly_data)

    bubble_data = await get_bubble_chart_data(user, since, until, top_albums, "album")
    bubble_chart = generate_chartjs_bubble_chart(bubble_data)

    stats_boxes = await get_stats_boxes_data(user, since, until, top_albums, "album")

    discovery_dates, discovery_counts = await get_discovery_timeline_data(
        user, since, until, "album"
    )

    discovery_chart = generate_chartjs_line_graph(
        discovery_dates,
        [
            {
                "label": "Albums Dsicovered",
                "data": discovery_counts,
                "color": "#1DB954",
            }
        ],
        x_label,
        fill_area=True,
    )

    time_labels, time_datasets = await get_time_period_distribution(
        user, since, until, top_albums, "album"
    )
    stacked_chart = generate_chartjs_stacked_bar_chart(time_labels, time_datasets)

    replay_labels, replay_values = await get_replay_gaps(
        user, since, until, top_albums, "album"
    )
    bar_chart = generate_chartjs_bar_chart(
        replay_labels, replay_values, y_label="Hours Between Plays"
    )

    context = {
        "segment": "album-stats",
        "time_range": time_range,
        "start_date": start_date,
        "end_date": end_date,
        "stats_title": "Albums",
        "top_albums": top_albums,
        "similar_albums": similar_albums,
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

    return render(request, "music/pages/album_stats.html", context)
