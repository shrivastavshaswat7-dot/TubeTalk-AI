"""Whole-video questions answered from stored Insights (no new LLM answer) with accurate sources."""
import json
from types import SimpleNamespace as NS

import pytest
from fastapi.testclient import TestClient

from app.api import deps
from app.core.config import get_settings
from app.core.errors import AppError
from app.main import app
from app.prompts.insights import FINAL_SYSTEM_PROMPT
from app.services.question_intent import OVERVIEW, POINTS, classify, route
from app.services.summary_answer import build_summary_answer, chunk_at
from tests.fakes import FakeChunkRepo, FakeInsightsRepo, FakeMessageRepo, FakeSessionRepo, FakeVideoRepo, new_id

URL = "https://www.youtube.com/watch?v=abcdefghijk"


# ── classifier ────────────────────────────────────────────────────────────────


@pytest.mark.parametrize("question,expected", [
    ("What is this video about?", OVERVIEW),
    ("what's it about", OVERVIEW),
    ("summary of the video", OVERVIEW),
    ("Summarise this video", OVERVIEW),
    ("Can you summarize it please?", OVERVIEW),
    ("Give me an overview", OVERVIEW),
    ("TL;DR", OVERVIEW),
    ("What topics are covered?", OVERVIEW),
    ("What does this video cover?", OVERVIEW),
    # statement word order (reported in the running app)
    ("what the video is about", OVERVIEW),
    ("what the video is about?", OVERVIEW),
    ("What this video is about?", OVERVIEW),
    ("Tell me what the video is about", OVERVIEW),
    ("what it is about", OVERVIEW),
    ("What is the video all about?", OVERVIEW),
    ("what's the video about", OVERVIEW),
    # ...but a subject left over still means a specific question
    ("what the video is about AI", None),
    ("what the video says about AI tools", None),
    ("does thiss video tell about AI?", None),
    ("What are the main points?", POINTS),
    ("key takeaways please", POINTS),
    # specific: stay on strict retrieval
    ("Summarise the part about pronunciation", None),
    ("What are the key points about AI tools?", None),
    ("What does the speaker conclude?", None),
    ("How can I stop being afraid of speaking English?", None),
    ("What does the video say about ChatGPT?", None),
    ("What is the speaker's name?", None),
    ("", None),
])
def test_classify(question, expected):
    assert classify(question) == expected


@pytest.mark.parametrize("message,standalone,expected", [
    # self-contained overview: classified as typed, even if the rewrite added subject words
    ("Give me an overview", "Give me an overview of the video about fear of speaking English", OVERVIEW),
    ("What is this video about?", "What is the video about overcoming fear?", OVERVIEW),
    # refers back: the rewritten question decides
    ("Summarise it", "Summarise the part about AI tools", None),
    ("Summarise it", "Summarise this video", OVERVIEW),
    ("What's this about?", "What is this video about?", OVERVIEW),
    ("What are its main points?", "What are the main points of the pronunciation tip?", None),
])
def test_route_uses_rewrite_only_for_references(message, standalone, expected):
    assert route(message, standalone) == expected


# ── answer builder ────────────────────────────────────────────────────────────

CHUNKS = [
    {"id": "c0", "chunk_index": 0, "content": "intro words", "start_time": 0.0, "end_time": 60.0},
    {"id": "c1", "chunk_index": 1, "content": "practice words", "start_time": 50.0, "end_time": 120.0},
    {"id": "c2", "chunk_index": 2, "content": "closing words", "start_time": 115.0, "end_time": 180.0},
]
INSIGHTS = {
    "status": "completed",
    "summary": "A video about practising English.",
    "key_takeaways": ["Practise daily.", "Use AI tools."],
    "topics": [
        {"name": "Intro", "start_time": 5.0},
        {"name": "Practice routine", "start_time": 55.0},  # inside c0 AND c1 (overlap) -> latest start: c1
        {"name": "No timestamp", "start_time": None},
        {"name": "Outside transcript", "start_time": 500.0},
    ],
    "model": "m",
    "generated_at": "2026-11-08T10:00:00+00:00",
}


def test_chunk_at_picks_containing_chunk_and_never_guesses():
    assert chunk_at(CHUNKS, 5)["id"] == "c0"
    assert chunk_at(CHUNKS, 55)["id"] == "c1"
    assert chunk_at(CHUNKS, 500) is None


def test_overview_answer_is_stored_text_with_only_verified_timestamps():
    answer, sources = build_summary_answer(OVERVIEW, INSIGHTS, CHUNKS, URL)
    assert answer.startswith("A video about practising English.")
    assert "- [00:05] Intro" in answer and "- [00:55] Practice routine" in answer
    assert "- No timestamp" in answer and "- Outside transcript" in answer  # listed, but no time
    assert "[08:20]" not in answer  # 500s is outside the transcript: no timestamp shown

    assert [s["kind"] for s in sources] == ["summary", "topic", "topic"]
    intro, practice = sources[1], sources[2]
    assert (intro["chunk_id"], intro["content"], intro["start_time"]) == ("c0", "intro words", 5.0)
    assert (practice["chunk_id"], practice["chunk_index"], practice["end_time"]) == ("c1", 1, 120.0)
    assert practice["timestamp_url"] == URL + "&t=55s"
    assert all(s["similarity"] is None for s in sources)  # not presented as similarity matches


def test_points_answer_lists_takeaways():
    answer, sources = build_summary_answer(POINTS, INSIGHTS, CHUNKS, URL)
    assert answer.startswith("**Key points**") and "- Practise daily." in answer and "- Use AI tools." in answer
    assert "A video about practising English." not in answer
    assert sources[0]["kind"] == "summary"


def test_no_valid_timestamps_still_answers_with_summary_source_only():
    insights = dict(INSIGHTS, topics=[{"name": "Only topic", "start_time": None}])
    answer, sources = build_summary_answer(OVERVIEW, insights, CHUNKS, URL)
    assert "- Only topic" in answer and [s["kind"] for s in sources] == ["summary"]


# ── chat API ──────────────────────────────────────────────────────────────────


@pytest.fixture
def env(monkeypatch):
    r = NS(videos=FakeVideoRepo(), sessions=FakeSessionRepo(), messages=FakeMessageRepo(),
           chunks=FakeChunkRepo(), insights=FakeInsightsRepo(), llm_calls=[], retrieval_calls=[])
    # Plain closures: a lambda with a default argument would be parsed by FastAPI as a query parameter.
    app.dependency_overrides[deps.get_video_repo] = lambda: r.videos
    app.dependency_overrides[deps.get_session_repo] = lambda: r.sessions
    app.dependency_overrides[deps.get_message_repo] = lambda: r.messages
    app.dependency_overrides[deps.get_chunk_repo] = lambda: r.chunks
    app.dependency_overrides[deps.get_insights_repo] = lambda: r.insights

    r.vid = new_id()
    r.videos.rows[r.vid] = {"id": r.vid, "youtube_video_id": "abcdefghijk", "youtube_url": URL,
                            "processing_status": "completed"}
    r.chunks.by_video[r.vid] = [dict(c) for c in CHUNKS]
    r.sid = r.sessions.create(r.vid)["id"]

    def fake_llm(system, user, llm=None):
        r.llm_calls.append(system)
        if system == FINAL_SYSTEM_PROMPT:  # insight generation
            return json.dumps({"summary": "Generated summary.", "key_takeaways": ["One."],
                               "topics": [{"name": "Intro", "timestamp": "00:05"}]})
        return "Specific grounded answer [00:05]."

    monkeypatch.setattr("app.services.llm.generate", fake_llm)
    monkeypatch.setattr("app.services.retrieval.embed_query",
                        lambda q, model=None: r.retrieval_calls.append(q) or [0.0] * 384)
    yield r
    app.dependency_overrides.clear()


client = TestClient(app)


def ask(env, text):
    return client.post("/api/chat", json={"video_id": env.vid, "session_id": env.sid, "message": text})


def seed_insights(env, **overrides):
    env.insights.rows[env.vid] = dict(INSIGHTS, video_id=env.vid, updated_at="2026-11-08T10:00:00+00:00", **overrides)


def test_broad_question_uses_cached_insights_without_llm_or_retrieval(env):
    seed_insights(env)
    r = ask(env, "What is this video about?")
    assert r.status_code == 200
    body = r.json()
    assert body["answer_type"] == "summary" and body["grounded"] is True
    assert body["answer"].startswith("A video about practising English.")
    assert [s["kind"] for s in body["sources"]] == ["summary", "topic", "topic"]
    assert body["sources"][1]["chunk_id"] == "c0" and body["sources"][1]["similarity"] is None
    assert env.llm_calls == [] and env.retrieval_calls == []  # no LLM answer, no similarity search
    history = env.messages.list_for_session(env.sid)
    assert history[1]["sources"][0]["kind"] == "summary"  # persisted with its sources


def test_points_question(env):
    seed_insights(env)
    body = ask(env, "What are the main points?").json()
    assert body["answer_type"] == "summary" and "- Practise daily." in body["answer"]


def test_missing_insights_generated_once_then_reused(env):
    first = ask(env, "Summarise this video").json()
    assert first["answer_type"] == "summary" and first["answer"].startswith("Generated summary.")
    assert env.llm_calls.count(FINAL_SYSTEM_PROMPT) == 1
    for _ in range(3):  # repeated broad questions reuse the cache
        assert ask(env, "Give me an overview").json()["answer_type"] == "summary"
    assert env.llm_calls.count(FINAL_SYSTEM_PROMPT) == 1


def test_summary_still_generating_is_a_distinct_loading_error(env):
    env.insights.mark_generating(env.vid)  # another request is generating right now
    r = ask(env, "What is this video about?")
    assert r.status_code == 409 and r.json()["error"] == "SUMMARY_GENERATING"
    assert env.messages.rows == [] and env.llm_calls == []  # nothing saved, no duplicate generation


def test_summary_generation_failure_is_distinct_from_a_refusal(env, monkeypatch):
    def failing(system, user, llm=None):
        raise AppError("LLM_ERROR", "down", 503)

    monkeypatch.setattr("app.services.llm.generate", failing)
    r = ask(env, "What is this video about?")
    assert r.status_code == 503 and r.json()["error"] == "SUMMARY_UNAVAILABLE"
    assert "overview question wasn't answered" in r.json()["message"]
    assert env.messages.rows == []  # never stored as if it were an answer or a refusal
    assert env.insights.rows[env.vid]["status"] == "failed"


def test_specific_question_still_uses_retrieval_with_unchanged_threshold(env):
    seed_insights(env)
    body = ask(env, "How do I practise speaking?").json()
    assert body["answer_type"] == "retrieval"
    assert env.retrieval_calls == ["How do I practise speaking?"]
    assert all(s["kind"] == "transcript" for s in body["sources"])
    assert get_settings().min_similarity == 0.25


def test_insights_generate_false_never_generates(env):
    r = client.get(f"/api/videos/{env.vid}/insights", params={"generate": "false"})
    assert r.status_code == 404 and r.json()["error"] == "INSIGHTS_NOT_READY"
    assert env.llm_calls == [] and env.vid not in env.insights.rows
    seed_insights(env)
    r = client.get(f"/api/videos/{env.vid}/insights", params={"generate": "false"})
    assert r.status_code == 200 and r.json()["cached"] is True


def test_statement_word_order_reaches_the_summary_path(env):
    """Regression: "what the video is about?" was sent to retrieval and refused in the running app."""
    seed_insights(env)
    body = ask(env, "what the video is about?").json()
    assert body["answer_type"] == "summary" and body["grounded"] is True
    assert body["answer"].startswith("A video about practising English.")
    assert env.retrieval_calls == [] and env.llm_calls == []
