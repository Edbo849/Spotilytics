from django.db import models


class SpotifyToken(models.Model):
    user = models.CharField(max_length=50, unique=True)
    spotify_user_id = models.CharField(max_length=50, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    refresh_token = models.CharField(max_length=150)
    access_token = models.CharField(max_length=150)
    expires_in = models.DateTimeField()
    token_type = models.CharField(max_length=50)
    scope = models.CharField(max_length=150)

    def __str__(self):
        return f"Token for {self.spotify_user_id or self.user}"
