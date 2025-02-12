import logging
from datetime import timedelta

from django.utils import timezone
from requests import post

from music.models import SpotifyUser

from .credentials import CLIENT_ID, CLIENT_SECRET
from .models import SpotifyToken

BASE_URL = "https://api.spotify.com/v1/"

logger = logging.getLogger(__name__)


def get_user_tokens(spotify_user_id: str) -> SpotifyToken | None:
    return SpotifyToken.objects.filter(
        spotify_user__spotify_user_id=spotify_user_id
    ).first()


def update_or_create_user_tokens(
    spotify_user_id,
    access_token,
    token_type,
    expires_in,
    refresh_token,
    scope,
):
    spotify_user = SpotifyUser.objects.get(spotify_user_id=spotify_user_id)
    expires_in = timezone.now() + timedelta(seconds=expires_in)

    tokens = SpotifyToken.objects.filter(spotify_user=spotify_user).first()

    if tokens:
        tokens.access_token = access_token
        tokens.refresh_token = refresh_token
        tokens.expires_in = expires_in
        tokens.token_type = token_type
        tokens.scope = scope
        tokens.save()
    else:
        tokens = SpotifyToken(
            spotify_user=spotify_user,
            access_token=access_token,
            refresh_token=refresh_token,
            expires_in=expires_in,
            token_type=token_type,
            scope=scope,
        )
        tokens.save()


def is_spotify_authenticated(spotify_user_id: str) -> bool:
    tokens = get_user_tokens(spotify_user_id)
    if tokens:
        if tokens.expires_in <= timezone.now():
            refresh_spotify_token(spotify_user_id)
        return True
    return False


def refresh_spotify_token(spotify_user_id: str) -> None:
    tokens = (
        SpotifyToken.objects.select_related("spotify_user")
        .filter(spotify_user__spotify_user_id=spotify_user_id)
        .first()
    )
    refresh_token = tokens.refresh_token if tokens else None

    if not refresh_token:
        logger.error(f"No refresh token available for user {spotify_user_id}.")
        return

    response = post(
        "https://accounts.spotify.com/api/token",
        data={
            "grant_type": "refresh_token",
            "refresh_token": refresh_token,
            "client_id": CLIENT_ID,
            "client_secret": CLIENT_SECRET,
        },
    )

    if response.status_code != 200:
        logger.error(
            f"Failed to refresh token for user {spotify_user_id}: {response.text}"
        )
        return

    tokens_data = response.json()
    access_token = tokens_data.get("access_token")
    token_type = tokens_data.get("token_type")
    expires_in_seconds = tokens_data.get("expires_in")
    new_refresh_token = tokens_data.get("refresh_token", refresh_token)

    if not all([access_token, token_type, expires_in_seconds]):
        logger.error(f"Missing tokens in refresh response for user {spotify_user_id}")
        return

    expires_in = timezone.now() + timedelta(seconds=expires_in_seconds)

    tokens.access_token = access_token
    tokens.token_type = token_type
    tokens.expires_in = expires_in
    tokens.refresh_token = new_refresh_token
    tokens.scope = tokens.scope
    tokens.save()


def delete_expired_tokens() -> None:
    """
    Delete expired Spotify tokens from the database.
    """
    now = timezone.now()
    expired_tokens = SpotifyToken.objects.filter(expires_in__lte=now)
    count = expired_tokens.count()
    expired_tokens.delete()
    logger.info(f"Deleted {count} expired Spotify tokens.")
