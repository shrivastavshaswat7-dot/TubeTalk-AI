from types import SimpleNamespace as NS
from unittest.mock import MagicMock

import pytest
from youtube_transcript_api import (
    AgeRestricted,
    IpBlocked,
    NoTranscriptFound,
    TranscriptsDisabled,
    VideoUnavailable,
)

from app.core.errors import AppError
from app.services.transcript import clean_segments, clean_text, fetch_transcript

VID = "jNQXAC9IVRw"


def snip(text, start=0.0, duration=1.0):
    return NS(text=text, start=start, duration=duration)


def fake_transcript(code="en", generated=False, snippets=None):
    t = MagicMock()
    t.language_code = code
    t.is_generated = generated
    t.fetch.return_value = NS(
        language_code=code,
        is_generated=generated,
        snippets=snippets if snippets is not None else [snip("hello world", 1.5, 2.0)],
    )
    return t


def api_with(*transcripts):
    api = MagicMock()
    api.list.return_value = list(transcripts)
    return api


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


def test_fetch_transcript_success():
    tr = fetch_transcript(VID, api=api_with(fake_transcript()))
    assert tr.youtube_video_id == VID
    assert tr.language_code == "en" and tr.is_generated is False
    assert tr.segments[0].text == "hello world"


def test_prefers_manual_english_over_generated():
    manual = fake_transcript("en", generated=False, snippets=[snip("manual")])
    auto = fake_transcript("en", generated=True, snippets=[snip("auto")])
    tr = fetch_transcript(VID, api=api_with(auto, manual))
    assert tr.segments[0].text == "manual"


def test_accepts_english_variants():
    tr = fetch_transcript(VID, api=api_with(fake_transcript("en-US", generated=True)))
    assert tr.language_code == "en-US"


def test_unsupported_language():
    with pytest.raises(AppError) as exc:
        fetch_transcript(VID, api=api_with(fake_transcript("ko"), fake_transcript("fr")))
    assert exc.value.error == "UNSUPPORTED_LANGUAGE"
    assert "fr" in exc.value.message and "ko" in exc.value.message


def test_empty_transcript_after_cleaning():
    t = fake_transcript(snippets=[snip(" "), snip("[Music]")])
    with pytest.raises(AppError) as exc:
        fetch_transcript(VID, api=api_with(t))
    assert exc.value.error == "TRANSCRIPT_UNAVAILABLE"


def test_no_transcripts_listed_is_unsupported_language():
    with pytest.raises(AppError) as exc:
        fetch_transcript(VID, api=api_with())
    assert exc.value.error == "UNSUPPORTED_LANGUAGE"


@pytest.mark.parametrize(
    "exception,code,status",
    [
        (TranscriptsDisabled(VID), "TRANSCRIPT_UNAVAILABLE", 422),
        (NoTranscriptFound(VID, ["en"], MagicMock()), "TRANSCRIPT_UNAVAILABLE", 422),
        (AgeRestricted(VID), "VIDEO_RESTRICTED", 403),
        (VideoUnavailable(VID), "VIDEO_RESTRICTED", 403),
        (IpBlocked(VID), "YOUTUBE_BLOCKED", 503),
        (ConnectionError("boom"), "NETWORK_ERROR", 503),
    ],
)
def test_error_mapping(exception, code, status):
    api = MagicMock()
    api.list.side_effect = exception
    with pytest.raises(AppError) as exc:
        fetch_transcript(VID, api=api)
    assert exc.value.error == code and exc.value.status_code == status
