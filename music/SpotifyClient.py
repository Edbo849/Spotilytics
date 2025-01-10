import asyncio
import logging
import re
import ssl
from typing import Any

import aiohttp
import certifi
from asgiref.sync import sync_to_async
from decouple import config

from music.models import SpotifyUser
from spotify.util import refresh_spotify_token

logger = logging.getLogger(__name__)


class SpotifyClient:
    SPOTIFY_API_BASE_URL = "https://api.spotify.com/v1"
    LASTFM_API_BASE_URL = "https://ws.audioscrobbler.com/2.0"
    LASTFM_TOKEN = config("LASTFM_TOKEN")

    def __init__(self, spotify_user_id: str):
        self.spotify_user_id = spotify_user_id
        self._session: aiohttp.ClientSession | None = None
        self.ssl_context = self._create_ssl_context()
        self.access_token: str | None = None

    async def __aenter__(self):
        """Async context manager enter."""
        await self._get_session()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        await self.close()

    def _create_ssl_context(self):
        context = ssl.create_default_context(cafile=certifi.where())
        return context

    async def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession()
        return self._session

    async def close(self):
        if self._session and not self._session.closed:
            await self._session.close()
            self._session = None

    async def get_access_token(self) -> str:
        """
        Retrieve the access token for a Spotify user asynchronously.
        """
        if self.access_token:
            return self.access_token
        try:
            user = await sync_to_async(SpotifyUser.objects.get)(
                spotify_user_id=self.spotify_user_id
            )
            is_expired = await sync_to_async(lambda: user.is_token_expired)()
            if is_expired:
                await sync_to_async(refresh_spotify_token)(self.spotify_user_id)
                user = await sync_to_async(SpotifyUser.objects.get)(
                    spotify_user_id=self.spotify_user_id
                )
            self.access_token = (
                await sync_to_async(lambda: user.spotifytoken.access_token)() or ""
            )
            return self.access_token
        except SpotifyUser.DoesNotExist:
            logger.error(f"SpotifyUser with ID {self.spotify_user_id} does not exist.")
        except Exception as e:
            logger.error(
                f"Error retrieving access token for user {self.spotify_user_id}: {e}"
            )
        return ""

    async def fetch(
        self,
        url: str,
        headers: dict[str, str] | None = None,
        params: dict[str, Any] | None = None,
    ) -> Any:
        """
        Perform an asynchronous GET request and return the JSON response.
        """
        session = await self._get_session()
        try:
            async with session.get(
                url, headers=headers, params=params, ssl=self.ssl_context
            ) as response:
                response.raise_for_status()
                return await response.json()
        except aiohttp.ClientResponseError as e:
            logger.error(f"HTTP error while fetching {url}: {e.status} {e.message}")
        except Exception as e:
            logger.error(f"Unexpected error while fetching {url}: {e}")
        return {}

    async def make_spotify_request(
        self, endpoint: str, params: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        """
        Make an asynchronous request to the Spotify API using the user's access token.
        """
        access_token = await self.get_access_token()
        if not access_token:
            logger.error(f"No access token available for user {self.spotify_user_id}.")
            return {}

        headers = {"Authorization": f"Bearer {access_token}"}
        url = f"{self.SPOTIFY_API_BASE_URL}/{endpoint}"

        return await self.fetch(url, headers=headers, params=params)

    async def get_spotify_track_id(
        self, song_name: str, artist_name: str
    ) -> str | None:
        query = f"track:{song_name} artist:{artist_name}"
        params = {"q": query, "type": "track", "limit": 1}
        response = await self.make_spotify_request("search", params=params)
        tracks = response.get("tracks", {}).get("items", [])
        if tracks:
            return tracks[0].get("id")
        return None

    async def get_track_details(
        self, track_id: str, preview: bool = True
    ) -> dict[str, Any]:
        track = await self.make_spotify_request(f"tracks/{track_id}")
        if not track.get("preview_url"):
            song_name = track.get("name")
            if song_name and preview:
                preview_url = await self.get_deezer_preview(
                    song_name, track["artists"][0]["name"]
                )
                track["preview_url"] = preview_url
        return track

    async def get_multiple_track_details(
        self, track_ids: list[str], include_preview: bool = False
    ) -> dict[str, Any]:
        """
        Fetch details for multiple tracks, optionally including preview URLs.

        :param track_ids: A list of Spotify track IDs.
        :param include_preview: Whether to fetch preview URLs from Deezer Music.
        :return: A dictionary containing track details.
        """
        headers = {"Authorization": f"Bearer {await self.get_access_token()}"}
        ids_param = ",".join(track_ids)
        params = {"ids": ids_param}
        url = f"{self.SPOTIFY_API_BASE_URL}/tracks"
        response = await self.fetch(url, headers=headers, params=params)
        tracks = response.get("tracks", [])

        if include_preview:
            preview_tasks = []
            for track in tracks:
                if not track.get("preview_url"):
                    song_name = track.get("name")
                    artist_name = (
                        track["artists"][0]["name"] if track.get("artists") else ""
                    )
                    task = asyncio.create_task(
                        self.get_deezer_preview(song_name, artist_name)
                    )
                    preview_tasks.append((track, task))

            for track, task in preview_tasks:
                preview_url = await task
                track["preview_url"] = preview_url

        return {"tracks": tracks}

    async def get_artist(self, artist_id: str) -> dict[str, Any]:
        return await self.make_spotify_request(f"artists/{artist_id}")

    async def get_multiple_artists(self, artist_ids: list[str]) -> dict[str, Any]:
        headers = {"Authorization": f"Bearer {await self.get_access_token()}"}
        ids_param = ",".join(artist_ids)
        params = {"ids": ids_param}
        url = f"{self.SPOTIFY_API_BASE_URL}/artists"
        response = await self.fetch(url, headers=headers, params=params)
        return {"artists": response.get("artists", [])}

    async def search_artist_on_spotify(self, artist_name: str) -> dict[str, Any]:
        """
        Search for an artist on Spotify by their name asynchronously.

        :param artist_name: The name of the artist to search for.
        :return: A dictionary representing the artist details.
        """
        access_token = await self.get_access_token()
        if not access_token:
            return {}

        headers = {"Authorization": f"Bearer {access_token}"}
        params = {"q": artist_name, "type": "artist", "limit": 1}
        search_url = f"{self.SPOTIFY_API_BASE_URL}/search"

        try:
            spotify_response = await self.fetch(
                search_url, headers=headers, params=params
            )
            artists = spotify_response.get("artists", {}).get("items", [])
            if artists:
                return artists[0]
        except Exception as e:
            logger.error(f"Error searching for artist {artist_name} on Spotify: {e}")
        return {}

    async def search_album_on_spotify(
        self,
        album_name: str,
    ) -> dict[str, Any]:
        """
        Search for an artist on Spotify by their name asynchronously.

        :param artist_name: The name of the artist to search for.
        :param session: The aiohttp ClientSession.
        :return: A dictionary representing the artist details.
        """
        access_token = await self.get_access_token()
        if not access_token:
            return {}

        headers = {"Authorization": f"Bearer {access_token}"}
        params = {"q": album_name, "type": "album", "limit": 1}
        search_url = f"{self.SPOTIFY_API_BASE_URL}/search"

        try:
            spotify_response = await self.fetch(
                search_url, headers=headers, params=params
            )
            albums = spotify_response.get("albums", {}).get("items", [])
            if albums:
                return albums[0]
        except Exception as e:
            logger.error(f"Error searching for artist {album_name} on Spotify: {e}")
        return {}

    async def search_spotify(self, query: str) -> dict[str, Any]:
        """
        Search Spotify for tracks, artists, albums, and playlists based on a query.

        :param query: The search query string.
        :return: The JSON response from Spotify.
        """
        params = {"q": query, "type": "track,artist,album,playlist", "limit": 25}
        return await self.make_spotify_request("search", params)

    async def get_recently_played(self, num: int) -> list[dict[str, Any]]:
        """
        Retrieve the user's recently played tracks.

        :param num: Number of recently played tracks to retrieve.
        :return: A list of recently played track dictionaries.
        """
        endpoint = "me/player/recently-played"
        params = {"limit": num}
        response = await self.make_spotify_request(endpoint, params)
        return response.get("items", [])

    async def get_artist_albums(
        self, artist_id: str, include_groups: list[str] | None = None
    ) -> list[dict[str, Any]]:
        """Get artist albums with optional filtering by release type."""
        params: dict[str, Any] = {
            "limit": 50,
        }

        type_mapping = {
            "album": "album",
            "single": "single",
            "compilation": "compilation",
            "appears_on": "appears_on",
        }

        if include_groups:
            valid_groups = [g for g in include_groups if g in type_mapping]
            if valid_groups:
                params["include_groups"] = ",".join(valid_groups)

        try:
            response = await self.make_spotify_request(
                f"artists/{artist_id}/albums", params
            )
            return response.get("items", [])
        except Exception:
            logger.error
            return []

    async def get_artist_top_tracks(
        self,
        num: int,
        artist_id: str,
    ) -> list[dict[str, Any]]:
        """
        Fetch the top tracks of a given artist.

        :param num: Number of top tracks to retrieve.
        :param artist_id: The Spotify artist ID.
        :return: A list of top track dictionaries.
        """
        endpoint = f"artists/{artist_id}/top-tracks"
        params = {"market": "UK"}
        response = await self.make_spotify_request(endpoint, params)
        return response.get("tracks", [])[:num]

    async def get_album(
        self,
        album_id: str,
        include_tracks: bool = True,
    ) -> dict[str, Any]:
        """
        Retrieve the details of a given album.

        :param album_id: The Spotify album ID.
        :return: A dictionary containing album details.
        """
        endpoint = f"albums/{album_id}"
        params = None
        if not include_tracks:
            params = {"fields": "artists,id,images,name,release_date"}
        return await self.make_spotify_request(endpoint, params)

    async def get_similar_artists(
        self, artist_name: str, limit: int = 20
    ) -> list[dict[str, Any]]:
        """
        Retrieve similar artists to a given artist using the Last.fm API and fetch their details from Spotify.

        :param artist_name: The name of the artist to find similar artists for.
        :param limit: Number of similar artists to retrieve.
        :return: A list of dictionaries representing similar artists with Spotify details.
        """
        similar_artists_spotify = []
        seen_artist_ids = set()
        try:
            lastfm_params = {
                "method": "artist.getsimilar",
                "artist": artist_name,
                "api_key": self.LASTFM_TOKEN,
                "format": "json",
                "limit": limit,
            }
            lastfm_url = self.LASTFM_API_BASE_URL
            lastfm_response = await self.fetch(lastfm_url, params=lastfm_params)
            similar_artists = lastfm_response.get("similarartists", {}).get(
                "artist", []
            )

            tasks = [
                self.search_artist_on_spotify(similar_artist["name"])
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
        self, track_id: str, get_preview: bool = True, limit: int = 5
    ) -> list[dict[str, Any]]:
        """
        Get similar tracks based on a seed track using artist similarity and track popularity.

        :param track_id: The Spotify track ID to base recommendations on.
        :param limit: Number of similar tracks to retrieve.
        :return: A list of similar track dictionaries.
        """
        track = await self.get_track_details(track_id, True)
        artist_name = track["artists"][0]["name"]

        similar_artists = await self.get_similar_artists(artist_name, limit=10)
        similar_tracks = []

        for artist in similar_artists:
            artist_top_tracks = await self.get_artist_top_tracks(1, artist["id"])
            for artist_track in artist_top_tracks:
                if get_preview:
                    track_details = await self.get_track_details(artist_track["id"])
                    similar_tracks.append(track_details)
                else:
                    track_details = await self.get_track_details(
                        artist_track["id"], False
                    )
                    similar_tracks.append(track_details)
        similar_tracks = sorted(
            similar_tracks, key=lambda x: x["popularity"], reverse=True
        )[:limit]

        return similar_tracks

    async def get_recently_played_full(self) -> list[dict[str, Any]]:
        """
        Fetch the user's recently played tracks.

        :return: A list of recently played track dictionaries.
        """
        access_token = await self.get_access_token()
        headers = {"Authorization": f"Bearer {access_token}"}
        params = {"limit": 50}
        url = f"{self.SPOTIFY_API_BASE_URL}/me/player/recently-played"

        recently_played = []

        while url:
            response = await self.fetch(url, headers=headers, params=params)
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

    async def get_artist_top_albums(
        self, artist_id: str, market: str = "US", limit: int = 3
    ) -> list[dict[str, Any]]:
        """
        Retrieve the top albums for a given artist.

        :param artist_id: The Spotify artist ID.
        :param market: The market code.
        :param limit: Number of top albums to retrieve.
        :return: A list of top album dictionaries.
        """
        endpoint = f"artists/{artist_id}/albums"
        params = {
            "include_groups": "album",
            "market": market,
            "limit": limit,
            "album_type": "album",
        }
        response = await self.make_spotify_request(endpoint, params)
        albums = response.get("items", [])
        unique_albums: dict[str, dict[str, Any]] = {}

        for album in albums:
            unique_albums.setdefault(album["name"], album)
        return list(unique_albums.values())[:limit]

    async def get_items_by_genre(
        self, genre_name: str
    ) -> tuple[list[dict], list[dict]]:
        """
        Search for artists and tracks by genre on Spotify.

        :param genre_name: The name of the genre to search for.
        :return: A tuple of lists containing artist and track dictionaries
        """
        params = {
            "q": f'genre:"{genre_name}"',
            "type": "artist,album,track",
            "limit": 25,
        }
        response = await self.make_spotify_request("search", params)
        artists = response.get("artists", {}).get("items", [])
        tracks = response.get("tracks", {}).get("items", [])
        return artists, tracks

    @staticmethod
    def sanitise_song_name(song_name: str) -> str:
        """
        Remove anything after the '-' symbol and content within parentheses or brackets from the song name.

        :param song_name: The original song name.
        :return: The sanitized song name.
        """
        sanitized_name = song_name.split("-", 1)[0].strip()

        sanitized_name = re.sub(r"\(.*?\)|\[.*?\]", "", sanitized_name).strip()

        return sanitized_name

    async def get_deezer_preview(self, song_name: str, artist_name: str) -> str | None:
        """
        Fetches the 30-second preview URL from Deezer based on song and artist name.
        :param song_name: The name of the song.
        :param artist_name: The name of the artist.
        :return: The preview URL if available, otherwise None.
        """
        song_name = self.sanitise_song_name(song_name)

        search_query = f'track:"{song_name}" artist:"{artist_name}"'

        try:
            response = await self.fetch(
                "https://api.deezer.com/search", params={"q": search_query, "limit": 1}
            )
            if response.get("data"):
                preview_url = response["data"][0].get("preview")
                return preview_url
        except aiohttp.ClientError as e:
            logger.error(
                f"Error fetching preview from Deezer for song '{song_name}' by '{artist_name}': {e}"
            )
        except Exception as e:
            logger.error(
                f"Unexpected error while fetching Deezer preview for '{song_name}' by '{artist_name}': {e}"
            )
        return None

    async def get_lastfm_similar_tracks(
        self, artist_name: str, track_name: str, limit: int = 20
    ) -> list[dict[str, Any]]:
        params = {
            "method": "track.getsimilar",
            "artist": artist_name,
            "track": track_name,
            "api_key": self.LASTFM_TOKEN,
            "format": "json",
            "limit": limit,
        }

        try:
            response = await self.fetch(self.LASTFM_API_BASE_URL, params=params)
            similar_tracks_data = response.get("similartracks", {}).get("track", [])
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
            return formatted_tracks
        except aiohttp.ClientError as e:
            logger.error(
                f"Error fetching similar tracks from Last.fm for '{artist_name} - {track_name}': {e}"
            )
        except Exception as e:
            logger.error(
                f"Unexpected error while fetching Last.fm similar tracks for '{artist_name} - {track_name}': {e}"
            )
        return []

    async def get_recently_played_since(
        self, after_timestamp: int
    ) -> list[dict[str, Any]]:
        """
        Fetches recently played tracks since a specific timestamp.

        :param after_timestamp: The timestamp to fetch tracks since.
        :return: A list of recently played track dictionaries.
        """
        access_token = await self.get_access_token()
        if not access_token:
            logger.error("No access token available.")
            return []

        headers = {"Authorization": f"Bearer {access_token}"}
        params = {"limit": 50, "after": after_timestamp}
        url = f"{self.SPOTIFY_API_BASE_URL}/me/player/recently-played"

        recently_played = []

        try:
            response = await self.fetch(url, headers=headers, params=params)
            if response.get("items"):
                recently_played.extend(response["items"])
        except aiohttp.ClientResponseError as e:
            if e.status == 429:
                retry_after = int(e.headers.get("Retry-After", 1))
                logger.warning(f"Rate limited. Retrying after {retry_after} seconds.")
                await asyncio.sleep(retry_after)
                return await self.get_recently_played_since(after_timestamp)
            else:
                logger.error(f"HTTP error while fetching recently played tracks: {e}")
        except Exception as e:
            logger.error(f"Unexpected error while fetching recently played tracks: {e}")

        return recently_played

    @staticmethod
    def get_duration_ms(duration_ms: int) -> str:
        """
        Convert duration from milliseconds to a string format of minutes and seconds.

        :param duration_ms: Duration in milliseconds.
        :return: Formatted duration string.
        """
        minutes, seconds = divmod(duration_ms / 1000, 60)
        return f"{int(minutes)}:{int(seconds):02d}"
