from django.urls import path

from . import graphs, views

app_name = "music"

urlpatterns = [
    path("", views.index, name=""),
    path("home/", views.home, name="home"),
    path("artist/<str:artist_id>", views.artist, name="artist"),
    path("search/", views.search, name="search"),
    path("album/<str:album_id>", views.album, name="album"),
    path("track/<str:track_id>", views.track, name="track"),
    path("line-graph/", graphs.line_graph, name="line_graph"),
    path("pie-chart/", graphs.pie_chart, name="pie_chart"),
]
