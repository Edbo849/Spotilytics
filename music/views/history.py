from music.views.utils.helpers import delete_listening_history, handle_history_import

from .utils.imports import *


@csrf_exempt
async def import_history(request: HttpRequest) -> HttpResponse:
    if request.method != "POST":
        return HttpResponse(status=405)

    files = request.FILES.getlist("history_files")
    if not files:
        return HttpResponse(
            "No files uploaded. Please attach at least one JSON file.", status=400
        )

    spotify_user_id = await sync_to_async(request.session.get)("spotify_user_id")
    if not spotify_user_id:
        return await sync_to_async(redirect)("spotify-auth")

    try:
        user = await sync_to_async(SpotifyUser.objects.get)(
            spotify_user_id=spotify_user_id
        )
    except SpotifyUser.DoesNotExist:
        return HttpResponse("User does not exist.", status=400)
    except Exception as e:
        logger.error(f"Database error: {e}")
        return HttpResponse(f"Database error: {str(e)}", status=500)

    for file in files:
        try:
            file_content = await sync_to_async(file.read)()
            file_hash = hashlib.sha256(file_content).hexdigest()
            await sync_to_async(file.seek)(0)

            file_path = os.path.join("listening_history", f"{file_hash}.json")
            exists = await sync_to_async(default_storage.exists)(file_path)
            if exists:
                return HttpResponse(
                    "Duplicate file detected. Import rejected.", status=400
                )

            success, result = await handle_history_import(user, file_content, file_hash)
            if not success:
                return HttpResponse(result, status=400)

            await sync_to_async(default_storage.save)(file_path, file)
            logger.info(f"Successfully imported and saved file: {file.name}")

        except Exception as e:
            logger.error(f"Failed to import file {file.name}: {e}")
            return HttpResponse(
                f"Failed to import file {file.name}: {str(e)}", status=500
            )

    return await sync_to_async(redirect)("music:home")


@csrf_exempt
async def delete_history(request: HttpRequest) -> HttpResponse:
    if request.method == "POST":
        success, message = await delete_listening_history()
        if not success:
            return HttpResponse(message, status=500)
        return HttpResponse(message, status=200)
    return HttpResponse(status=405)
