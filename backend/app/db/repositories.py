"""Thin repositories over Supabase. These are the only code that touches the database.

Rows are returned as plain dicts. Any database failure becomes AppError DATABASE_ERROR.

Ownership: videos and transcript_chunks are shared, reusable content (one copy per YouTube video).
Everything private is reached through a repository bound to one user (`user_id=`): the library,
chat sessions (and so their messages) and insights. Those repositories filter every read and stamp
every write with that user, so another user's rows are simply never found.
"""
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Any

from app.core.errors import AppError
from app.db.client import get_client
from app.schemas.chunk import TranscriptChunk
from app.schemas.transcript import VideoMetadata

INSERT_BATCH_SIZE = 200


@contextmanager
def _db_errors():
    try:
        yield
    except AppError:
        raise
    except Exception:
        raise AppError("DATABASE_ERROR", "A database error occurred. Please try again.", 503)


def _first(response) -> dict[str, Any] | None:
    return response.data[0] if response.data else None


class VideoRepository:
    def __init__(self, client=None):
        self.client = client or get_client()

    def get(self, video_id: str) -> dict | None:
        with _db_errors():
            return _first(self.client.table("videos").select("*").eq("id", video_id).limit(1).execute())

    def get_by_youtube_id(self, youtube_video_id: str) -> dict | None:
        with _db_errors():
            return _first(
                self.client.table("videos")
                .select("*")
                .eq("youtube_video_id", youtube_video_id)
                .limit(1)
                .execute()
            )

    def upsert_from_metadata(self, meta: VideoMetadata, status: str = "pending") -> dict:
        """One shared record per YouTube video (single-user V1)."""
        row = {
            "youtube_video_id": meta.youtube_video_id,
            "youtube_url": meta.youtube_url,
            "title": meta.title,
            "channel_name": meta.channel_name,
            "thumbnail_url": meta.thumbnail_url,
            "processing_status": status,
            "error_message": None,
        }
        with _db_errors():
            return _first(
                self.client.table("videos").upsert(row, on_conflict="youtube_video_id").execute()
            )

    def update_status(
        self, video_id: str, status: str, error_message: str | None = None, language: str | None = None
    ) -> dict | None:
        values: dict[str, Any] = {"processing_status": status, "error_message": error_message}
        if language is not None:
            values["transcript_language"] = language
        with _db_errors():
            return _first(self.client.table("videos").update(values).eq("id", video_id).execute())

    def list_recent(self, limit: int = 20) -> list[dict]:
        with _db_errors():
            return (
                self.client.table("videos")
                .select("*")
                .order("updated_at", desc=True)
                .limit(limit)
                .execute()
                .data
            )


class LibraryRepository:
    """One user's video library (table user_videos)."""

    def __init__(self, client=None, *, user_id: str):
        self.client = client or get_client()
        self.user_id = user_id

    def has(self, video_id: str) -> bool:
        with _db_errors():
            return bool(
                self.client.table("user_videos").select("video_id")
                .eq("user_id", self.user_id).eq("video_id", video_id).limit(1).execute().data
            )

    def add(self, video_id: str) -> None:
        """Idempotent: adding a video that is already in the library changes nothing."""
        with _db_errors():
            self.client.table("user_videos").upsert(
                {"user_id": self.user_id, "video_id": video_id},
                on_conflict="user_id,video_id", ignore_duplicates=True,
            ).execute()

    def list_videos(self, limit: int = 20) -> list[dict]:
        """The user's videos, most recently added first (never ordered by other users' activity)."""
        with _db_errors():
            rows = (
                self.client.table("user_videos")
                .select("created_at, video:videos(*)")
                .eq("user_id", self.user_id)
                .order("created_at", desc=True)
                .limit(limit)
                .execute()
                .data
            )
        return [r["video"] for r in rows if r.get("video")]


class SessionRepository:
    """One user's chat sessions."""

    def __init__(self, client=None, *, user_id: str):
        self.client = client or get_client()
        self.user_id = user_id

    def create(self, video_id: str, title: str = "New Conversation") -> dict:
        with _db_errors():
            return _first(
                self.client.table("chat_sessions")
                .insert({"video_id": video_id, "session_title": title, "user_id": self.user_id})
                .execute()
            )

    def get(self, session_id: str) -> dict | None:
        with _db_errors():
            return _first(
                self.client.table("chat_sessions").select("*")
                .eq("id", session_id).eq("user_id", self.user_id).limit(1).execute()
            )

    def get_for_video(self, session_id: str, video_id: str) -> dict:
        """Isolation guard: the session must exist and belong to this video."""
        session = self.get(session_id)
        if session is None:
            raise AppError("SESSION_NOT_FOUND", "The requested chat session does not exist.", 404)
        if session["video_id"] != video_id:
            raise AppError(
                "SESSION_VIDEO_MISMATCH", "The session does not belong to the requested video.", 400
            )
        return session

    def list_for_video(self, video_id: str) -> list[dict]:
        with _db_errors():
            return (
                self.client.table("chat_sessions")
                .select("*")
                .eq("video_id", video_id)
                .eq("user_id", self.user_id)
                .order("updated_at", desc=True)
                .execute()
                .data
            )

    def delete(self, session_id: str) -> bool:
        """Deletes the session and (via cascade) its messages; never the video or chunks."""
        with _db_errors():
            return bool(
                self.client.table("chat_sessions").delete()
                .eq("id", session_id).eq("user_id", self.user_id).execute().data
            )


class MessageRepository:
    def __init__(self, client=None):
        self.client = client or get_client()

    def add(self, session_id: str, role: str, content: str, sources: list[dict] | None = None) -> dict:
        row = {"session_id": session_id, "role": role, "content": content, "sources": sources}
        with _db_errors():
            return _first(self.client.table("chat_messages").insert(row).execute())

    def delete(self, message_id: str) -> None:
        with _db_errors():
            self.client.table("chat_messages").delete().eq("id", message_id).execute()

    def list_for_session(self, session_id: str, limit: int | None = None) -> list[dict]:
        """Chronological messages of ONE session. With a limit, returns the most recent N."""
        with _db_errors():
            q = self.client.table("chat_messages").select("*").eq("session_id", session_id)
            if limit is None:
                return q.order("created_at").execute().data
            rows = q.order("created_at", desc=True).limit(limit).execute().data
            return list(reversed(rows))


class ChunkRepository:
    def __init__(self, client=None):
        self.client = client or get_client()

    def insert_many(
        self, video_id: str, chunks: list[TranscriptChunk], embeddings: list[list[float]] | None = None
    ) -> int:
        if embeddings is not None and len(embeddings) != len(chunks):
            raise ValueError("embeddings and chunks must have the same length")
        rows = [
            {
                "video_id": video_id,
                "chunk_index": c.chunk_index,
                "content": c.content,
                "start_time": c.start_time,
                "end_time": c.end_time,
                "embedding": embeddings[i] if embeddings is not None else None,
            }
            for i, c in enumerate(chunks)
        ]
        with _db_errors():
            for i in range(0, len(rows), INSERT_BATCH_SIZE):
                self.client.table("transcript_chunks").insert(rows[i : i + INSERT_BATCH_SIZE]).execute()
        return len(rows)

    def delete_for_video(self, video_id: str) -> None:
        with _db_errors():
            self.client.table("transcript_chunks").delete().eq("video_id", video_id).execute()

    def list_for_video(self, video_id: str) -> list[dict]:
        """All chunks of one video in transcript order (paginated)."""
        page, rows, start = 1000, [], 0
        with _db_errors():
            while True:
                batch = (
                    self.client.table("transcript_chunks")
                    .select("id,chunk_index,content,start_time,end_time")
                    .eq("video_id", video_id)
                    .order("chunk_index")
                    .range(start, start + page - 1)
                    .execute()
                    .data
                )
                rows.extend(batch)
                if len(batch) < page:
                    return rows
                start += page

    def count_for_video(self, video_id: str) -> int:
        with _db_errors():
            r = (
                self.client.table("transcript_chunks")
                .select("id", count="exact")
                .eq("video_id", video_id)
                .limit(1)
                .execute()
            )
            return r.count or 0

    def match(self, video_id: str, query_embedding: list[float], k: int = 5) -> list[dict]:
        """Similarity search; the SQL function always filters by video_id."""
        if not video_id:
            raise ValueError("video_id is required for retrieval")
        with _db_errors():
            return self.client.rpc(
                "match_transcript_chunks",
                {"p_video_id": video_id, "query_embedding": query_embedding, "match_count": k},
            ).execute().data


class InsightsRepository:
    """One user's cached insights, one row per (user, video) (table user_video_insights). The legacy
    shared table video_insights is no longer used by the app; it is kept for the backfill."""

    TABLE = "user_video_insights"
    CONFLICT = "user_id,video_id"

    def __init__(self, client=None, *, user_id: str):
        self.client = client or get_client()
        self.user_id = user_id

    def get(self, video_id: str) -> dict | None:
        with _db_errors():
            return _first(
                self.client.table(self.TABLE).select("*")
                .eq("user_id", self.user_id).eq("video_id", video_id).limit(1).execute()
            )

    def mark_generating(self, video_id: str) -> None:
        """Only touches status/error, so previously generated content survives a regeneration."""
        with _db_errors():
            self.client.table(self.TABLE).upsert(
                {"user_id": self.user_id, "video_id": video_id, "status": "generating", "error_message": None},
                on_conflict=self.CONFLICT,
            ).execute()

    def save_completed(
        self, video_id: str, summary: str, key_takeaways: list[str], topics: list[dict], model: str
    ) -> dict:
        row = {
            "user_id": self.user_id,
            "video_id": video_id,
            "status": "completed",
            "summary": summary,
            "key_takeaways": key_takeaways,
            "topics": topics,
            "model": model,
            "error_message": None,
            "generated_at": datetime.now(timezone.utc).isoformat(),
        }
        with _db_errors():
            return _first(self.client.table(self.TABLE).upsert(row, on_conflict=self.CONFLICT).execute())

    def save_failed(self, video_id: str, message: str) -> None:
        """A failed regeneration keeps the previous completed insights; a first failure is 'failed'."""
        existing = self.get(video_id)
        status = "completed" if existing and existing.get("summary") else "failed"
        with _db_errors():
            self.client.table(self.TABLE).upsert(
                {"user_id": self.user_id, "video_id": video_id, "status": status, "error_message": message},
                on_conflict=self.CONFLICT,
            ).execute()
