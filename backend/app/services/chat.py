"""Chat: validates session ownership, uses ONLY this session's history, answers via RAG, persists."""
from dataclasses import dataclass

from app.core.errors import AppError
from app.db.repositories import (
    ChunkRepository,
    InsightsRepository,
    MessageRepository,
    SessionRepository,
    VideoRepository,
)
from app.prompts.chat import CONTEXTUALIZE_SYSTEM_PROMPT, CONTEXTUALIZE_USER_TEMPLATE, format_history
from app.schemas.chunk import RetrievedChunk
from app.schemas.api import MAX_MESSAGE_LENGTH
from app.services import insights as insights_service
from app.services import llm
from app.services.question_intent import _normalise, refers_back, route
from app.services.rag import RagAnswer, answer_question
from app.services.summary_answer import build_summary_answer

HISTORY_MESSAGES = 6  # most recent messages used for follow-up resolution


@dataclass(frozen=True)
class ChatResult:
    standalone_question: str
    rag: RagAnswer
    user_message: dict
    assistant_message: dict
    answer_type: str = "retrieval"  # "retrieval" | "summary" | "clarification"


# Persisted as the assistant message's only "source", so a reloaded conversation still shows the
# message as a clarifying question (not as a refusal or a transcript answer).
CLARIFICATION_SOURCE = {
    "kind": "clarification", "topic": None, "chunk_id": None, "chunk_index": None, "content": "",
    "start_time": None, "end_time": None, "similarity": None, "timestamp_url": None,
}


def _summary_answer(intent: str, video: dict, videos, insights, chunks, llm_client) -> tuple[str, list[dict]]:
    """Answer a whole-video question from stored Insights (generated once, then cached).
    Failures raise distinct errors so they are never mistaken for a transcript refusal."""
    try:
        row, _ = insights_service.get_or_generate(video["id"], videos, insights, chunks, llm_client=llm_client)
    except AppError as exc:
        if exc.error == "INSIGHTS_GENERATING":
            raise AppError(
                "SUMMARY_GENERATING",
                "The video summary is still being prepared. Please try again in a moment.",
                409,
            )
        raise AppError(
            "SUMMARY_UNAVAILABLE",
            "I couldn't prepare the video summary, so this overview question wasn't answered. "
            "Please try again, or ask about something specific in the video.",
            503,
        )
    return build_summary_answer(intent, row, chunks.list_for_video(video["id"]), video["youtube_url"])


def contextualize_question(question: str, history: list[dict], llm_client=None) -> str:
    """Rewrite a follow-up into a standalone question. Falls back to the original on any problem."""
    if not history:
        return question
    prompt = CONTEXTUALIZE_USER_TEMPLATE.format(history=format_history(history), question=question)
    try:
        rewritten = llm.generate(CONTEXTUALIZE_SYSTEM_PROMPT, prompt, llm=llm_client)
    except AppError:
        return question
    rewritten = rewritten.strip().strip('"').strip()
    if not rewritten or "\n" in rewritten or len(rewritten) > MAX_MESSAGE_LENGTH:
        return question
    return rewritten


def build_retrieval_query(message: str, standalone: str, history: list[dict]) -> str:
    """What to search the transcript with for this turn.

    The follow-up rewrite is used only if it actually resolved the reference (it no longer contains
    words like "he", "it", "them"). Otherwise, never trusting the rewrite, the previous user question
    is added so retrieval stays anchored to what the conversation was about. No extra LLM call."""
    if not history or not refers_back(message):
        return standalone
    rewritten = standalone.strip()
    if rewritten and _normalise(rewritten) != _normalise(message) and not refers_back(rewritten):
        return rewritten
    previous = next((m["content"] for m in reversed(history) if m.get("role") == "user" and m.get("content")), "")
    return f"{previous.strip()} {rewritten or message}".strip()


def answer_turn(video_id: str, message: str, history: list[dict], chunks=None, model=None, llm_client=None,
                standalone: str | None = None):
    """One transcript-answer turn: (standalone rewrite, retrieval query, RagAnswer).
    History must come from the active session only; it is used to resolve references, never as evidence.
    Pass `standalone` if the rewrite was already computed (avoids a second rewrite call)."""
    if standalone is None:
        standalone = contextualize_question(message, history, llm_client=llm_client)
    retrieval_query = build_retrieval_query(message, standalone, history)
    rag = answer_question(
        video_id, message, chunk_repo=chunks, model=model, llm_client=llm_client,
        history=history, retrieval_query=retrieval_query, interpreted=standalone,
    )
    return standalone, retrieval_query, rag


def source_to_dict(chunk: RetrievedChunk, youtube_url: str) -> dict:
    url = None
    if chunk.start_time is not None:
        sep = "&" if "?" in youtube_url else "?"
        url = f"{youtube_url}{sep}t={int(chunk.start_time)}s"
    return {
        "kind": "transcript",
        "topic": None,
        "chunk_id": chunk.chunk_id,
        "chunk_index": chunk.chunk_index,
        "content": chunk.content,
        "start_time": chunk.start_time,
        "end_time": chunk.end_time,
        "similarity": chunk.similarity,
        "timestamp_url": url,
    }


def chat(
    video_id: str,
    session_id: str,
    message: str,
    videos: VideoRepository,
    sessions: SessionRepository,
    messages: MessageRepository,
    chunks: ChunkRepository,
    model=None,
    llm_client=None,
    insights: InsightsRepository | None = None,
) -> ChatResult:
    message = (message or "").strip()
    if not message:
        raise AppError("EMPTY_MESSAGE", "Please enter a question.", 400)

    sessions.get_for_video(session_id, video_id)  # 404 / SESSION_VIDEO_MISMATCH
    video = videos.get(video_id)
    if video is None:
        raise AppError("VIDEO_NOT_FOUND", "The requested video does not exist.", 404)
    if video["processing_status"] != "completed":
        raise AppError("VIDEO_NOT_READY", "This video has not finished processing.", 409)

    history = messages.list_for_session(session_id, limit=HISTORY_MESSAGES)  # active session only
    standalone = contextualize_question(message, history, llm_client=llm_client)

    intent = route(message, standalone)
    if intent:  # whole-video question: stored Insights, no new LLM answer
        text, sources = _summary_answer(
            intent, video, videos, insights or InsightsRepository(), chunks, llm_client
        )
        rag, answer_type = RagAnswer(answer=text, sources=[], grounded=True), "summary"
    else:  # specific question: transcript answer with this session's history for references
        _, _, rag = answer_turn(video_id, message, history, chunks=chunks, model=model,
                                llm_client=llm_client, standalone=standalone)
        if rag.kind == "clarification":
            sources, answer_type = [dict(CLARIFICATION_SOURCE)], "clarification"
        else:
            sources = [source_to_dict(c, video["youtube_url"]) for c in rag.sources]
            answer_type = "retrieval"

    # Nothing is persisted until an answer exists, so failures leave no half-saved exchange.
    user_row = messages.add(session_id, "user", message)
    try:
        assistant_row = messages.add(session_id, "assistant", rag.answer, sources=sources)
    except Exception:
        try:  # don't leave an unanswered question in the history
            messages.delete(user_row["id"])
        except Exception:
            pass  # never hide the original error
        raise
    return ChatResult(standalone, rag, user_row, assistant_row, answer_type)
