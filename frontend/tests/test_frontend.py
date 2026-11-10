"""Frontend tests. UI tests use streamlit.testing.v1.AppTest with api_client functions monkeypatched
(no network). Fixture data mirrors real backend responses, including full-length (~800 char)
excerpts and the same chunk cited by two answers, which used to crash the UI.

Run:  cd frontend ; python -m pytest tests -q
"""
from pathlib import Path

import pytest
import requests
from streamlit.testing.v1 import AppTest

import api_client
import auth
from api_client import ApiError
from components import format as fmt
from components.errors import friendly_message

APP = str(Path(__file__).resolve().parents[1] / "app.py")

VID = "11111111-1111-4111-8111-111111111111"
VID_B = "22222222-2222-4222-8222-222222222222"
SID = "33333333-3333-4333-8333-333333333333"
SID_2 = "44444444-4444-4444-8444-444444444444"
URL = "https://www.youtube.com/watch?v=jNQXAC9IVRw"
LONG_TEXT = ("All right, so here we are, in front of the elephants. " * 16)[:800]
SIGNED_IN = {"access_token": "test-access", "refresh_token": "test-refresh", "expires_at": 4102444800.0,
             "user": {"id": "aaaaaaaa-0000-4000-8000-00000000000a", "email": "a@example.com", "name": "Ada"}}

VIDEO = {
    "id": VID, "youtube_video_id": "jNQXAC9IVRw", "youtube_url": URL, "title": "Me at the zoo",
    "channel_name": "jawed", "thumbnail_url": None, "transcript_language": "en",
    "processing_status": "completed", "created_at": "2026-11-08T09:00:00+00:00",
}
FAILED_VIDEO = dict(VIDEO, id=VID_B, title="Broken video", processing_status="failed")
SESSION = {"id": SID, "video_id": VID, "session_title": "New Conversation",
           "created_at": "2026-11-08T09:00:00+00:00", "updated_at": "2026-11-08T09:05:00+00:00"}
SESSION_2 = dict(SESSION, id=SID_2, updated_at="2026-11-08T08:00:00+00:00")
SOURCE = {"chunk_id": "c1", "chunk_index": 0, "content": LONG_TEXT, "start_time": 1.2,
          "end_time": 18.4, "similarity": 0.71, "timestamp_url": URL + "&t=1s"}
SOURCE_2 = dict(SOURCE, chunk_id="c2", chunk_index=1, start_time=40.0, end_time=55.0, timestamp_url=URL + "&t=40s")


def msg(i, role, content, sources=None):
    return {"id": f"m{i}", "session_id": SID, "role": role, "content": content,
            "sources": sources, "created_at": "2026-11-08T09:01:00+00:00"}


HISTORY = [
    msg(1, "user", "What animals are there?"),
    msg(2, "assistant", "Elephants. [00:01 - 00:18]", [SOURCE_2, SOURCE]),
    msg(3, "user", "What is cool about them?"),
    msg(4, "assistant", "Their long trunks. [00:01 - 00:18]", [SOURCE]),  # same chunk cited again
    msg(5, "user", "What is the capital of France?"),
    msg(6, "assistant", "I couldn't find information about that in this video's transcript.", []),
]
INSIGHTS = {"success": True, "video_id": VID, "cached": True, "insights": {
    "summary": "A short video at the zoo.", "key_takeaways": ["Elephants have long trunks."],
    "topics": [{"name": "Elephants", "start_time": 1.0, "timestamp": "00:01", "timestamp_url": URL + "&t=1s"},
               {"name": "Closing", "start_time": None, "timestamp": None, "timestamp_url": None}],
    "model": "openai/gpt-oss-20b", "generated_at": "2026-11-08T09:10:00+00:00"}}


class Calls:
    """Records calls to patched api_client functions."""

    def __init__(self):
        self.log = []

    def count(self, name):
        return sum(1 for n, _ in self.log if n == name)

    def args(self, name):
        return [a for n, a in self.log if n == name]


@pytest.fixture
def api(monkeypatch):
    """Patch every api_client function with working defaults; tests override what they need."""
    calls = Calls()

    def patch(name, result=None, error=None, fn=None):
        def fake(*args, **kwargs):
            calls.log.append((name, args + tuple(sorted(kwargs.items()))))
            if fn:
                return fn(*args)
            if error:
                raise error
            return result

        monkeypatch.setattr(api_client, name, fake)

    # UI tests run as a signed-in user (sign-in itself is covered in test_auth.py).
    monkeypatch.setattr(auth, "current_session", lambda: SIGNED_IN)
    patch("check_health", (True, "TubeTalk AI"))
    patch("list_videos", {"success": True, "videos": [VIDEO, FAILED_VIDEO]})
    patch("get_video", {"success": True, "video": VIDEO})
    patch("list_sessions", {"success": True, "sessions": [SESSION, SESSION_2]})
    patch("create_session", {"success": True, "session": SESSION_2})
    patch("get_messages", {"success": True, "messages": HISTORY})
    patch("delete_session", {"success": True, "message": "deleted"})
    patch("process_video", {"success": True, "message": "ok", "reused": False, "video": VIDEO, "session": SESSION})
    patch("get_insights", INSIGHTS)
    patch("get_suggestions", {"success": True, "video_id": VID, "insights_ready": True, "suggestions": []})
    patch("regenerate_insights", INSIGHTS)
    patch("chat", fn=lambda v, s, m: {
        "success": True, "session_id": s, "answer": "Elephants.", "grounded": True, "sources": [SOURCE],
        "standalone_question": m, "user_message": msg(90, "user", m),
        "assistant_message": msg(91, "assistant", "Elephants.", [SOURCE])})
    calls.patch = patch
    return calls


def run_home():
    at = AppTest.from_file(APP, default_timeout=30)
    at.run()
    return at


def run_workspace(view="Chat"):
    """Open the workspace the way a refreshed browser would: from ?video=&session=."""
    at = AppTest.from_file(APP, default_timeout=30)
    at.query_params["video"] = VID
    at.query_params["session"] = SID
    at.run()
    if view != "Chat":
        at.session_state["workspace_view"] = view
        at.run()
    return at


def texts(at):
    parts = []
    for coll in (at.markdown, at.caption, at.info, at.error, at.warning, at.success, at.subheader):
        parts.extend(str(e.value) for e in coll)
    return "\n".join(parts)


def button(at, label):
    return next(b for b in at.button if b.label == label)


# ── Home ──────────────────────────────────────────────────────────────────────


def test_home_renders_hero_and_only_completed_videos(api):
    at = run_home()
    assert not at.exception
    page = texts(at)
    assert "Talk to any YouTube video." in page
    assert "Me at the zoo" in page and "Broken video" not in page  # failed videos hidden
    assert at.session_state["page"] == "home"


def test_submit_button_is_never_disabled(api):
    at = run_home()
    assert all(not b.disabled for b in at.button if b.label == "Process video")


def test_empty_submit_shows_error_without_calling_backend(api):
    at = run_home()
    submit = next(b for b in at.button if b.label == "Process video")
    submit.click().run()
    assert "Please enter a valid YouTube link." in texts(at)
    assert api.count("process_video") == 0


def test_process_success_opens_workspace_with_url_params(api):
    at = run_home()
    at.text_input[0].set_value("https://youtu.be/jNQXAC9IVRw")
    next(b for b in at.button if b.label == "Process video").click().run()
    assert not at.exception
    assert api.args("process_video") == [("https://youtu.be/jNQXAC9IVRw",)]
    assert at.session_state["page"] == "workspace"
    assert at.query_params["video"] == VID and at.query_params["session"] == SID
    assert "Me at the zoo" in texts(at)


def test_reused_video_is_announced(api):
    api.patch("process_video", {"success": True, "message": "ok", "reused": True, "video": VIDEO, "session": SESSION})
    at = run_home()
    at.text_input[0].set_value(URL)
    next(b for b in at.button if b.label == "Process video").click().run()
    assert any("Already processed" in str(t.value) for t in at.toast)


@pytest.mark.parametrize("code,message,expected", [
    ("INVALID_VIDEO_URL", "x", "Please enter a valid YouTube link."),
    ("TRANSCRIPT_UNAVAILABLE", "Captions are disabled for this video.", "Captions are disabled for this video."),
    ("UNSUPPORTED_LANGUAGE", "Only English transcripts are supported right now. Available languages: ko.",
     "Available languages: ko."),
    ("BACKEND_UNREACHABLE", "x", "Can't reach the backend."),
    ("TIMEOUT", "x", "taking longer than expected"),
    ("YOUTUBE_BLOCKED", "YouTube blocked the transcript request from this server. Please try again later.",
     "YouTube didn't allow this server to download its transcript"),
])
def test_processing_errors_are_shown_outside_the_collapsed_status(api, code, message, expected):
    api.patch("process_video", error=ApiError(code, message))
    at = run_home()
    at.text_input[0].set_value(URL)
    next(b for b in at.button if b.label == "Process video").click().run()
    assert not at.exception
    assert any(expected in str(e.value) for e in at.error)
    assert at.session_state["page"] == "home"


@pytest.mark.parametrize("value", [None, "", "   "])
def test_missing_backend_address_shows_configuration_error(api, monkeypatch, value):
    if value is None:
        monkeypatch.delenv("API_BASE_URL", raising=False)
    else:
        monkeypatch.setenv("API_BASE_URL", value)
    at = run_home()
    assert not at.exception
    assert any("API_BASE_URL" in str(e.value) and "missing" in str(e.value) for e in at.error)
    assert api.log == []  # nothing is called, in particular not localhost


def test_backend_address_is_trimmed(monkeypatch):
    import config

    monkeypatch.setenv("API_BASE_URL", " https://api.example.test/ ")
    assert config.get_api_base_url() == "https://api.example.test"


def test_recent_videos_error_offers_retry(api):
    api.patch("list_videos", error=ApiError("BACKEND_UNREACHABLE", "x"))
    at = run_home()
    assert "Can't reach the backend" in texts(at)
    assert any(b.label == "Try again" for b in at.button)


def test_sidebar_status_shows_unreachable_backend(api):
    api.patch("check_health", (False, "ConnectionError"))
    at = run_home()
    assert "Backend unreachable" in texts(at)
    api.patch("check_health", (True, "TubeTalk AI"))
    next(b for b in at.button if b.key == "refresh_health").click().run()  # "Check again" re-checks
    assert "Backend unreachable" not in texts(at)


def test_healthy_backend_shows_no_status_but_is_still_checked(api):
    for at in (run_home(), run_workspace()):
        assert "Backend connected" not in texts(at) and "Backend unreachable" not in texts(at)
        assert not any(b.key == "refresh_health" for b in at.button)
    assert api.count("check_health") >= 1  # the health check itself still runs


def test_streamlit_developer_controls_are_hidden_for_end_users():
    import tomllib

    from components import style

    config = tomllib.loads((Path(APP).parent / ".streamlit" / "config.toml").read_text(encoding="utf-8"))
    assert config["client"]["toolbarMode"] == "viewer"  # no Deploy / Rerun / Auto rerun / Clear cache
    # The whole ⋮ menu (Print, Record screen, "Made with Streamlit" included) is never shown.
    assert '[data-testid="stMainMenu"] { display: none; }' in style._CSS
    assert '[data-testid="stMainMenuPopover"] { visibility: hidden !important; }' in style._CSS


def theme_selectors(at):
    return [h for h in at.get("html") if 'class="tt-theme"' in h.proto.body]


@pytest.mark.parametrize("start", ["home", "workspace"])
def test_theme_selector_is_on_every_page_once(api, start):
    at = run_home() if start == "home" else run_workspace()
    assert len(theme_selectors(at)) == 1
    at.run()  # and stays single across reruns
    assert len(theme_selectors(at)) == 1


def test_theme_selector_offers_light_dark_system_and_drives_streamlits_switch(api):
    from components import theme

    body = theme_selectors(run_home())[0].proto.body
    for name in ("Light", "Dark", "System"):
        assert f'data-tt-theme="{name}"' in body
    # It changes the real theme by choosing Streamlit's own menu item, not by restyling the page.
    assert 'stMainMenuButton' in body and 'stMainMenuItem-theme-${name}' in body
    assert theme.THEMES == ("Light", "Dark", "System")
    # Streamlit's sanitiser silently drops a <script> whose text contains "<" + letter or "/".
    import re

    script = theme._SCRIPT.split("<script>", 1)[1].rsplit("</script>", 1)[0]
    assert not re.search(r"<[/\w!]", script)


def test_theme_selector_does_not_touch_session_state_or_the_player(api):
    at = run_workspace()
    seek(at, "0:40–0:55")
    before = (player(at), at.session_state["player_seek"], at.session_state["session_id"])
    at.run()
    assert (player(at), at.session_state["player_seek"], at.session_state["session_id"]) == before


# ── Workspace and chat ────────────────────────────────────────────────────────


def test_workspace_restores_from_url_and_renders_real_shaped_history(api):
    at = run_workspace()
    assert not at.exception  # long excerpts + repeated chunk: no nested-expander / duplicate-key errors
    page = texts(at)
    assert "Me at the zoo" in page and "Their long trunks." in page
    assert api.args("get_messages")[0] == (SID, VID)  # history always requested with its video


def test_sources_are_sorted_by_time_and_seek_the_player(api):
    at = run_workspace()
    seek_labels = [b.label for b in at.button if b.label and "–" in b.label]
    assert seek_labels[:2] == ["0:01–0:18", "0:40–0:55"]  # answer 2 listed SOURCE_2 first; UI sorts by time
    next(b for b in at.button if b.label == "0:40–0:55").click().run()
    assert at.session_state["player_start"] == 40


def test_ungrounded_answer_is_distinct_and_has_no_sources(api):
    at = run_workspace()
    assert any("couldn't find information" in str(i.value) for i in at.info)
    assert len([e for e in at.expander if "Sources" in e.label]) == 2  # only the two grounded answers


def test_send_message_uses_active_video_and_session_and_updates_history(api):
    at = run_workspace()
    at.chat_input[0].set_value("Where are they?").run()
    assert not at.exception
    assert api.args("chat") == [(VID, SID, "Where are they?")]
    cached = at.session_state[f"messages_{VID}_{SID}"]
    assert [m["content"] for m in cached[-2:]] == ["Where are they?", "Elephants."]


def test_failed_message_keeps_error_and_retry_resends_same_text(api):
    api.patch("chat", error=ApiError("LLM_RATE_LIMITED", "busy", 429))
    at = run_workspace()
    at.chat_input[0].set_value("Where are they?").run()
    assert "The AI service is busy" in texts(at)  # survives the rerun
    assert "Where are they?" in texts(at)  # tells the user what wasn't sent
    assert len(at.session_state[f"messages_{VID}_{SID}"]) == len(HISTORY)  # no phantom message

    api.patch("chat", fn=lambda v, s, m: {
        "success": True, "session_id": s, "answer": "Ok.", "grounded": True, "sources": [SOURCE],
        "standalone_question": m, "user_message": msg(92, "user", m),
        "assistant_message": msg(93, "assistant", "Ok.", [SOURCE])})
    button(at, "Try again").click().run()
    assert api.args("chat")[-1] == (VID, SID, "Where are they?")
    assert "The AI service is busy" not in texts(at)


def test_starter_question_is_sent(api):
    api.patch("get_messages", {"success": True, "messages": []})
    at = run_workspace()
    assert "Ask anything about this video." in texts(at)
    button(at, "Summarise this video").click().run()
    assert api.args("chat") == [(VID, SID, "Summarise this video")]


def test_switching_session_loads_that_sessions_history_only(api):
    at = run_workspace()
    other = next(b for b in at.button if b.key == f"sess_{SID_2}")
    api.patch("get_messages", {"success": True, "messages": []})
    other.click().run()
    assert at.session_state["session_id"] == SID_2
    assert api.args("get_messages")[-1] == (SID_2, VID)
    assert at.query_params["session"] == SID_2
    assert "Ask anything about this video." in texts(at)


def test_new_conversation_creates_and_switches(api):
    at = run_workspace()
    button(at, "New conversation").click().run()
    assert api.args("create_session") == [(VID,)]
    assert at.session_state["session_id"] == SID_2


@pytest.mark.parametrize("code", ["SESSION_NOT_FOUND", "VALIDATION_ERROR", "SESSION_VIDEO_MISMATCH"])
def test_bad_link_shows_friendly_message_and_way_home(api, code):
    api.patch("get_messages", error=ApiError(code, "x"))
    at = run_workspace()
    assert not at.exception
    assert "couldn’t be reopened" in texts(at)
    assert any(b.label == "Back to all videos" for b in at.button)


# ── Insights ──────────────────────────────────────────────────────────────────


def test_insights_render_and_are_fetched_once_per_video(api):
    at = run_workspace("Insights")
    page = texts(at)
    assert "A short video at the zoo." in page and "Elephants have long trunks." in page
    assert any(b.label == "00:01" for b in at.button)  # topic with a timestamp
    assert "Closing" in page  # topic without a timestamp still listed
    at.run()
    at.run()
    assert api.count("get_insights") == 1


def test_insights_generating_offers_check_again(api):
    api.patch("get_insights", error=ApiError("INSIGHTS_GENERATING", "x", 409))
    at = run_workspace("Insights")
    assert any("being generated" in str(i.value) for i in at.info)
    assert any(b.label == "Check again" for b in at.button)


def test_insights_failure_offers_try_again(api):
    api.patch("get_insights", error=ApiError("INSIGHTS_FAILED", "x", 500))
    at = run_workspace("Insights")
    assert "Couldn't generate insights" in texts(at)
    assert any(b.label == "Try again" for b in at.button)


# ── api_client ────────────────────────────────────────────────────────────────


class FakeResp:
    def __init__(self, status, body=None, reason="", json_ok=True):
        self.status_code, self._body, self.reason, self._json_ok = status, body, reason, json_ok
        self.ok = status < 400

    def json(self):
        if not self._json_ok:
            raise ValueError("not json")
        return self._body


def test_client_maps_backend_error_body(monkeypatch):
    monkeypatch.setattr(api_client.requests, "request", lambda *a, **k: FakeResp(
        422, {"success": False, "error": "TRANSCRIPT_UNAVAILABLE", "message": "Captions are disabled."}))
    with pytest.raises(ApiError) as e:
        api_client.process_video(URL)
    assert (e.value.code, e.value.message, e.value.status) == ("TRANSCRIPT_UNAVAILABLE", "Captions are disabled.", 422)


@pytest.mark.parametrize("exc,code", [(requests.ConnectionError(), "BACKEND_UNREACHABLE"), (requests.Timeout(), "TIMEOUT")])
def test_client_maps_network_failures(monkeypatch, exc, code):
    def boom(*a, **k):
        raise exc

    monkeypatch.setattr(api_client.requests, "request", boom)
    with pytest.raises(ApiError) as e:
        api_client.list_videos()
    assert e.value.code == code


def test_client_handles_non_json_error(monkeypatch):
    monkeypatch.setattr(api_client.requests, "request", lambda *a, **k: FakeResp(502, reason="Bad Gateway", json_ok=False))
    with pytest.raises(ApiError) as e:
        api_client.get_video(VID)
    assert e.value.code == "HTTP_ERROR" and e.value.status == 502


def test_client_sends_ids_and_timeouts(monkeypatch):
    seen = {}

    def capture(method, url, timeout, **kwargs):
        seen.update(method=method, url=url, timeout=timeout, **kwargs)
        return FakeResp(200, {"success": True})

    monkeypatch.setattr(api_client.requests, "request", capture)
    api_client.get_messages(SID, VID)
    assert seen["url"].endswith(f"/api/sessions/{SID}/messages") and seen["params"] == {"video_id": VID}
    assert seen["timeout"] == 60  # long enough for a sleeping free-tier backend to wake up
    api_client.chat(VID, SID, "hi")
    assert seen["json"] == {"video_id": VID, "session_id": SID, "message": "hi"} and seen["timeout"] == 300
    api_client.process_video(URL)
    assert seen["timeout"] == 300


def test_health_check_waits_for_a_waking_backend(monkeypatch):
    seen = {}

    def capture(url, timeout):
        seen.update(url=url, timeout=timeout)
        resp = FakeResp(200, {"status": "healthy", "application": "TubeTalk AI"})
        resp.raise_for_status = lambda: None
        return resp

    monkeypatch.setattr(api_client.requests, "get", capture)
    assert api_client.check_health() == (True, "TubeTalk AI")
    assert seen["url"].endswith("/health") and seen["timeout"] == 60


# ── Formatting / errors ───────────────────────────────────────────────────────


@pytest.mark.parametrize("secs,expected", [(0, "0:00"), (75.9, "1:15"), (3725, "1:02:05"), (None, "–:––")])
def test_fmt_seconds(secs, expected):
    assert fmt.fmt_seconds(secs) == expected


def test_md_escape_neutralises_markdown_in_titles():
    assert fmt.md_escape("**$5** [x](y)") == r"\*\*\$5\*\* \[x\]\(y\)"


def test_truncate():
    assert fmt.truncate("abcdef", 4) == "abc…" and fmt.truncate(" ab ", 4) == "ab"


@pytest.mark.parametrize("code,expected", [
    ("INVALID_VIDEO_URL", "Please enter a valid YouTube link."),
    ("SOME_NEW_CODE", "raw message"),
])
def test_friendly_message(code, expected):
    assert friendly_message(ApiError(code, "raw message")) == expected


# ── Whole-video questions answered from the summary ───────────────────────────

SUMMARY_SOURCE = {"kind": "summary", "topic": None, "chunk_id": None, "chunk_index": None, "content": "",
                  "start_time": None, "end_time": None, "similarity": None, "timestamp_url": None}
TOPIC_SOURCE = {"kind": "topic", "topic": "Elephants", "chunk_id": "c1", "chunk_index": 0, "content": LONG_TEXT,
                "start_time": 1.0, "end_time": 18.4, "similarity": None, "timestamp_url": URL + "&t=1s"}


def test_summary_answer_is_labelled_and_offers_view_summary(api):
    api.patch("get_messages", {"success": True, "messages": [
        msg(1, "user", "What is this video about?"),
        msg(2, "assistant", "A short video at the zoo.\n\n**Topics covered**\n\n- [00:01] Elephants",
            [SUMMARY_SOURCE, TOPIC_SOURCE]),
    ]})
    at = run_workspace()
    assert not at.exception
    page = texts(at)
    assert "Answered from the video summary" in page
    assert not any("couldn't find" in str(i.value) for i in at.info)  # not shown as a refusal
    assert any(e.label == "Topics (1)" for e in at.expander)  # the summary marker is not counted
    assert any(b.label == "0:01" for b in at.button)  # topic timestamp seeks the player
    next(b for b in at.button if b.label == "View summary").click().run()
    assert at.session_state["workspace_view"] == "Insights"
    assert "A short video at the zoo." in texts(at)  # Insights view now showing


def topic_labels(at):
    return [b.label for b in at.button if b.label and b.label.startswith("What does the video say")]


def test_empty_chat_shows_only_backend_validated_suggestions(api):
    api.patch("get_messages", {"success": True, "messages": []})
    api.patch("get_suggestions", {"success": True, "video_id": VID, "insights_ready": True,
                                  "suggestions": ["What does the video say about elephants?"]})
    at = run_workspace()
    labels = [b.label for b in at.button]
    assert "Summarise this video" in labels and "View summary" in labels
    # exactly what the backend validated; topics it rejected (e.g. "Closing") never appear
    assert topic_labels(at) == ["What does the video say about elephants?"]
    assert api.args("get_suggestions") == [(VID,)]
    assert api.count("get_insights") == 0  # the empty chat never touches (or generates) insights
    button(at, "What does the video say about elephants?").click().run()
    assert api.args("chat") == [(VID, SID, "What does the video say about elephants?")]


def test_zero_valid_suggestions_keeps_summary_actions(api):
    api.patch("get_messages", {"success": True, "messages": []})
    api.patch("get_suggestions", {"success": True, "video_id": VID, "insights_ready": True, "suggestions": []})
    at = run_workspace()
    assert not at.exception and topic_labels(at) == []
    labels = [b.label for b in at.button]
    assert "Summarise this video" in labels and "View summary" in labels
    assert "Or ask about a topic" not in texts(at)


def test_shows_at_most_three_suggestions(api):
    api.patch("get_messages", {"success": True, "messages": []})
    many = [f"What does the video say about topic {i}?" for i in range(5)]
    api.patch("get_suggestions", {"success": True, "video_id": VID, "insights_ready": True, "suggestions": many})
    assert topic_labels(run_workspace()) == many[:3]


def test_suggestions_appear_once_insights_are_ready(api):
    api.patch("get_messages", {"success": True, "messages": []})
    api.patch("get_suggestions", {"success": True, "video_id": VID, "insights_ready": False, "suggestions": []})
    at = run_workspace()
    assert topic_labels(at) == [] and "Summarise this video" in [b.label for b in at.button]
    api.patch("get_suggestions", {"success": True, "video_id": VID, "insights_ready": True,
                                  "suggestions": ["What does the video say about elephants?"]})
    at.run()  # "not ready" was not cached, so it checks again
    assert topic_labels(at) == ["What does the video say about elephants?"]
    at.run()
    assert api.count("get_suggestions") == 2  # a ready result is cached


def test_suggestions_error_does_not_break_empty_chat(api):
    api.patch("get_messages", {"success": True, "messages": []})
    api.patch("get_suggestions", error=ApiError("BACKEND_UNREACHABLE", "x"))
    at = run_workspace()
    assert not at.exception and topic_labels(at) == []
    assert "Summarise this video" in [b.label for b in at.button]


def test_summary_still_preparing_is_a_wait_not_an_error(api):
    api.patch("chat", error=ApiError("SUMMARY_GENERATING", "x", 409))
    at = run_workspace()
    at.chat_input[0].set_value("What is this video about?").run()
    assert any("still being prepared" in str(i.value) for i in at.info)
    assert not any("still being prepared" in str(e.value) for e in at.error)
    assert any(b.label == "Try again" for b in at.button)


def test_summary_unavailable_is_distinct_from_a_refusal(api):
    message = ("I couldn't prepare the video summary, so this overview question wasn't answered. "
               "Please try again, or ask about something specific in the video.")
    api.patch("chat", error=ApiError("SUMMARY_UNAVAILABLE", message, 503))
    at = run_workspace()
    at.chat_input[0].set_value("Summarise this video").run()
    assert any("overview question wasn't answered" in str(e.value) for e in at.error)
    assert len(at.session_state[f"messages_{VID}_{SID}"]) == len(HISTORY)  # nothing added to history


def test_client_peek_insights_never_generates(monkeypatch):
    seen = {}

    def capture(method, url, timeout, **kwargs):
        seen.update(url=url, timeout=timeout, **kwargs)
        return FakeResp(200, {"success": True})

    monkeypatch.setattr(api_client.requests, "request", capture)
    api_client.get_insights(VID, generate=False)
    assert seen["params"] == {"generate": "false"} and seen["timeout"] == 60  # waits out a cold start


def test_client_suggestions_endpoint(monkeypatch):
    seen = {}

    def capture(method, url, timeout, **kwargs):
        seen.update(method=method, url=url)
        return FakeResp(200, {"success": True, "suggestions": []})

    monkeypatch.setattr(api_client.requests, "request", capture)
    api_client.get_suggestions(VID)
    assert seen == {"method": "GET", "url": seen["url"]} and seen["url"].endswith(f"/api/videos/{VID}/suggestions")


CLARIFICATION_SOURCE = {"kind": "clarification", "topic": None, "chunk_id": None, "chunk_index": None, "content": "",
                        "start_time": None, "end_time": None, "similarity": None, "timestamp_url": None}


def test_clarifying_question_is_shown_as_a_question_not_a_refusal(api):
    api.patch("get_messages", {"success": True, "messages": [
        msg(1, "user", "What did he say about that?"),
        msg(2, "assistant", "Which part of the video do you mean by 'that'?", [CLARIFICATION_SOURCE]),
    ]})
    at = run_workspace()
    assert not at.exception
    page = texts(at)
    assert "Which part of the video do you mean by 'that'?" in page
    assert "Reply with a bit more detail" in page
    assert not any("Which part" in str(i.value) for i in at.info)  # not styled as a refusal
    assert not any("Sources" in e.label for e in at.expander)


# ── Player seeking ────────────────────────────────────────────────────────────


def test_repeated_seek_to_the_same_timestamp_counts_as_a_new_seek(api):
    at = run_workspace()
    assert at.session_state["player_seek"] == 0
    for expected in (1, 2):  # same time twice: the second click must still remount the player
        next(b for b in at.button if b.label == "0:40–0:55").click().run()
        assert at.session_state["player_start"] == 40
        assert at.session_state["player_seek"] == expected


def test_topic_seek_in_insights_counts_as_a_seek(api):
    at = run_workspace("Insights")
    button(at, "00:01").click().run()
    assert at.session_state["player_start"] == 1 and at.session_state["player_seek"] == 1


def test_ordinary_reruns_do_not_remount_the_player(api):
    at = run_workspace()
    at.chat_input[0].set_value("Where are they?").run()
    at.session_state["workspace_view"] = "Insights"
    at.run()
    at.run()  # plain rerun (e.g. the cached health check refreshing)
    assert at.session_state["player_seek"] == 0


def player(at):
    """(start_time, autoplay) of the rendered player; together with the container key these decide
    whether the browser gets a new iframe."""
    video = at.get("video")[0].proto
    return video.start_time, video.autoplay


def seek(at, label):
    next(b for b in at.button if b.label == label).click().run()


def test_player_does_not_autoplay_when_a_video_is_opened(api):
    assert player(run_workspace()) == (0, False)


def test_clicking_different_timestamps_seeks_and_autoplays(api):
    at = run_workspace()
    seek(at, "0:40–0:55")
    assert player(at) == (40, True)
    seek(at, "0:01–0:18")
    assert player(at) == (1, True) and at.session_state["player_seek"] == 2


def test_clicking_the_same_timestamp_twice_autoplays_both_times(api):
    at = run_workspace()
    for expected_seek in (1, 2):
        seek(at, "0:40–0:55")
        assert player(at) == (40, True)
        assert at.session_state["player_seek"] == expected_seek  # new key -> fresh iframe each time


def test_insights_topic_click_autoplays(api):
    at = run_workspace("Insights")
    seek(at, "00:01")
    assert player(at) == (1, True)


def test_reruns_after_a_seek_keep_the_playing_player(api):
    """Same key, start time and autoplay flag -> the browser keeps the iframe, so playback continues."""
    at = run_workspace()
    seek(at, "0:40–0:55")
    before = (player(at), at.session_state["player_seek"])
    at.chat_input[0].set_value("Where are they?").run()
    assert (player(at), at.session_state["player_seek"]) == before
    at.session_state["workspace_view"] = "Insights"
    at.run()
    assert (player(at), at.session_state["player_seek"]) == before
    at.run()  # plain rerun
    assert (player(at), at.session_state["player_seek"]) == before


def test_opening_another_video_does_not_autoplay_it(api):
    other = dict(VIDEO, id=VID_B, title="Another video", youtube_url="https://www.youtube.com/watch?v=dQw4w9WgXcQ")
    api.patch("list_videos", {"success": True, "videos": [VIDEO, other]})
    at = run_workspace()
    seek(at, "0:40–0:55")
    assert player(at) == (40, True)
    next(b for b in at.button if b.key == f"rv_{VID_B}").click().run()
    assert not at.exception
    assert at.session_state["video"]["id"] == VID_B
    assert player(at) == (0, False) and at.session_state["player_seek"] == 0


# ── URL-based routing ─────────────────────────────────────────────────────────


def test_url_params_win_over_a_remembered_home_page(api):
    """All videos → browser Back → reload: Streamlit can reattach the old session (page="home")
    while the URL names a conversation again. The URL decides."""
    at = run_home()
    assert at.session_state["page"] == "home"
    at.query_params["video"] = VID
    at.query_params["session"] = SID
    at.run()
    assert not at.exception
    assert at.session_state["page"] == "workspace"
    assert at.session_state["session_id"] == SID and "Their long trunks." in texts(at)


def test_url_without_params_shows_home_even_if_a_workspace_was_open(api):
    at = run_workspace()
    del at.query_params["video"]
    del at.query_params["session"]
    at.run()
    assert at.session_state["page"] == "home"
    assert "Talk to any YouTube video." in texts(at)


def test_url_naming_another_conversation_restores_it(api):
    at = run_workspace()
    api.patch("get_messages", {"success": True, "messages": []})
    at.query_params["session"] = SID_2  # e.g. browser Back after switching conversations
    at.run()
    assert not at.exception
    assert at.session_state["session_id"] == SID_2
    assert api.args("get_messages")[-1] == (SID_2, VID)
    assert "Ask anything about this video." in texts(at)


def test_matching_url_does_not_refetch_the_video(api):
    at = run_workspace()
    at.run()
    at.run()
    assert api.count("get_video") == 1 and api.count("get_messages") == 1


def test_url_naming_a_deleted_conversation_is_handled(api):
    at = run_workspace()
    api.patch("get_messages", error=ApiError("SESSION_NOT_FOUND", "x"))
    at.query_params["session"] = SID_2
    at.run()
    assert not at.exception
    assert "couldn’t be reopened" in texts(at)
    assert "session" not in at.query_params  # the bad link is cleared…
    at.run()
    assert at.session_state["page"] == "home"  # …so the next run lands on Home
