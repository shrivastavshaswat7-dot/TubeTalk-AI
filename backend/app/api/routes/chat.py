from fastapi import APIRouter, Depends

from app.api.deps import get_chunk_repo, get_insights_repo, get_message_repo, get_session_repo, get_video_repo
from app.db.repositories import (
    ChunkRepository,
    InsightsRepository,
    MessageRepository,
    SessionRepository,
    VideoRepository,
)
from app.schemas.api import ChatRequest, ChatResponse
from app.services.chat import chat

router = APIRouter(prefix="/api", tags=["chat"])


@router.post("/chat", response_model=ChatResponse)
def send_message(
    body: ChatRequest,
    videos: VideoRepository = Depends(get_video_repo),
    sessions: SessionRepository = Depends(get_session_repo),
    messages: MessageRepository = Depends(get_message_repo),
    chunks: ChunkRepository = Depends(get_chunk_repo),
    insights: InsightsRepository = Depends(get_insights_repo),
):
    result = chat(
        str(body.video_id), str(body.session_id), body.message, videos, sessions, messages, chunks,
        insights=insights,
    )
    return {
        "session_id": str(body.session_id),
        "answer": result.rag.answer,
        "grounded": result.rag.grounded,
        "sources": result.assistant_message["sources"] or [],
        "standalone_question": result.standalone_question,
        "answer_type": result.answer_type,
        "user_message": result.user_message,
        "assistant_message": result.assistant_message,
    }
