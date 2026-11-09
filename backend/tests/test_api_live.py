"""End-to-end through the real HTTP API: real YouTube, embeddings, Supabase and Groq.

Skipped unless Groq and Supabase are configured. Uses two real public videos and removes
only rows it created (it refuses to run if either video is already in the database).
"""
import pytest
from fastapi.testclient import TestClient

from app.core.config import get_settings
from app.db.repositories import ChunkRepository, VideoRepository
from app.main import app

_s = get_settings()


def _set(v: str) -> bool:
    return bool(v) and "your_" not in v


pytestmark = pytest.mark.skipif(
    not (_set(_s.groq_api_key) and _set(_s.groq_model) and _set(_s.supabase_url) and _set(_s.supabase_key)),
    reason="Groq and Supabase credentials not configured",
)

ZOO = "jNQXAC9IVRw"  # "Me at the zoo": elephants with long trunks
RICK = "dQw4w9WgXcQ"  # song lyrics, nothing about elephants


@pytest.fixture
def api():
    videos = VideoRepository()
    if any(videos.get_by_youtube_id(y) for y in (ZOO, RICK)):
        pytest.skip("test videos already exist in the database; refusing to touch real data")
    client = TestClient(app)
    yield client
    for y in (ZOO, RICK):
        row = videos.get_by_youtube_id(y)
        if row:
            videos.client.table("videos").delete().eq("id", row["id"]).execute()


def test_full_flow_with_follow_up_and_isolation(api):
    chunks = ChunkRepository()

    # --- process two videos
    zoo = api.post("/api/videos/process", json={"youtube_url": f"https://www.youtube.com/watch?v={ZOO}"}).json()
    rick = api.post("/api/videos/process", json={"youtube_url": f"https://youtu.be/{RICK}"}).json()
    assert zoo["success"] and rick["success"] and not zoo["reused"]
    zid, zsid = zoo["video"]["id"], zoo["session"]["id"]
    rid, rsid = rick["video"]["id"], rick["session"]["id"]
    assert zoo["video"]["title"] == "Me at the zoo"

    # --- reuse: same video again does not duplicate chunks
    n = chunks.count_for_video(zid)
    again = api.post("/api/videos/process", json={"youtube_url": f"https://youtu.be/{ZOO}"}).json()
    assert again["reused"] and again["video"]["id"] == zid and again["session"]["id"] == zsid
    assert chunks.count_for_video(zid) == n

    # --- grounded answer with sources, then a follow-up that needs history
    r1 = api.post("/api/chat", json={"video_id": zid, "session_id": zsid,
                                     "message": "What animals are in front of the speaker?"}).json()
    assert r1["success"] and r1["grounded"] and "elephant" in r1["answer"].lower()
    assert r1["sources"] and r1["sources"][0]["timestamp_url"].startswith("https://www.youtube.com/watch?v=" + ZOO)

    r2 = api.post("/api/chat", json={"video_id": zid, "session_id": zsid,
                                     "message": "What is cool about them?"}).json()
    assert r2["success"] and r2["grounded"]
    assert r2["standalone_question"] != "What is cool about them?"  # rewritten using history
    assert "elephant" in r2["standalone_question"].lower()
    assert "trunk" in r2["answer"].lower()

    # --- persisted history, with sources
    msgs = api.get(f"/api/sessions/{zsid}/messages", params={"video_id": zid}).json()["messages"]
    assert [m["role"] for m in msgs] == ["user", "assistant", "user", "assistant"]
    assert msgs[1]["sources"] and msgs[1]["sources"][0]["start_time"] is not None

    # --- isolation: the other video's session is empty and its transcript knows nothing about elephants
    assert api.get(f"/api/sessions/{rsid}/messages", params={"video_id": rid}).json()["messages"] == []
    r3 = api.post("/api/chat", json={"video_id": rid, "session_id": rsid,
                                     "message": "What is cool about elephants' trunks?"}).json()
    assert r3["success"] and r3["grounded"] is False and r3["sources"] == []

    # --- ownership guard over real HTTP
    bad = api.post("/api/chat", json={"video_id": rid, "session_id": zsid, "message": "hi"})
    assert bad.status_code == 400 and bad.json()["error"] == "SESSION_VIDEO_MISMATCH"
    bad2 = api.get(f"/api/sessions/{zsid}/messages", params={"video_id": rid})
    assert bad2.status_code == 400

    # --- a second session on the same video starts with no history
    s2 = api.post("/api/sessions", json={"video_id": zid, "session_title": "Second"}).json()["session"]
    assert api.get(f"/api/sessions/{s2['id']}/messages", params={"video_id": zid}).json()["messages"] == []
    assert len(api.get(f"/api/videos/{zid}/sessions").json()["sessions"]) == 2

    # --- deleting a session leaves the video and its chunks
    assert api.delete(f"/api/sessions/{s2['id']}", params={"video_id": zid}).json()["success"]
    assert chunks.count_for_video(zid) == n
