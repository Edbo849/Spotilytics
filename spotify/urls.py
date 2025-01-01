from django.urls import path

from .views import AuthURL, IsAuthenticated, logout_view, spotify_callback

urlpatterns = [
    path("get-auth-url/", AuthURL.as_view(), name="spotify-auth"),
    path("redirect/", spotify_callback, name="spotify-callback"),
    path("is-authenticated/", IsAuthenticated.as_view(), name="is-authenticated"),
    path("logout/", logout_view, name="spotify-logout"),
]
