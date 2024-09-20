from django.urls import path
from .views import index, home

app_name = "music"

urlpatterns = [
    path("", index, name=""),
    path("home/", home, name="home"),
]
