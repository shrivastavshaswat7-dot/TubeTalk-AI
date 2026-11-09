from uuid import UUID

from fastapi import APIRouter, Depends

from app.api.deps import get_chunk_repo, get_session_repo, get_video_repo
from app.core.errors import AppError
from app.db.repositories import ChunkRepository, SessionRepository, VideoRepository
from app.schemas.api import (
    ProcessVideoRequest,
    ProcessVideoResponse,
    SessionsResponse,
    VideoResponse,
    VideosResponse,
)
from app.services.ingestion import process_video

router = APIRouter(prefix="/api/videos", tags=["videos"])


# Plain `def` routes run in FastAPI's threadpool, so CPU-heavy embedding does not block the server.
@router.post("/process", response_model=ProcessVideoResponse)
def process(
    body: ProcessVideoRequest,
    videos: VideoRepository = Depends(get_video_repo),
    sessions: SessionRepository = Depends(get_session_repo),
    chunks: ChunkRepository = Depends(get_chunk_repo),
):
    video, session, reused = process_video(body.youtube_url, videos, sessions, chunks)
    return {
        "message": "Video already processed" if reused else "Video processed successfully",
        "reused": reused,
        "video": video,
        "session": session,
    }


@router.get("", response_model=VideosResponse)
def list_videos(videos: VideoRepository = Depends(get_video_repo)):
    return {"videos": videos.list_recent()}


@router.get("/{video_id}", response_model=VideoResponse)
def get_video(video_id: UUID, videos: VideoRepository = Depends(get_video_repo)):
    video = videos.get(str(video_id))
    if video is None:
        raise AppError("VIDEO_NOT_FOUND", "The requested video does not exist.", 404)
    return {"video": video}


@router.get("/{video_id}/sessions", response_model=SessionsResponse)
def list_video_sessions(
    video_id: UUID,
    videos: VideoRepository = Depends(get_video_repo),
    sessions: SessionRepository = Depends(get_session_repo),
):
    if videos.get(str(video_id)) is None:
        raise AppError("VIDEO_NOT_FOUND", "The requested video does not exist.", 404)
    return {"sessions": sessions.list_for_video(str(video_id))}
