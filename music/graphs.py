# music/graphs.py

import matplotlib
import numpy as np

matplotlib.use("Agg")

import io
from datetime import datetime, timedelta

import matplotlib.pyplot as plt
import pytz
from django.http import HttpResponse

from .spotify_api import get_recently_played_full, get_top_genres


def line_graph(request):
    session_id = request.session.session_key
    recently_played = get_recently_played_full(session_id)

    now = datetime.now(pytz.utc)
    one_week_ago = now - timedelta(days=6)
    dates = []

    for item in recently_played:
        played_at = item["played_at"]
        played_datetime = parse_datetime(played_at)
        if played_datetime >= one_week_ago:
            dates.append(played_datetime.date())

    date_counts = {}
    for date in dates:
        date_counts[date] = date_counts.get(date, 0) + 1

    date_list = [one_week_ago.date() + timedelta(days=x) for x in range(7)]
    counts = [date_counts.get(date, 0) for date in date_list]
    date_labels = [date.strftime("%b %d") for date in date_list]

    fig, ax = plt.subplots(figsize=(8, 3))
    fig.patch.set_facecolor("#333333")
    ax.set_facecolor("#333333")

    ax.plot(date_labels, counts, marker="o", color="#1DB954")

    ax.set_xlabel("Date", color="white", fontsize=12)
    ax.set_ylabel("Number of Songs", color="white", fontsize=12)

    ax.tick_params(axis="x", colors="white", rotation=45)
    ax.tick_params(axis="y", colors="white")

    ax.grid(True, color="gray", linestyle="--", linewidth=0.5)

    for spine in ax.spines.values():
        spine.set_edgecolor("white")

    plt.tight_layout()

    buffer = io.BytesIO()
    plt.savefig(buffer, format="png", dpi=150)
    plt.close()
    buffer.seek(0)

    return HttpResponse(buffer.getvalue(), content_type="image/png")


def pie_chart(request):
    """Generate a pie chart of user's top genres."""
    session_id = request.session.session_key
    time_range = request.GET.get("time_range", "medium_term")

    top_genres = get_top_genres(50, session_id, time_range)

    genres = [item["genre"] for item in top_genres]
    counts = [item["count"] for item in top_genres]

    fig, ax = plt.subplots(figsize=(8, 8))
    fig.patch.set_facecolor("#333333")
    ax.set_facecolor("#333333")

    wedges, texts, autotexts = ax.pie(
        counts,
        labels=genres,
        autopct="%1.1f%%",
        colors=plt.cm.Paired(np.linspace(0, 1, len(genres))),
        wedgeprops={"edgecolor": "white"},
    )

    plt.setp(texts, color="white", size=10)
    plt.setp(autotexts, color="white", size=8)

    plt.tight_layout()

    buffer = io.BytesIO()
    plt.savefig(buffer, format="png", dpi=150, facecolor="#333333")
    plt.close()
    buffer.seek(0)

    return HttpResponse(buffer.getvalue(), content_type="image/png")


def parse_datetime(played_at):
    try:
        return datetime.strptime(played_at, "%Y-%m-%dT%H:%M:%S.%fZ").replace(
            tzinfo=pytz.utc
        )
    except ValueError:
        return datetime.strptime(played_at, "%Y-%m-%dT%H:%M:%SZ").replace(
            tzinfo=pytz.utc
        )
