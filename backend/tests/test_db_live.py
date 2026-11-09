"""Live checks against a real Supabase project. Skipped unless backend/.env is configured.

Uses a throwaway video (random YouTube ID) and deletes it afterwards (cascade).
"""
import uuid

import pytest

from app.core.config import get_settings
from app.core.errors import AppError
from app.db.repositories import ChunkRepository, MessageRepository, SessionRepository, VideoRepository
from app.schemas.chunk import TranscriptChunk
from app.schemas.transcript import VideoMetadata

_s = get_settings()
pytestmark = pytest.mark.skipif(
    not (_s.supabase_url and _s.supabase_key), reason="Supabase credentials not configured"
)


def unit_vec(i: int) -> list[float]:
    v = [0.0] * 384
    v[i] = 1.0
    return v


@pytest.fixture
def two_videos():
    videos = VideoRepository()
    made = []
    for _ in range(2):
        yt = "T" + uuid.uuid4().hex[:10]
        made.append(
            videos.upsert_from_metadata(VideoMetadata(yt, f"https://www.youtube.com/watch?v={yt}", "t"))
        )
    yield made
    for v in made:
        videos.client.table("videos").delete().eq("id", v["id"]).execute()


def test_end_to_end_isolation(two_videos):
    a, b = two_videos
    sessions, messages, chunks = SessionRepository(), MessageRepository(), ChunkRepository()

    # chunks: A has axes 0/1, B has axis 0 only -> a query on axis 0 must never return B's data for A
    chunks.insert_many(a["id"], [TranscriptChunk(0, "A zero", 0, 5), TranscriptChunk(1, "A one", 5, 9)],
                       [unit_vec(0), unit_vec(1)])
    chunks.insert_many(b["id"], [TranscriptChunk(0, "B zero", 0, 5)], [unit_vec(0)])
    hits_a = chunks.match(a["id"], unit_vec(0), k=5)
    assert [h["content"] for h in hits_a] == ["A zero", "A one"]
    assert hits_a[0]["similarity"] == pytest.approx(1.0)
    assert [h["content"] for h in chunks.match(b["id"], unit_vec(0), k=5)] == ["B zero"]

    # sessions: guard rejects cross-video use
    sa = sessions.create(a["id"])
    sessions.get_for_video(sa["id"], a["id"])
    with pytest.raises(AppError) as exc:
        sessions.get_for_video(sa["id"], b["id"])
    assert exc.value.error == "SESSION_VIDEO_MISMATCH"

    # messages: order + sources persisted; deleting the session keeps video and chunks
    messages.add(sa["id"], "user", "q?")
    messages.add(sa["id"], "assistant", "a.", sources=[{"start_time": 1.5, "content": "A zero"}])
    msgs = messages.list_for_session(sa["id"])
    assert [m["role"] for m in msgs] == ["user", "assistant"]
    assert msgs[1]["sources"][0]["start_time"] == 1.5
    assert sessions.delete(sa["id"]) is True
    assert messages.list_for_session(sa["id"]) == []
    assert chunks.count_for_video(a["id"]) == 2
