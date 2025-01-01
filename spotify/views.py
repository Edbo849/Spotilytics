from django.contrib.auth import logout
from django.http import HttpRequest, HttpResponse, HttpResponseRedirect
from django.shortcuts import redirect
from requests import Request, get, post
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from music.models import SpotifyUser
from spotify.models import SpotifyToken

from .credentials import CLIENT_ID, CLIENT_SECRET, REDIRECT_URI
from .util import is_spotify_authenticated, update_or_create_user_tokens


class AuthURL(APIView):
    def get(self, request, format=None):
        scopes = (
            "ugc-image-upload "
            "user-read-playback-state "
            "user-modify-playback-state "
            "user-read-currently-playing "
            "app-remote-control "
            "streaming "
            "playlist-read-private "
            "playlist-read-collaborative "
            "playlist-modify-private "
            "playlist-modify-public "
            "user-follow-modify "
            "user-follow-read "
            "user-library-modify "
            "user-library-read "
            "user-read-email "
            "user-read-private "
            "user-top-read "
            "user-read-recently-played "
            "user-read-playback-position "
        )

        url = (
            Request(
                "GET",
                "https://accounts.spotify.com/authorize",
                params={
                    "scope": scopes,
                    "response_type": "code",
                    "redirect_uri": REDIRECT_URI,
                    "client_id": CLIENT_ID,
                },
            )
            .prepare()
            .url
        )

        return HttpResponseRedirect(url)


def spotify_callback(request: HttpRequest) -> HttpResponse:
    code = request.GET.get("code")
    error = request.GET.get("error")

    if error:
        return HttpResponse(f"Error: {error}")

    if not code:
        return HttpResponse("Error: Missing authorization code")

    try:
        response = post(
            "https://accounts.spotify.com/api/token",
            data={
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": REDIRECT_URI,
                "client_id": CLIENT_ID,
                "client_secret": CLIENT_SECRET,
            },
        )
        response.raise_for_status()
    except Exception as e:
        return HttpResponse(f"Error fetching tokens from Spotify: {e}")

    tokens = response.json()
    access_token = tokens.get("access_token")
    token_type = tokens.get("token_type")
    refresh_token = tokens.get("refresh_token")
    expires_in = tokens.get("expires_in")
    scope = tokens.get("scope")

    if not all([access_token, token_type, refresh_token, expires_in]):
        return HttpResponse("Error: Missing tokens in the response")

    try:
        user_profile = get(
            "https://api.spotify.com/v1/me",
            headers={"Authorization": f"Bearer {access_token}"},
        )
        user_profile.raise_for_status()
    except Exception as e:
        return HttpResponse(f"Error fetching user profile from Spotify: {e}")

    user_profile_data = user_profile.json()
    spotify_user_id = user_profile_data.get("id")
    display_name = user_profile_data.get("display_name")

    if not spotify_user_id:
        return HttpResponse("Error: Missing Spotify user ID in the response")

    request.session["spotify_user_id"] = spotify_user_id
    request.session["display_name"] = display_name

    SpotifyUser.objects.update_or_create(
        spotify_user_id=spotify_user_id,
        defaults={"display_name": display_name},
    )

    update_or_create_user_tokens(
        spotify_user_id,
        access_token,
        token_type,
        expires_in,
        refresh_token,
        scope,
    )

    return redirect("music:home")


def logout_view(request: HttpRequest) -> HttpResponse:
    spotify_user_id = request.session.get("spotify_user_id")

    # Clear session
    logout(request)
    request.session.flush()

    # Delete associated token if it exists
    if spotify_user_id:
        SpotifyToken.objects.filter(
            spotify_user__spotify_user_id=spotify_user_id
        ).delete()

    # Force clear any remaining session data
    request.session.clear()
    request.session.cycle_key()

    return redirect("music:index")


class IsAuthenticated(APIView):
    def get(self, request, format=None):
        is_authenticated = is_spotify_authenticated(self.request.session.session_key)
        return Response({"status": is_authenticated}, status=status.HTTP_200_OK)
