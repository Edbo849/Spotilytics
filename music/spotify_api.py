# music/spotify_api.py
from django.utils import timezone
import requests
from spotify.models import SpotifyToken
from spotify.util import refresh_spotify_token
import logging

logger = logging.getLogger(__name__)

SPOTIFY_API_BASE_URL = "https://api.spotify.com/v1"


def search_spotify(query: str, session_id: str) -> dict:
    access_token = get_access_token(session_id)
    if not access_token:
        raise ValueError("No access token available")

    response = requests.get(
        f"{SPOTIFY_API_BASE_URL}/search",
        headers={"Authorization": f"Bearer {access_token}"},
        params={"q": query, "type": "track,artist,album", "limit": 50},
    )
    if response.status_code != 200:
        response.raise_for_status()
    return response.json()


def get_top_tracks(num: int, session_id: str) -> list:
    access_token = get_access_token(session_id)
    if not access_token:
        raise ValueError("No access token available")

    response = requests.get(
        f"{SPOTIFY_API_BASE_URL}/me/top/tracks",
        headers={"Authorization": f"Bearer {access_token}"},
        params={"limit": num},
    )
    if response.status_code != 200:
        response.raise_for_status()
    return response.json()["items"]


def get_top_artists(num: int, session_id: str) -> list:
    access_token = get_access_token(session_id)
    if not access_token:
        raise ValueError("No access token available")

    response = requests.get(
        f"{SPOTIFY_API_BASE_URL}/me/top/artists",
        headers={"Authorization": f"Bearer {access_token}"},
        params={"limit": num},
    )
    if response.status_code != 200:
        response.raise_for_status()
    return response.json()["items"]


def get_recently_played(num: int, session_id: str) -> list:
    access_token = get_access_token(session_id)
    if not access_token:
        raise ValueError("No access token available")

    response = requests.get(
        f"{SPOTIFY_API_BASE_URL}/me/player/recently-played",
        headers={"Authorization": f"Bearer {access_token}"},
        params={"limit": num},
    )
    if response.status_code != 200:
        response.raise_for_status()
    return response.json()["items"]


def get_access_token(session_id: str) -> str:
    tokens = SpotifyToken.objects.filter(user=session_id)
    if tokens.exists():
        token = tokens[0]
        if token.expires_in <= timezone.now():
            refresh_spotify_token(session_id)
            token = SpotifyToken.objects.get(user=session_id)
        return token.access_token
    return None


def fetch_artist_details(artist_id: str, access_token: str) -> dict:
    response = requests.get(
        f"{SPOTIFY_API_BASE_URL}/artists/{artist_id}",
        headers={"Authorization": f"Bearer {access_token}"},
    )
    if response.status_code != 200:
        response.raise_for_status()
    return response.json()


def fetch_artist_albums(artist_id: str, access_token: str) -> list:
    response = requests.get(
        f"{SPOTIFY_API_BASE_URL}/artists/{artist_id}/albums",
        headers={"Authorization": f"Bearer {access_token}"},
        params={"include_groups": "album", "limit": 25},
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


def get_artist(artist_id: str, session_id: str) -> dict:
    access_token = get_access_token(session_id)
    if not access_token:
        raise ValueError("No access token available")

    artist_data = fetch_artist_details(artist_id, access_token)
    artist_data["albums"] = fetch_artist_albums(artist_id, access_token)
    artist_data["top_tracks"] = fetch_artist_top_tracks(artist_id, access_token)[:5]

    return artist_data
