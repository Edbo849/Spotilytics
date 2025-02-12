from django.db import models
from django.utils import timezone

from spotify.models import SpotifyToken


class SpotifyUser(models.Model):
    spotify_user_id = models.CharField(max_length=255, primary_key=True)
    display_name = models.CharField(max_length=255, blank=True, null=True)

    @property
    def is_token_expired(self) -> bool:
        """
        Check if the user's access token has expired.
        """
        try:
            token = self.spotifytoken
            return token.expires_in <= timezone.now()
        except SpotifyToken.DoesNotExist:
            return True

    def __str__(self):
        return f"{self.display_name}"


class PlayedTrack(models.Model):
    stream_id = models.AutoField(primary_key=True)
    user = models.ForeignKey(SpotifyUser, on_delete=models.CASCADE)
    track_id = models.CharField(max_length=50, db_index=True)
    played_at = models.DateTimeField(db_index=True)
    track_name = models.CharField(max_length=200)
    artist_name = models.CharField(max_length=200)
    album_name = models.CharField(max_length=200)
    duration_ms = models.BigIntegerField(default=0)
    genres = models.JSONField(default=list)
    popularity = models.IntegerField(default=0)
    artist_id = models.CharField(max_length=50, db_index=True)
    album_id = models.CharField(max_length=50, db_index=True)

    class Meta:
        unique_together = ("user", "stream_id", "played_at")
        indexes = [
            models.Index(fields=["user", "played_at"]),
            models.Index(fields=["user", "artist_name"]),
            models.Index(fields=["user", "track_id"]),
            models.Index(fields=["user", "album_id"]),
            models.Index(fields=["user", "duration_ms"]),
            models.Index(fields=["user", "genres"]),
        ]

    def __str__(self):
        return f"{self.track_name} by {self.artist_name}"
