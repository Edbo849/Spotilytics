from django.contrib import admin

from .models import PlayedTrack, SpotifyUser

admin.site.register(SpotifyUser)
admin.site.register(PlayedTrack)
