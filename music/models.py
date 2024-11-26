from django.db import models


class SpotifyUser(models.Model):
    spotify_user_id = models.CharField(max_length=50, unique=True)
    display_name = models.CharField(max_length=200, null=True, blank=True)

    def __str__(self):
        return self.display_name or self.spotify_user_id


class PlayedTrack(models.Model):
    user = models.ForeignKey(SpotifyUser, on_delete=models.CASCADE)
    track_id = models.CharField(max_length=50)
    played_at = models.DateTimeField()
    track_name = models.CharField(max_length=200)
    artist_name = models.CharField(max_length=200)
    album_name = models.CharField(max_length=200)

    def __str__(self):
        return f"{self.track_name} by {self.artist_name}"
