from music.views.utils.helpers import get_artist_all_songs_data, get_artist_page_data

from .utils.imports import *


@vary_on_cookie
@cache_page(60 * 60 * 24 * 7)
async def artist(request: HttpRequest, artist_id: str) -> HttpResponse:
    spotify_user_id = await sync_to_async(request.session.get)("spotify_user_id")
    if not spotify_user_id or not await sync_to_async(is_spotify_authenticated)(
        spotify_user_id
    ):
        return redirect("spotify-auth")

    async with SpotifyClient(spotify_user_id) as client:
        data = await get_artist_page_data(client, artist_id)

    return await sync_to_async(render)(request, "music/pages/artist.html", data)


@vary_on_cookie
@cache_page(60 * 60 * 24 * 7)
@csrf_exempt
async def artist_all_songs(request: HttpRequest, artist_id: str) -> HttpResponse:
    spotify_user_id = await sync_to_async(request.session.get)("spotify_user_id")
    if not spotify_user_id or not await sync_to_async(is_spotify_authenticated)(
        spotify_user_id
    ):
        return await sync_to_async(redirect)("spotify-auth")

    async with SpotifyClient(spotify_user_id) as client:
        data = await get_artist_all_songs_data(client, artist_id)

    return await sync_to_async(render)(request, "music/pages/artist_tracks.html", data)


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
