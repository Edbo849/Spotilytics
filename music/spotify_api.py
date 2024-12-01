import asyncio
import hashlib
import logging
import ssl
from typing import Any

import aiohttp
import certifi
import requests
from asgiref.sync import sync_to_async
from decouple import config
from django.core.cache import cache

from music.models import SpotifyUser
from spotify.util import refresh_spotify_token

logger = logging.getLogger(__name__)

ssl_context = ssl.create_default_context(cafile=certifi.where())

SPOTIFY_API_BASE_URL = "https://api.spotify.com/v1"
LASTFM_API_BASE_URL = "http://ws.audioscrobbler.com/2.0/"
LASTFM_TOKEN = config("LASTFM_TOKEN")


async def fetch(
    session: aiohttp.ClientSession,
    url: str,
    headers: dict[str, str] | None = None,
    params: dict[str, Any] | None = None,
) -> Any:
    """
    Perform an asynchronous GET request and return the JSON response.

    :param session: The aiohttp ClientSession.
    :param url: The URL to send the GET request to.
    :param headers: Optional headers for the request.
    :param params: Optional query parameters for the request.
    :return: The JSON response.
    """
    try:
        ssl_context = ssl.create_default_context()
        ssl_context.check_hostname = False
        ssl_context.verify_mode = ssl.CERT_NONE

        async with session.get(
            url, headers=headers, params=params, ssl=ssl_context
        ) as response:
            response.raise_for_status()
            return await response.json()
    except aiohttp.ClientResponseError as e:
        logger.error(f"HTTP error while fetching {url}: {e.status} {e.message}")
    except Exception as e:
        logger.error(f"Unexpected error while fetching {url}: {e}")
    return {}


def get_duration_ms(duration_ms: int) -> str:
    """
    Convert duration from milliseconds to a string format of minutes and seconds.

    :param duration_ms: Duration in milliseconds.
    :return: Formatted duration string.
    """
    minutes, seconds = divmod(duration_ms / 1000, 60)
    return f"{int(minutes)}:{int(seconds):02d}"


async def get_access_token(spotify_user_id: str) -> str:
    """
    Retrieve the access token for a Spotify user asynchronously.

    :param spotify_user_id: The Spotify user ID.
    :return: Access token string.
    """
    try:
        user = await sync_to_async(SpotifyUser.objects.get)(
            spotify_user_id=spotify_user_id
        )
        is_expired = await sync_to_async(lambda: user.is_token_expired)()
        if is_expired:
            await sync_to_async(refresh_spotify_token)(spotify_user_id)

            user = await sync_to_async(SpotifyUser.objects.get)(
                spotify_user_id=spotify_user_id
            )

        token = await sync_to_async(lambda: user.spotifytoken.access_token)()
        return token

    except SpotifyUser.DoesNotExist:
        logger.error(f"SpotifyUser with ID {spotify_user_id} does not exist.")
    except Exception as e:
        logger.error(f"Error retrieving access token for user {spotify_user_id}: {e}")
    return ""


async def make_spotify_request(
    endpoint: str, spotify_user_id: str, params: dict[str, Any] | None = None
) -> dict[str, Any]:
    """
    Make an asynchronous request to the Spotify API using the user's access token.

    :param endpoint: The Spotify API endpoint (e.g., "search", "me/top/tracks").
    :param spotify_user_id: The Spotify user ID.
    :param params: Optional query parameters for the request.
    :return: The JSON response from Spotify.
    """
    access_token = await get_access_token(spotify_user_id)
    if not access_token:
        logger.error(f"No access token available for user {spotify_user_id}.")
        return {}

    headers = {"Authorization": f"Bearer {access_token}"}
    url = f"{SPOTIFY_API_BASE_URL}/{endpoint}"

    async with aiohttp.ClientSession() as session:
        return await fetch(session, url, headers=headers, params=params)


async def get_spotify_track_id(
    song_name: str, artist_name: str, spotify_user_id: str
) -> str | None:
    """
    Search for a track on Spotify by its name and artist to retrieve its Spotify ID.

    :param song_name: The name of the song.
    :param artist_name: The name of the artist.
    :param spotify_user_id: The Spotify user ID.
    :return: Spotify track ID if found, otherwise None.
    """
    cache_key = f"spotify_track_id_{hashlib.sha256((song_name + artist_name).lower().encode()).hexdigest()}"
    spotify_id = cache.get(cache_key)
    if spotify_id:
        return spotify_id

    query = f"track:{song_name} artist:{artist_name}"
    params = {"q": query, "type": "track", "limit": 1}
    response = await make_spotify_request("search", spotify_user_id, params=params)
    tracks = response.get("tracks", {}).get("items", [])
    if tracks:
        spotify_id = tracks[0].get("id")
        cache.set(cache_key, spotify_id, timeout=86400)
        return spotify_id
    return None


async def get_deezer_preview(song_name: str) -> str | None:
    cache_key = (
        f"deezer_preview_{hashlib.sha256(song_name.lower().encode()).hexdigest()}"
    )
    preview_url = cache.get(cache_key)
    if preview_url:
        return preview_url

    async with aiohttp.ClientSession() as session:
        try:
            async with session.get(
                "https://api.deezer.com/search",
                params={"q": song_name, "limit": 1},
                ssl=ssl_context,
            ) as response:
                response.raise_for_status()
                data = await response.json()
                if data.get("data"):
                    preview_url = data["data"][0].get("preview")
                    cache.set(cache_key, preview_url, timeout=86400)
                    return preview_url
        except aiohttp.ClientError as e:
            logger.error(
                f"Error fetching preview from Deezer for song '{song_name}': {e}"
            )
    return None


async def search_artist_on_spotify(
    artist_name: str, spotify_user_id: str, session: aiohttp.ClientSession
) -> dict[str, Any]:
    """
    Search for an artist on Spotify by their name asynchronously.

    :param artist_name: The name of the artist to search for.
    :param spotify_user_id: The Spotify user ID.
    :param session: The aiohttp ClientSession.
    :return: A dictionary representing the artist details.
    """
    access_token = await get_access_token(spotify_user_id)
    if not access_token:
        return {}

    headers = {"Authorization": f"Bearer {access_token}"}
    params = {"q": artist_name, "type": "artist", "limit": 1}
    search_url = f"{SPOTIFY_API_BASE_URL}/search"

    try:
        spotify_response = await fetch(
            session, search_url, headers=headers, params=params
        )
        artists = spotify_response.get("artists", {}).get("items", [])
        if artists:
            return artists[0]
    except Exception as e:
        logger.error(f"Error searching for artist {artist_name} on Spotify: {e}")
    return {}


async def search_spotify(query: str, spotify_user_id: str) -> dict[str, Any]:
    """
    Search Spotify for tracks, artists, albums, and playlists based on a query.

    :param query: The search query string.
    :param spotify_user_id: The Spotify user ID.
    :return: The JSON response from Spotify.
    """
    params = {"q": query, "type": "track,artist,album,playlist", "limit": 25}
    return await make_spotify_request("search", spotify_user_id, params)


async def get_top_tracks(
    num: int, spotify_user_id: str, time_range: str
) -> list[dict[str, Any]]:
    """
    Retrieve the user's top tracks.

    :param num: Number of top tracks to retrieve.
    :param spotify_user_id: The Spotify user ID.
    :param time_range: The time range for top tracks (e.g., "short_term", "medium_term", "long_term").
    :return: A list of top track dictionaries.
    """
    endpoint = "me/top/tracks"
    params = {"limit": num, "time_range": time_range}
    response = await make_spotify_request(endpoint, spotify_user_id, params)
    return response.get("items", [])


async def get_top_artists(
    num: int, spotify_user_id: str, time_range: str
) -> list[dict[str, Any]]:
    """
    Retrieve the user's top artists.

    :param num: Number of top artists to retrieve.
    :param spotify_user_id: The Spotify user ID.
    :param time_range: The time range for top artists (e.g., "short_term", "medium_term", "long_term").
    :return: A list of top artist dictionaries.
    """
    endpoint = "me/top/artists"
    params = {"limit": num, "time_range": time_range}
    response = await make_spotify_request(endpoint, spotify_user_id, params)
    return response.get("items", [])


async def get_top_genres(
    num: int, spotify_user_id: str, time_range: str
) -> list[dict[str, Any]]:
    """
    Fetch the user's top genres from their top artists.

    :param num: Number of top genres to retrieve.
    :param spotify_user_id: The Spotify user ID.
    :param time_range: The time range for top genres.
    :return: A list of dictionaries containing genre names and their counts.
    """
    top_artists = await get_top_artists(num, spotify_user_id, time_range)
    genre_counts: dict[str, int] = {}

    for artist in top_artists:
        for genre in artist.get("genres", []):
            genre_counts[genre] = genre_counts.get(genre, 0) + 1

    sorted_genres = sorted(
        genre_counts.items(), key=lambda item: item[1], reverse=True
    )[:10]
    return [{"genre": genre, "count": count} for genre, count in sorted_genres]


async def get_recently_played(num: int, spotify_user_id: str) -> list[dict[str, Any]]:
    """
    Retrieve the user's recently played tracks.

    :param num: Number of recently played tracks to retrieve.
    :param spotify_user_id: The Spotify user ID.
    :return: A list of recently played track dictionaries.
    """
    endpoint = "me/player/recently-played"
    params = {"limit": num}
    response = await make_spotify_request(endpoint, spotify_user_id, params)
    return response.get("items", [])


async def fetch_artist_albums(
    artist_id: str, spotify_user_id: str, include_single: bool = False
) -> list[dict[str, Any]]:
    """
    Fetch the albums of a given artist.

    :param artist_id: The Spotify artist ID.
    :param spotify_user_id: The Spotify user ID.
    :param include_single: Whether to include singles in the album list.
    :return: A list of unique album dictionaries.
    """
    params = {
        "include_groups": "album,single" if include_single else "album",
        "limit": 50,
    }
    endpoint = f"artists/{artist_id}/albums"
    response = await make_spotify_request(endpoint, spotify_user_id, params)
    albums = response.get("items", [])
    unique_albums = {album["name"]: album for album in albums}
    return list(unique_albums.values())


async def fetch_artist_top_tracks(
    num: int, artist_id: str, spotify_user_id: str
) -> list[dict[str, Any]]:
    """
    Fetch the top tracks of a given artist.

    :param num: Number of top tracks to retrieve.
    :param artist_id: The Spotify artist ID.
    :param spotify_user_id: The Spotify user ID.
    :return: A list of top track dictionaries.
    """
    endpoint = f"artists/{artist_id}/top-tracks"
    params = {"market": "UK"}
    response = await make_spotify_request(endpoint, spotify_user_id, params)
    return response.get("tracks", [])[:num]


async def get_track_details(track_id: str, spotify_user_id: str) -> dict[str, Any]:
    """
    Retrieve detailed information about a specific track.

    :param track_id: The Spotify track ID.
    :param spotify_user_id: The Spotify user ID.
    :return: A dictionary containing track details.
    """
    track = await make_spotify_request(f"tracks/{track_id}", spotify_user_id)
    if not track.get("preview_url"):
        song_name = track.get("name")
        if song_name:
            preview_url = await get_deezer_preview(song_name)
            track["preview_url"] = preview_url
    return track


async def get_artist(artist_id: str, spotify_user_id: str) -> dict[str, Any]:
    """
    Retrieve the details of a given artist.

    :param artist_id: The Spotify artist ID.
    :param spotify_user_id: The Spotify user ID.
    :return: A dictionary containing artist details.
    """
    endpoint = f"artists/{artist_id}"
    return await make_spotify_request(endpoint, spotify_user_id)


async def get_album(album_id: str, spotify_user_id: str) -> dict[str, Any]:
    """
    Retrieve the details of a given album.

    :param album_id: The Spotify album ID.
    :param spotify_user_id: The Spotify user ID.
    :return: A dictionary containing album details.
    """
    endpoint = f"albums/{album_id}"
    return await make_spotify_request(endpoint, spotify_user_id)


async def get_similar_artists(
    artist_name: str, spotify_user_id: str, limit: int = 20
) -> list[dict[str, Any]]:
    """
    Retrieve similar artists to a given artist using the Last.fm API and fetch their details from Spotify.

    :param artist_name: The name of the artist to find similar artists for.
    :param spotify_user_id: The Spotify user ID.
    :param limit: Number of similar artists to retrieve.
    :return: A list of dictionaries representing similar artists with Spotify details.
    """
    similar_artists_spotify = []
    seen_artist_ids = set()
    try:
        async with aiohttp.ClientSession() as session:
            lastfm_params = {
                "method": "artist.getsimilar",
                "artist": artist_name,
                "api_key": LASTFM_TOKEN,
                "format": "json",
                "limit": limit,
            }
            lastfm_url = LASTFM_API_BASE_URL
            lastfm_response = await fetch(session, lastfm_url, params=lastfm_params)
            similar_artists = lastfm_response.get("similarartists", {}).get(
                "artist", []
            )

            tasks = [
                search_artist_on_spotify(
                    similar_artist["name"], spotify_user_id, session
                )
                for similar_artist in similar_artists
            ]
            results = await asyncio.gather(*tasks, return_exceptions=True)

            for result in results:
                if isinstance(result, dict) and result:
                    artist_id = result.get("id")
                    if artist_id and artist_id not in seen_artist_ids:
                        seen_artist_ids.add(artist_id)
                        similar_artists_spotify.append(result)

    except Exception as e:
        logger.error(
            f"Error getting similar artists for {artist_name} from Last.fm: {e}"
        )

    return similar_artists_spotify


async def get_similar_tracks(
    track_id: str, spotify_user_id: str
) -> list[dict[str, Any]]:
    """
    Get similar tracks based on a seed track using Last.fm's API.

    :param track_id: The Spotify track ID to base recommendations on.
    :param spotify_user_id: The Spotify user ID.
    :return: A list of similar track dictionaries.
    """
    track = await get_track_details(track_id, spotify_user_id)
    song_name = track.get("name")
    artists = track.get("artists", [])
    if not song_name or not artists:
        return []

    artist_name = artists[0].get("name")
    if not artist_name:
        return []

    similar_tracks = await get_lastfm_similar_tracks(artist_name, song_name)

    similar_tracks_with_details = []
    for similar in similar_tracks:
        similar_track_name = similar.get("name")
        similar_artist_name = similar.get("artist", {}).get("name")
        spotify_id = None
        if similar_track_name and similar_artist_name:
            spotify_id = await get_spotify_track_id(
                similar_track_name, similar_artist_name, spotify_user_id
            )
            if spotify_id:
                track_details = await get_track_details(spotify_id, spotify_user_id)
                similar_tracks_with_details.append(track_details)
            else:
                logger.warning(
                    f"Spotify ID not found for track '{similar_track_name}' by '{similar_artist_name}'."
                )
        else:
            logger.warning(
                f"Missing track name or artist name for similar track: {similar}"
            )

    return similar_tracks_with_details


async def get_lastfm_similar_tracks(
    artist_name: str, track_name: str, limit: int = 20
) -> list[dict[str, Any]]:
    """
    Fetch similar tracks from Last.fm based on artist and track name.

    :param artist_name: The name of the artist.
    :param track_name: The name of the track.
    :param limit: Number of similar tracks to retrieve.
    :return: A list of similar track dictionaries.
    """
    cache_key = f"lastfm_similar_tracks_{hashlib.sha256(f'{artist_name}_{track_name}'.encode()).hexdigest()}"
    similar_tracks = cache.get(cache_key)
    if similar_tracks:
        return similar_tracks

    params = {
        "method": "track.getsimilar",
        "artist": artist_name,
        "track": track_name,
        "api_key": LASTFM_TOKEN,
        "format": "json",
        "limit": limit,
    }

    async with aiohttp.ClientSession() as session:
        try:
            async with session.get(
                LASTFM_API_BASE_URL,
                params=params,
                ssl=ssl_context,
            ) as response:
                response.raise_for_status()
                data = await response.json()
                similar_tracks_data = data.get("similartracks", {}).get("track", [])
                formatted_tracks = []
                for track in similar_tracks_data:
                    formatted_tracks.append(
                        {
                            "name": track.get("name"),
                            "artist": {
                                "name": track.get("artist", {}).get("name"),
                                "mbid": track.get("artist", {}).get("mbid"),
                            },
                            "url": track.get("url"),
                        }
                    )
                cache.set(cache_key, formatted_tracks, timeout=86400)
                return formatted_tracks
        except aiohttp.ClientError as e:
            logger.error(
                f"Error fetching similar tracks from Last.fm for '{artist_name} - {track_name}': {e}"
            )
            return []


async def get_recently_played_full(spotify_user_id: str) -> list[dict[str, Any]]:
    """
    Fetch the user's recently played tracks.
    """
    access_token = await get_access_token(spotify_user_id)
    headers = {"Authorization": f"Bearer {access_token}"}
    params = {"limit": 50}
    url = f"{SPOTIFY_API_BASE_URL}/me/player/recently-played"

    recently_played = []

    while url:
        response = requests.get(url, headers=headers, params=params)
        response.raise_for_status()
        data = response.json()
        items = data.get("items", [])
        recently_played.extend(items)

        if len(recently_played) >= 350:
            break

        url = data.get("next")
        if not url:
            break

    return recently_played


async def get_items_by_genre(
    genre_name: str, spotify_user_id: str
) -> tuple[list[dict], list[dict]]:
    params = {"q": f'genre:"{genre_name}"', "type": "artist,album,track", "limit": 25}
    response = await make_spotify_request("search", spotify_user_id, params)
    artists = response.get("artists", {}).get("items", [])
    tracks = response.get("tracks", {}).get("items", [])
    return artists, tracks


async def get_recently_played_since(
    spotify_user_id: str, after_timestamp: int
) -> list[dict[str, Any]]:
    """
    Fetch up to 50 recently played tracks since a specific timestamp.
    """
    access_token = await get_access_token(spotify_user_id)
    if not access_token:
        logger.error(f"No access token available for user {spotify_user_id}.")
        return []

    headers = {"Authorization": f"Bearer {access_token}"}
    params = {"limit": 50, "after": after_timestamp}
    url = f"{SPOTIFY_API_BASE_URL}/me/player/recently-played"

    recently_played = []

    async with aiohttp.ClientSession(
        connector=aiohttp.TCPConnector(ssl=ssl_context)
    ) as session:
        try:
            async with session.get(url, headers=headers, params=params) as response:
                if response.status == 429:
                    retry_after = int(response.headers.get("Retry-After", 1))
                    logger.warning(
                        f"Rate limited. Retrying after {retry_after} seconds."
                    )
                    await asyncio.sleep(retry_after)
                    return await get_recently_played_since(
                        spotify_user_id, after_timestamp
                    )

                response.raise_for_status()
                data = await response.json()
                items = data.get("items", [])

                if items:
                    recently_played.extend(items)

        except aiohttp.ClientError as e:
            logger.error(f"HTTP error while fetching recently played tracks: {e}")
        except Exception as e:
            logger.error(f"Unexpected error: {e}")

    return recently_played
