"""In-memory repositories for API tests. They subclass the real repositories and override only
the primitive DB calls, so higher-level logic (e.g. the session/video isolation guard) is the
real production code.

Per-user repositories (library, sessions, insights) are bound to one user like the real ones; their
storage is shared, and `for_user()` returns another user's view of the same storage, so tests can
check that one user never sees another user's rows. Requests sign in with AUTH_A / AUTH_B."""
import itertools
from datetime import datetime, timezone

from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.api import deps
from app.core import auth
from app.core.errors import AppError
from app.db.repositories import (
    ChunkRepository,
    InsightsRepository,
    LibraryRepository,
    MessageRepository,
    SessionRepository,
    VideoRepository,
)

USER_A = "aaaaaaaa-0000-4000-8000-00000000000a"
USER_B = "bbbbbbbb-0000-4000-8000-00000000000b"
_TOKENS = {"token-a": USER_A, "token-b": USER_B}
AUTH_A = {"Authorization": "Bearer token-a"}
AUTH_B = {"Authorization": "Bearer token-b"}

_ids = itertools.count(1)


def fake_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(HTTPBearer(auto_error=False)),
) -> auth.CurrentUser:
    """Stands in for Supabase token verification: only the two test tokens are valid."""
    user_id = _TOKENS.get(credentials.credentials) if credentials else None
    if user_id is None:
        raise AppError("AUTH_REQUIRED", "Please sign in to continue.", 401)
    return auth.CurrentUser(id=user_id)


def install_overrides(app, r) -> None:
    """Route the app's dependencies to the in-memory repositories in `r` (an object with any of
    videos / sessions / messages / chunks / insights), bound to the signed-in test user. Adds
    r.library if missing. Undo with app.dependency_overrides.clear()."""
    if not hasattr(r, "library"):
        r.library = FakeLibraryRepo(r.videos)
    app.dependency_overrides[auth.get_current_user] = fake_current_user

    def library(user: auth.CurrentUser = Depends(auth.get_current_user)):
        return r.library.for_user(user.id)

    def sessions(user: auth.CurrentUser = Depends(auth.get_current_user)):
        return r.sessions.for_user(user.id)

    def insights(user: auth.CurrentUser = Depends(auth.get_current_user)):
        return r.insights.for_user(user.id)

    app.dependency_overrides[deps.get_video_repo] = lambda: r.videos
    app.dependency_overrides[deps.get_library_repo] = library
    if hasattr(r, "sessions"):
        app.dependency_overrides[deps.get_session_repo] = sessions
    if hasattr(r, "messages"):
        app.dependency_overrides[deps.get_message_repo] = lambda: r.messages
    if hasattr(r, "chunks"):
        app.dependency_overrides[deps.get_chunk_repo] = lambda: r.chunks
    if hasattr(r, "insights"):
        app.dependency_overrides[deps.get_insights_repo] = insights


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


class FakeLibraryRepo(LibraryRepository):
    def __init__(self, videos: FakeVideoRepo, user_id=USER_A, store=None):
        self.videos, self.user_id = videos, user_id
        self.store: dict[str, list[str]] = store if store is not None else {}  # user -> video ids, oldest first

    def for_user(self, user_id):
        return FakeLibraryRepo(self.videos, user_id, self.store)

    def has(self, video_id):
        return video_id in self.store.get(self.user_id, [])

    def add(self, video_id):
        ids = self.store.setdefault(self.user_id, [])
        if video_id not in ids:
            ids.append(video_id)

    def list_videos(self, limit=20):
        return [self.videos.rows[v] for v in reversed(self.store.get(self.user_id, []))][:limit]


class FakeSessionRepo(SessionRepository):
    def __init__(self, user_id=USER_A, rows=None):
        self.user_id = user_id
        self.rows: dict[str, dict] = rows if rows is not None else {}  # all users' sessions

    def for_user(self, user_id):
        return FakeSessionRepo(user_id, self.rows)

    def create(self, video_id, title="New Conversation"):
        row = {"id": new_id(), "video_id": video_id, "session_title": title, "user_id": self.user_id,
               "created_at": now(), "updated_at": now()}
        self.rows[row["id"]] = row
        return row

    def get(self, session_id):
        row = self.rows.get(session_id)
        return row if row and row.get("user_id") == self.user_id else None

    def list_for_video(self, video_id):
        rows = [r for r in self.rows.values() if r["video_id"] == video_id and r.get("user_id") == self.user_id]
        return sorted(rows, key=lambda r: r["updated_at"], reverse=True)

    def delete(self, session_id):
        if self.get(session_id) is None:
            return False
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
        assert self.row["user_id"] == self.repo.user_id  # every write is stamped with its owner
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
        assert on_conflict == InsightsRepository.CONFLICT
        return _UpsertQuery(self.repo, row)


class _FakeInsightsClient:
    def __init__(self, repo):
        self.repo = repo

    def table(self, name):
        assert name == InsightsRepository.TABLE  # per-user table, never the legacy shared one
        return _FakeTable(self.repo)


class FakeInsightsRepo(InsightsRepository):
    """Real mark_generating/save_completed/save_failed logic over an in-memory per-user table.
    `rows` holds this user's rows by video id; `store` holds every user's."""

    def __init__(self, user_id=USER_A, store=None):
        self.user_id = user_id
        self.store: dict[str, dict[str, dict]] = store if store is not None else {}
        self.rows: dict[str, dict] = self.store.setdefault(user_id, {})
        self.client = _FakeInsightsClient(self)

    def for_user(self, user_id):
        return FakeInsightsRepo(user_id, self.store)

    def get(self, video_id):
        return self.rows.get(video_id)
