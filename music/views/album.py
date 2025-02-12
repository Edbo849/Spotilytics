from .utils.imports import *


@vary_on_cookie
@cache_page(60 * 60 * 24 * 30)
async def album(request: HttpRequest, album_id: str) -> HttpResponse:
    spotify_user_id = await sync_to_async(request.session.get)("spotify_user_id")
    if not spotify_user_id or not await sync_to_async(is_spotify_authenticated)(
        spotify_user_id
    ):
        return redirect("spotify-auth")

    try:
        async with SpotifyClient(spotify_user_id) as client:
            cache_key = client.sanitize_cache_key(f"album_details_{album_id}")
            album = cache.get(cache_key)

            if album is None:
                album = await client.get_album(album_id)
                if album:
                    cache.set(cache_key, album, timeout=None)
                else:
                    raise ValueError("Album not found")

            tracks = album["tracks"]["items"]

            artist_id = album["artists"][0]["id"]
            cache_key = client.sanitize_cache_key(f"artist_details_{artist_id}")
            artist_details = cache.get(cache_key)

            if artist_details is None:
                artist_details = await client.get_artist(artist_id)
                if artist_details:
                    cache.set(cache_key, artist_details, timeout=604800)

            genres = artist_details.get("genres", []) if artist_details else []

            for track in tracks:
                cache_key = client.sanitize_cache_key(f"track_details_{track['id']}")
                track_details = cache.get(cache_key)

                if track_details is None:
                    track_details = await client.get_track_details(track["id"])
                    if track_details:
                        cache.set(cache_key, track_details, timeout=None)

                duration_ms = track["duration_ms"]
                track["duration"] = client.get_duration_ms(duration_ms)
                track["preview_url"] = (
                    track_details.get("preview_url") if track_details else None
                )
                track["popularity"] = (
                    track_details.get("popularity", "N/A") if track_details else "N/A"
                )

    except Exception as e:
        logger.critical(f"Error fetching album data from Spotify: {e}")
        album, tracks, genres = None, [], []
        artist_id = None

    context = {
        "artist_id": artist_id,
        "album": album,
        "tracks": tracks,
        "genres": genres,
    }
    return await sync_to_async(render)(request, "music/pages/album.html", context)
