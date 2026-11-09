"""Topic starter questions are shown only if they pass normal retrieval at the global threshold."""
from types import SimpleNamespace as NS

import pytest
from fastapi.testclient import TestClient

from app.api import deps
from app.core.config import get_settings
from app.main import app
from app.schemas.chunk import RetrievedChunk
from app.services import suggestions as sug
from app.services.suggestions import topic_question, validated_suggestions
from tests.fakes import FakeChunkRepo, FakeInsightsRepo, FakeMessageRepo, FakeSessionRepo, FakeVideoRepo, new_id

URL = "https://www.youtube.com/watch?v=abcdefghijk"


def topics(*names):
    return [{"name": n, "start_time": float(i * 10)} for i, n in enumerate(names)]


@pytest.fixture
def env(monkeypatch):
    r = NS(videos=FakeVideoRepo(), insights=FakeInsightsRepo(), chunks=FakeChunkRepo(),
           messages=FakeMessageRepo(), sessions=FakeSessionRepo(), llm_calls=[], retrieved=[])
    r.vid = new_id()
    r.videos.rows[r.vid] = {"id": r.vid, "youtube_video_id": "abcdefghijk", "youtube_url": URL,
                            "processing_status": "completed"}
    r.chunks.by_video[r.vid] = [{"id": "c0", "chunk_index": 0, "content": "text", "start_time": 0.0, "end_time": 30.0}]

    def seed(*names):
        r.insights.rows[r.vid] = {"video_id": r.vid, "status": "completed", "summary": "S", "key_takeaways": ["T"],
                                  "topics": topics(*names), "updated_at": "2026-11-08T10:00:00+00:00"}

    r.seed = seed
    monkeypatch.setattr("app.services.llm.generate", lambda *a, **k: r.llm_calls.append(a) or "x")
    return r


def score_by_question(monkeypatch, env, scores: dict[str, float]):
    """Control retrieval scores per question; record every retrieval call."""
    def fake_retrieve(video_id, question, top_k=None, chunk_repo=None, model=None):
        env.retrieved.append((video_id, question, top_k))
        s = scores.get(question)
        return [] if s is None else [RetrievedChunk("c0", 0, "text", 0.0, 30.0, s)]

    monkeypatch.setattr(sug, "retrieve", fake_retrieve)


def run(env, video_id=None):
    return validated_suggestions(video_id or env.vid, env.videos, env.insights, env.chunks)


def q(name):
    return topic_question(name)


def test_topic_question_wording():
    assert q("Three-step practice routine.") == "What does the video say about three-step practice routine?"
    assert q("AI tools") == "What does the video say about AI tools?"  # acronym kept
    assert q("  ") is None and q(None) is None


def test_only_passing_suggestions_are_returned_in_topic_order(env, monkeypatch):
    env.seed("Fear", "Routine", "AI tools", "Pauses")
    score_by_question(monkeypatch, env, {q("Fear"): 0.46, q("Routine"): 0.12, q("AI tools"): 0.32, q("Pauses"): 0.30})
    result, ready = run(env)
    assert ready is True
    assert result == [q("Fear"), q("AI tools"), q("Pauses")]  # "Routine" rejected
    assert all(vid == env.vid and k == 1 for vid, _, k in env.retrieved)  # video-scoped, top match only


def test_at_most_three_and_stops_early(env, monkeypatch):
    env.seed("A", "B", "C", "D", "E")
    score_by_question(monkeypatch, env, {q(n): 0.9 for n in "ABCDE"})
    result, _ = run(env)
    assert result == [q("A"), q("B"), q("C")]
    assert len(env.retrieved) == 3  # no wasted searches after three passed


def test_rejected_suggestions_are_never_returned(env, monkeypatch):
    env.seed("Routine", "No match at all")
    score_by_question(monkeypatch, env, {q("Routine"): 0.2})  # second has no hits at all
    assert run(env) == ([], True)


def test_threshold_is_the_global_one_and_inclusive(env, monkeypatch):
    assert get_settings().min_similarity == 0.25
    env.seed("Exactly", "Just below")
    score_by_question(monkeypatch, env, {q("Exactly"): 0.25, q("Just below"): 0.2499})
    assert run(env)[0] == [q("Exactly")]


def test_zero_topics_or_insights_missing_never_generates(env, monkeypatch):
    score_by_question(monkeypatch, env, {})
    assert run(env) == ([], False)  # no insights stored
    assert env.vid not in env.insights.rows and env.llm_calls == [] and env.retrieved == []
    env.insights.mark_generating(env.vid)
    assert run(env) == ([], False)  # being generated elsewhere: still no generation, no wait
    env.seed()  # completed but no topics
    assert run(env) == ([], True)


def test_isolation_through_the_real_retrieval_pipeline(env, monkeypatch):
    """Video B has matching transcript; video A has none. A's suggestions must not use B's chunks."""
    monkeypatch.setattr("app.services.retrieval.embed_query", lambda text, model=None: [0.0] * 384)
    vid_b = new_id()
    env.videos.rows[vid_b] = dict(env.videos.rows[env.vid], id=vid_b)
    env.chunks.by_video[vid_b] = env.chunks.by_video.pop(env.vid)  # only B has transcript chunks
    env.seed("Fear")
    env.insights.rows[vid_b] = dict(env.insights.rows[env.vid], video_id=vid_b)
    assert run(env) == ([], True)  # A: nothing retrievable, so nothing suggested
    assert run(env, vid_b) == ([q("Fear")], True)  # B: FakeChunkRepo scores its own chunks 0.9


def test_validation_is_read_only(env, monkeypatch):
    env.seed("Fear")
    score_by_question(monkeypatch, env, {q("Fear"): 0.5})
    before = dict(env.insights.rows[env.vid])
    run(env)
    assert env.insights.rows[env.vid] == before and env.messages.rows == [] and env.llm_calls == []


# ── endpoint ──────────────────────────────────────────────────────────────────

client = TestClient(app)


@pytest.fixture
def api(env):
    app.dependency_overrides[deps.get_video_repo] = lambda: env.videos
    app.dependency_overrides[deps.get_insights_repo] = lambda: env.insights
    app.dependency_overrides[deps.get_chunk_repo] = lambda: env.chunks
    yield env
    app.dependency_overrides.clear()


def test_endpoint_returns_validated_suggestions(api, monkeypatch):
    api.seed("Fear", "Routine")
    score_by_question(monkeypatch, api, {q("Fear"): 0.4, q("Routine"): 0.1})
    body = client.get(f"/api/videos/{api.vid}/suggestions").json()
    assert body == {"success": True, "video_id": api.vid, "insights_ready": True, "suggestions": [q("Fear")]}


def test_endpoint_without_insights_and_unknown_video(api, monkeypatch):
    score_by_question(monkeypatch, api, {})
    body = client.get(f"/api/videos/{api.vid}/suggestions").json()
    assert body["insights_ready"] is False and body["suggestions"] == []
    assert api.vid not in api.insights.rows  # not generated
    r = client.get("/api/videos/00000000-0000-4000-8000-999999999999/suggestions")
    assert r.status_code == 404 and r.json()["error"] == "VIDEO_NOT_FOUND"
