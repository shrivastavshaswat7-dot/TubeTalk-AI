"""Insights end to end through the real HTTP API: real YouTube, Supabase and Groq.

Skipped unless Groq/Supabase are configured AND database/migrations/002_video_insights.sql has been
applied. Uses one short public video; refuses to run if it is already in the database.
"""
import uuid

import pytest
from fastapi.testclient import TestClient

from app.core.config import get_settings
from app.core.errors import AppError
from app.db.repositories import InsightsRepository, VideoRepository
from app.main import app
from app.services import llm

_s = get_settings()


def _set(v: str) -> bool:
    return bool(v) and "your_" not in v


pytestmark = pytest.mark.skipif(
    not (_set(_s.groq_api_key) and _set(_s.groq_model) and _set(_s.supabase_url) and _set(_s.supabase_key)),
    reason="Groq and Supabase credentials not configured",
)

ZOO = "jNQXAC9IVRw"  # "Me at the zoo": 19 seconds, elephants


@pytest.fixture
def api(monkeypatch):
    try:
        InsightsRepository().get(str(uuid.uuid4()))
    except AppError:
        pytest.skip("video_insights table missing: run database/migrations/002_video_insights.sql")
    videos = VideoRepository()
    if videos.get_by_youtube_id(ZOO):
        pytest.skip("test video already exists in the database; refusing to touch real data")

    calls = []
    real = llm.generate
    monkeypatch.setattr(llm, "generate", lambda s, u, llm=None: calls.append(s) or real(s, u, llm=llm))
    client = TestClient(app)
    client.llm_calls = calls
    yield client
    row = videos.get_by_youtube_id(ZOO)
    if row:
        videos.client.table("videos").delete().eq("id", row["id"]).execute()  # cascades to insights


def test_insights_generated_cached_regenerated_and_cleaned_up(api):
    video = api.post("/api/videos/process", json={"youtube_url": f"https://youtu.be/{ZOO}"}).json()["video"]
    vid = video["id"]

    first = api.get(f"/api/videos/{vid}/insights")
    assert first.status_code == 200, first.text
    body = first.json()
    assert body["cached"] is False
    ins = body["insights"]
    assert "elephant" in ins["summary"].lower()
    assert ins["key_takeaways"] and all(isinstance(t, str) for t in ins["key_takeaways"])
    assert ins["topics"] and all(t["name"] for t in ins["topics"])
    for t in ins["topics"]:
        if t["start_time"] is not None:  # timestamps must be real positions inside the video
            assert 0 <= t["start_time"] <= 25
            assert t["timestamp_url"] == f"https://www.youtube.com/watch?v={ZOO}&t={int(t['start_time'])}s"
    assert ins["model"] == _s.groq_model and ins["generated_at"]

    # persisted in Supabase
    stored = InsightsRepository().get(vid)
    assert stored["status"] == "completed" and stored["summary"] == ins["summary"]

    # cached: summary/takeaways/topics endpoints reuse it with NO new LLM calls
    n = len(api.llm_calls)
    s = api.get(f"/api/videos/{vid}/summary").json()
    t = api.get(f"/api/videos/{vid}/takeaways").json()
    p = api.get(f"/api/videos/{vid}/topics").json()
    assert s["cached"] and t["cached"] and p["cached"]
    assert s["summary"] == ins["summary"] and t["key_takeaways"] == ins["key_takeaways"]
    assert len(api.llm_calls) == n

    # regeneration produces a fresh, valid result and replaces the stored row
    again = api.post(f"/api/videos/{vid}/insights/regenerate")
    assert again.status_code == 200 and again.json()["cached"] is False
    assert len(api.llm_calls) > n
    assert InsightsRepository().get(vid)["status"] == "completed"

    # deleting the video cascades to its insights
    VideoRepository().client.table("videos").delete().eq("id", vid).execute()
    assert InsightsRepository().get(vid) is None
