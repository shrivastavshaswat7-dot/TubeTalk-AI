from uuid import UUID

from fastapi import APIRouter, Depends

from app.api.deps import (
    get_chunk_repo,
    get_library_repo,
    get_session_repo,
    get_video_repo,
    require_library_video,
)
from app.core.auth import get_current_user
from app.db.repositories import ChunkRepository, LibraryRepository, SessionRepository, VideoRepository
from app.schemas.api import (
    ProcessVideoRequest,
    ProcessVideoResponse,
    SessionsResponse,
    VideoResponse,
    VideosResponse,
)
from app.services.ingestion import process_video

router = APIRouter(prefix="/api/videos", tags=["videos"], dependencies=[Depends(get_current_user)])


# Plain `def` routes run in FastAPI's threadpool, so CPU-heavy embedding does not block the server.
@router.post("/process", response_model=ProcessVideoResponse)
def process(
    body: ProcessVideoRequest,
    videos: VideoRepository = Depends(get_video_repo),
    sessions: SessionRepository = Depends(get_session_repo),
    chunks: ChunkRepository = Depends(get_chunk_repo),
    library: LibraryRepository = Depends(get_library_repo),
):
    video, session, reused = process_video(body.youtube_url, videos, sessions, chunks, library=library)
    return {
        "message": "Video already processed" if reused else "Video processed successfully",
        "reused": reused,
        "video": video,
        "session": session,
    }


@router.get("", response_model=VideosResponse)
def list_videos(library: LibraryRepository = Depends(get_library_repo)):
    return {"videos": library.list_videos()}


@router.get("/{video_id}", response_model=VideoResponse)
def get_video(
    video_id: UUID,
    videos: VideoRepository = Depends(get_video_repo),
    library: LibraryRepository = Depends(get_library_repo),
):
    return {"video": require_library_video(str(video_id), library, videos)}


@router.get("/{video_id}/sessions", response_model=SessionsResponse)
def list_video_sessions(
    video_id: UUID,
    videos: VideoRepository = Depends(get_video_repo),
    sessions: SessionRepository = Depends(get_session_repo),
    library: LibraryRepository = Depends(get_library_repo),
):
    require_library_video(str(video_id), library, videos)
    return {"sessions": sessions.list_for_video(str(video_id))}
