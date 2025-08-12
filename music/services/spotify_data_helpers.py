"""Helper functions for fetching Spotify data through the API."""

import asyncio
import logging
from typing import Any

from django.core.cache import cache

logger = logging.getLogger(__name__)


async def get_album_details(client, album_id: str) -> dict[str, Any]:
    """
    Get album details with caching.

    Args:
        client: Spotify API client instance
        album_id: Spotify album ID

    Returns:
        Dictionary containing album details

    Raises:
        ValueError: If album is not found
    """
    cache_key = client.sanitize_cache_key(f"album_details_{album_id}")
    album = cache.get(cache_key)

    if album is None:
        album = await client.get_album(album_id)
        if album:
            cache.set(cache_key, album, timeout=client.CACHE_TIMEOUT)
        else:
            raise ValueError("Album not found")
    return album


async def get_tracks_batch(
    client, track_ids: list[str], batch_size: int = 50
) -> dict[str, Any]:
    """
    Get track details in batches.

    Args:
        client: Spotify API client instance
        track_ids: List of Spotify track IDs
        batch_size: Number of tracks to fetch in each batch

    Returns:
        Dictionary mapping track IDs to track details
    """
    track_details_dict = {}

    async def fetch_track_batch(batch_ids: list[str]) -> None:
        """Fetch and store a batch of track details."""
        response = await client.get_multiple_track_details(batch_ids)
        tracks = response.get("tracks", [])
        for track in tracks:
            if track and track.get("id"):
                track_details_dict[track["id"]] = track

    # Create tasks for each batch
    tasks = [
        asyncio.create_task(fetch_track_batch(track_ids[i : i + batch_size]))
        for i in range(0, len(track_ids), batch_size)
    ]

    await asyncio.gather(*tasks)
    return track_details_dict


async def get_artist_all_songs_data(client, artist_id: str) -> dict[str, Any]:
    """
    Get all songs data for an artist.

    Args:
        client: Spotify API client instance
        artist_id: Spotify artist ID

    Returns:
        Dictionary containing artist info and list of all tracks
    """
    try:
        # Get artist details
        artist = await client.get_artist(artist_id)

        # Get all albums with caching
        cache_key = client.sanitize_cache_key(f"artist_albums_{artist_id}")
        albums = cache.get(cache_key)
        if albums is None:
            albums = await client.get_artist_albums(
                artist_id, include_groups=["album", "single", "compilation"]
            )
            if albums:
                cache.set(cache_key, albums, timeout=client.CACHE_TIMEOUT)

        # Get all track IDs from albums
        track_ids_set: set[str] = set()
        album_data_cache = {}  # Local cache to avoid duplicate API calls

        for album in albums:
            album_id = album["id"]
            album_data = await get_album_details(client, album_id)
            album_data_cache[album_id] = album_data

            album_tracks = album_data.get("tracks", {}).get("items", [])
            # Add all valid track IDs to the set
            track_ids_set.update(
                track["id"] for track in album_tracks if track.get("id")
            )

        # Fetch track details in batches
        track_details_dict = await get_tracks_batch(client, list(track_ids_set))

        # Compile tracks list
        tracks = []
        for album in albums:
            album_id = album["id"]
            album_data = album_data_cache.get(album_id) or await get_album_details(
                client, album_id
            )
            album_tracks = album_data.get("tracks", {}).get("items", [])

            for track in album_tracks:
                track_id = track.get("id")
                if track_id and track_id in track_details_dict:
                    track_detail = track_details_dict[track_id]

                    # Get duration in appropriate format
                    duration = (
                        client.get_duration_ms(track_detail.get("duration_ms"))
                        if hasattr(client, "get_duration_ms")
                        else track_detail.get("duration_ms")
                    )

                    # Create track info dictionary
                    track_info = {
                        "id": track_id,
                        "name": track_detail.get("name"),
                        "album": {
                            "id": album_id,
                            "name": album["name"],
                            "images": album["images"],
                            "release_date": album.get("release_date"),
                        },
                        "duration": duration,
                        "popularity": track_detail.get("popularity", "N/A"),
                    }
                    tracks.append(track_info)

        return {"artist": artist, "tracks": tracks}
    except Exception as e:
        logger.error(f"Error fetching artist data from Spotify: {e}")
        return {"artist": None, "tracks": []}
