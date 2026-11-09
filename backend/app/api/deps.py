"""FastAPI dependencies. Repositories are created per request so tests can override them."""
from app.db.repositories import (
    ChunkRepository,
    InsightsRepository,
    MessageRepository,
    SessionRepository,
    VideoRepository,
)


def get_video_repo() -> VideoRepository:
    return VideoRepository()


def get_session_repo() -> SessionRepository:
    return SessionRepository()


def get_message_repo() -> MessageRepository:
    return MessageRepository()


def get_chunk_repo() -> ChunkRepository:
    return ChunkRepository()


def get_insights_repo() -> InsightsRepository:
    return InsightsRepository()
