import asyncio
import base64
import logging
import re
import ssl
import time
from typing import Any

import aiohttp
import certifi
from asgiref.sync import sync_to_async
from decouple import config
from django.core.cache import cache

from music.models import SpotifyUser
from spotify.util import refresh_spotify_token

logger = logging.getLogger(__name__)


class RateLimiter:
    """Token bucket rate limiter for Spotify API"""

    def __init__(self, rate_limit: int, time_window: float):
        self.rate_limit = rate_limit
        self.time_window = time_window
        self.tokens = float(rate_limit)
        self.last_update = time.time()

    async def acquire(self) -> bool:
        """Acquire a token, waiting if necessary"""
        while self.tokens <= 0:
            now = time.time()
            time_passed = now - self.last_update
            self.tokens = min(
                self.rate_limit,
                self.tokens + (time_passed * self.rate_limit / self.time_window),
            )
            self.last_update = now

            if self.tokens <= 0:
                await asyncio.sleep(0.1)

        self.tokens -= 1
        return True


class SpotifyClient:
    """Client for interacting with Spotify API."""

    SPOTIFY_API_BASE_URL = "https://api.spotify.com/v1"
    LASTFM_API_BASE_URL = "https://ws.audioscrobbler.com/2.0"
    LASTFM_TOKEN = config("LASTFM_TOKEN")
    DEEZER_PREVIEW_CACHE_TIMEOUT = 60 * 60 * 24 * 7  # 7 days
    CACHE_TIMEOUT = 60 * 60 * 24 * 30  # 30 days

    def __init__(self, spotify_user_id: str):
        """Initialize a SpotifyClient for a specific user.

        Args:
            spotify_user_id: The Spotify user ID to authenticate as
        """
        self.spotify_user_id = spotify_user_id
        self._session: aiohttp.ClientSession | None = None
        self.ssl_context = self._create_ssl_context()
        self.access_token: str | None = None
        self.general_limiter = RateLimiter(rate_limit=50, time_window=30)
        self.player_limiter = RateLimiter(rate_limit=10, time_window=30)

    async def __aenter__(self):
        """Async context manager enter."""
        await self._get_session()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        await self.close()

    def _create_ssl_context(self) -> ssl.SSLContext:
        """Create SSL context for secure connections."""
        return ssl.create_default_context(cafile=certifi.where())

    async def _get_session(self) -> aiohttp.ClientSession:
        """Get or create the aiohttp session."""
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession()
        return self._session

    async def close(self) -> None:
        """Close the aiohttp session if it exists."""
        if self._session and not self._session.closed:
            await self._session.close()
            self._session = None

    async def get_access_token(self) -> str:
        """
        Retrieve the access token for a Spotify user asynchronously.

        Returns:
            The access token string or empty string if not available
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
        max_retries: int = 3,
        retry_delay: float = 1.0,
    ) -> Any:
        """
        Perform an asynchronous GET request with rate limiting and retries.

        Args:
            url: The URL to fetch
            headers: Optional HTTP headers
            params: Optional query parameters
            max_retries: Maximum number of retry attempts
            retry_delay: Base delay between retries in seconds

        Returns:
            JSON response data or empty dict on failure
        """
        # Select the appropriate rate limiter based on the endpoint
        limiter = self.player_limiter if "/player/" in url else self.general_limiter

        for attempt in range(max_retries):
            try:
                await limiter.acquire()
                session = await self._get_session()

                async with session.get(
                    url, headers=headers, params=params, ssl=self.ssl_context
                ) as response:
                    if response.status == 429:
                        retry_after = int(response.headers.get("Retry-After", 1))
                        logger.warning(f"Rate limited. Waiting {retry_after} seconds")
                        await asyncio.sleep(retry_after)
                        continue

                    response.raise_for_status()
                    return await response.json()

            except aiohttp.ClientConnectorError as e:
                if "Connection reset by peer" in str(e):
                    if attempt < max_retries - 1:
                        wait_time = retry_delay * (attempt + 1)
                        logger.warning(
                            f"Connection reset, retrying in {wait_time} seconds. "
                            f"Attempt {attempt + 1}/{max_retries}"
                        )
                        await asyncio.sleep(wait_time)
                        continue
                    else:
                        logger.error(
                            f"Connection reset after {max_retries} retries: {e}"
                        )
                else:
                    logger.error(f"Connection error while fetching {url}: {e}")
            except aiohttp.ClientResponseError as e:
                logger.error(f"HTTP error while fetching {url}: {e.status} {e.message}")
            except Exception as e:
                logger.error(f"Unexpected error while fetching {url}: {e}")
                if attempt < max_retries - 1:
                    wait_time = retry_delay * (attempt + 1)
                    logger.warning(
                        f"Retrying in {wait_time} seconds. "
                        f"Attempt {attempt + 1}/{max_retries}"
                    )
                    await asyncio.sleep(wait_time)
                    continue

        return {}

    async def make_spotify_request(
        self, endpoint: str, params: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        """
        Make an asynchronous request to the Spotify API using the user's access token.

        Args:
            endpoint: The Spotify API endpoint to request
            params: Optional query parameters

        Returns:
            JSON response data or empty dict on failure
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
        """
        Get Spotify track ID from track name and artist name.

        Args:
            song_name: Name of the song
            artist_name: Name of the artist

        Returns:
            Spotify track ID or None if not found
        """
        query = f"track:{song_name} artist:{artist_name}"
        params = {"q": query, "type": "track", "limit": 1}
        response = await self.make_spotify_request("search", params=params)
        tracks = response.get("tracks", {}).get("items", [])
        return tracks[0].get("id") if tracks else None

    def sanitize_cache_key(self, key: str) -> str:
        """
        Sanitize cache key to be safe for memcached.

        Args:
            key: The raw cache key

        Returns:
            A base64-encoded safe key
        """
        return base64.b64encode(key.encode()).decode()

    async def get_track_details(
        self, track_id: str, preview: bool = True
    ) -> dict[str, Any]:
        """
        Get detailed information about a Spotify track.

        Args:
            track_id: Spotify track ID
            preview: Whether to fetch preview URL if missing

        Returns:
            Track details dictionary
        """
        track = await self.make_spotify_request(f"tracks/{track_id}")

        # Add preview URL from Deezer if missing and requested
        if track and not track.get("preview_url") and preview:
            song_name = track.get("name")
            if song_name and track.get("artists"):
                artist_name = track["artists"][0]["name"]
                cache_key = self.sanitize_cache_key(
                    f"deezer_preview_{song_name}_{artist_name}"
                )
                preview_url = cache.get(cache_key)

                if preview_url is None:
                    preview_url = await self.get_deezer_preview(song_name, artist_name)
                    if preview_url:
                        cache.set(
                            cache_key,
                            preview_url,
                            timeout=self.DEEZER_PREVIEW_CACHE_TIMEOUT,
                        )

                if preview_url:
                    track["preview_url"] = preview_url

        return track

    async def get_multiple_track_details(
        self, track_ids: list[str], include_preview: bool = False
    ) -> dict[str, Any]:
        """
        Fetch details for multiple tracks, optionally including preview URLs.

        Args:
            track_ids: A list of Spotify track IDs
            include_preview: Whether to fetch preview URLs from Deezer Music

        Returns:
            A dictionary containing track details
        """
        headers = {"Authorization": f"Bearer {await self.get_access_token()}"}
        ids_param = ",".join(track_ids)
        params = {"ids": ids_param}
        url = f"{self.SPOTIFY_API_BASE_URL}/tracks"
        response = await self.fetch(url, headers=headers, params=params)
        tracks = response.get("tracks", [])

        if include_preview and tracks:
            preview_tasks = []
            for track in tracks:
                if not track.get("preview_url") and track.get("artists"):
                    song_name = track.get("name")
                    artist_name = (
                        track["artists"][0]["name"] if track.get("artists") else ""
                    )
                    if song_name and artist_name:
                        task = asyncio.create_task(
                            self.get_deezer_preview(song_name, artist_name)
                        )
                        preview_tasks.append((track, task))

            for track, task in preview_tasks:
                preview_url = await task
                if preview_url:
                    track["preview_url"] = preview_url

        return {"tracks": tracks}

    async def get_artist(self, artist_id: str) -> dict[str, Any]:
        """
        Get artist details from Spotify.

        Args:
            artist_id: Spotify artist ID

        Returns:
            Artist details dictionary
        """
        return await self.make_spotify_request(f"artists/{artist_id}")

    async def get_multiple_artists(self, artist_ids: list[str]) -> dict[str, Any]:
        """
        Get details for multiple artists at once.

        Args:
            artist_ids: List of Spotify artist IDs

        Returns:
            Dictionary with artists array
        """
        headers = {"Authorization": f"Bearer {await self.get_access_token()}"}
        ids_param = ",".join(artist_ids)
        params = {"ids": ids_param}
        url = f"{self.SPOTIFY_API_BASE_URL}/artists"
        response = await self.fetch(url, headers=headers, params=params)
        return {"artists": response.get("artists", [])}

    async def search_artist_on_spotify(self, artist_name: str) -> dict[str, Any]:
        """
        Search for an artist on Spotify by their name asynchronously.

        Args:
            artist_name: The name of the artist to search for

        Returns:
            A dictionary representing the artist details or empty dict if not found
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
        Search for an album on Spotify by its name.

        Args:
            album_name: The name of the album to search for

        Returns:
            A dictionary representing the album details or empty dict if not found
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
            logger.error(f"Error searching for album {album_name} on Spotify: {e}")
        return {}

    async def search_spotify(self, query: str) -> dict[str, Any]:
        """
        Search Spotify for tracks, artists, albums, and playlists based on a query.

        Args:
            query: The search query string

        Returns:
            The JSON response from Spotify
        """
        params = {"q": query, "type": "track,artist,album,playlist", "limit": 25}
        return await self.make_spotify_request("search", params)

    async def get_recently_played(self, num: int) -> list[dict[str, Any]]:
        """
        Retrieve the user's recently played tracks.

        Args:
            num: Number of recently played tracks to retrieve

        Returns:
            A list of recently played track dictionaries
        """
        endpoint = "me/player/recently-played"
        params = {"limit": num}
        response = await self.make_spotify_request(endpoint, params)
        return response.get("items", [])

    async def get_new_releases(
        self, country: str = "US", limit: int = 50
    ) -> dict[str, Any]:
        """
        Get new releases from Spotify.

        Args:
            country: Country code for market filtering
            limit: Number of releases to fetch

        Returns:
            Dictionary with new release albums
        """
        try:
            params = {"country": country, "limit": limit}
            response = await self.make_spotify_request("browse/new-releases", params)
            return response
        except Exception as e:
            logger.error(f"Error fetching new releases: {e}")
            return {"albums": {"items": []}}

    async def get_artist_albums(
        self, artist_id: str, include_groups: list[str] | None = None
    ) -> list[dict[str, Any]]:
        """
        Get artist albums with optional filtering by release type.

        Args:
            artist_id: Spotify artist ID
            include_groups: List of album types to include

        Returns:
            List of album dictionaries
        """
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
        except Exception as e:
            logger.error(f"Error fetching artist albums: {e}")
            return []

    async def get_artist_top_tracks(
        self,
        num: int,
        artist_id: str,
    ) -> list[dict[str, Any]]:
        """
        Fetch the top tracks of a given artist.

        Args:
            num: Number of top tracks to retrieve
            artist_id: The Spotify artist ID

        Returns:
            A list of top track dictionaries
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

        Args:
            album_id: The Spotify album ID
            include_tracks: Whether to include track details

        Returns:
            A dictionary containing album details
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

        Args:
            artist_name: The name of the artist to find similar artists for
            limit: Number of similar artists to retrieve

        Returns:
            A list of dictionaries representing similar artists with Spotify details
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

            # Create tasks for parallel execution
            tasks = [
                self.search_artist_on_spotify(similar_artist["name"])
                for similar_artist in similar_artists
            ]
            results = await asyncio.gather(*tasks, return_exceptions=True)

            # Process results and keep only valid, unique artists
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

        Args:
            track_id: Spotify track ID to find similar tracks for
            get_preview: Whether to include preview URLs
            limit: Maximum number of similar tracks to return

        Returns:
            List of similar track details
        """
        # Get track details from cache or API
        cache_key = self.sanitize_cache_key(f"track_details_{track_id}")
        track = cache.get(cache_key)

        if track is None:
            track = await self.get_track_details(track_id, preview=False)
            if track:
                cache.set(cache_key, track, timeout=self.CACHE_TIMEOUT)

        if not track or not track.get("artists"):
            return []

        # Get similar artists from cache or API
        artist_name = track["artists"][0]["name"]
        similar_artists_key = self.sanitize_cache_key(
            f"similar_artists_10_{artist_name}"
        )
        similar_artists = cache.get(similar_artists_key)

        if similar_artists is None:
            similar_artists = await self.get_similar_artists(artist_name, limit=10)
            if similar_artists:
                cache.set(
                    similar_artists_key, similar_artists, timeout=self.CACHE_TIMEOUT
                )

        if not similar_artists:
            return []

        # Get top tracks from each similar artist
        similar_tracks = []
        for artist in similar_artists:
            top_tracks_key = self.sanitize_cache_key(
                f"artist_top_tracks_1_{artist['id']}"
            )
            artist_top_tracks = cache.get(top_tracks_key)

            if artist_top_tracks is None:
                artist_top_tracks = await self.get_artist_top_tracks(1, artist["id"])
                if artist_top_tracks:
                    cache.set(
                        top_tracks_key, artist_top_tracks, timeout=604800
                    )  # 1 week

            # Process each top track
            for artist_track in artist_top_tracks:
                details_key = self.sanitize_cache_key(
                    f"track_details_{artist_track['id']}"
                )
                track_details = cache.get(details_key)

                if track_details is None:
                    track_details = await self.get_track_details(
                        artist_track["id"], preview=False
                    )
                    if track_details:
                        cache.set(
                            details_key, track_details, timeout=self.CACHE_TIMEOUT
                        )

                if track_details:
                    # Add preview URL if requested
                    if (
                        get_preview
                        and not track_details.get("preview_url")
                        and track_details.get("artists")
                    ):
                        preview_key = self.sanitize_cache_key(
                            f"preview_url_{artist_track['id']}"
                        )
                        preview_url = cache.get(preview_key)

                        if preview_url is None:
                            preview_url = await self.get_deezer_preview(
                                track_details["name"],
                                track_details["artists"][0]["name"],
                            )
                            if preview_url:
                                cache.set(
                                    preview_key,
                                    preview_url,
                                    timeout=self.DEEZER_PREVIEW_CACHE_TIMEOUT,
                                )

                        if preview_url:
                            track_details["preview_url"] = preview_url

                    similar_tracks.append(track_details)

        # Sort by popularity and limit results
        similar_tracks = sorted(
            similar_tracks, key=lambda x: x.get("popularity", 0), reverse=True
        )[:limit]

        return similar_tracks

    async def get_recently_played_full(self) -> list[dict[str, Any]]:
        """
        Fetch the user's complete recently played tracks history.

        Returns:
            A list of recently played track dictionaries (up to 350 tracks)
        """
        access_token = await self.get_access_token()
        if not access_token:
            return []

        headers = {"Authorization": f"Bearer {access_token}"}
        params: dict[str, int] | None = {"limit": 50}
        url = f"{self.SPOTIFY_API_BASE_URL}/me/player/recently-played"

        recently_played: list[dict[str, Any]] = []

        while url and len(recently_played) < 350:
            try:
                response = await self.fetch(url, headers=headers, params=params)
                items = response.get("items", [])
                recently_played.extend(items)

                # Get next page URL if available
                url = response.get("next")
                if not url:
                    break

                # Clear params since next URL already includes them
                params = None

            except Exception as e:
                logger.error(f"Error fetching recently played tracks: {e}")
                break

        return recently_played

    async def get_artist_top_albums(
        self, artist_id: str, market: str = "US", limit: int = 3
    ) -> list[dict[str, Any]]:
        """
        Retrieve the top albums for a given artist.

        Args:
            artist_id: The Spotify artist ID
            market: The market code
            limit: Number of top albums to retrieve

        Returns:
            A list of top album dictionaries
        """
        endpoint = f"artists/{artist_id}/albums"
        params = {
            "include_groups": "album",
            "market": market,
            "limit": 50,  # Get more to find unique albums
            "album_type": "album",
        }
        response = await self.make_spotify_request(endpoint, params)
        albums = response.get("items", [])

        # De-duplicate albums by name
        unique_albums: dict[str, dict[str, Any]] = {}
        for album in albums:
            album_name = album.get("name", "")
            if album_name:
                unique_albums.setdefault(album_name, album)

        return list(unique_albums.values())[:limit]

    async def get_items_by_genre(
        self, genre_name: str
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        """
        Search for artists and tracks by genre on Spotify.

        Args:
            genre_name: The name of the genre to search for

        Returns:
            A tuple of lists containing artist and track dictionaries
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

        Args:
            song_name: The original song name

        Returns:
            The sanitized song name
        """
        # Get part before any dash
        sanitized_name = song_name.split("-", 1)[0].strip()

        # Remove content in parentheses or brackets
        sanitized_name = re.sub(r"\(.*?\)|\[.*?\]", "", sanitized_name).strip()

        return sanitized_name

    async def get_deezer_preview(self, song_name: str, artist_name: str) -> str | None:
        """
        Fetches the 30-second preview URL from Deezer based on song and artist name.

        Args:
            song_name: The name of the song
            artist_name: The name of the artist

        Returns:
            The preview URL if available, otherwise None
        """
        song_name = self.sanitise_song_name(song_name)
        search_query = f'track:"{song_name}" artist:"{artist_name}"'

        try:
            response = await self.fetch(
                "https://api.deezer.com/search", params={"q": search_query, "limit": 1}
            )
            data = response.get("data", [])
            if data:
                return data[0].get("preview")
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
        """
        Get similar tracks from Last.fm based on artist and track name.

        Args:
            artist_name: Artist name
            track_name: Track name
            limit: Maximum number of similar tracks to return

        Returns:
            List of similar track information
        """
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

            # Format the track data into a consistent structure
            return [
                {
                    "name": track.get("name", ""),
                    "artist": {
                        "name": track.get("artist", {}).get("name", ""),
                        "mbid": track.get("artist", {}).get("mbid", ""),
                    },
                    "url": track.get("url", ""),
                }
                for track in similar_tracks_data
            ]

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

        Args:
            after_timestamp: The timestamp to fetch tracks since

        Returns:
            A list of recently played track dictionaries
        """
        access_token = await self.get_access_token()
        if not access_token:
            logger.error("No access token available.")
            return []

        headers = {"Authorization": f"Bearer {access_token}"}
        params = {"limit": 50, "after": after_timestamp}
        url = f"{self.SPOTIFY_API_BASE_URL}/me/player/recently-played"

        try:
            response = await self.fetch(url, headers=headers, params=params)
            return response.get("items", [])
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

        return []

    @staticmethod
    def get_duration_ms(duration_ms: int) -> str:
        """
        Convert duration from milliseconds to a string format of minutes and seconds.

        Args:
            duration_ms: Duration in milliseconds

        Returns:
            Formatted duration string (e.g. "3:45")
        """
        minutes, seconds = divmod(duration_ms / 1000, 60)
        return f"{int(minutes)}:{int(seconds):02d}"
