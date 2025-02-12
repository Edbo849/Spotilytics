from .utils.imports import *


@vary_on_cookie
@cache_page(60 * 60 * 24 * 7)
async def genre(request: HttpRequest, genre_name: str) -> HttpResponse:
    spotify_user_id = await sync_to_async(request.session.get)("spotify_user_id")
    if not spotify_user_id or not await sync_to_async(is_spotify_authenticated)(
        spotify_user_id
    ):
        return await sync_to_async(redirect)("spotify-auth")

    artists = []
    tracks = []

    try:
        async with SpotifyClient(spotify_user_id) as client:
            cache_key = client.sanitize_cache_key(f"genre_items_{genre_name}")
            genre_items = cache.get(cache_key)

            if genre_items is None:
                artists, tracks = await client.get_items_by_genre(genre_name)
                if artists or tracks:
                    genre_items = {"artists": artists, "tracks": tracks}
                    cache.set(cache_key, genre_items, timeout=None)
            else:
                artists = genre_items.get("artists", [])
                tracks = genre_items.get("tracks", [])

    except Exception as e:
        logger.error(f"Error fetching items for genre {genre_name}: {e}")
        artists, tracks = [], []

    context = {
        "genre_name": genre_name,
        "artists": artists,
        "tracks": tracks,
    }
    return await sync_to_async(render)(request, "music/genre.html", context)
