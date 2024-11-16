import logging

import requests
from django.utils import timezone

from spotify.models import SpotifyToken
from spotify.util import refresh_spotify_token

logger = logging.getLogger(__name__)

SPOTIFY_API_BASE_URL = "https://api.spotify.com/v1"


def get_duration_ms(duration_ms: int) -> str:
    """
    Convert duration from milliseconds to a string format of minutes and seconds.
    """
    minutes, seconds = divmod(duration_ms / 1000, 60)
    return f"{int(minutes)}:{int(seconds):02d}"


def get_access_token(session_id: str) -> str:
    """
    Retrieve a valid access token for the given session.
    """
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
    """
    Search Spotify for tracks, artists, albums, and playlists based on a query.
    """
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
    response.raise_for_status()
    return response.json()


def get_top_tracks(num: int, session_id: str, time_range: str) -> list[dict]:
    """
    Retrieve the user's top tracks.
    """
    access_token = get_access_token(session_id)
    params: dict[str, str | int] = {"limit": num, "time_range": time_range}

    response = requests.get(
        f"{SPOTIFY_API_BASE_URL}/me/top/tracks",
        headers={"Authorization": f"Bearer {access_token}"},
        params=params,
    )
    response.raise_for_status()
    return response.json().get("items", [])


def get_top_artists(num: int, session_id: str, time_range: str) -> list[dict]:
    """
    Retrieve the user's top artists.
    """
    access_token = get_access_token(session_id)
    params: dict[str, str | int] = {"limit": num, "time_range": time_range}

    response = requests.get(
        f"{SPOTIFY_API_BASE_URL}/me/top/artists",
        headers={"Authorization": f"Bearer {access_token}"},
        params=params,
    )
    response.raise_for_status()
    return response.json().get("items", [])


def get_top_genres(num: int, session_id: str, time_range: str) -> list[dict]:
    """
    Fetch the user's top genres from their top artists.
    """
    access_token = get_access_token(session_id)
    params: dict[str, str | int] = {"limit": num, "time_range": time_range}

    response = requests.get(
        f"{SPOTIFY_API_BASE_URL}/me/top/artists",
        headers={"Authorization": f"Bearer {access_token}"},
        params=params,
    )
    data = response.json()
    artists = data.get("items", [])

    genre_counts: dict[str, int] = {}
    for artist in artists:
        for genre in artist.get("genres", []):
            genre_counts[genre] = genre_counts.get(genre, 0) + 1

    sorted_genres = sorted(
        genre_counts.items(), key=lambda item: item[1], reverse=True
    )[:10]
    genres = [{"genre": genre, "count": count} for genre, count in sorted_genres]
    return genres


def get_recently_played(num: int, session_id: str) -> list[dict]:
    """
    Retrieve the user's recently played tracks.
    """
    access_token = get_access_token(session_id)
    params: dict[str, str | int] = {"limit": num}

    response = requests.get(
        f"{SPOTIFY_API_BASE_URL}/me/player/recently-played",
        headers={"Authorization": f"Bearer {access_token}"},
        params=params,
    )
    response.raise_for_status()
    return response.json().get("items", [])


def fetch_artist_albums(artist_id: str, access_token: str) -> list:
    """
    Fetch the albums of a given artist.
    """
    params: dict[str, str | int] = {"include_groups": "album", "limit": 25}

    response = requests.get(
        f"{SPOTIFY_API_BASE_URL}/artists/{artist_id}/albums",
        headers={"Authorization": f"Bearer {access_token}"},
        params=params,
    )
    response.raise_for_status()

    return response.json()["items"]


def fetch_artist_top_tracks(num: int, artist_id: str, access_token: str) -> list:
    """
    Fetch the top tracks of a given artist.
    """
    params: dict[str, str | int] = {"market": "UK"}

    response = requests.get(
        f"{SPOTIFY_API_BASE_URL}/artists/{artist_id}/top-tracks",
        headers={"Authorization": f"Bearer {access_token}"},
        params=params,
    )
    response.raise_for_status()
    tracks = response.json()["tracks"]
    return tracks[:num]


def get_track_details(track_id: str, session_id: str) -> dict:
    """
    Retrieve the details of a given track.
    """
    access_token = get_access_token(session_id)
    if not access_token:
        raise ValueError("No access token available")

    response = requests.get(
        f"{SPOTIFY_API_BASE_URL}/tracks/{track_id}",
        headers={"Authorization": f"Bearer {access_token}"},
    )
    response.raise_for_status()
    return response.json()


def get_artist(artist_id: str, session_id: str) -> dict:
    """
    Retrieve the details of a given artist.
    """
    access_token = get_access_token(session_id)

    response = requests.get(
        f"{SPOTIFY_API_BASE_URL}/artists/{artist_id}",
        headers={"Authorization": f"Bearer {access_token}"},
    )
    response.raise_for_status()
    return response.json()


def get_album(album_id: str, session_id: str) -> dict:
    """
    Retrieve the details of a given album.
    """
    access_token = get_access_token(session_id)
    if not access_token:
        raise ValueError("No access token available")

    response = requests.get(
        f"{SPOTIFY_API_BASE_URL}/albums/{album_id}",
        headers={"Authorization": f"Bearer {access_token}"},
    )
    response.raise_for_status()
    return response.json()


def get_similar_artists(artist_id: str, session_id: str) -> list[dict]:
    """
    Retrieve similar artists to a given artist.
    """
    access_token = get_access_token(session_id)

    response = requests.get(
        f"{SPOTIFY_API_BASE_URL}/artists/{artist_id}/related-artists",
        headers={"Authorization": f"Bearer {access_token}"},
    )
    response.raise_for_status()
    return response.json().get("artists", [])


def get_similar_tracks(track_id: str, session_id: str) -> list:
    """
    Retrieve similar tracks to a given track.
    """
    access_token = get_access_token(session_id)
    headers = {"Authorization": f"Bearer {access_token}"}
    params: dict[str, str | int] = {"seed_tracks": track_id, "limit": 20}
    response = requests.get(
        "https://api.spotify.com/v1/recommendations", headers=headers, params=params
    )
    response.raise_for_status()
    return response.json().get("tracks", [])
