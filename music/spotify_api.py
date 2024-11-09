# music/spotify_api.py
import logging

import requests
from django.utils import timezone

from spotify.models import SpotifyToken
from spotify.util import refresh_spotify_token

logger = logging.getLogger(__name__)

SPOTIFY_API_BASE_URL = "https://api.spotify.com/v1"


def get_access_token(session_id: str) -> str:
    """Retrieve a valid access token for the given session."""
    tokens = SpotifyToken.objects.filter(user=session_id)
    if tokens.exists():
        token = tokens.first()
        if token.expires_in <= timezone.now():
            refresh_spotify_token(session_id)
            token = SpotifyToken.objects.get(user=session_id)
        return token.access_token
    else:
        raise ValueError("No Spotify token found for the given session.")


def search_spotify(query: str, session_id: str) -> dict:
    access_token = get_access_token(session_id)
    if not access_token:
        raise ValueError("No access token available")

    params: dict[str, str | int] = {
        "q": query,
        "type": "track,artist,album,playlist",
        "limit": 25,
    }

    response = requests.get(
        f"{SPOTIFY_API_BASE_URL}/search",
        headers={"Authorization": f"Bearer {access_token}"},
        params=params,
    )
    if response.status_code != 200:
        response.raise_for_status()
    return response.json()


def get_top_tracks(num: int, session_id: str) -> list[dict]:
    access_token = get_access_token(session_id)
    params: dict[str, str | int] = {"limit": num, "time_range": "medium_term"}

    response = requests.get(
        f"{SPOTIFY_API_BASE_URL}/me/top/tracks",
        headers={"Authorization": f"Bearer {access_token}"},
        params=params,
    )
    response.raise_for_status()
    return response.json().get("items", [])


def get_top_artists(num: int, session_id: str) -> list[dict]:
    access_token = get_access_token(session_id)
    params: dict[str, str | int] = {"limit": num, "time_range": "medium_term"}

    response = requests.get(
        f"{SPOTIFY_API_BASE_URL}/me/top/artists",
        headers={"Authorization": f"Bearer {access_token}"},
        params=params,
    )
    response.raise_for_status()
    return response.json().get("items", [])


def get_recently_played(num: int, session_id: str) -> list[dict]:
    access_token = get_access_token(session_id)
    params: dict[str, str | int] = {"limit": num}

    response = requests.get(
        f"{SPOTIFY_API_BASE_URL}/me/player/recently-played",
        headers={"Authorization": f"Bearer {access_token}"},
        params=params,
    )
    response.raise_for_status()
    return response.json().get("items", [])


def fetch_artist_details(artist_id: str, access_token: str) -> dict:
    response = requests.get(
        f"{SPOTIFY_API_BASE_URL}/artists/{artist_id}",
        headers={"Authorization": f"Bearer {access_token}"},
    )
    if response.status_code != 200:
        response.raise_for_status()
    return response.json()


def fetch_artist_albums(artist_id: str, access_token: str) -> list:
    params: dict[str, str | int] = {"include_groups": "album", "limit": 25}

    response = requests.get(
        f"{SPOTIFY_API_BASE_URL}/artists/{artist_id}/albums",
        headers={"Authorization": f"Bearer {access_token}"},
        params=params,
    )
    if response.status_code != 200:
        response.raise_for_status()
    return response.json()["items"]


def fetch_artist_top_tracks(artist_id: str, access_token: str) -> list:
    response = requests.get(
        f"{SPOTIFY_API_BASE_URL}/artists/{artist_id}/top-tracks",
        headers={"Authorization": f"Bearer {access_token}"},
        params={"market": "UK"},
    )
    if response.status_code != 200:
        response.raise_for_status()
    return response.json()["tracks"]


def fetch_album_details(album_id: str, access_token: str) -> dict:
    response = requests.get(
        f"{SPOTIFY_API_BASE_URL}/albums/{album_id}",
        headers={"Authorization": f"Bearer {access_token}"},
    )
    if response.status_code != 200:
        response.raise_for_status()
    return response.json()


def fetch_album_songs(album_id: str, session_id: str) -> list:
    access_token = get_access_token(session_id)
    if not access_token:
        raise ValueError("No access token available")

    response = requests.get(
        f"{SPOTIFY_API_BASE_URL}/albums/{album_id}/tracks",
        headers={"Authorization": f"Bearer {access_token}"},
    )
    if response.status_code != 200:
        response.raise_for_status()
    return response.json()["items"]


def get_track_details(track_id: str, session_id: str) -> dict:
    access_token = get_access_token(session_id)
    if not access_token:
        raise ValueError("No access token available")

    response = requests.get(
        f"{SPOTIFY_API_BASE_URL}/tracks/{track_id}",
        headers={"Authorization": f"Bearer {access_token}"},
    )
    if response.status_code != 200:
        response.raise_for_status()
    return response.json()


def get_artist(artist_id: str, session_id: str) -> dict:
    access_token = get_access_token(session_id)

    response = requests.get(
        f"{SPOTIFY_API_BASE_URL}/artists/{artist_id}",
        headers={"Authorization": f"Bearer {access_token}"},
    )
    response.raise_for_status()
    return response.json()


def get_album(album_id: str, session_id: str) -> dict:
    access_token = get_access_token(session_id)
    if not access_token:
        raise ValueError("No access token available")

    response = requests.get(
        f"{SPOTIFY_API_BASE_URL}/albums/{album_id}",
        headers={"Authorization": f"Bearer {access_token}"},
    )
    if response.status_code != 200:
        response.raise_for_status()
    return response.json()


def get_similar_artists(artist_id: str, session_id: str) -> list[dict]:
    access_token = get_access_token(session_id)

    response = requests.get(
        f"{SPOTIFY_API_BASE_URL}/artists/{artist_id}/related-artists",
        headers={"Authorization": f"Bearer {access_token}"},
    )
    response.raise_for_status()
    return response.json().get("artists", [])
