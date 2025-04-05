"""
History Import View Module.
Handles importing and deleting Spotify listening history files.
"""

import hashlib
import logging
import os

from asgiref.sync import sync_to_async
from django.core.files.storage import default_storage
from django.http import HttpRequest, HttpResponse
from django.shortcuts import redirect
from django.views.decorators.csrf import csrf_exempt

from music.models import SpotifyUser
from music.views.utils.helpers import delete_listening_history, handle_history_import

# Configure logger
logger = logging.getLogger(__name__)


@csrf_exempt
async def import_history(request: HttpRequest) -> HttpResponse:
    """
    Handle importing Spotify listening history files.

    Accepts uploaded JSON files containing Spotify listening history,
    validates them, and processes their contents into the database.

    Args:
        request: The HTTP request with file uploads

    Returns:
        HTTP response indicating success or failure
    """
    # Only allow POST requests
    if request.method != "POST":
        return HttpResponse(status=405)  # Method Not Allowed

    # Validate that files were uploaded
    files = request.FILES.getlist("history_files")
    if not files:
        return HttpResponse(
            "No files uploaded. Please attach at least one JSON file.", status=400
        )

    # Verify user authentication
    spotify_user_id = await sync_to_async(request.session.get)("spotify_user_id")
    if not spotify_user_id:
        return await sync_to_async(redirect)("spotify-auth")

    # Get user object from database
    try:
        user = await sync_to_async(SpotifyUser.objects.get)(
            spotify_user_id=spotify_user_id
        )
    except SpotifyUser.DoesNotExist:
        logger.error(f"User with ID {spotify_user_id} does not exist")
        return HttpResponse("User does not exist.", status=400)
    except Exception as e:
        logger.error(f"Database error when fetching user: {e}", exc_info=True)
        return HttpResponse(f"Database error: {str(e)}", status=500)

    # Process each uploaded file
    for file in files:
        try:
            # Read file content and create a hash to identify duplicates
            file_content = await sync_to_async(file.read)()
            file_hash = hashlib.sha256(file_content).hexdigest()
            await sync_to_async(file.seek)(
                0
            )  # Reset file pointer for future operations

            # Check if this exact file has already been imported
            file_path = os.path.join("listening_history", f"{file_hash}.json")
            exists = await sync_to_async(default_storage.exists)(file_path)
            if exists:
                return HttpResponse(
                    "Duplicate file detected. Import rejected.", status=400
                )

            # Process the file contents and import the listening history
            success, result = await handle_history_import(user, file_content, file_hash)
            if not success:
                return HttpResponse(result, status=400)

            # Save the file for future reference
            await sync_to_async(default_storage.save)(file_path, file)
            logger.info(f"Successfully imported and saved file: {file.name}")

        except Exception as e:
            logger.error(f"Failed to import file {file.name}: {e}", exc_info=True)
            return HttpResponse(
                f"Failed to import file {file.name}: {str(e)}", status=500
            )

    # Redirect to home page on successful import
    return await sync_to_async(redirect)("music:home")


@csrf_exempt
async def delete_history(request: HttpRequest) -> HttpResponse:
    """
    Handle deletion of all listening history data.

    Removes all listening history files and database records.

    Args:
        request: The HTTP request

    Returns:
        HTTP response indicating success or failure
    """
    # Only allow POST requests
    if request.method == "POST":
        # Call helper function to delete all history data
        success, message = await delete_listening_history()

        # Return appropriate response based on success or failure
        if not success:
            logger.error(f"Failed to delete listening history: {message}")
            return HttpResponse(message, status=500)

        logger.info("Successfully deleted all listening history")
        return HttpResponse(message, status=200)

    # Method not allowed for non-POST requests
    return HttpResponse(status=405)  # Method Not Allowed
