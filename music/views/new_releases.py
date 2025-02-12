from .utils.imports import *


@vary_on_cookie
@cache_page(60 * 60 * 24)
async def new_releases(request: HttpRequest) -> HttpResponse:
    spotify_user_id = await sync_to_async(request.session.get)("spotify_user_id")
    if not spotify_user_id or not await sync_to_async(is_spotify_authenticated)(
        spotify_user_id
    ):
        return redirect("spotify-auth")

    try:
        async with SpotifyClient(spotify_user_id) as client:
            new_releases = await client.get_new_releases()
            albums = new_releases.get("albums", {}).get("items", [])
    except Exception as e:
        logger.error(f"Error fetching new releases: {e}")
        albums = []

    context = {"segment": "new-releases", "albums": albums}
    return render(request, "music/new_releases.html", context)
