"""API tests for the insights endpoints (in-memory repositories, mocked LLM)."""
import json
from types import SimpleNamespace as NS

import pytest
from fastapi.testclient import TestClient

from app.api import deps
from app.core.errors import AppError
from app.main import app
from tests.fakes import FakeChunkRepo, FakeInsightsRepo, FakeVideoRepo, new_id

URL = "https://www.youtube.com/watch?v=abcdefghijk"
FINAL = {
    "summary": "This video explains neural networks.",
    "key_takeaways": ["Neurons hold numbers", "Layers transform activations"],
    "topics": [{"name": "Neurons", "timestamp": "00:30"}, {"name": "Layers", "timestamp": "02:00"}, {"name": "Oops", "timestamp": "99:00"}],
}


@pytest.fixture
def env(monkeypatch):
    r = NS(videos=FakeVideoRepo(), insights=FakeInsightsRepo(), chunks=FakeChunkRepo(), llm_calls=[])
    app.dependency_overrides[deps.get_video_repo] = lambda: r.videos
    app.dependency_overrides[deps.get_insights_repo] = lambda: r.insights
    app.dependency_overrides[deps.get_chunk_repo] = lambda: r.chunks

    r.vid = new_id()
    r.videos.rows[r.vid] = {"id": r.vid, "youtube_video_id": "abcdefghijk", "youtube_url": URL,
                            "processing_status": "completed", "title": "T"}
    r.chunks.by_video[r.vid] = [
        {"id": new_id(), "chunk_index": i, "content": f"content {i}", "start_time": i * 60.0, "end_time": i * 60.0 + 55}
        for i in range(4)
    ]

    def fake_generate(system, user, llm=None):
        r.llm_calls.append(system)
        return json.dumps(FINAL)

    monkeypatch.setattr("app.services.llm.generate", fake_generate)
    yield r
    app.dependency_overrides.clear()


client = TestClient(app)


def test_get_insights_generates_then_serves_cache(env):
    first = client.get(f"/api/videos/{env.vid}/insights").json()
    assert first["success"] and first["cached"] is False and first["video_id"] == env.vid
    ins = first["insights"]
    assert ins["summary"] == FINAL["summary"] and ins["key_takeaways"] == FINAL["key_takeaways"]
    assert ins["generated_at"]
    second = client.get(f"/api/videos/{env.vid}/insights").json()
    assert second["cached"] is True and second["insights"]["summary"] == ins["summary"]
    assert len(env.llm_calls) == 1  # generated once


def test_topics_have_timestamps_and_links_and_bad_timestamps_become_null(env):
    topics = client.get(f"/api/videos/{env.vid}/topics").json()["topics"]
    assert topics[0] == {"name": "Neurons", "start_time": 30.0, "timestamp": "00:30", "timestamp_url": URL + "&t=30s"}
    assert topics[1]["timestamp"] == "02:00" and topics[1]["timestamp_url"].endswith("t=120s")
    assert topics[2] == {"name": "Oops", "start_time": None, "timestamp": None, "timestamp_url": None}


def test_summary_and_takeaways_endpoints(env):
    s = client.get(f"/api/videos/{env.vid}/summary").json()
    assert s["success"] and s["summary"] == FINAL["summary"] and s["cached"] is False
    t = client.get(f"/api/videos/{env.vid}/takeaways").json()
    assert t["key_takeaways"] == FINAL["key_takeaways"] and t["cached"] is True
    assert len(env.llm_calls) == 1  # the three endpoints share one cached generation


def test_regenerate_forces_new_generation(env):
    client.get(f"/api/videos/{env.vid}/insights")
    r = client.post(f"/api/videos/{env.vid}/insights/regenerate")
    assert r.status_code == 200 and r.json()["cached"] is False
    assert len(env.llm_calls) == 2


def test_failed_regeneration_returns_error_but_get_still_serves_old_insights(env, monkeypatch):
    client.get(f"/api/videos/{env.vid}/insights")

    def failing(system, user, llm=None):
        raise AppError("LLM_ERROR", "Unable to generate a response at the moment.", 503)

    monkeypatch.setattr("app.services.llm.generate", failing)
    r = client.post(f"/api/videos/{env.vid}/insights/regenerate")
    assert r.status_code == 503 and r.json() == {
        "success": False, "error": "LLM_ERROR", "message": "Unable to generate a response at the moment."}
    again = client.get(f"/api/videos/{env.vid}/summary").json()
    assert again["cached"] is True and again["summary"] == FINAL["summary"]


def test_first_generation_failure_is_an_error_and_retried_later(env, monkeypatch):
    monkeypatch.setattr("app.services.llm.generate", lambda s, u, llm=None: "not json")
    r = client.get(f"/api/videos/{env.vid}/summary")
    assert r.status_code == 500 and r.json()["error"] == "INSIGHTS_FAILED"
    assert env.insights.rows[env.vid]["status"] == "failed"
    monkeypatch.setattr("app.services.llm.generate", lambda s, u, llm=None: json.dumps(FINAL))
    assert client.get(f"/api/videos/{env.vid}/summary").status_code == 200


def test_rate_limit_error_is_passed_through(env, monkeypatch):
    def limited(system, user, llm=None):
        raise AppError("LLM_RATE_LIMITED", "The language model is busy right now. Please try again shortly.", 429)

    monkeypatch.setattr("app.services.llm.generate", limited)
    monkeypatch.setattr("app.services.insights.RATE_LIMIT_WAITS", ())  # no waiting in tests
    r = client.get(f"/api/videos/{env.vid}/insights")
    assert r.status_code == 429 and r.json()["error"] == "LLM_RATE_LIMITED"


def test_generation_in_progress_returns_409(env):
    env.insights.mark_generating(env.vid)
    r = client.get(f"/api/videos/{env.vid}/summary")
    assert r.status_code == 409 and r.json()["error"] == "INSIGHTS_GENERATING"


@pytest.mark.parametrize("path", ["insights", "summary", "takeaways", "topics"])
def test_unknown_video_and_invalid_id(env, path):
    r = client.get(f"/api/videos/00000000-0000-4000-8000-999999999999/{path}")
    assert r.status_code == 404 and r.json()["error"] == "VIDEO_NOT_FOUND"
    assert client.get(f"/api/videos/not-a-uuid/{path}").status_code == 422


def test_unprocessed_video_is_not_ready(env):
    env.videos.rows[env.vid]["processing_status"] = "failed"
    r = client.get(f"/api/videos/{env.vid}/insights")
    assert r.status_code == 409 and r.json()["error"] == "VIDEO_NOT_READY"
    assert env.llm_calls == []


def test_insights_are_per_video(env):
    other = new_id()
    env.videos.rows[other] = {"id": other, "youtube_video_id": "zzzzzzzzzzz", "youtube_url": "https://www.youtube.com/watch?v=zzzzzzzzzzz",
                              "processing_status": "completed"}
    env.chunks.by_video[other] = [{"id": new_id(), "chunk_index": 0, "content": "other", "start_time": 0.0, "end_time": 5.0}]
    client.get(f"/api/videos/{env.vid}/insights")
    assert other not in env.insights.rows
    assert client.get(f"/api/videos/{other}/insights").json()["cached"] is False
    assert len(env.llm_calls) == 2


def test_regenerate_requires_post(env):
    assert client.get(f"/api/videos/{env.vid}/insights/regenerate").status_code in (404, 405)
