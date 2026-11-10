"""Video processing: URL -> metadata -> transcript -> chunks -> embeddings -> database.

Already-processed videos are reused across all users (no duplicate chunks, no second transcript
lookup); each user then gets the video in their own library and their own sessions.
"""
from datetime import datetime, timedelta, timezone

from app.core.errors import AppError
from app.db.repositories import ChunkRepository, LibraryRepository, SessionRepository, VideoRepository
from app.services.chunking import chunk_transcript
from app.services.retrieval import store_chunks
from app.services.transcript import fetch_transcript
from app.services.youtube import extract_video_id, fetch_metadata

STALE_PROCESSING_AFTER = timedelta(minutes=15)  # a crashed run must not block a video forever
NO_TRANSCRIPT_CODES = {"TRANSCRIPT_UNAVAILABLE", "UNSUPPORTED_LANGUAGE"}


def _is_stale(video: dict) -> bool:
    try:
        updated = datetime.fromisoformat(video["updated_at"])
        return datetime.now(timezone.utc) - updated > STALE_PROCESSING_AFTER
    except (KeyError, TypeError, ValueError):
        return True


def _default_session(sessions: SessionRepository, video_id: str) -> dict:
    existing = sessions.list_for_video(video_id)  # newest activity first
    return existing[0] if existing else sessions.create(video_id)


def _mark_failed(videos: VideoRepository, video_id: str, status: str, message: str) -> None:
    try:
        videos.update_status(video_id, status, error_message=message)
    except Exception:
        pass  # never hide the original error


def process_video(
    youtube_url: str,
    videos: VideoRepository,
    sessions: SessionRepository,
    chunks: ChunkRepository,
    model=None,
    *,
    library: LibraryRepository,
) -> tuple[dict, dict, bool]:
    """Return (video_row, session_row, reused).

    The video row and its transcript chunks are shared: a video already processed (by anyone) is
    reused as it is, with no new transcript lookup, no new embeddings and no write to the shared rows.
    It is then added to this user's library, and the session is this user's own. `reused` means
    "already in your library", so it never reveals whether another user processed the video before.
    """
    youtube_id = extract_video_id(youtube_url)

    existing = videos.get_by_youtube_id(youtube_id)
    if existing and existing["processing_status"] == "completed" and chunks.count_for_video(existing["id"]) > 0:
        video = existing
    else:
        if existing and existing["processing_status"] == "processing" and not _is_stale(existing):
            raise AppError("VIDEO_PROCESSING", "This video is being prepared right now. Please try again in a minute.", 409)
        video = _ingest(youtube_id, videos, chunks, model)

    reused = library.has(video["id"])
    library.add(video["id"])
    return video, _default_session(sessions, video["id"]), reused


def _ingest(youtube_id: str, videos: VideoRepository, chunks: ChunkRepository, model=None) -> dict:
    """Fetch, chunk, embed and store one video's transcript (the shared, reusable part)."""
    metadata = fetch_metadata(youtube_id)
    video = videos.upsert_from_metadata(metadata, status="processing")
    try:
        transcript = fetch_transcript(youtube_id)
        store_chunks(video["id"], chunk_transcript(transcript), chunk_repo=chunks, model=model)
    except AppError as exc:
        status = "transcript_unavailable" if exc.error in NO_TRANSCRIPT_CODES else "failed"
        _mark_failed(videos, video["id"], status, exc.message)
        raise
    except Exception:
        _mark_failed(videos, video["id"], "failed", "Processing failed unexpectedly.")
        raise AppError("PROCESSING_FAILED", "The video could not be processed. Please try again.", 500)

    try:
        return videos.update_status(video["id"], "completed", language=transcript.language_code)
    except Exception:  # otherwise the video would stay "processing" and block re-submits
        _mark_failed(videos, video["id"], "failed", "Processing failed unexpectedly.")
        raise
