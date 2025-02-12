from .utils.imports import *


@vary_on_cookie
@cache_page(60 * 60 * 24 * 7)
async def artist(request: HttpRequest, artist_id: str) -> HttpResponse:
    spotify_user_id = await sync_to_async(request.session.get)("spotify_user_id")
    if not spotify_user_id or not await sync_to_async(is_spotify_authenticated)(
        spotify_user_id
    ):
        return redirect("spotify-auth")

    try:
        async with SpotifyClient(spotify_user_id) as client:
            artist = await client.get_artist(artist_id)
            if not artist:
                raise ValueError("Artist not found")

            cache_key = client.sanitize_cache_key(f"similar_artists_{artist_id}")
            similar_artists = cache.get(cache_key)
            if similar_artists is None:
                similar_artists = await client.get_similar_artists(artist["name"])
                if similar_artists:
                    cache.set(cache_key, similar_artists, timeout=None)

            similar_artists_spotify = similar_artists if similar_artists else []
            similar_artists_spotify = [
                similar
                for similar in similar_artists_spotify
                if similar.get("id") != artist_id
            ]

            cache_key = client.sanitize_cache_key(f"artist_albums_all_{artist_id}")
            albums = cache.get(cache_key)
            if albums is None:
                albums = await client.get_artist_albums(artist_id, include_groups=None)
                if albums:
                    cache.set(cache_key, albums, timeout=604800)

            compilations = [
                album for album in albums if album.get("album_type") == "compilation"
            ]

            cache_key = client.sanitize_cache_key(f"artist_top_tracks_{artist_id}_5")
            top_tracks = cache.get(cache_key)

            if top_tracks is None:
                top_tracks = await client.get_artist_top_tracks(5, artist_id)
                if top_tracks:
                    cache.set(cache_key, top_tracks, timeout=604800)

            for track in top_tracks:
                if track and track.get("id"):
                    cache_key = client.sanitize_cache_key(
                        f"track_details_{track['id']}"
                    )
                    track_details = cache.get(cache_key)

                    if track_details is None:
                        track_details = await client.get_track_details(track["id"])
                        if track_details:
                            cache.set(cache_key, track_details, timeout=None)

                    track["preview_url"] = track_details.get("preview_url")
                    track["album"] = track_details.get("album")

    except Exception as e:
        logger.critical(f"Error fetching artist data from Spotify: {e}")
        artist, similar_artists_spotify, albums, compilations, top_tracks = (
            None,
            [],
            [],
            [],
            [],
        )

    context = {
        "artist": artist,
        "similar_artists": similar_artists_spotify,
        "albums": albums,
        "compilations": compilations,
        "top_tracks": top_tracks,
    }
    return await sync_to_async(render)(request, "music/pages/artist.html", context)


@vary_on_cookie
@cache_page(60 * 60 * 24 * 7)
@csrf_exempt
async def artist_all_songs(request: HttpRequest, artist_id: str) -> HttpResponse:
    spotify_user_id = await sync_to_async(request.session.get)("spotify_user_id")
    if not spotify_user_id or not await sync_to_async(is_spotify_authenticated)(
        spotify_user_id
    ):
        return await sync_to_async(redirect)("spotify-auth")

    try:
        async with SpotifyClient(spotify_user_id) as client:
            artist = await client.get_artist(artist_id)

            cache_key = client.sanitize_cache_key(f"artist_albums_{artist_id}")
            artist_albums = cache.get(cache_key)

            if artist_albums is None:
                albums = await client.get_artist_albums(
                    artist_id, include_groups=["album", "single", "compilation"]
                )
                if artist_albums:
                    cache.set(cache_key, artist_albums, timeout=None)

            track_ids_set: set[str] = set()
            for album in albums:
                cache_key = client.sanitize_cache_key(f"album_details_{album['id']}")
                album_data = cache.get(cache_key)

                if album_data is None:
                    album_data = await client.get_album(album["id"])
                    if album_data:
                        cache.set(cache_key, album_data, timeout=None)

                album_tracks = album_data.get("tracks", {}).get("items", [])
                for track in album_tracks:
                    track_id = track.get("id")
                    if track_id:
                        track_ids_set.add(track_id)

            track_ids_list: list[str] = list(track_ids_set)
            batch_size = 50
            track_details_dict = {}

            async def fetch_track_batch(batch_ids):
                response = await client.get_multiple_track_details(batch_ids)
                tracks = response.get("tracks", [])
                for track in tracks:
                    if track and track.get("id"):
                        track_details_dict[track["id"]] = track

            tasks = [
                asyncio.create_task(
                    fetch_track_batch(track_ids_list[i : i + batch_size])
                )
                for i in range(0, len(track_ids_list), batch_size)
            ]

            await asyncio.gather(*tasks)

            tracks = []
            for album in albums:
                cache_key = client.sanitize_cache_key(f"album_details_{album['id']}")
                album_data = cache.get(cache_key)

                if album_data is None:
                    album_data = await client.get_album(album["id"])
                    if album_data:
                        cache.set(cache_key, album_data, timeout=None)

                album_tracks = album_data.get("tracks", {}).get("items", [])
                for track in album_tracks:
                    track_id = track.get("id")
                    if track_id and track_id in track_details_dict:
                        track_detail = track_details_dict[track_id]
                        track_info = {
                            "id": track_id,
                            "name": track_detail.get("name"),
                            "album": {
                                "id": album["id"],
                                "name": album["name"],
                                "images": album["images"],
                                "release_date": album.get("release_date"),
                            },
                            "duration": SpotifyClient.get_duration_ms(
                                track_detail.get("duration_ms")
                            ),
                            "popularity": track_detail.get("popularity", "N/A"),
                        }
                        tracks.append(track_info)

    except Exception as e:
        logger.error(f"Error fetching artist data from Spotify: {e}")
        artist, tracks = None, []

    context = {
        "artist": artist,
        "tracks": tracks,
    }
    return await sync_to_async(render)(
        request, "music/pages/artist_tracks.html", context
    )


@vary_on_cookie
async def get_artist_releases(request: HttpRequest, artist_id: str) -> JsonResponse:
    spotify_user_id = await sync_to_async(request.session.get)("spotify_user_id")
    if not spotify_user_id:
        return JsonResponse({"error": "Not authenticated"}, status=401)

    release_type = request.GET.get("type", "all")

    try:
        async with SpotifyClient(spotify_user_id) as client:
            releases = await client.get_artist_albums(
                artist_id,
                include_groups=[release_type] if release_type != "all" else None,
            )
            return JsonResponse({"releases": releases})
    except Exception as e:
        logger.error(f"Error fetching artist releases: {e}")
        return JsonResponse({"error": str(e)}, status=500)
