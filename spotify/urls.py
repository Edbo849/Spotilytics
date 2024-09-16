from django.urls import path
from .views import AuthURL, spotify_callback, IsAuthenticated

urlpatterns = [
    path("get-auth-url/", AuthURL.as_view(), name="spotify-auth"),
    path("redirect/", spotify_callback, name="spotify-callback"),
    path("is-authenticated/", IsAuthenticated.as_view(), name="is-authenticated"),
]
