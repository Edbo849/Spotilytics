from django.contrib import admin

from .models import PlayedTrack, SpotifyUser


class PlayedTrackAdmin(admin.ModelAdmin):
    list_display = ("track_name", "artist_name", "album_name", "played_at")
    list_filter = ("played_at",)
    ordering = ("-played_at",)


admin.site.register(SpotifyUser)
admin.site.register(PlayedTrack, PlayedTrackAdmin)
