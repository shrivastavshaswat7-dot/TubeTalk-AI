"""In-memory repositories for API tests. They subclass the real repositories and override only
the primitive DB calls, so higher-level logic (e.g. the session/video isolation guard) is the
real production code."""
import itertools
from datetime import datetime, timezone

from app.db.repositories import (
    ChunkRepository,
    InsightsRepository,
    MessageRepository,
    SessionRepository,
    VideoRepository,
)

_ids = itertools.count(1)


def new_id() -> str:
    return f"00000000-0000-4000-8000-{next(_ids):012d}"


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


class FakeVideoRepo(VideoRepository):
    def __init__(self):
        self.rows: dict[str, dict] = {}

    def get(self, video_id):
        return self.rows.get(video_id)

    def get_by_youtube_id(self, youtube_video_id):
        return next((r for r in self.rows.values() if r["youtube_video_id"] == youtube_video_id), None)

    def upsert_from_metadata(self, meta, status="pending"):
        row = self.get_by_youtube_id(meta.youtube_video_id)
        if row is None:
            row = {"id": new_id(), "created_at": now(), "transcript_language": None}
            self.rows[row["id"]] = row
        row.update(
            youtube_video_id=meta.youtube_video_id, youtube_url=meta.youtube_url, title=meta.title,
            channel_name=meta.channel_name, thumbnail_url=meta.thumbnail_url,
            processing_status=status, error_message=None, updated_at=now(),
        )
        return row

    def update_status(self, video_id, status, error_message=None, language=None):
        row = self.rows[video_id]
        row.update(processing_status=status, error_message=error_message, updated_at=now())
        if language is not None:
            row["transcript_language"] = language
        return row

    def list_recent(self, limit=20):
        return list(self.rows.values())[:limit]


class FakeSessionRepo(SessionRepository):
    def __init__(self):
        self.rows: dict[str, dict] = {}

    def create(self, video_id, title="New Conversation"):
        row = {"id": new_id(), "video_id": video_id, "session_title": title,
               "created_at": now(), "updated_at": now()}
        self.rows[row["id"]] = row
        return row

    def get(self, session_id):
        return self.rows.get(session_id)

    def list_for_video(self, video_id):
        rows = [r for r in self.rows.values() if r["video_id"] == video_id]
        return sorted(rows, key=lambda r: r["updated_at"], reverse=True)

    def delete(self, session_id):
        return self.rows.pop(session_id, None) is not None


class FakeMessageRepo(MessageRepository):
    def __init__(self):
        self.rows: list[dict] = []

    def add(self, session_id, role, content, sources=None):
        row = {"id": new_id(), "session_id": session_id, "role": role, "content": content,
               "sources": sources, "created_at": now()}
        self.rows.append(row)
        return row

    def delete(self, message_id):
        self.rows = [r for r in self.rows if r["id"] != message_id]

    def list_for_session(self, session_id, limit=None):
        rows = [r for r in self.rows if r["session_id"] == session_id]
        return rows[-limit:] if limit else rows


class FakeChunkRepo(ChunkRepository):
    def __init__(self):
        self.by_video: dict[str, list[dict]] = {}

    def insert_many(self, video_id, chunks, embeddings=None):
        self.by_video.setdefault(video_id, []).extend(
            {"id": new_id(), "chunk_index": c.chunk_index, "content": c.content,
             "start_time": c.start_time, "end_time": c.end_time} for c in chunks
        )
        return len(chunks)

    def delete_for_video(self, video_id):
        self.by_video.pop(video_id, None)

    def list_for_video(self, video_id):
        return sorted(self.by_video.get(video_id, []), key=lambda c: c["chunk_index"])

    def count_for_video(self, video_id):
        return len(self.by_video.get(video_id, []))

    def match(self, video_id, query_embedding, k=5):
        # Only ever returns the requested video's chunks (like the real RPC).
        return [{**c, "similarity": 0.9 - 0.01 * i} for i, c in enumerate(self.by_video.get(video_id, [])[:k])]


class _Result:
    def __init__(self, data):
        self.data = data


class _UpsertQuery:
    def __init__(self, repo, row):
        self.repo, self.row = repo, row

    def execute(self):
        # Like PostgREST merge-duplicates: only the provided columns change on an existing row.
        existing = self.repo.rows.setdefault(
            self.row["video_id"],
            {"status": "generating", "summary": None, "key_takeaways": None,
             "topics": None, "model": None, "generated_at": None},
        )
        existing.update(self.row, updated_at=now())
        return _Result([existing])


class _FakeTable:
    def __init__(self, repo):
        self.repo = repo

    def upsert(self, row, on_conflict=None):
        return _UpsertQuery(self.repo, row)


class _FakeInsightsClient:
    def __init__(self, repo):
        self.repo = repo

    def table(self, name):
        assert name == "video_insights"
        return _FakeTable(self.repo)


class FakeInsightsRepo(InsightsRepository):
    """Real mark_generating/save_completed/save_failed logic over an in-memory table."""

    def __init__(self):
        self.rows: dict[str, dict] = {}
        self.client = _FakeInsightsClient(self)

    def get(self, video_id):
        return self.rows.get(video_id)
