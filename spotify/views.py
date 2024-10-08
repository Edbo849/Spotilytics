from django.shortcuts import render, redirect
from rest_framework import status
from rest_framework.response import Response
from django.http import HttpRequest, HttpResponse, HttpResponseRedirect

import music
from .util import *
from .credentials import *
from rest_framework.views import APIView
from requests import Request, post, get


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
    error = response.get("error")

    if not request.session.exists(request.session.session_key):
        request.session.create()

    update_or_create_user_tokens(
        request.session.session_key, access_token, token_type, expires_in, refresh_token
    )

    return redirect("music:home")


class IsAuthenticated(APIView):
    def get(self, request, format=None):
        is_authenticated = is_spotify_authenticated(self.request.session.session_key)
        return Response({"status": is_authenticated}, status=status.HTTP_200_OK)
