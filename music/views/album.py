from music.views.utils.helpers import (
    enrich_track_details,
    get_album_details,
    get_artist_details,
)

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
            album = await get_album_details(client, album_id)
            tracks = album["tracks"]["items"]

            artist_id = album["artists"][0]["id"]
            artist_details = await get_artist_details(client, artist_id)
            genres = artist_details.get("genres", []) if artist_details else []

            tracks = await enrich_track_details(client, tracks)

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
