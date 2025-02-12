# music/services/openai_service.py
import logging
from typing import Any

import openai
from django.conf import settings
from django.db.models import Count

from music.core.models import PlayedTrack

logger = logging.getLogger(__name__)


class OpenAIService:
    def __init__(self):
        self.api_key = settings.OPENAI_API_KEY
        openai.api_key = self.api_key

    def get_listening_data(self, spotify_user_id: str) -> str:
        """Get user's listening history data formatted for OpenAI prompt"""
        top_artists = (
            PlayedTrack.objects.filter(user_id=spotify_user_id)
            .values("artist_name")
            .annotate(count=Count("artist_name"))
            .order_by("-count")[:15]
        )
        top_tracks = (
            PlayedTrack.objects.filter(user_id=spotify_user_id)
            .values("track_name")
            .annotate(count=Count("track_name"))
            .order_by("-count")[:15]
        )
        top_albums = (
            PlayedTrack.objects.filter(user_id=spotify_user_id)
            .values("album_name")
            .annotate(count=Count("album_name"))
            .order_by("-count")[:15]
        )

        artists = ", ".join([artist["artist_name"] for artist in top_artists])
        tracks = ", ".join([track["track_name"] for track in top_tracks])
        albums = ", ".join([album["album_name"] for album in top_albums])

        return f"Top artists: {artists}. Top tracks: {tracks}. Top albums: {albums}."

    def create_prompt(self, user_message: str, listening_data: str) -> str:
        """Create prompt for OpenAI API"""
        return (
            f"User's listening data: {listening_data}\n"
            f"User's question: {user_message}\n"
            f"AI response:"
        )

    def get_ai_response(self, prompt: str) -> str:
        """Get response from OpenAI API"""
        try:
            response = openai.ChatCompletion.create(
                model="gpt-3.5-turbo",
                messages=[
                    {"role": "system", "content": "You are a helpful assistant."},
                    {"role": "user", "content": prompt},
                ],
                max_tokens=150,
                temperature=0.7,
            )
            return response.choices[0].message["content"].strip()
        except Exception as e:
            logger.error(f"OpenAI API error: {e}")
            return "I'm sorry, I couldn't process your request at the moment."
