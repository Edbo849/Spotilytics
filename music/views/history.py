from .utils.imports import *


@csrf_exempt
async def import_history(request: HttpRequest) -> HttpResponse:
    if request.method == "POST":
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

                try:
                    data = json.loads(file_content.decode("utf-8"))
                except json.JSONDecodeError:
                    return HttpResponse(
                        "Invalid JSON file. Please upload a valid JSON file.",
                        status=400,
                    )

                if not data:
                    return HttpResponse(
                        "Empty JSON file. Please upload a non-empty JSON file.",
                        status=400,
                    )

                if not isinstance(data, list):
                    return HttpResponse(
                        "Invalid JSON format. Expected a list of tracks.", status=400
                    )

                track_ids = []
                durations = {}
                track_info_list = []

                for item in data:
                    required_keys = [
                        "ts",
                        "master_metadata_track_name",
                        "master_metadata_album_artist_name",
                        "master_metadata_album_album_name",
                        "spotify_track_uri",
                    ]
                    if not all(key in item for key in required_keys):
                        continue

                    played_at_str = item["ts"]
                    try:
                        played_at = datetime.strptime(
                            played_at_str, "%Y-%m-%dT%H:%M:%S%z"
                        )
                    except ValueError:
                        continue

                    if played_at > timezone.now():
                        continue

                    track_name = item["master_metadata_track_name"]
                    artist_name = item["master_metadata_album_artist_name"]
                    album_name = item["master_metadata_album_album_name"]
                    track_uri = item.get("spotify_track_uri")
                    duration_ms = item.get("ms_played", 0)

                    if not track_uri or not track_uri.startswith("spotify:track:"):
                        continue

                    track_id = track_uri.split(":")[-1]
                    track_ids.append(track_id)
                    durations[track_id] = duration_ms
                    track_info_list.append(
                        {
                            "track_id": track_id,
                            "played_at": played_at,
                            "track_name": track_name,
                            "artist_name": artist_name,
                            "album_name": album_name,
                            "duration_ms": duration_ms,
                        }
                    )

                if not track_ids:
                    return HttpResponse(
                        "No valid tracks found in the uploaded file.", status=400
                    )

                batch_size = 50
                track_details_dict = {}
                for i in range(0, len(track_ids), batch_size):
                    batch_ids = track_ids[i : i + batch_size]
                    async with SpotifyClient(spotify_user_id) as client:
                        track_details_response = (
                            await client.get_multiple_track_details(batch_ids)
                        )
                    track_details_list = track_details_response.get("tracks", [])

                    for track_details in track_details_list:
                        track_id = track_details.get("id")
                        if track_id:
                            track_details_dict[track_id] = track_details

                artist_ids = set()
                for track_details in track_details_dict.values():
                    artist_info_list = track_details.get("artists", [])
                    if artist_info_list:
                        artist_id = artist_info_list[0].get("id")
                        if artist_id:
                            artist_ids.add(artist_id)

                artist_details_dict = {}
                for i in range(0, len(artist_ids), batch_size):
                    batch_artist_ids = list(artist_ids)[i : i + batch_size]
                    async with SpotifyClient(spotify_user_id) as client:
                        artists_response = await client.get_multiple_artists(
                            batch_artist_ids
                        )
                    artist_details_list = artists_response.get("artists", [])
                    for artist_details in artist_details_list:
                        artist_id = artist_details.get("id")
                        if artist_id:
                            artist_details_dict[artist_id] = artist_details

                new_tracks_added = await save_tracks_atomic(
                    user, track_info_list, track_details_dict, artist_details_dict
                )

                await sync_to_async(default_storage.save)(file_path, file)
                logger.info(
                    f"Successfully imported and saved file: {file.name} {new_tracks_added} tracks)"
                )

            except Exception as e:
                logger.error(f"Failed to import file {file.name}: {e}")
                return HttpResponse(
                    f"Failed to import file {file.name}: {str(e)}", status=500
                )

        return await sync_to_async(redirect)("music:home")
    return HttpResponse(status=405)


@csrf_exempt
async def delete_history(request: HttpRequest) -> HttpResponse:
    if request.method == "POST":
        listening_history_path = os.path.join(
            settings.BASE_DIR, "media/listening_history"
        )

        try:
            filenames = await sync_to_async(os.listdir)(listening_history_path)
        except FileNotFoundError:
            return HttpResponse("Listening history directory not found.", status=404)
        except Exception as e:
            logger.error(f"Error accessing listening history directory: {e}")
            return HttpResponse(f"Error: {str(e)}", status=500)

        for filename in filenames:
            file_path = os.path.join(listening_history_path, filename)
            if await sync_to_async(os.path.isfile)(file_path):
                try:
                    await sync_to_async(os.remove)(file_path)
                except Exception as e:
                    logger.error(f"Error removing file {file_path}: {e}")
                    return HttpResponse(f"Error removing file: {file_path}", status=500)

        try:
            await sync_to_async(PlayedTrack.objects.all().delete)()
        except Exception as e:
            logger.error(f"Error deleting listening history from database: {e}")
            return HttpResponse(f"Database error: {str(e)}", status=500)

        return HttpResponse("All listening history has been deleted.", status=200)
    return HttpResponse(status=405)
