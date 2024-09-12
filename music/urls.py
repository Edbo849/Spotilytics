from django.urls import path
from .views import index

app_name = "music"

urlpatterns = [
    path("", index, name=""),
]
