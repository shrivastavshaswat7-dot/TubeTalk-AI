"""Transcript fetching through FreeTranscriptAPI. The HTTP call is always mocked: no test ever
reaches the real service (each real lookup would spend a credit)."""
from types import SimpleNamespace as NS

import pytest
import requests

from app.core.errors import AppError
from app.services import transcript as transcript_service
from app.services.transcript import clean_segments, clean_text, fetch_transcript

VID = "jNQXAC9IVRw"
KEY = "test-key-not-real"


def snip(text, start=0.0, duration=1.0):
    return NS(text=text, start=start, duration=duration)


class FakeResponse:
    def __init__(self, status=200, body=None, json_ok=True):
        self.status_code = status
        self.ok = status < 400
        self._body = body
        self._json_ok = json_ok

    def json(self):
        if not self._json_ok:
            raise ValueError("not json")
        return self._body


def ok_body(lines=None, language="en"):
    return {
        "language": language,
        "title": "Me at the zoo",
        "transcript": lines if lines is not None else [
            {"text": "All right, so here we are", "start": 1.2, "duration": 2.16},
            {"text": "in front of the elephants", "start": 3.36, "duration": 2.0},
        ],
    }


@pytest.fixture
def http(monkeypatch):
    """Replace requests.get in the transcript module; records every call."""
    calls = []
    state = NS(response=FakeResponse(200, ok_body()), error=None, calls=calls)

    def fake_get(url, **kwargs):
        calls.append(NS(url=url, **kwargs))
        if state.error:
            raise state.error
        return state.response

    monkeypatch.setattr(transcript_service.requests, "get", fake_get)
    return state


# --- cleaning -------------------------------------------------------------


def test_clean_text_normalises_whitespace_and_entities():
    assert clean_text("  it&#39;s \n  a   test ") == "it's a test"


def test_clean_segments_drops_empty_noise_and_repeats_keeps_timestamps():
    raw = [
        snip("  "),
        snip("[Music]", 0, 2),
        snip("Hello   there", 3.0, 2.0),
        snip("Hello there", 5.0, 2.0),  # repeat
        snip("(applause)", 7, 1),
        snip("Next line", 9.0, 1.5),
    ]
    out = clean_segments(raw)
    assert [s.text for s in out] == ["Hello there", "Next line"]
    assert out[0].start == 3.0 and out[0].duration == 2.0 and out[0].end == 5.0
    assert out[1].start == 9.0


# --- fetching -------------------------------------------------------------


def test_fetch_transcript_success_keeps_text_timestamps_and_language(http):
    tr = fetch_transcript(VID, api_key=KEY)
    assert tr.youtube_video_id == VID and tr.language_code == "en"
    assert [s.text for s in tr.segments] == ["All right, so here we are", "in front of the elephants"]
    assert (tr.segments[0].start, tr.segments[0].duration) == (1.2, 2.16)
    assert tr.segments[1].start == 3.36 and tr.segments[1].end == pytest.approx(5.36)


def test_request_shape_one_call_with_bearer_key_and_timeout(http):
    fetch_transcript(VID, api_key=KEY)
    assert len(http.calls) == 1  # never retried: every lookup costs a credit
    call = http.calls[0]
    assert call.url == "https://api.freetranscriptapi.com/v1/transcript"
    assert call.params == {"video_url": VID, "lang": "en"}
    assert call.headers == {"Authorization": f"Bearer {KEY}"}
    assert call.timeout == transcript_service.TRANSCRIPT_TIMEOUT_SECONDS


def test_key_is_read_from_settings(http, monkeypatch):
    monkeypatch.setattr(transcript_service, "get_settings", lambda: NS(free_transcript_api_key=" from-env "))
    fetch_transcript(VID)
    assert http.calls[0].headers == {"Authorization": "Bearer from-env"}


def test_cleaning_is_applied_to_service_captions(http):
    http.response = FakeResponse(200, ok_body([
        {"text": "[Music]", "start": 0, "duration": 1},
        {"text": "it&#39;s  here", "start": 1, "duration": 2},
        {"text": "it's here", "start": 3, "duration": 2},
    ]))
    tr = fetch_transcript(VID, api_key=KEY)
    assert [(s.text, s.start) for s in tr.segments] == [("it's here", 1.0)]


def test_accepts_english_variants(http):
    http.response = FakeResponse(200, ok_body(language="en-US"))
    assert fetch_transcript(VID, api_key=KEY).language_code == "en-US"


@pytest.mark.parametrize("key", ["", "   "])
def test_missing_key_is_a_clear_error_and_makes_no_request(http, key):
    with pytest.raises(AppError) as exc:
        fetch_transcript(VID, api_key=key)
    assert exc.value.error == "TRANSCRIPT_SERVICE_NOT_CONFIGURED" and exc.value.status_code == 503
    assert http.calls == []


def test_non_english_fallback_is_unsupported_language(http):
    http.response = FakeResponse(200, ok_body(language="ko"))
    with pytest.raises(AppError) as exc:
        fetch_transcript(VID, api_key=KEY)
    assert exc.value.error == "UNSUPPORTED_LANGUAGE" and "ko" in exc.value.message


@pytest.mark.parametrize("lines", [[], [{"text": " ", "start": 0, "duration": 1}, {"text": "[Music]", "start": 1, "duration": 1}]])
def test_empty_transcript(http, lines):
    http.response = FakeResponse(200, ok_body(lines))
    with pytest.raises(AppError) as exc:
        fetch_transcript(VID, api_key=KEY)
    assert exc.value.error == "TRANSCRIPT_UNAVAILABLE" and exc.value.status_code == 422


@pytest.mark.parametrize("response", [
    FakeResponse(200, json_ok=False),  # not JSON
    FakeResponse(200, ["not", "an", "object"]),
    FakeResponse(200, {"language": "en", "title": "x"}),  # no transcript field
    FakeResponse(200, ok_body([{"text": "no timestamps"}])),
    FakeResponse(200, ok_body([{"text": "x", "start": "soon", "duration": 1}])),
])
def test_malformed_responses_are_a_service_error(http, response):
    http.response = response
    with pytest.raises(AppError) as exc:
        fetch_transcript(VID, api_key=KEY)
    assert exc.value.error == "TRANSCRIPT_SERVICE_ERROR" and exc.value.status_code == 502


@pytest.mark.parametrize("status,code,expected,expected_status", [
    (404, "video_not_found", "TRANSCRIPT_UNAVAILABLE", 422),
    (402, "insufficient_credits", "TRANSCRIPT_SERVICE_UNAVAILABLE", 503),
    (401, "unauthorized", "TRANSCRIPT_SERVICE_UNAVAILABLE", 503),
    (429, "rate_limit_exceeded", "TRANSCRIPT_RATE_LIMITED", 429),
    (429, "anonymous_daily_cap_exceeded", "TRANSCRIPT_RATE_LIMITED", 429),
    (400, "invalid_request", "TRANSCRIPT_SERVICE_ERROR", 502),
    (500, "internal_error", "TRANSCRIPT_SERVICE_ERROR", 502),
])
def test_documented_api_errors(http, status, code, expected, expected_status):
    http.response = FakeResponse(status, {"error": {"code": code, "message": "secret-ish detail fta_live_sk_x"}})
    with pytest.raises(AppError) as exc:
        fetch_transcript(VID, api_key=KEY)
    assert exc.value.error == expected and exc.value.status_code == expected_status
    assert "fta_live" not in exc.value.message and KEY not in exc.value.message  # body never passed on
    assert len(http.calls) == 1


def test_error_without_json_body(http):
    http.response = FakeResponse(503, json_ok=False)
    with pytest.raises(AppError) as exc:
        fetch_transcript(VID, api_key=KEY)
    assert exc.value.error == "TRANSCRIPT_SERVICE_ERROR"


@pytest.mark.parametrize("error,expected,status", [
    (requests.Timeout("slow"), "TRANSCRIPT_TIMEOUT", 504),
    (requests.ConnectionError("down"), "NETWORK_ERROR", 503),
])
def test_network_failures(http, error, expected, status):
    http.error = error
    with pytest.raises(AppError) as exc:
        fetch_transcript(VID, api_key=KEY)
    assert exc.value.error == expected and exc.value.status_code == status
    assert KEY not in exc.value.message and len(http.calls) == 1
