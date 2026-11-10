"""FastAPI dependencies. Repositories are created per request so tests can override them.

Private data (library, sessions and their messages, insights) is only ever reached through
repositories bound to the signed-in user. Shared content (videos, transcript chunks) is reached only
after `require_library_video` has confirmed the video is in that user's library.
"""
from uuid import UUID

from fastapi import Depends

from app.core.auth import CurrentUser, get_current_user
from app.core.errors import AppError
from app.db.repositories import (
    ChunkRepository,
    InsightsRepository,
    LibraryRepository,
    MessageRepository,
    SessionRepository,
    VideoRepository,
)


def get_video_repo() -> VideoRepository:
    return VideoRepository()


def get_library_repo(user: CurrentUser = Depends(get_current_user)) -> LibraryRepository:
    return LibraryRepository(user_id=user.id)


def get_session_repo(user: CurrentUser = Depends(get_current_user)) -> SessionRepository:
    return SessionRepository(user_id=user.id)


def get_message_repo() -> MessageRepository:
    # Messages are only read or written after their session was found through the user's
    # SessionRepository, which is what keeps them private.
    return MessageRepository()


def get_chunk_repo() -> ChunkRepository:
    return ChunkRepository()


def get_insights_repo(user: CurrentUser = Depends(get_current_user)) -> InsightsRepository:
    return InsightsRepository(user_id=user.id)


def require_library_video(video_id: str, library: LibraryRepository, videos: VideoRepository) -> dict:
    """The video, if it is in this user's library. Anything else, including another user's video,
    is reported exactly like a video that does not exist."""
    video = videos.get(video_id) if library.has(video_id) else None
    if video is None:
        raise AppError("VIDEO_NOT_FOUND", "The requested video does not exist.", 404)
    return video


def library_video_from_path(
    video_id: UUID,
    videos: VideoRepository = Depends(get_video_repo),
    library: LibraryRepository = Depends(get_library_repo),
) -> dict:
    """Router-level guard for routes under /api/videos/{video_id}/…"""
    return require_library_video(str(video_id), library, videos)
