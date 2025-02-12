from .utils.imports import *


@vary_on_cookie
async def chat(request: HttpRequest) -> HttpResponse:
    spotify_user_id = await sync_to_async(request.session.get)("spotify_user_id")
    if not spotify_user_id or not await sync_to_async(is_spotify_authenticated)(
        spotify_user_id
    ):
        return redirect("spotify-auth")

    return render(request, "music/chat.html", {"segment": "chat"})


@method_decorator(csrf_exempt, name="dispatch")
class ChatAPI(View):
    def post(self, request: HttpRequest) -> JsonResponse:
        try:
            data = json.loads(request.body)
            user_message = data.get("message")
            if not user_message:
                return JsonResponse({"error": "No message provided."}, status=400)

            spotify_user_id = request.session.get("spotify_user_id")
            if not spotify_user_id or not is_spotify_authenticated(spotify_user_id):
                return JsonResponse({"error": "User not authenticated."}, status=401)

            openai_service = OpenAIService()
            listening_data = openai_service.get_listening_data(spotify_user_id)
            prompt = openai_service.create_prompt(user_message, listening_data)
            ai_response = openai_service.get_ai_response(prompt)

            return JsonResponse({"reply": ai_response})

        except Exception as e:
            logger.error(f"Error in ChatAPI: {e}")
            return JsonResponse({"error": "Internal server error."}, status=500)
