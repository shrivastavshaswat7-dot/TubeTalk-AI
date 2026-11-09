"""Basic semantic retrieval: store chunk embeddings and search within ONE video."""
from app.core.config import get_settings
from app.core.errors import AppError
from app.db.repositories import ChunkRepository
from app.schemas.chunk import RetrievedChunk, TranscriptChunk
from app.services.embeddings import embed_query, embed_texts


def store_chunks(
    video_id: str,
    chunks: list[TranscriptChunk],
    chunk_repo: ChunkRepository | None = None,
    model=None,
) -> int:
    """Embed chunks in batches and store them. Replaces any existing chunks for the video,
    and removes partial data if anything fails, so a video never has half a transcript."""
    if not chunks:
        raise AppError("TRANSCRIPT_UNAVAILABLE", "There is no transcript content to store.", 422)
    repo = chunk_repo or ChunkRepository()
    embeddings = embed_texts([c.content for c in chunks], model=model)  # fail before touching the DB
    try:
        repo.delete_for_video(video_id)
        return repo.insert_many(video_id, chunks, embeddings)
    except Exception:
        try:
            repo.delete_for_video(video_id)
        except Exception:
            pass
        raise


def retrieve(
    video_id: str,
    question: str,
    top_k: int | None = None,
    chunk_repo: ChunkRepository | None = None,
    model=None,
) -> list[RetrievedChunk]:
    """Top-k most similar chunks of the given video, best first. May return an empty list."""
    if not video_id:
        raise AppError("INVALID_VIDEO_ID", "A video is required for retrieval.", 400)
    if not question or not question.strip():
        raise AppError("EMPTY_MESSAGE", "Please enter a question.", 400)
    k = top_k or get_settings().top_k
    repo = chunk_repo or ChunkRepository()
    rows = repo.match(video_id, embed_query(question, model=model), k)
    return [
        RetrievedChunk(
            chunk_id=r["id"],
            chunk_index=r["chunk_index"],
            content=r["content"],
            start_time=r["start_time"],
            end_time=r["end_time"],
            similarity=float(r["similarity"]),
        )
        for r in rows
    ]
