from django.db import models


class SpotifyToken(models.Model):
    spotify_user = models.OneToOneField(
        "music.SpotifyUser",
        on_delete=models.CASCADE,
        related_name="spotifytoken",
        null=True,
        blank=True,
    )
    created_at = models.DateTimeField(auto_now_add=True)
    refresh_token = models.CharField(max_length=500)
    access_token = models.CharField(max_length=500)
    expires_in = models.DateTimeField()
    token_type = models.CharField(max_length=50)
    scope = models.CharField(max_length=500)

    def __str__(self):
        return f"Token for {self.spotify_user.display_name or self.spotify_user.spotify_user_id}"
