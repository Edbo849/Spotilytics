from venv import logger

import matplotlib
import numpy as np
from asgiref.sync import sync_to_async
from django.shortcuts import redirect

from spotify.util import is_spotify_authenticated

matplotlib.use("Agg")

import io
from datetime import datetime, timedelta

import matplotlib.pyplot as plt
import pytz
from django.http import HttpResponse

from .spotify_api import get_recently_played_full, get_top_genres


def generate_line_graph(date_labels, counts):
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
    return buffer


async def line_graph(request):
    spotify_user_id = await sync_to_async(request.session.get)("spotify_user_id")
    if not spotify_user_id or not await sync_to_async(is_spotify_authenticated)(
        spotify_user_id
    ):
        return await sync_to_async(redirect)("spotify-auth")

    try:
        recently_played = await get_recently_played_full(spotify_user_id)
    except Exception as e:
        logger.error(f"Error generating line graph: {e}")
        return HttpResponse("Error generating line graph", status=500)

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

    buffer = await sync_to_async(generate_line_graph)(date_labels, counts)

    return HttpResponse(buffer.getvalue(), content_type="image/png")


async def pie_chart(request):
    """Generate a pie chart of user's top genres."""
    spotify_user_id = await sync_to_async(request.session.get)("spotify_user_id")
    if not spotify_user_id or not await sync_to_async(is_spotify_authenticated)(
        spotify_user_id
    ):
        return await sync_to_async(redirect)("spotify-auth")

    time_range = request.GET.get("time_range", "medium_term")

    try:
        top_genres = await get_top_genres(50, spotify_user_id, time_range)
    except Exception as e:
        logger.error(f"Error generating pie chart: {e}")
        return HttpResponse("Error generating pie chart", status=500)

    genres = [item["genre"] for item in top_genres]
    counts = [item["count"] for item in top_genres]

    buffer = await sync_to_async(generate_pie_chart)(genres, counts)

    return HttpResponse(buffer.getvalue(), content_type="image/png")


def generate_pie_chart(genres, counts):
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
    return buffer


def parse_datetime(played_at):
    try:
        return datetime.strptime(played_at, "%Y-%m-%dT%H:%M:%S.%fZ").replace(
            tzinfo=pytz.utc
        )
    except ValueError:
        return datetime.strptime(played_at, "%Y-%m-%dT%H:%M:%SZ").replace(
            tzinfo=pytz.utc
        )
