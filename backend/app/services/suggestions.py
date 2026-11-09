"""Starter questions built from a video's Insights topics, shown only if they would actually work.

Each candidate is checked with the normal retrieval pipeline (same embedding model, video-scoped
search, the global MIN_SIMILARITY threshold) and kept only if at least one transcript chunk scores
at or above the threshold. No LLM call, never generates Insights, never writes anything.
"""
from app.core.config import get_settings
from app.core.errors import AppError
from app.db.repositories import ChunkRepository, InsightsRepository, VideoRepository
from app.services import insights as insights_service
from app.services.retrieval import retrieve

MAX_SUGGESTIONS = 3


def topic_question(name: str | None) -> str | None:
    name = (name or "").strip().rstrip(".?!").strip()
    if not name:
        return None
    if not (len(name) > 1 and name[1].isupper()):  # keep acronyms like "AI tools" intact
        name = name[0].lower() + name[1:]
    return f"What does the video say about {name}?"


def validated_suggestions(
    video_id: str,
    videos: VideoRepository,
    insights: InsightsRepository,
    chunks: ChunkRepository,
    model=None,
    limit: int = MAX_SUGGESTIONS,
) -> tuple[list[str], bool]:
    """Return (questions that pass retrieval, insights_ready). Read-only."""
    try:
        row, _ = insights_service.get_or_generate(video_id, videos, insights, chunks, generate=False)
    except AppError as exc:
        if exc.error in ("INSIGHTS_NOT_READY", "INSIGHTS_GENERATING"):
            return [], False  # nothing to suggest yet; generation is never triggered from here
        raise

    threshold = get_settings().min_similarity
    passing: list[str] = []
    for topic in row.get("topics") or []:
        question = topic_question(topic.get("name"))
        if not question or question in passing:
            continue
        hits = retrieve(video_id, question, top_k=1, chunk_repo=chunks, model=model)
        if hits and hits[0].similarity >= threshold:
            passing.append(question)
            if len(passing) >= limit:
                break
    return passing, True
