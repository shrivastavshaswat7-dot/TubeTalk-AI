"""Session routes. Sessions are only found through the signed-in user's SessionRepository, and every
route that takes a session also requires its video_id and verifies the pair, so neither another
user's session nor another video's session can be read or changed."""
from uuid import UUID

from fastapi import APIRouter, Depends

from app.api.deps import (
    get_library_repo,
    get_message_repo,
    get_session_repo,
    get_video_repo,
    require_library_video,
)
from app.core.auth import get_current_user
from app.core.errors import AppError
from app.db.repositories import LibraryRepository, MessageRepository, SessionRepository, VideoRepository
from app.schemas.api import (
    CreateSessionRequest,
    DeleteResponse,
    MessagesResponse,
    SessionResponse,
)

router = APIRouter(prefix="/api/sessions", tags=["sessions"], dependencies=[Depends(get_current_user)])


@router.post("", response_model=SessionResponse, status_code=201)
def create_session(
    body: CreateSessionRequest,
    videos: VideoRepository = Depends(get_video_repo),
    sessions: SessionRepository = Depends(get_session_repo),
    library: LibraryRepository = Depends(get_library_repo),
):
    video = require_library_video(str(body.video_id), library, videos)
    if video["processing_status"] != "completed":
        raise AppError("VIDEO_NOT_READY", "This video has not finished processing.", 409)
    return {"session": sessions.create(str(body.video_id), body.session_title)}


@router.get("/{session_id}", response_model=SessionResponse)
def get_session(
    session_id: UUID, video_id: UUID, sessions: SessionRepository = Depends(get_session_repo)
):
    return {"session": sessions.get_for_video(str(session_id), str(video_id))}


@router.get("/{session_id}/messages", response_model=MessagesResponse)
def get_messages(
    session_id: UUID,
    video_id: UUID,
    sessions: SessionRepository = Depends(get_session_repo),
    messages: MessageRepository = Depends(get_message_repo),
):
    sessions.get_for_video(str(session_id), str(video_id))
    return {"messages": messages.list_for_session(str(session_id))}


@router.delete("/{session_id}", response_model=DeleteResponse)
def delete_session(
    session_id: UUID, video_id: UUID, sessions: SessionRepository = Depends(get_session_repo)
):
    sessions.get_for_video(str(session_id), str(video_id))
    sessions.delete(str(session_id))
    return {"message": "Session deleted successfully"}
