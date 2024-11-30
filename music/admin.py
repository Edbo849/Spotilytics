# Register your models here.
from django.contrib import admin

from .models import PlayedTrack, SpotifyUser

# Register your models here.
admin.site.register(SpotifyUser)
admin.site.register(PlayedTrack)
