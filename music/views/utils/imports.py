# Python standard library
import asyncio
import hashlib
import json
import logging
import os
from datetime import datetime, timedelta

# Third party imports
import openai

# Django imports
from asgiref.sync import sync_to_async
from django.conf import settings
from django.core.cache import cache
from django.core.files.storage import default_storage
from django.db import IntegrityError, transaction
from django.db.models import Count
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import redirect, render
from django.utils import timezone
from django.utils.decorators import method_decorator
from django.views import View
from django.views.decorators.cache import cache_page
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.vary import vary_on_cookie

from music.models import PlayedTrack, SpotifyUser

# Local imports
from music.services.graphs import (
    generate_chartjs_bar_chart,
    generate_chartjs_bubble_chart,
    generate_chartjs_doughnut_chart,
    generate_chartjs_line_graph,
    generate_chartjs_pie_chart,
    generate_chartjs_polar_area_chart,
    generate_chartjs_radar_chart,
    generate_chartjs_stacked_bar_chart,
)
from music.services.openai_service import OpenAIService
from music.services.SpotifyClient import SpotifyClient
from music.utils.db_utils import (
    get_bubble_chart_data,
    get_dashboard_stats,
    get_date_range,
    get_discovery_timeline_data,
    get_doughnut_chart_data,
    get_hourly_listening_data,
    get_item_stats_util,
    get_listening_stats,
    get_radar_chart_data,
    get_recently_played,
    get_replay_gaps,
    get_stats_boxes_data,
    get_streaming_trend_data,
    get_time_period_distribution,
    get_top_albums,
    get_top_artists,
    get_top_genres,
    get_top_tracks,
    save_tracks_atomic,
)
from music.views.utils.helpers import get_x_label
from spotify.util import is_spotify_authenticated

# Initialize logger
logger = logging.getLogger(__name__)
