"""Request/response models for the HTTP API."""
from uuid import UUID

from pydantic import BaseModel, Field

MAX_MESSAGE_LENGTH = 2000


class ProcessVideoRequest(BaseModel):
    youtube_url: str = Field(max_length=500)


class CreateSessionRequest(BaseModel):
    video_id: UUID
    session_title: str = Field(default="New Conversation", min_length=1, max_length=120)


class ChatRequest(BaseModel):
    video_id: UUID
    session_id: UUID
    # Emptiness is checked in the service so it returns EMPTY_MESSAGE rather than a 422.
    message: str = Field(max_length=MAX_MESSAGE_LENGTH)


class VideoOut(BaseModel):
    id: str
    youtube_video_id: str
    youtube_url: str
    title: str | None = None
    channel_name: str | None = None
    thumbnail_url: str | None = None
    transcript_language: str | None = None
    processing_status: str
    created_at: str | None = None


class SessionOut(BaseModel):
    id: str
    video_id: str
    session_title: str | None = None
    created_at: str | None = None
    updated_at: str | None = None


class SourceOut(BaseModel):
    # kind: "transcript" = retrieved by similarity; "topic" = stored chunk at an Insights topic's
    # timestamp; "summary" = the answer came from the transcript-derived video summary;
    # "clarification" = the assistant asked what the user meant (no transcript sources).
    kind: str = "transcript"
    topic: str | None = None
    chunk_id: str | None = None  # None only for kind="summary" / "clarification"
    chunk_index: int | None = None
    content: str
    start_time: float | None = None
    end_time: float | None = None
    similarity: float | None = None  # None for topic/summary sources (not a similarity match)
    timestamp_url: str | None = None  # opens YouTube at start_time


class MessageOut(BaseModel):
    id: str
    session_id: str
    role: str
    content: str
    sources: list[SourceOut] | None = None
    created_at: str | None = None


class ProcessVideoResponse(BaseModel):
    success: bool = True
    message: str
    reused: bool
    video: VideoOut
    session: SessionOut


class VideoResponse(BaseModel):
    success: bool = True
    video: VideoOut


class VideosResponse(BaseModel):
    success: bool = True
    videos: list[VideoOut]


class SessionResponse(BaseModel):
    success: bool = True
    session: SessionOut


class SessionsResponse(BaseModel):
    success: bool = True
    sessions: list[SessionOut]


class MessagesResponse(BaseModel):
    success: bool = True
    messages: list[MessageOut]


class DeleteResponse(BaseModel):
    success: bool = True
    message: str


class ChatResponse(BaseModel):
    success: bool = True
    session_id: str
    answer: str
    grounded: bool
    sources: list[SourceOut]
    standalone_question: str  # the question actually used for retrieval
    answer_type: str = "retrieval"  # "retrieval" | "summary" (stored Insights) | "clarification"
    user_message: MessageOut
    assistant_message: MessageOut


class TopicOut(BaseModel):
    name: str
    start_time: float | None = None
    timestamp: str | None = None  # "mm:ss"
    timestamp_url: str | None = None  # opens YouTube at start_time


class InsightsOut(BaseModel):
    summary: str
    key_takeaways: list[str]
    topics: list[TopicOut]
    model: str | None = None
    generated_at: str | None = None


class InsightsResponse(BaseModel):
    success: bool = True
    video_id: str
    cached: bool
    insights: InsightsOut


class SummaryResponse(BaseModel):
    success: bool = True
    video_id: str
    cached: bool
    summary: str
    generated_at: str | None = None


class TakeawaysResponse(BaseModel):
    success: bool = True
    video_id: str
    cached: bool
    key_takeaways: list[str]
    generated_at: str | None = None


class SuggestionsResponse(BaseModel):
    success: bool = True
    video_id: str
    insights_ready: bool  # False: insights not generated yet, so there are no topic suggestions
    suggestions: list[str]  # only questions that passed retrieval at the global threshold


class TopicsResponse(BaseModel):
    success: bool = True
    video_id: str
    cached: bool
    topics: list[TopicOut]
    generated_at: str | None = None
