"""API tests with in-memory repositories; YouTube, embeddings and Groq are mocked."""
from types import SimpleNamespace as NS
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from app.core.errors import AppError
from app.main import app
from app.schemas.chunk import TranscriptChunk
from app.schemas.transcript import Transcript, TranscriptSegment, VideoMetadata
from app.services import chat as chat_service
from app.services import ingestion
from tests.fakes import (
    AUTH_A,
    FakeChunkRepo,
    FakeInsightsRepo,
    FakeMessageRepo,
    FakeSessionRepo,
    FakeVideoRepo,
    install_overrides,
)

VID_A = "AAAAAAAAAAA"
VID_B = "BBBBBBBBBBB"
URL_A = f"https://www.youtube.com/watch?v={VID_A}"
URL_B = f"https://youtu.be/{VID_B}"


@pytest.fixture
def env(monkeypatch):
    repos = NS(videos=FakeVideoRepo(), sessions=FakeSessionRepo(), messages=FakeMessageRepo(),
               chunks=FakeChunkRepo(), insights=FakeInsightsRepo())
    install_overrides(app, repos)

    calls = NS(metadata=0, transcript=0, llm=[])
    repos.calls = calls

    def fake_metadata(yt_id):
        calls.metadata += 1
        return VideoMetadata(yt_id, f"https://www.youtube.com/watch?v={yt_id}", f"Title {yt_id}", "Chan", "thumb")

    def fake_transcript(yt_id):
        calls.transcript += 1
        segs = [TranscriptSegment(f"{yt_id} sentence {i} " + "word " * 12, i * 10.0, 9.0) for i in range(40)]
        return Transcript(yt_id, "en", False, segs)

    def fake_store(video_id, chunks, chunk_repo=None, model=None):
        return chunk_repo.insert_many(video_id, chunks, None)

    monkeypatch.setattr(ingestion, "fetch_metadata", fake_metadata)
    monkeypatch.setattr(ingestion, "fetch_transcript", fake_transcript)
    monkeypatch.setattr(ingestion, "store_chunks", fake_store)

    # Retrieval: skip the embedding model (the fake chunk repo ignores the vector).
    monkeypatch.setattr("app.services.retrieval.embed_query", lambda q, model=None: [0.0] * 384)

    def fake_generate(system, user, llm=None):
        calls.llm.append((system, user))
        if "standalone question" in system:  # contextualisation call
            return "REWRITTEN: " + user.split("Latest message:")[1].split("\n")[0].strip()
        return "Grounded answer [00:00]."

    monkeypatch.setattr("app.services.llm.generate", fake_generate)
    yield repos
    app.dependency_overrides.clear()


client = TestClient(app, headers=AUTH_A)


def process(url):
    r = client.post("/api/videos/process", json={"youtube_url": url})
    return r


def start(env, url=URL_A):
    body = process(url).json()
    return body["video"]["id"], body["session"]["id"]


# ---------------------------------------------------------------- processing


def test_process_new_video_creates_chunks_and_default_session(env):
    r = process(URL_A)
    assert r.status_code == 200
    body = r.json()
    assert body["success"] and body["reused"] is False
    assert body["video"]["processing_status"] == "completed"
    assert body["video"]["title"] == f"Title {VID_A}" and body["video"]["transcript_language"] == "en"
    assert env.chunks.count_for_video(body["video"]["id"]) > 0
    assert body["session"]["video_id"] == body["video"]["id"]


def test_reprocessing_reuses_without_duplicating_chunks(env):
    first = process(URL_A).json()
    n_chunks = env.chunks.count_for_video(first["video"]["id"])
    second = process(f"https://youtu.be/{VID_A}").json()  # different URL form, same video
    assert second["reused"] is True
    assert second["video"]["id"] == first["video"]["id"]
    assert second["session"]["id"] == first["session"]["id"]
    assert env.chunks.count_for_video(first["video"]["id"]) == n_chunks
    assert env.calls.transcript == 1 and env.calls.metadata == 1  # no second fetch
    assert len(env.sessions.rows) == 1


def test_invalid_url(env):
    r = process("https://example.com/x")
    assert r.status_code == 400 and r.json()["error"] == "INVALID_VIDEO_URL"


def test_missing_url_field_is_validation_error(env):
    r = client.post("/api/videos/process", json={})
    assert r.status_code == 422 and r.json()["error"] == "VALIDATION_ERROR"


def test_transcript_unavailable_marks_status_and_creates_no_session(env, monkeypatch):
    def boom(yt_id):
        raise AppError("TRANSCRIPT_UNAVAILABLE", "Captions are disabled for this video.", 422)

    monkeypatch.setattr(ingestion, "fetch_transcript", boom)
    r = process(URL_A)
    assert r.status_code == 422 and r.json()["error"] == "TRANSCRIPT_UNAVAILABLE"
    row = env.videos.get_by_youtube_id(VID_A)
    assert row["processing_status"] == "transcript_unavailable" and row["error_message"]
    assert env.sessions.rows == {} and env.chunks.by_video == {}


def test_unexpected_failure_marks_failed_without_leaking(env, monkeypatch):
    monkeypatch.setattr(ingestion, "store_chunks", MagicMock(side_effect=RuntimeError("secret db host")))
    r = process(URL_A)
    assert r.status_code == 500 and r.json()["error"] == "PROCESSING_FAILED"
    assert "secret" not in r.text
    assert env.videos.get_by_youtube_id(VID_A)["processing_status"] == "failed"


def test_failed_video_can_be_retried(env, monkeypatch):
    monkeypatch.setattr(ingestion, "store_chunks", MagicMock(side_effect=RuntimeError("x")))
    assert process(URL_A).status_code == 500
    monkeypatch.setattr(ingestion, "store_chunks", lambda v, c, chunk_repo=None, model=None: chunk_repo.insert_many(v, c, None))
    r = process(URL_A)
    assert r.status_code == 200 and r.json()["reused"] is False


def test_failure_to_mark_completed_does_not_leave_video_processing(env, monkeypatch):
    real_update = env.videos.update_status

    def update(video_id, status, error_message=None, language=None):
        if status == "completed":
            raise AppError("DATABASE_ERROR", "A database error occurred.", 503)
        return real_update(video_id, status, error_message=error_message, language=language)

    monkeypatch.setattr(env.videos, "update_status", update)
    r = process(URL_A)
    assert r.status_code == 503 and r.json()["error"] == "DATABASE_ERROR"
    assert env.videos.get_by_youtube_id(VID_A)["processing_status"] == "failed"  # re-submittable at once


def test_concurrent_processing_is_rejected_but_stale_is_retried(env):
    process(URL_A)
    row = env.videos.get_by_youtube_id(VID_A)
    row["processing_status"] = "processing"
    r = process(URL_A)
    assert r.status_code == 409 and r.json()["error"] == "VIDEO_PROCESSING"
    row["updated_at"] = "2020-01-01T00:00:00+00:00"  # crashed long ago
    assert process(URL_A).status_code == 200


# ---------------------------------------------------------------- videos


def test_get_and_list_videos(env):
    vid, _ = start(env)
    assert client.get(f"/api/videos/{vid}").json()["video"]["youtube_video_id"] == VID_A
    assert len(client.get("/api/videos").json()["videos"]) == 1
    r = client.get("/api/videos/00000000-0000-4000-8000-999999999999")
    assert r.status_code == 404 and r.json()["error"] == "VIDEO_NOT_FOUND"
    assert client.get("/api/videos/not-a-uuid").status_code == 422


# ---------------------------------------------------------------- sessions


def test_create_and_list_sessions_for_video(env):
    vid, default = start(env)
    r = client.post("/api/sessions", json={"video_id": vid, "session_title": "Exam prep"})
    assert r.status_code == 201 and r.json()["session"]["session_title"] == "Exam prep"
    listed = client.get(f"/api/videos/{vid}/sessions").json()["sessions"]
    assert {s["id"] for s in listed} == {default, r.json()["session"]["id"]}


def test_create_session_unknown_or_unready_video(env):
    r = client.post("/api/sessions", json={"video_id": "00000000-0000-4000-8000-999999999999"})
    assert r.status_code == 404 and r.json()["error"] == "VIDEO_NOT_FOUND"
    vid, _ = start(env)
    env.videos.rows[vid]["processing_status"] = "failed"
    assert client.post("/api/sessions", json={"video_id": vid}).json()["error"] == "VIDEO_NOT_READY"


def test_sessions_only_list_their_own_video(env):
    va, sa = start(env, URL_A)
    vb, sb = start(env, URL_B)
    assert [s["id"] for s in client.get(f"/api/videos/{va}/sessions").json()["sessions"]] == [sa]
    assert [s["id"] for s in client.get(f"/api/videos/{vb}/sessions").json()["sessions"]] == [sb]


def test_session_ownership_enforced_on_every_session_route(env):
    va, sa = start(env, URL_A)
    vb, _ = start(env, URL_B)
    for method, path in [
        ("get", f"/api/sessions/{sa}?video_id={vb}"),
        ("get", f"/api/sessions/{sa}/messages?video_id={vb}"),
        ("delete", f"/api/sessions/{sa}?video_id={vb}"),
    ]:
        r = getattr(client, method)(path)
        assert r.status_code == 400 and r.json()["error"] == "SESSION_VIDEO_MISMATCH", path
    assert sa in env.sessions.rows  # the mismatched delete did nothing
    assert client.get(f"/api/sessions/{sa}?video_id={va}").status_code == 200


def test_session_route_requires_video_id_and_valid_session(env):
    va, sa = start(env)
    assert client.get(f"/api/sessions/{sa}").status_code == 422  # video_id missing
    r = client.get(f"/api/sessions/00000000-0000-4000-8000-999999999999?video_id={va}")
    assert r.status_code == 404 and r.json()["error"] == "SESSION_NOT_FOUND"


def test_delete_session_keeps_video_chunks_and_removes_session(env):
    vid, sid = start(env)
    assert client.delete(f"/api/sessions/{sid}?video_id={vid}").json()["success"]
    assert sid not in env.sessions.rows
    assert env.videos.get(vid) is not None and env.chunks.count_for_video(vid) > 0


# ---------------------------------------------------------------- chat


def chat(vid, sid, msg):
    return client.post("/api/chat", json={"video_id": vid, "session_id": sid, "message": msg})


def test_chat_persists_messages_and_sources_with_timestamps(env):
    vid, sid = start(env)
    r = chat(vid, sid, "What is said?")
    assert r.status_code == 200
    body = r.json()
    assert body["grounded"] and body["answer"] == "Grounded answer [00:00]."
    assert body["sources"] and body["sources"][0]["timestamp_url"].endswith("t=0s")
    assert body["standalone_question"] == "What is said?"  # no history -> unchanged

    history = client.get(f"/api/sessions/{sid}/messages?video_id={vid}").json()["messages"]
    assert [m["role"] for m in history] == ["user", "assistant"]
    assert history[1]["sources"][0]["start_time"] == 0.0  # sources survive a reload
    assert history[0]["sources"] is None


def test_followup_uses_history_for_contextualisation(env):
    vid, sid = start(env)
    chat(vid, sid, "What is deep learning?")
    r = chat(vid, sid, "What are its applications?")
    assert r.json()["standalone_question"] == "REWRITTEN: What are its applications?"
    ctx_system, ctx_user = [c for c in env.calls.llm if "standalone question" in c[0]][0]
    assert "What is deep learning?" in ctx_user and "Grounded answer" in ctx_user


def test_first_message_makes_no_contextualisation_call(env):
    vid, sid = start(env)
    chat(vid, sid, "Hello?")
    assert not any("standalone question" in s for s, _ in env.calls.llm)


def test_history_is_never_mixed_across_sessions_or_videos(env):
    va, s1 = start(env, URL_A)
    s2 = client.post("/api/sessions", json={"video_id": va}).json()["session"]["id"]
    vb, s3 = start(env, URL_B)
    chat(va, s1, "SECRET-QUESTION-ONE about topic")
    # Second session of the same video and a different video must not see session 1's text.
    chat(va, s2, "Another question")
    chat(vb, s3, "Question for video B")
    chat(vb, s3, "Follow up for video B")
    for sid, vid in [(s2, va), (s3, vb)]:
        msgs = client.get(f"/api/sessions/{sid}/messages?video_id={vid}").json()["messages"]
        assert all("SECRET-QUESTION-ONE" not in m["content"] for m in msgs)
    # No contextualisation prompt (which carries history) may contain session 1's text.
    assert "SECRET-QUESTION-ONE" not in " ".join(u for s, u in env.calls.llm if "standalone question" in s)
    assert len(client.get(f"/api/sessions/{s1}/messages?video_id={va}").json()["messages"]) == 2


def test_retrieval_is_scoped_to_the_active_video(env):
    va, sa = start(env, URL_A)
    vb, sb = start(env, URL_B)
    r = chat(vb, sb, "anything")
    assert all(VID_B in s["content"] for s in r.json()["sources"])
    assert not any(VID_A in s["content"] for s in r.json()["sources"])


def test_chat_rejects_session_from_another_video(env):
    va, sa = start(env, URL_A)
    vb, _ = start(env, URL_B)
    r = chat(vb, sa, "hi")
    assert r.status_code == 400 and r.json()["error"] == "SESSION_VIDEO_MISMATCH"
    assert env.messages.rows == []  # nothing persisted


@pytest.mark.parametrize("msg", ["", "   \n "])
def test_chat_empty_message(env, msg):
    vid, sid = start(env)
    r = chat(vid, sid, msg)
    assert r.status_code == 400 and r.json()["error"] == "EMPTY_MESSAGE"
    assert env.messages.rows == []


def test_chat_message_too_long(env):
    vid, sid = start(env)
    assert chat(vid, sid, "x" * 2001).status_code == 422


def test_chat_unknown_session_and_invalid_ids(env):
    vid, _ = start(env)
    r = chat(vid, "00000000-0000-4000-8000-999999999999", "hi")
    assert r.status_code == 404 and r.json()["error"] == "SESSION_NOT_FOUND"
    assert client.post("/api/chat", json={"video_id": "x", "session_id": "y", "message": "hi"}).status_code == 422


def test_chat_video_not_ready(env):
    vid, sid = start(env)
    env.videos.rows[vid]["processing_status"] = "failed"
    r = chat(vid, sid, "hi")
    assert r.status_code == 409 and r.json()["error"] == "VIDEO_NOT_READY"


def test_ungrounded_question_is_persisted_with_empty_sources(env, monkeypatch):
    vid, sid = start(env)
    env.chunks.by_video[vid] = []  # nothing retrievable
    r = chat(vid, sid, "Unrelated?")
    assert r.json()["grounded"] is False and r.json()["sources"] == []
    msgs = client.get(f"/api/sessions/{sid}/messages?video_id={vid}").json()["messages"]
    assert [m["role"] for m in msgs] == ["user", "assistant"] and msgs[1]["sources"] == []


def test_llm_failure_returns_error_and_persists_nothing(env, monkeypatch):
    vid, sid = start(env)

    def failing(system, user, llm=None):
        raise AppError("LLM_RATE_LIMITED", "The language model is busy right now. Please try again shortly.", 429)

    monkeypatch.setattr("app.services.llm.generate", failing)
    r = chat(vid, sid, "hi")
    assert r.status_code == 429 and r.json()["error"] == "LLM_RATE_LIMITED"
    assert env.messages.rows == []


def test_failed_answer_write_leaves_no_unanswered_question(env, monkeypatch):
    vid, sid = start(env)
    real_add = env.messages.add

    def add(session_id, role, content, sources=None):
        if role == "assistant":
            raise AppError("DATABASE_ERROR", "A database error occurred.", 503)
        return real_add(session_id, role, content, sources)

    monkeypatch.setattr(env.messages, "add", add)
    r = chat(vid, sid, "hi")
    assert r.status_code == 503 and r.json()["error"] == "DATABASE_ERROR"
    assert env.messages.rows == []  # the user's message was removed again


def test_contextualisation_failure_falls_back_to_original_question(env, monkeypatch):
    vid, sid = start(env)
    chat(vid, sid, "First question")

    def flaky(system, user, llm=None):
        if "standalone question" in system:
            raise AppError("LLM_ERROR", "x", 503)
        return "Answer."

    monkeypatch.setattr("app.services.llm.generate", flaky)
    r = chat(vid, sid, "And then?")
    assert r.status_code == 200 and r.json()["standalone_question"] == "And then?"


@pytest.mark.parametrize(
    "model_output,expected",
    [
        ('"What are the applications of deep learning?"', "What are the applications of deep learning?"),
        ("Line one\nLine two (model rambled)", "its applications?"),  # multi-line -> fall back
        ("x" * 3000, "its applications?"),  # absurdly long -> fall back
    ],
)
def test_contextualiser_sanitises_model_output(monkeypatch, model_output, expected):
    monkeypatch.setattr("app.services.llm.generate", lambda s, u, llm=None: model_output)
    history = [{"role": "user", "content": "What is deep learning?"}]
    assert chat_service.contextualize_question("its applications?", history) == expected


def test_contextualiser_skips_llm_without_history(monkeypatch):
    spy = MagicMock()
    monkeypatch.setattr("app.services.llm.generate", spy)
    assert chat_service.contextualize_question("hello?", []) == "hello?"
    spy.assert_not_called()
