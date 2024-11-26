from datetime import timedelta
from typing import Any

from django.utils import timezone
from requests import get, post, put

from .credentials import CLIENT_ID, CLIENT_SECRET
from .models import SpotifyToken

BASE_URL = "https://api.spotify.com/v1/"


def get_user_tokens(session_id: str) -> SpotifyToken | None:
    return SpotifyToken.objects.filter(user=session_id).first()


def update_or_create_user_tokens(
    session_id,
    access_token,
    token_type,
    expires_in,
    refresh_token,
    spotify_user_id,
    scope,
):
    tokens = SpotifyToken.objects.filter(user=session_id).first()
    expires_in = timezone.now() + timedelta(seconds=expires_in)

    if tokens:
        tokens.access_token = access_token
        tokens.refresh_token = refresh_token
        tokens.expires_in = expires_in
        tokens.token_type = token_type
        tokens.spotify_user_id = spotify_user_id
        tokens.scope = scope
        tokens.save(
            update_fields=[
                "access_token",
                "refresh_token",
                "expires_in",
                "token_type",
                "spotify_user_id",
                "scope",
            ]
        )
    else:
        tokens = SpotifyToken(
            user=session_id,
            access_token=access_token,
            refresh_token=refresh_token,
            expires_in=expires_in,
            token_type=token_type,
            spotify_user_id=spotify_user_id,
            scope=scope,
        )
        tokens.save()


def is_spotify_authenticated(session_id: str) -> bool:
    tokens = get_user_tokens(session_id)
    if tokens:
        if tokens.expires_in <= timezone.now():
            refresh_spotify_token(session_id, tokens.spotify_user_id, tokens.scope)
        return True
    return False


def refresh_spotify_token(session_id: str, spotify_user_id: str, scope: str) -> None:
    tokens = get_user_tokens(session_id)
    refresh_token = tokens.refresh_token if tokens else None

    if not refresh_token:
        return

    response = post(
        "https://accounts.spotify.com/api/token",
        data={
            "grant_type": "refresh_token",
            "refresh_token": refresh_token,
            "client_id": CLIENT_ID,
            "client_secret": CLIENT_SECRET,
        },
    ).json()

    access_token = response.get("access_token")
    token_type = response.get("token_type")
    expires_in = response.get("expires_in")

    if access_token and token_type and expires_in:
        update_or_create_user_tokens(
            session_id,
            access_token,
            token_type,
            expires_in,
            refresh_token,
            spotify_user_id,
            scope,
        )


def execute_spotify_api_request(
    session_id: str, endpoint: str, post_: bool = False, put_: bool = False
) -> dict[str, Any] | str:
    tokens = get_user_tokens(session_id)
    if not tokens or not tokens.access_token:
        return {"Error": "Authentication Required"}

    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {tokens.access_token}",
    }

    if post_:
        response = post(BASE_URL + endpoint, headers=headers)
    elif put_:
        response = put(BASE_URL + endpoint, headers=headers)
    else:
        response = get(BASE_URL + endpoint, headers=headers)

    try:
        return response.json()
    except Exception:
        return {"Error": "Issue with request"}
