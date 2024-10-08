from django.shortcuts import redirect, render
from .spotify_api import (
    get_top_tracks,
    get_top_artists,
    get_recently_played,
    get_artist,
)
from spotify.util import is_spotify_authenticated
import logging

logger = logging.getLogger(__name__)


def index(request):
    return render(request, "music/index.html")


def home(request):
    if not is_spotify_authenticated(request.session.session_key):
        return redirect("spotify-auth")

    try:
        top_tracks = get_top_tracks(3, session_id=request.session.session_key)
        top_artists = get_top_artists(3, session_id=request.session.session_key)
        recently_played = get_recently_played(3, session_id=request.session.session_key)
    except Exception as e:
        logger.error(f"Error fetching data from Spotify: {e}")
        top_tracks, top_artists, recently_played = [], [], []

    context = {
        "top_tracks": top_tracks,
        "top_artists": top_artists,
        "recently_played": recently_played,
    }
    return render(request, "music/home.html", context)


def artist(request, artist_id):
    if not is_spotify_authenticated(request.session.session_key):
        return redirect("spotify-auth")

    try:
        artist = get_artist(artist_id, session_id=request.session.session_key)
    except Exception as e:
        logger.error(f"Error fetching artist data from Spotify: {e}")
        artist = None

    logger.info(artist)
    logger.info("This is a test")

    context = {
        "artist": artist,
    }
    return render(request, "music/artist.html", context)
