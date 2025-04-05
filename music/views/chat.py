"""
Chat Interface View Module.
Handles the AI chat functionality for the user's music listening data.
"""

import json
import logging

from asgiref.sync import sync_to_async
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import redirect, render
from django.utils.decorators import method_decorator
from django.views import View
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.vary import vary_on_cookie

from music.views.utils.helpers import handle_chat_message
from spotify.util import is_spotify_authenticated

# Configure logger
logger = logging.getLogger(__name__)


@vary_on_cookie
async def chat(request: HttpRequest) -> HttpResponse:
    """
    Render the chat interface page.

    Args:
        request: The HTTP request object

    Returns:
        Rendered chat page or redirect to authentication
    """
    # Verify user authentication
    spotify_user_id = await sync_to_async(request.session.get)("spotify_user_id")
    if not spotify_user_id or not await sync_to_async(is_spotify_authenticated)(
        spotify_user_id
    ):
        return redirect("spotify-auth")

    # Render chat interface with minimal context
    return render(request, "music/pages/chat.html", {"segment": "chat"})


@method_decorator(csrf_exempt, name="dispatch")
class ChatAPI(View):
    """
    API endpoint to handle chat message exchanges with the AI assistant.
    """

    async def post(self, request: HttpRequest) -> JsonResponse:
        """
        Process incoming chat messages and return AI responses.

        Args:
            request: The HTTP request with JSON message payload

        Returns:
            JSON response with AI reply or error message
        """
        try:
            # Parse request data
            data = json.loads(request.body)
            user_message = data.get("message")

            # Get user ID from session
            spotify_user_id = await sync_to_async(request.session.get)(
                "spotify_user_id"
            )

            # Process message through helper function
            response, status_code = await handle_chat_message(
                spotify_user_id, user_message
            )

            return JsonResponse(response, status=status_code)

        except json.JSONDecodeError:
            logger.error("Invalid JSON received in chat request")
            return JsonResponse({"error": "Invalid request format."}, status=400)
        except Exception as e:
            logger.error(f"Error in ChatAPI: {e}", exc_info=True)
            return JsonResponse({"error": "Internal server error."}, status=500)
