from music.views.utils.helpers import get_genre_items

from .utils.imports import *


@vary_on_cookie
@cache_page(60 * 60 * 24 * 7)
async def genre(request: HttpRequest, genre_name: str) -> HttpResponse:
    spotify_user_id = await sync_to_async(request.session.get)("spotify_user_id")
    if not spotify_user_id or not await sync_to_async(is_spotify_authenticated)(
        spotify_user_id
    ):
        return await sync_to_async(redirect)("spotify-auth")

    async with SpotifyClient(spotify_user_id) as client:
        items = await get_genre_items(client, genre_name)

    context = {
        "genre_name": genre_name,
        "artists": items["artists"],
        "tracks": items["tracks"],
    }
    return await sync_to_async(render)(request, "music/pages/genre.html", context)
