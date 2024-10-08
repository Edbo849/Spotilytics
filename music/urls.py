from django.urls import path
from .views import artist, home, index

app_name = "music"

urlpatterns = [
    path("", index, name=""),
    path("home/", home, name="home"),
    path("artist/<str:artist_id>", artist, name="artist"),
]
