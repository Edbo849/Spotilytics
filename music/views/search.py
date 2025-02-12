from .utils.imports import *


async def search(request: HttpRequest) -> HttpResponse:
    spotify_user_id = await sync_to_async(request.session.get)("spotify_user_id")
    if not spotify_user_id or not await sync_to_async(is_spotify_authenticated)(
        spotify_user_id
    ):
        return redirect("spotify-auth")
    query = request.GET.get("q")
    if not query:
        return render(request, "music/pages/search_results.html", {"results": None})

    try:
        async with SpotifyClient(spotify_user_id) as client:
            results = await client.search_spotify(query)
    except Exception as e:
        logger.critical(f"Error searching Spotify: {e}")
        results = None

    return render(request, "music/pages/search_results.html", {"results": results})
