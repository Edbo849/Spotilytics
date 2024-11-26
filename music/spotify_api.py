import logging
from typing import Any

import requests
from django.utils import timezone

from spotify.models import SpotifyToken
from spotify.util import refresh_spotify_token

logger = logging.getLogger(__name__)

SPOTIFY_API_BASE_URL = "https://api.spotify.com/v1"


def get_user_tokens_by_spotify_id(spotify_user_id: str) -> SpotifyToken | None:
    return SpotifyToken.objects.filter(spotify_user_id=spotify_user_id).first()


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
            refresh_spotify_token(session_id, token.spotify_user_id, token.scope)
            token = SpotifyToken.objects.get(user=session_id)
        return token.access_token
    else:
        raise ValueError("No Spotify token found for the given session.")


def make_spotify_request(
    endpoint: str, session_id: str, params: dict[str, Any] | None = None
) -> dict[str, Any]:
    """
    Helper function to make a request to the Spotify API.
    """
    access_token = get_access_token(session_id)
    headers = {"Authorization": f"Bearer {access_token}"}
    response = requests.get(
        f"{SPOTIFY_API_BASE_URL}/{endpoint}", headers=headers, params=params
    )
    response.raise_for_status()
    return response.json()


def search_spotify(query: str, session_id: str) -> dict[str, Any]:
    """
    Search Spotify for tracks, artists, albums, and playlists based on a query.
    """
    params = {"q": query, "type": "track,artist,album,playlist", "limit": 25}
    return make_spotify_request("search", session_id, params)


def get_top_tracks(num: int, session_id: str, time_range: str) -> list[dict[str, Any]]:
    """
    Retrieve the user's top tracks.
    """
    params = {"limit": num, "time_range": time_range}
    return make_spotify_request("me/top/tracks", session_id, params).get("items", [])


def get_top_artists(num: int, session_id: str, time_range: str) -> list[dict[str, Any]]:
    """
    Retrieve the user's top artists.
    """
    params = {"limit": num, "time_range": time_range}
    return make_spotify_request("me/top/artists", session_id, params).get("items", [])


def get_top_genres(num: int, session_id: str, time_range: str) -> list[dict[str, Any]]:
    """
    Fetch the user's top genres from their top artists.
    """
    params = {"limit": num, "time_range": time_range}
    artists = make_spotify_request("me/top/artists", session_id, params).get(
        "items", []
    )

    genre_counts: dict[str, int] = {}
    for artist in artists:
        for genre in artist.get("genres", []):
            genre_counts[genre] = genre_counts.get(genre, 0) + 1

    sorted_genres = sorted(
        genre_counts.items(), key=lambda item: item[1], reverse=True
    )[:10]
    return [{"genre": genre, "count": count} for genre, count in sorted_genres]


def get_recently_played(num: int, session_id: str) -> list[dict[str, Any]]:
    """
    Retrieve the user's recently played tracks.
    """
    params = {"limit": num}
    return make_spotify_request("me/player/recently-played", session_id, params).get(
        "items", []
    )


def fetch_artist_albums(
    artist_id: str, session_id: str, single: bool
) -> list[dict[str, Any]]:
    """
    Fetch the albums of a given artist.
    """
    params = {"include_groups": "album,single" if single else "album"}
    albums = make_spotify_request(
        f"artists/{artist_id}/albums", session_id, params
    ).get("items", [])
    unique_albums = {album["name"]: album for album in albums}
    return list(unique_albums.values())


def fetch_artist_top_tracks(
    num: int, artist_id: str, session_id: str
) -> list[dict[str, Any]]:
    """
    Fetch the top tracks of a given artist.
    """
    params = {"market": "UK"}
    tracks = make_spotify_request(
        f"artists/{artist_id}/top-tracks", session_id, params
    ).get("tracks", [])
    return tracks[:num]


def get_track_details(track_id: str, session_id: str) -> dict[str, Any]:
    """
    Retrieve the details of a given track.
    """
    return make_spotify_request(f"tracks/{track_id}", session_id)


def get_artist(artist_id: str, session_id: str) -> dict[str, Any]:
    """
    Retrieve the details of a given artist.
    """
    return make_spotify_request(f"artists/{artist_id}", session_id)


def get_album(album_id: str, session_id: str) -> dict[str, Any]:
    """
    Retrieve the details of a given album.
    """
    return make_spotify_request(f"albums/{album_id}", session_id)


def get_similar_artists(artist_id: str, session_id: str) -> list[dict[str, Any]]:
    """
    Retrieve similar artists to a given artist.
    """
    return make_spotify_request(f"artists/{artist_id}/related-artists", session_id).get(
        "artists", []
    )


def get_similar_tracks(track_id: str, session_id: str) -> list[dict[str, Any]]:
    """
    Get similar tracks based on seed track.
    """
    params = {"seed_tracks": track_id, "limit": 10}
    data = make_spotify_request("recommendations", session_id, params)
    track_ids = [track["id"] for track in data["tracks"]]
    params_tracks = {"ids": ",".join(track_ids)}
    full_tracks_data = make_spotify_request("tracks", session_id, params_tracks)
    return full_tracks_data["tracks"]


def get_recently_played_full(session_id: str) -> list[dict[str, Any]]:
    """
    Fetch the user's recently played tracks.
    """
    access_token = get_access_token(session_id)
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
