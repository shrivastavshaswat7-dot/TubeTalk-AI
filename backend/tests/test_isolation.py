"""Multi-user isolation: sign-in on every API route, per-user libraries, sessions, messages and
insights, and reuse of the shared transcript + embeddings across users. In-memory repositories;
YouTube, the transcript service, embeddings and Groq are mocked."""
import json
import uuid
from types import SimpleNamespace as NS

import pytest
from fastapi.testclient import TestClient

from app.core import auth
from app.main import app
from app.prompts.insights import FINAL_SYSTEM_PROMPT
from app.schemas.transcript import Transcript, TranscriptSegment, VideoMetadata
from app.services import ingestion
from tests.fakes import (
    AUTH_A,
    AUTH_B,
    USER_A,
    USER_B,
    FakeChunkRepo,
    FakeInsightsRepo,
    FakeMessageRepo,
    FakeSessionRepo,
    FakeVideoRepo,
    install_overrides,
    new_id,
)

YT = "AAAAAAAAAAA"
URL = f"https://www.youtube.com/watch?v={YT}"
PUBLIC_PATHS = {"/", "/health"}

as_a = TestClient(app, headers=AUTH_A)
as_b = TestClient(app, headers=AUTH_B)
anonymous = TestClient(app)


@pytest.fixture
def env(monkeypatch):
    r = NS(videos=FakeVideoRepo(), sessions=FakeSessionRepo(), messages=FakeMessageRepo(),
           chunks=FakeChunkRepo(), insights=FakeInsightsRepo(),
           calls=NS(metadata=0, transcript=0, stored=0, prompts=[], insights=0))
    install_overrides(app, r)

    def fake_metadata(yt_id):
        r.calls.metadata += 1
        return VideoMetadata(yt_id, f"https://www.youtube.com/watch?v={yt_id}", f"Title {yt_id}", "Chan", "thumb")

    def fake_transcript(yt_id):  # a real lookup costs a FreeTranscriptAPI credit
        r.calls.transcript += 1
        segs = [TranscriptSegment(f"{yt_id} sentence {i} " + "word " * 12, i * 10.0, 9.0) for i in range(40)]
        return Transcript(yt_id, "en", False, segs)

    def fake_store(video_id, chunks, chunk_repo=None, model=None):  # embedding + storage
        r.calls.stored += 1
        return chunk_repo.insert_many(video_id, chunks, None)

    def fake_generate(system, user, llm=None):
        r.calls.prompts.append(user)
        if "standalone question" in system:
            return "REWRITTEN: " + user.split("Latest message:")[1].split("\n")[0].strip()
        if system == FINAL_SYSTEM_PROMPT:
            r.calls.insights += 1
            return json.dumps({"summary": f"Summary number {r.calls.insights}.", "key_takeaways": ["One."],
                               "topics": [{"name": "Intro", "timestamp": "00:05"}]})
        return "Grounded answer [C1]."

    monkeypatch.setattr(ingestion, "fetch_metadata", fake_metadata)
    monkeypatch.setattr(ingestion, "fetch_transcript", fake_transcript)
    monkeypatch.setattr(ingestion, "store_chunks", fake_store)
    monkeypatch.setattr("app.services.retrieval.embed_query", lambda q, model=None: [0.0] * 384)
    monkeypatch.setattr("app.services.llm.generate", fake_generate)
    yield r
    app.dependency_overrides.clear()


def process(client, url=URL):
    return client.post("/api/videos/process", json={"youtube_url": url})


def user_a_with_history(env):
    """User A processes a video, chats once and generates insights."""
    body = process(as_a).json()
    vid, sid = body["video"]["id"], body["session"]["id"]
    assert as_a.post("/api/chat", json={"video_id": vid, "session_id": sid,
                                        "message": "What is user A's secret question?"}).status_code == 200
    assert as_a.get(f"/api/videos/{vid}/insights").status_code == 200
    return vid, sid


# ---------------------------------------------------------------- sign-in required everywhere


def _api_operations():
    """Every (method, path) the app serves, from its own OpenAPI schema (generated from the routes)."""
    return [(method.upper(), path) for path, ops in app.openapi()["paths"].items() for method in ops]


def _requests_for_every_api_route():
    some = str(uuid.uuid4())
    return [
        pytest.param(method, path.replace("{video_id}", some).replace("{session_id}", some), id=f"{method} {path}")
        for method, path in _api_operations()
        if path not in PUBLIC_PATHS
    ]


@pytest.mark.parametrize("method,path", _requests_for_every_api_route())
def test_every_api_route_requires_sign_in(env, method, path):
    body = {"youtube_url": URL, "video_id": str(uuid.uuid4()), "session_id": str(uuid.uuid4()), "message": "hi"}
    for client in (anonymous, TestClient(app, headers={"Authorization": "Bearer not-a-real-token"})):
        r = client.request(method, path, params={"video_id": str(uuid.uuid4())}, json=body)
        assert r.status_code == 401 and r.json()["error"] == "AUTH_REQUIRED", (method, path, r.text)
    assert env.calls.transcript == 0 and env.messages.rows == [] and env.calls.prompts == []


def test_route_enumeration_is_complete():
    """Guard for the test above: new routes are picked up automatically, and only / and /health are public."""
    operations = _api_operations()
    assert PUBLIC_PATHS <= {path for _, path in operations}
    assert len(_requests_for_every_api_route()) == len(operations) - len(PUBLIC_PATHS) >= 15


def test_public_routes_still_work_without_sign_in():
    assert anonymous.get("/health").json()["status"] == "healthy"
    assert anonymous.get("/").status_code == 200


def test_real_token_check_is_wired_into_the_routes(monkeypatch):
    """No test override: the real dependency rejects a token Supabase does not accept."""
    def get_claims(token):
        raise ValueError("invalid")

    monkeypatch.setattr(auth, "get_client", lambda: NS(auth=NS(get_claims=get_claims)))
    app.dependency_overrides.clear()
    r = TestClient(app, headers={"Authorization": "Bearer forged"}).get("/api/videos")
    assert r.status_code == 401 and r.json()["error"] == "AUTH_REQUIRED"


# ---------------------------------------------------------------- user B can't reach user A's data


def _b_requests(vid, sid):
    return [
        ("GET", f"/api/videos/{vid}", None, None),
        ("GET", f"/api/videos/{vid}/sessions", None, None),
        ("POST", "/api/sessions", None, {"video_id": vid}),
        ("GET", f"/api/sessions/{sid}", {"video_id": vid}, None),
        ("GET", f"/api/sessions/{sid}/messages", {"video_id": vid}, None),
        ("DELETE", f"/api/sessions/{sid}", {"video_id": vid}, None),
        ("POST", "/api/chat", None, {"video_id": vid, "session_id": sid, "message": "Tell me A's chat"}),
        ("GET", f"/api/videos/{vid}/insights", None, None),
        ("GET", f"/api/videos/{vid}/insights", {"generate": "false"}, None),
        ("POST", f"/api/videos/{vid}/insights/regenerate", None, None),
        ("GET", f"/api/videos/{vid}/summary", None, None),
        ("GET", f"/api/videos/{vid}/takeaways", None, None),
        ("GET", f"/api/videos/{vid}/topics", None, None),
        ("GET", f"/api/videos/{vid}/suggestions", None, None),
    ]


def test_user_b_cannot_reach_any_of_user_a_data(env):
    vid, sid = user_a_with_history(env)
    a_messages = list(env.messages.rows)
    a_insights = dict(env.insights.store[USER_A][vid])
    prompts_before = len(env.calls.prompts)

    for method, path, params, body in _b_requests(vid, sid):
        r = as_b.request(method, path, params=params, json=body)
        assert r.status_code == 404, (method, path, r.status_code, r.text)
        assert r.json()["error"] in ("VIDEO_NOT_FOUND", "SESSION_NOT_FOUND"), (method, path)
        assert f"Title {YT}" not in r.text and "secret question" not in r.text

    assert as_b.get("/api/videos").json()["videos"] == []
    assert sid in env.sessions.rows  # B's delete did nothing
    assert env.messages.rows == a_messages  # B's chat wrote nothing
    assert env.insights.store[USER_A][vid] == a_insights  # B's regenerate did nothing
    assert env.insights.store.get(USER_B, {}) == {}
    assert len(env.calls.prompts) == prompts_before  # no Groq call on B's behalf


def test_another_users_video_looks_exactly_like_a_missing_one(env):
    vid, sid = user_a_with_history(env)
    missing = str(uuid.uuid4())
    for path in (f"/api/videos/{{}}", f"/api/videos/{{}}/insights", f"/api/videos/{{}}/sessions"):
        theirs, nothing = as_b.get(path.format(vid)), as_b.get(path.format(missing))
        assert (theirs.status_code, theirs.json()) == (nothing.status_code, nothing.json())
    theirs = as_b.get(f"/api/sessions/{sid}/messages", params={"video_id": vid})
    nothing = as_b.get(f"/api/sessions/{missing}/messages", params={"video_id": vid})
    assert (theirs.status_code, theirs.json()) == (nothing.status_code, nothing.json())


# ---------------------------------------------------------------- shared transcript + embeddings


def test_second_user_reuses_transcript_and_embeddings_without_learning_about_it(env):
    a = process(as_a).json()
    assert (env.calls.transcript, env.calls.stored) == (1, 1)
    chunks_before = list(env.chunks.by_video[a["video"]["id"]])

    b = process(as_b)
    assert b.status_code == 200
    b = b.json()
    assert b["video"]["id"] == a["video"]["id"]  # the same shared video row
    assert (env.calls.transcript, env.calls.stored, env.calls.metadata) == (1, 1, 1)  # no second lookup or embedding
    assert env.chunks.by_video[a["video"]["id"]] == chunks_before  # shared chunks untouched
    # Same response as for a brand-new video: nothing reveals that user A processed it first.
    assert b["reused"] is False and b["message"] == "Video processed successfully"
    assert b["session"]["id"] != a["session"]["id"]
    assert env.sessions.rows[b["session"]["id"]]["user_id"] == USER_B
    assert [v["id"] for v in as_b.get("/api/videos").json()["videos"]] == [a["video"]["id"]]

    again = process(as_b).json()  # now it is in B's own library
    assert again["reused"] is True and again["session"]["id"] == b["session"]["id"]


def test_both_users_chat_on_the_shared_video_with_separate_histories(env):
    vid, a_sid = user_a_with_history(env)
    b = process(as_b).json()
    b_sid = b["session"]["id"]

    sessions_b = as_b.get(f"/api/videos/{vid}/sessions").json()["sessions"]
    assert [s["id"] for s in sessions_b] == [b_sid]
    assert as_b.get(f"/api/sessions/{b_sid}/messages", params={"video_id": vid}).json()["messages"] == []

    start = len(env.calls.prompts)
    r = as_b.post("/api/chat", json={"video_id": vid, "session_id": b_sid, "message": "And what about that?"})
    assert r.status_code == 200 and r.json()["grounded"] is True
    assert all("secret question" not in p for p in env.calls.prompts[start:])  # A's history never used
    b_msgs = as_b.get(f"/api/sessions/{b_sid}/messages", params={"video_id": vid}).json()["messages"]
    assert [m["content"] for m in b_msgs if m["role"] == "user"] == ["And what about that?"]
    a_msgs = as_a.get(f"/api/sessions/{a_sid}/messages", params={"video_id": vid}).json()["messages"]
    assert all(m["content"] != "And what about that?" for m in a_msgs)


def test_insights_are_per_user_and_never_overwritten_across_users(env):
    vid, _ = user_a_with_history(env)
    a_summary = as_a.get(f"/api/videos/{vid}/summary").json()["summary"]
    process(as_b)

    b_first = as_b.get(f"/api/videos/{vid}/insights").json()
    assert b_first["cached"] is False  # B gets their own insights, not A's cached row
    b_summary = b_first["insights"]["summary"]
    assert b_summary != a_summary

    as_b.post(f"/api/videos/{vid}/insights/regenerate")
    assert as_a.get(f"/api/videos/{vid}/summary").json()["summary"] == a_summary  # A unaffected
    as_a.post(f"/api/videos/{vid}/insights/regenerate")
    b_after = as_b.get(f"/api/videos/{vid}/summary").json()["summary"]
    assert b_after != as_a.get(f"/api/videos/{vid}/summary").json()["summary"]
    assert set(env.insights.store) == {USER_A, USER_B}


# ---------------------------------------------------------------- legacy rows and libraries


def test_sessions_without_an_owner_are_invisible_to_everyone(env):
    vid = process(as_a).json()["video"]["id"]
    legacy = new_id()
    env.sessions.rows[legacy] = {"id": legacy, "video_id": vid, "session_title": "old", "user_id": None,
                                 "created_at": "2026-11-08T00:00:00+00:00", "updated_at": "2027-01-01T00:00:00+00:00"}
    for client in (as_a, as_b):
        assert legacy not in [s["id"] for s in client.get(f"/api/videos/{vid}/sessions").json().get("sessions", [])]
        assert client.get(f"/api/sessions/{legacy}/messages", params={"video_id": vid}).status_code == 404


def test_videos_list_contains_only_the_users_own_library(env):
    a_vid = process(as_a).json()["video"]["id"]
    b_vid = process(as_b, "https://youtu.be/BBBBBBBBBBB").json()["video"]["id"]
    assert [v["id"] for v in as_a.get("/api/videos").json()["videos"]] == [a_vid]
    assert [v["id"] for v in as_b.get("/api/videos").json()["videos"]] == [b_vid]


def test_a_failed_processing_attempt_adds_nothing_to_the_library(env, monkeypatch):
    from app.core.errors import AppError

    def no_captions(yt_id):
        raise AppError("TRANSCRIPT_UNAVAILABLE", "No captions.", 422)

    monkeypatch.setattr(ingestion, "fetch_transcript", no_captions)
    assert process(as_a).status_code == 422
    assert as_a.get("/api/videos").json()["videos"] == []
    assert env.sessions.rows == {}
