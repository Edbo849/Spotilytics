from .utils.imports import *


@vary_on_cookie
@cache_page(60 * 60 * 24 * 30)
async def track(request: HttpRequest, track_id: str) -> HttpResponse:
    spotify_user_id = await sync_to_async(request.session.get)("spotify_user_id")
    if not spotify_user_id or not await sync_to_async(is_spotify_authenticated)(
        spotify_user_id
    ):
        return redirect("spotify-auth")

    artist_id = None
    similar_tracks = []
    seen_tracks = set()

    try:
        async with SpotifyClient(spotify_user_id) as client:
            cache_key = client.sanitize_cache_key(f"track_details_{track_id}")
            track_details = cache.get(cache_key)

            if track_details is None:
                track_details = await client.get_track_details(track_id)
                if track_details:
                    cache.set(cache_key, track_details, timeout=None)
                else:
                    raise ValueError("Track details not found.")

            track = track_details

            duration_ms = track.get("duration_ms")
            track["duration"] = (
                await sync_to_async(client.get_duration_ms)(duration_ms)
                if duration_ms
                else "N/A"
            )

            if track.get("album"):
                album_id = track["album"]["id"]
                cache_key = client.sanitize_cache_key(f"album_details_{album_id}")
                album = cache.get(cache_key)

                if album is None:
                    album = await client.get_album(album_id)
                    if album:
                        cache.set(cache_key, album, timeout=None)
            else:
                album = None

            artist_id = (
                track["artists"][0]["id"]
                if track.get("artists") and len(track["artists"]) > 0
                else None
            )

            if not artist_id:
                artist = None
            else:
                cache_key = client.sanitize_cache_key(f"artist_details_{artist_id}")
                artist = cache.get(cache_key)

                if artist is None:
                    artist = await client.get_artist(artist_id)
                    if artist:
                        cache.set(cache_key, artist, timeout=604800)

            if track.get("artists") and len(track["artists"]) > 0:
                cache_key = client.sanitize_cache_key(
                    f"lastfm_similar_10_{track['artists'][0]['name']}_{track['name']}"
                )
                lastfm_similar = cache.get(cache_key)

                if lastfm_similar is None:
                    lastfm_similar = await client.get_lastfm_similar_tracks(
                        track["artists"][0]["name"], track["name"], limit=10
                    )
                    if lastfm_similar:
                        cache.set(cache_key, lastfm_similar, timeout=None)

                for similar in lastfm_similar:
                    identifier = (similar["name"], similar["artist"]["name"])
                    if identifier not in seen_tracks:
                        id_cache_key = client.sanitize_cache_key(
                            f"spotify_track_id_{similar['name']}_{similar['artist']['name']}"
                        )
                        similar_track_id = cache.get(id_cache_key)

                        if similar_track_id is None:
                            similar_track_id = await client.get_spotify_track_id(
                                similar["name"], similar["artist"]["name"]
                            )
                            if similar_track_id:
                                cache.set(id_cache_key, similar_track_id, timeout=None)

                        if similar_track_id:
                            details_cache_key = client.sanitize_cache_key(
                                f"track_details_false_{similar_track_id}"
                            )
                            track_details = cache.get(details_cache_key)

                            if track_details is None:
                                track_details = await client.get_track_details(
                                    similar_track_id, preview=False
                                )
                                if track_details:
                                    cache.set(
                                        details_cache_key, track_details, timeout=None
                                    )

                            if track_details:
                                seen_tracks.add(identifier)
                                similar_tracks.append(track_details)

    except Exception:
        return HttpResponse("Error fetching track details", status=500)

    context = {
        "track": track,
        "album": album,
        "artist": artist,
        "similar_tracks": similar_tracks,
    }
    return await sync_to_async(render)(request, "music/pages/track.html", context)


@vary_on_cookie
async def get_preview_urls(request: HttpRequest) -> JsonResponse:
    spotify_user_id = await sync_to_async(request.session.get)("spotify_user_id")
    if not spotify_user_id:
        return JsonResponse({"error": "Not authenticated"}, status=401)

    track_ids = request.GET.get("track_ids", "").split(",")
    if not track_ids:
        return JsonResponse({"error": "No track IDs provided"}, status=400)

    try:
        async with SpotifyClient(spotify_user_id) as client:
            preview_urls = {}
            for track_id in track_ids:
                cache_key = client.sanitize_cache_key(f"track_details_true_{track_id}")
                track = cache.get(cache_key)

                if track is None:
                    track = await client.get_track_details(track_id, preview=True)
                    if track:
                        cache.set(cache_key, track, timeout=None)

                if track and track.get("preview_url"):
                    preview_urls[track_id] = track["preview_url"]

            return JsonResponse(preview_urls)
    except Exception as e:
        logger.error(f"Error fetching preview URLs: {e}")
        return JsonResponse({"error": str(e)}, status=500)
