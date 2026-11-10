"""Video processing: URL -> metadata -> transcript -> chunks -> embeddings -> database.

Already-processed videos are reused (no duplicate chunks).
"""
from datetime import datetime, timedelta, timezone

from app.core.errors import AppError
from app.db.repositories import ChunkRepository, SessionRepository, VideoRepository
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
) -> tuple[dict, dict, bool]:
    """Return (video_row, session_row, reused)."""
    youtube_id = extract_video_id(youtube_url)

    existing = videos.get_by_youtube_id(youtube_id)
    if existing:
        if existing["processing_status"] == "completed" and chunks.count_for_video(existing["id"]) > 0:
            return existing, _default_session(sessions, existing["id"]), True
        if existing["processing_status"] == "processing" and not _is_stale(existing):
            raise AppError("VIDEO_PROCESSING", "This video is already being processed. Please wait.", 409)

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
        video = videos.update_status(video["id"], "completed", language=transcript.language_code)
    except Exception:  # otherwise the video would stay "processing" and block re-submits
        _mark_failed(videos, video["id"], "failed", "Processing failed unexpectedly.")
        raise
    return video, _default_session(sessions, video["id"]), False
