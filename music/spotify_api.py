import requests
from spotify.models import SpotifyToken
from spotify.util import get_user_tokens

SPOTIFY_API_BASE_URL = "https://api.spotify.com/v1/me"


def get_access_token(session_id: str) -> str:
    token = get_user_tokens(session_id)
    return token.access_token if token else None


def get_top_tracks(num: int, session_id: str) -> list:
    access_token = get_access_token(session_id)
    if not access_token:
        return []

    response = requests.get(
        f"{SPOTIFY_API_BASE_URL}/top/tracks",
        headers={"Authorization": "Bearer " + access_token},
    )
    if response.status_code == 200:
        return response.json()["items"][:num]
    return []


def get_top_artists(num: int, session_id: str) -> list:
    access_token = get_access_token(session_id)
    if not access_token:
        return []

    response = requests.get(
        f"{SPOTIFY_API_BASE_URL}/top/artists",
        headers={"Authorization": "Bearer " + access_token},
    )
    if response.status_code == 200:
        return response.json()["items"][:num]
    return []


def get_recently_played(num: int, session_id: str) -> list:
    access_token = get_access_token(session_id)
    if not access_token:
        return []

    response = requests.get(
        f"{SPOTIFY_API_BASE_URL}/player/recently-played",
        headers={"Authorization": "Bearer " + access_token},
    )
    if response.status_code == 200:
        return response.json()["items"][:num]
    return []


def get_artist(artist_id: str, session_id: str) -> dict:
    token = get_access_token(session_id)
    response = requests.get(
        f"{SPOTIFY_API_BASE_URL}/artists/{artist_id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    return response.json()
