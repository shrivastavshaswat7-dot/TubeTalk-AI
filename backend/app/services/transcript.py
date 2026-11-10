"""Transcript fetching (FreeTranscriptAPI) and cleaning.

YouTube blocks transcript requests from many cloud servers, so the hosted backend fetches captions
through FreeTranscriptAPI instead of from YouTube directly. Every lookup costs one credit, even when
the video has no transcript, so a failed lookup is never retried automatically.
"""
import html
import logging
import re

import requests

from app.core.config import get_settings
from app.core.errors import AppError
from app.schemas.transcript import Transcript, TranscriptSegment

logger = logging.getLogger("tubetalk")

TRANSCRIPT_API_URL = "https://api.freetranscriptapi.com/v1/transcript"
# (connect, read) seconds: long videos can take a while to transcribe on the service's side.
TRANSCRIPT_TIMEOUT_SECONDS = (10, 60)

# The embedding model (all-MiniLM-L6-v2) is English-centric, so V1 accepts English only.
SUPPORTED_LANGUAGE_PREFIX = "en"

_WS_RE = re.compile(r"\s+")
_NOISE_RE = re.compile(r"^\[[^\]]*\]$|^\([^)]*\)$")  # e.g. [Music], (applause)


def clean_text(text: str) -> str:
    return _WS_RE.sub(" ", html.unescape(text)).strip()


def clean_segments(raw_segments) -> list[TranscriptSegment]:
    """Normalise text, drop empty/noise-only segments, keep timestamps, collapse repeats."""
    cleaned: list[TranscriptSegment] = []
    for seg in raw_segments:
        text = clean_text(seg.text)
        if not text or _NOISE_RE.match(text):
            continue
        if cleaned and cleaned[-1].text == text:  # repeated caption line
            continue
        cleaned.append(
            TranscriptSegment(text=text, start=float(seg.start), duration=float(seg.duration))
        )
    return cleaned


def _service_error() -> AppError:
    return AppError(
        "TRANSCRIPT_SERVICE_ERROR",
        "The transcript service had a problem, so this video couldn't be processed. "
        "Please try again later.",
        502,
    )


def _service_unavailable() -> AppError:
    # Bad key or no credits: the visitor can't fix it, so the message stays general.
    return AppError(
        "TRANSCRIPT_SERVICE_UNAVAILABLE",
        "New videos can't be processed right now because the transcript service is unavailable. "
        "Videos that are already processed still work.",
        503,
    )


def _error_for(response: requests.Response) -> AppError:
    """Map FreeTranscriptAPI's documented error responses. Only the status and the error code are
    looked at; the response body is never passed on to the user."""
    try:
        code = (response.json().get("error") or {}).get("code")
    except (ValueError, AttributeError):
        code = None
    status = response.status_code
    if status == 404 or code == "video_not_found":
        return AppError(
            "TRANSCRIPT_UNAVAILABLE",
            "No transcript is available for this video. It may have no captions, or it may be "
            "private or removed.",
            422,
        )
    if status == 429:
        return AppError(
            "TRANSCRIPT_RATE_LIMITED",
            "The transcript service is busy right now. Please try again in a few minutes.",
            429,
        )
    if status in (401, 402, 403):
        logger.warning("Transcript service refused the request (HTTP %s, %s)", status, code)
        return _service_unavailable()
    logger.warning("Transcript service error (HTTP %s, %s)", status, code)
    return _service_error()


def _segments_from(items) -> list[TranscriptSegment]:
    """FreeTranscriptAPI caption lines -> cleaned segments (raises on a malformed payload)."""
    if not isinstance(items, list):
        raise _service_error()
    raw = []
    for item in items:
        try:
            raw.append(TranscriptSegment(
                text=str(item["text"]), start=float(item["start"]), duration=float(item["duration"])
            ))
        except (KeyError, TypeError, ValueError):
            raise _service_error()
    return clean_segments(raw)


def fetch_transcript(video_id: str, api_key: str | None = None) -> Transcript:
    """Fetch the English transcript of one video. One request, one credit, no retries."""
    key = (api_key if api_key is not None else get_settings().free_transcript_api_key).strip()
    if not key:
        raise AppError(
            "TRANSCRIPT_SERVICE_NOT_CONFIGURED",
            "New videos can't be processed right now because transcript fetching isn't set up "
            "on this server. Videos that are already processed still work.",
            503,
        )
    try:
        response = requests.get(
            TRANSCRIPT_API_URL,
            params={"video_url": video_id, "lang": SUPPORTED_LANGUAGE_PREFIX},
            headers={"Authorization": f"Bearer {key}"},
            timeout=TRANSCRIPT_TIMEOUT_SECONDS,
        )
    except requests.Timeout:
        raise AppError(
            "TRANSCRIPT_TIMEOUT",
            "The transcript service took too long to respond. Please try again later.",
            504,
        )
    except requests.RequestException:
        raise AppError("NETWORK_ERROR", "Could not reach the transcript service. Please try again.", 503)

    if not response.ok:
        raise _error_for(response)
    try:
        data = response.json()
    except ValueError:
        raise _service_error()
    if not isinstance(data, dict):
        raise _service_error()

    # `lang` is only a preference: the service falls back to another language's captions.
    language = str(data.get("language") or "").strip()
    if not language.lower().startswith(SUPPORTED_LANGUAGE_PREFIX):
        raise AppError(
            "UNSUPPORTED_LANGUAGE",
            "Only English transcripts are supported right now. "
            f"This video's transcript is in: {language or 'an unknown language'}.",
            422,
        )

    segments = _segments_from(data.get("transcript"))
    if not segments:
        raise AppError("TRANSCRIPT_UNAVAILABLE", "The transcript is empty.", 422)
    return Transcript(
        youtube_video_id=video_id,
        language_code=language,
        is_generated=False,  # not reported by the service; nothing downstream depends on it
        segments=segments,
    )
