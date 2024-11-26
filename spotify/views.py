from django.http import HttpRequest, HttpResponse, HttpResponseRedirect
from django.shortcuts import redirect
from requests import Request, get, post
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from music.models import SpotifyUser

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

    response = post(
        "https://accounts.spotify.com/api/token",
        data={
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": REDIRECT_URI,
            "client_id": CLIENT_ID,
            "client_secret": CLIENT_SECRET,
        },
    ).json()

    access_token = response.get("access_token")
    token_type = response.get("token_type")
    refresh_token = response.get("refresh_token")
    expires_in = response.get("expires_in")
    scope = response.get("scope")
    error = response.get("error")

    if not all([access_token, token_type, refresh_token, expires_in]):
        return HttpResponse("Error: Missing tokens in the response")

    if not request.session.exists(request.session.session_key):
        request.session.create()

    user_profile = get(
        "https://api.spotify.com/v1/me",
        headers={"Authorization": f"Bearer {access_token}"},
    ).json()
    spotify_user_id = user_profile.get("id")
    display_name = user_profile.get("display_name")

    update_or_create_user_tokens(
        request.session.session_key,
        access_token,
        token_type,
        expires_in,
        refresh_token,
        spotify_user_id,
        scope,
    )

    request.session["spotify_user_id"] = spotify_user_id
    request.session["display_name"] = display_name

    SpotifyUser.objects.update_or_create(
        spotify_user_id=spotify_user_id,
        defaults={"display_name": display_name},
    )

    return redirect("music:home")


class IsAuthenticated(APIView):
    def get(self, request, format=None):
        is_authenticated = is_spotify_authenticated(self.request.session.session_key)
        return Response({"status": is_authenticated}, status=status.HTTP_200_OK)
