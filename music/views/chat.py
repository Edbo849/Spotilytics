from music.views.utils.helpers import handle_chat_message

from .utils.imports import *


@vary_on_cookie
async def chat(request: HttpRequest) -> HttpResponse:
    spotify_user_id = await sync_to_async(request.session.get)("spotify_user_id")
    if not spotify_user_id or not await sync_to_async(is_spotify_authenticated)(
        spotify_user_id
    ):
        return redirect("spotify-auth")

    return render(request, "music/pages/chat.html", {"segment": "chat"})


@method_decorator(csrf_exempt, name="dispatch")
class ChatAPI(View):
    async def post(self, request: HttpRequest) -> JsonResponse:
        try:
            data = json.loads(request.body)
            user_message = data.get("message")
            spotify_user_id = await sync_to_async(request.session.get)(
                "spotify_user_id"
            )

            response, status_code = await handle_chat_message(
                spotify_user_id, user_message
            )
            return JsonResponse(response, status=status_code)

        except Exception as e:
            logger.error(f"Error in ChatAPI: {e}")
            return JsonResponse({"error": "Internal server error."}, status=500)
