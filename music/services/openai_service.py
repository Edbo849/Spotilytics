import logging

import openai
from asgiref.sync import sync_to_async
from django.conf import settings
from django.db import close_old_connections
from django.db.models import Count

from music.models import PlayedTrack

logger = logging.getLogger(__name__)


class OpenAIService:
    """Service for interacting with OpenAI API based on user's listening data."""

    def __init__(self):
        self.api_key = settings.OPENAI_API_KEY

    @sync_to_async(thread_sensitive=False)
    def get_listening_data(self, spotify_user_id: str) -> str:
        """
        Retrieve user's top artists, tracks, and albums as a formatted string.

        Args:
            spotify_user_id: The Spotify user ID to retrieve data for

        Returns:
            Formatted string with top listening data
        """
        close_old_connections()

        # Use a common query builder function to reduce code duplication
        top_artists = self._get_top_items(spotify_user_id, "artist_name")
        top_tracks = self._get_top_items(spotify_user_id, "track_name")
        top_albums = self._get_top_items(spotify_user_id, "album_name")

        # Convert query results to comma-separated strings
        artists = ", ".join(item["artist_name"] for item in top_artists)
        tracks = ", ".join(item["track_name"] for item in top_tracks)
        albums = ", ".join(item["album_name"] for item in top_albums)

        return f"Top artists: {artists}. Top tracks: {tracks}. Top albums: {albums}."

    def _get_top_items(
        self, user_id: str, field_name: str, limit: int = 15
    ) -> list[dict]:
        """
        Helper method to retrieve top items for a given field.

        Args:
            user_id: Spotify user ID
            field_name: Database field to query (artist_name, track_name, etc.)
            limit: Maximum number of items to return

        Returns:
            List of dictionaries with the field_name and count
        """
        return (
            PlayedTrack.objects.filter(user_id=user_id)
            .values(field_name)
            .annotate(count=Count(field_name))
            .order_by("-count")[:limit]
        )

    @sync_to_async(thread_sensitive=False)
    def create_prompt(self, user_message: str, listening_data: str) -> str:
        """
        Create a formatted prompt for OpenAI API combining user data and question.

        Args:
            user_message: The user's question or message
            listening_data: The user's listening history data

        Returns:
            Formatted prompt string
        """
        return (
            f"User's listening data: {listening_data}\n"
            f"User's question: {user_message}\n"
            f"AI response:"
        )

    @sync_to_async(thread_sensitive=False)
    def get_ai_response(self, prompt: str) -> str:
        """
        Send prompt to OpenAI API and get the response.

        Args:
            prompt: The formatted prompt string

        Returns:
            AI response text or error message
        """
        try:
            openai.api_key = self.api_key
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
